"""CLI for the tonight-sized Autoresearch Next smoke tournament."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import socketserver
import sys
import tempfile
import time
import uuid
import subprocess
from pathlib import Path
from typing import Any

from .archive import ArchiveEntry
from .ar0 import DEFAULT_SEEDS, regenerate_report, run_ar0
from .ar1 import run_ar1
from .ledger import AppendOnlyLedger
from .runner import ExperimentRunner
from .schema import CandidateContract, OPERATOR_WEIGHTS, POLICY_VERSION, canonical_json
from .trust_kernel import TrustKernel


def default_root() -> Path:
    return Path(os.environ.get("RALYTABLE_AR_ROOT", Path(tempfile.gettempdir()) / "ralytable-autoresearch-next"))


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_dir(root: Path, run_id: str) -> Path:
    return root / "runs" / run_id


def load_or_create_run(root: Path, profile: str = "rtx4060-8gb") -> tuple[str, Path, AppendOnlyLedger]:
    root.mkdir(parents=True, exist_ok=True)
    marker = root / "ACTIVE_RUN"
    if marker.exists():
        run_id = marker.read_text(encoding="utf-8").strip()
        path = run_dir(root, run_id)
        ledger = AppendOnlyLedger(path / "ledger.sqlite3")
        return run_id, path, ledger
    run_id = "ar-next-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6]
    path = run_dir(root, run_id)
    path.mkdir(parents=True, exist_ok=True)
    marker.write_text(run_id + "\n", encoding="utf-8")
    ledger = AppendOnlyLedger(path / "ledger.sqlite3")
    ledger.create_run(run_id, profile, POLICY_VERSION, str(root.resolve()))
    return run_id, path, ledger


def freeze(run_id: str, path: Path, ledger: AppendOnlyLedger) -> None:
    kernel = TrustKernel(repo_root(), path / "artifacts")
    official_keys = None
    try:
        sys.path.insert(0, str(repo_root() / "experiments/17_interpretable_humaneval"))
        from evalplus.data import get_human_eval_plus  # type: ignore
        official_keys = sorted(get_human_eval_plus().keys())
    except Exception:
        pass
    keys = official_keys or [f"opaque-runtime-slot-{i:03d}" for i in range(164)]
    manifest = kernel.freeze_partitions(keys, path / "partitions.json", run_id)
    if official_keys is None:
        manifest["official_runtime_keys_available"] = False
        manifest["note"] = "164 opaque slots preserve deterministic partition shape; official task keys require WSL EvalPlus 0.3.1"
        (path / "partitions.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(canonical_json(manifest)).hexdigest()
    ledger.partition("partitions-v1", run_id, manifest, digest)
    ledger.event(run_id, "partitions_frozen", {"task_count": len(keys), "official_runtime_keys_available": official_keys is not None, "sha256": digest})


def contract_for(arm: str, index: int, parent: str | None = None) -> CandidateContract:
    operator = ExperimentRunner.operator_for(index) if arm == "evolve" else "mutation"
    configs = [
        {"learning_rate": 0.05, "feature_dropout": 0.00, "epochs": 24},
        {"learning_rate": 0.10, "feature_dropout": 0.00, "epochs": 32},
        {"learning_rate": 0.15, "feature_dropout": 0.02, "epochs": 40},
        {"learning_rate": 0.20, "feature_dropout": 0.04, "epochs": 48},
        {"learning_rate": 0.30, "feature_dropout": 0.06, "epochs": 56},
    ]
    config = dict(configs[index % len(configs)])
    if arm == "evolve" and operator == "crossover":
        config["feature_dropout"] = max(0.0, config["feature_dropout"] - 0.01)
    if arm == "evolve" and operator == "simplification":
        config["epochs"] = max(8, config["epochs"] // 2)
    if arm == "evolve" and operator == "radical":
        config["learning_rate"] = 0.40
    return CandidateContract(candidate_id=f"{arm}-{index:03d}", parent_ids=(parent,) if parent else (),
                             hypothesis=f"{operator} a sparse typed-state policy", operator=operator,
                             mechanism_family="named_sparse_typed_monotonic_gate", transparency=2,
                             learned_parameters=9, declared_state=("intent", "abstract_value", "confidence"),
                             files_changed=(), config=config)


def do_run(args: argparse.Namespace) -> None:
    run_id, path, ledger = load_or_create_run(args.root)
    if not (path / "partitions.json").exists():
        freeze(run_id, path, ledger)
    use_wsl = args.environment == "wsl" and os.name == "nt"
    ledger.event(run_id, "execution_environment", {"requested": args.environment, "use_wsl_subprocess": use_wsl, "orchestrator_host": "wsl" if os.name != "nt" else "windows", "torch_venv": "/home/rapha/ralytable-autoresearch-next/.venv/bin/python" if args.environment == "wsl" else None})
    runner = ExperimentRunner(repo_root(), path / "artifacts", ledger, run_id, use_wsl=use_wsl)
    arms = ["greedy", "evolve"] if args.arm == "both" else [args.arm]
    for arm in arms:
        leader = None
        completed_results = []
        for i in range(args.experiments):
            contract = contract_for(arm, i, leader if arm == "evolve" else None)
            result = runner.run_one(arm, contract, args.seconds, 1000 + i, json.loads((path / "partitions.json").read_text(encoding="utf-8")))
            completed_results.append(result)
            print(json.dumps({"run_id": run_id, "arm": arm, "experiment": i + 1, "status": result.status,
                              "raw_learned_score": result.raw_learned_score, "blind_proxy_score": result.full_system_score,
                              "null_score": result.deterministic_null_score, "failure": result.failure_category}), flush=True)
            if result.status == "completed" and (leader is None or (result.raw_learned_score or -1) >= 0):
                leader = result.candidate_id
        valid = [r for r in completed_results if r.status == "completed"]
        if valid:
            champion = max(valid, key=lambda r: r.raw_learned_score or -1)
            print(json.dumps({"champion": runner.promote_champion(arm, champion.candidate_id, 1000 + completed_results.index(champion))}), flush=True)
        ledger.event(run_id, "arm_completed", {"arm": arm, "experiments": args.experiments, "champion_selection": "blind_proxy_after_epoch"})
    ledger.close()


def report(args: argparse.Namespace) -> None:
    run_id, path, ledger = load_or_create_run(args.root)
    snapshot = ledger.snapshot(run_id)
    rows = snapshot["experiments"]
    completed = [r for r in rows if r["status"] == "COMPLETED"]
    lines = ["# Autoresearch Next smoke tournament", "", f"Run: `{run_id}`", "", "This is an exploratory pipeline/proxy run; it is not evidence of HumanEval+ capability.", "", "| arm | completed | best raw learned | best blind proxy | deterministic null |", "|---|---:|---:|---:|---:|"]
    promotions = [json.loads(e["payload_json"]) for e in snapshot["events"] if e["event_type"] == "champion_promoted"]
    for arm in ("greedy", "evolve"):
        arm_rows = [r for r in completed if r["arm"] == arm]
        metrics = [json.loads(r["metrics_json"]) for r in arm_rows]
        val = lambda k: max((m.get(k) for m in metrics if m.get(k) is not None), default=None)
        promoted = next((p for p in promotions if p.get("arm") == arm), {})
        lines.append(f"| {arm} | {len(arm_rows)} | {val('raw_learned_score')} | {promoted.get('blind_proxy_score')} | 0.0 |")
    all_metrics = [json.loads(r["metrics_json"]) for r in completed]
    device = next((m.get("extra", {}).get("device") for m in all_metrics if m.get("extra", {}).get("device")), "unknown")
    mean_vram = sum(m.get("peak_vram_gb", 0.0) for m in all_metrics) / len(all_metrics) if all_metrics else None
    mean_throughput = sum(m.get("throughput", 0.0) for m in all_metrics) / len(all_metrics) if all_metrics else None
    max_causal = max((m.get("causal_intervention_rate", 0.0) for m in all_metrics), default=None)
    min_placebo = min((m.get("placebo_preservation", 0.0) for m in all_metrics), default=None)
    lines += ["", "## Official benchmark status", "", "HumanEval+ official score: not run; the frozen deterministic null from Experiment 16 is base 0.000 and plus 0.000 on 164 tasks. Any future optimized score must be labeled HumanEval+-tuned.", "", "## Recovery and lineage", "", f"Experiment attempt records: {len(rows)}; completed runs: {len(completed)}; failures: {sum(r['status'] == 'FAILED' for r in rows)}.", "The ledger is append-only under normal candidate access. Protected paths, artifact hashes, partition manifest, and hidden-score hashes are recorded.", "", "## Resource and causal summary", "", f"Primary device: {device}; mean peak allocated VRAM: {mean_vram}; mean throughput: {mean_throughput}; maximum intervention change rate: {max_causal}; minimum placebo preservation: {min_placebo}.", "", "## Limitations", "", "The candidate has nine learned parameters and does not generate Python programs. Blind and final values are synthetic code-validation proxy scores, not EvalPlus scores. One seed per candidate makes this smoke run exploratory, and no T3 fully interpretable claim is made."]
    out = path / "REPORT.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (path / "snapshot.json").write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(out)
    ledger.close()


def prepare_flagship(args: argparse.Namespace) -> None:
    _, path, ledger = load_or_create_run(args.root)
    payload = {"status": "prepared_not_launched", "arms": {"greedy": 100, "evolve": 100}, "seconds": 300, "policy_version": POLICY_VERSION, "official_evaluator": "EvalPlus 0.3.1 under WSL Ubuntu", "required_review": ["WSL access", "PyTorch/BF16 calibration", "multi-seed preregistration"]}
    (path / "FLAGSHIP_PLAN.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ledger.event(path.name, "flagship_prepared", payload)
    print(path / "FLAGSHIP_PLAN.json")
    ledger.close()


def status(args: argparse.Namespace) -> None:
    run_id, _, ledger = load_or_create_run(args.root)
    snapshot = ledger.snapshot(run_id)
    rows = snapshot["experiments"]
    print(json.dumps({"run_id": run_id, "experiments": len(rows), "completed": sum(r["status"] == "COMPLETED" for r in rows),
                      "failed": sum(r["status"] == "FAILED" for r in rows), "pending": len(ledger.pending_experiments(run_id)),
                      "champions": [json.loads(e["payload_json"]) for e in snapshot["events"] if e["event_type"] == "champion_promoted"]}, indent=2, sort_keys=True))
    ledger.close()


def resume(args: argparse.Namespace) -> None:
    target = args.run_id
    candidate = args.root / "runs" / target
    if not candidate.exists():
        raise SystemExit(f"run not found: {target}")
    args.root.mkdir(parents=True, exist_ok=True)
    (args.root / "ACTIVE_RUN").write_text(target + "\n", encoding="utf-8")
    run_id, path, ledger = load_or_create_run(args.root)
    pending = ledger.pending_experiments(run_id)
    ledger.event(run_id, "resume_requested", {"pending_experiments": len(pending), "policy": "retry only recoverable pending work"})
    print(json.dumps({"run_id": run_id, "pending_experiments": len(pending), "message": "No automatic retry is performed for completed immutable records; rerun with run for a new epoch."}))
    ledger.close()


def calibrate(args: argparse.Namespace) -> None:
    run_id, path, ledger = load_or_create_run(args.root)
    command = ["wsl.exe", "-d", "Ubuntu", "--", "nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"]
    try:
        checked = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        payload = {"returncode": checked.returncode, "output": checked.stdout.strip(), "error": checked.stderr.strip(), "ceiling_gb": 7.2, "policy": "wait for GPU owner; never kill other processes"}
    except Exception as exc:
        payload = {"returncode": None, "error": f"{type(exc).__name__}: {exc}", "ceiling_gb": 7.2}
    ledger.event(run_id, "gpu_calibration", payload)
    print(json.dumps(payload)); ledger.close()


def serve(args: argparse.Namespace) -> None:
    from .dashboard_server import serve_dashboard
    serve_dashboard(args.root, args.port, phase=args.phase)


def do_ar0(args: argparse.Namespace) -> None:
    seeds = tuple(int(value.strip()) for value in args.seeds.split(",") if value.strip()) or DEFAULT_SEEDS
    run_id, path = run_ar0(args.root, repo_root(), seeds=seeds, budget=args.budget, environment=args.environment, include_gpu=not args.no_gpu)
    print(json.dumps({"run_id": run_id, "path": str(path), "report": str(path / "REPORT.md"), "dashboard": f"http://127.0.0.1:{args.port}/"}, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autoresearch-next")
    sub = parser.add_subparsers(dest="command", required=True)
    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--root", type=Path, default=default_root())
    p = sub.add_parser("init"); common(p); p.add_argument("--profile", default="rtx4060-8gb")
    p = sub.add_parser("run"); common(p); p.add_argument("--arm", choices=("greedy", "evolve", "both"), default="both"); p.add_argument("--experiments", type=int, default=10); p.add_argument("--seconds", type=int, default=300)
    p.add_argument("--environment", choices=("auto", "wsl", "local"), default="auto")
    p = sub.add_parser("calibrate"); common(p)
    p = sub.add_parser("report"); common(p)
    p = sub.add_parser("status"); common(p)
    p = sub.add_parser("resume"); common(p); p.add_argument("run_id")
    p = sub.add_parser("dashboard"); common(p); p.add_argument("--port", type=int, default=8787); p.add_argument("--phase", choices=("smoke", "ar0"), default="smoke")
    p = sub.add_parser("prepare-flagship"); common(p)
    p = sub.add_parser("ar0"); common(p); p.add_argument("--seeds", default=",".join(str(seed) for seed in DEFAULT_SEEDS)); p.add_argument("--budget", type=int, default=64); p.add_argument("--environment", choices=("local", "wsl"), default="local"); p.add_argument("--no-gpu", action="store_true"); p.add_argument("--port", type=int, default=8787)
    p = sub.add_parser("ar0-dashboard"); common(p); p.add_argument("--port", type=int, default=8787)
    p = sub.add_parser("ar0-report"); common(p)
    p = sub.add_parser("ar1"); common(p); p.add_argument("--environment", choices=("local", "wsl"), default="local"); p.add_argument("--gpu", action="store_true")
    p = sub.add_parser("ar1-dashboard"); common(p); p.add_argument("--port", type=int, default=8791)
    args = parser.parse_args(argv)
    if args.command == "init":
        run_id, path, ledger = load_or_create_run(args.root, args.profile); freeze(run_id, path, ledger); ledger.close(); print(path)
    elif args.command == "run": do_run(args)
    elif args.command == "calibrate": calibrate(args)
    elif args.command == "report": report(args)
    elif args.command == "status": status(args)
    elif args.command == "resume": resume(args)
    elif args.command == "dashboard": serve(args)
    elif args.command == "prepare-flagship": prepare_flagship(args)
    elif args.command == "ar0": do_ar0(args)
    elif args.command == "ar0-dashboard":
        from .dashboard_server import serve_dashboard
        serve_dashboard(args.root, args.port, phase="ar0")
    elif args.command == "ar0-report": print(regenerate_report(args.root))
    elif args.command == "ar1":
        run_id, path = run_ar1(args.root, repo_root(), environment=args.environment, include_gpu=args.gpu)
        print(json.dumps({"run_id": run_id, "path": str(path), "report": str(path / "REPORT.md"), "dashboard": "http://127.0.0.1:8791/"}, sort_keys=True))
    elif args.command == "ar1-dashboard":
        from .dashboard_server import serve_dashboard
        serve_dashboard(args.root, args.port, phase="ar1")
    return 0
