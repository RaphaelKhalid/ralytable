"""Autoresearcher AR0: deterministic meta-evaluation and a small CUDA calibration.

The module measures search policies on synthetic, exhaustively enumerable
landscapes. It never imports benchmark data and does not alter the trust
kernel or evaluator contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ledger import AppendOnlyLedger
from .meta_landscapes import BitVector, Landscape, crossover, hamming, make_landscapes, mutate, radical, simplify
from .runner import gpu_owner
from .schema import OPERATOR_WEIGHTS
from .trust_kernel import TrustKernel


POLICIES = ("greedy", "map_elites_fixed", "adaptive_ucb", "adaptive_ucb_aged")
VISIBLE_LANDSCAPES = ("deceptive_local", "sparse_reward", "neutral_plateau", "epistatic_crossover")
DEFAULT_SEEDS = (11, 23, 37)


def _finite_score(score: float) -> float:
    return score if math.isfinite(score) else 0.0


def _normal(score: float, optimum: float) -> float:
    if not math.isfinite(score) or optimum == 0:
        return 0.0
    return max(0.0, min(1.0, score / optimum))


def niche(point: BitVector, landscape: Landscape, collapsed: bool = False) -> str:
    if collapsed:
        return "collapsed"
    half = landscape.dimension // 2
    return ":".join(("valid" if landscape.feasible(point) else "invalid", str(sum(point) // 2), str(sum(point[:half]) // 2), str(sum(point[half:]) // 2)))


@dataclass
class PointRecord:
    point: BitVector
    score: float
    depth: int
    candidate_id: str
    operator: str


@dataclass
class Trial:
    landscape: Landscape
    policy: str
    seed: int
    budget: int
    novelty_weight: float = 0.25
    invert_credit: bool = False
    collapsed_niches: bool = False
    rng: random.Random = field(init=False)
    population: list[PointRecord] = field(default_factory=list)
    archive: dict[str, PointRecord] = field(default_factory=dict)
    seen: set[BitVector] = field(default_factory=set)
    curve: list[float] = field(default_factory=list)
    proposal_times: list[float] = field(default_factory=list)
    operator_counts: dict[str, int] = field(default_factory=lambda: {name: 0 for name in OPERATOR_WEIGHTS})
    operator_improvements: dict[str, int] = field(default_factory=lambda: {name: 0 for name in OPERATOR_WEIGHTS})
    operator_credit: dict[str, float] = field(default_factory=lambda: {name: 0.0 for name in OPERATOR_WEIGHTS})
    operator_uses: dict[str, int] = field(default_factory=lambda: {name: 0 for name in OPERATOR_WEIGHTS})
    best_score: float = float("-inf")
    best: PointRecord | None = None
    current_step: int = 0
    valid_count: int = 0
    duplicate_count: int = 0
    novelty_sum: float = 0.0
    max_depth: int = 0

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self._observe(tuple(0 for _ in range(self.landscape.dimension)), "seed", 0, initial=True)

    def _parents(self) -> list[PointRecord]:
        if self.archive:
            return list(self.archive.values())
        if self.population:
            return self.population
        return [self.best] if self.best else []

    def _choose_operator(self) -> str:
        if self.policy == "greedy":
            return "mutation"
        if self.policy == "map_elites_fixed":
            pick = self.rng.random()
            total = 0.0
            for name, weight in OPERATOR_WEIGHTS.items():
                total += weight
                if pick < total:
                    return name
            return "radical"
        for name in OPERATOR_WEIGHTS:
            if self.operator_uses[name] == 0:
                return name
        total = max(1, sum(self.operator_uses.values()))
        scores = {name: self.operator_credit[name] / self.operator_uses[name] + 0.7 * math.sqrt(math.log(total + 1) / self.operator_uses[name]) for name in OPERATOR_WEIGHTS}
        return max(scores, key=scores.get)

    def _select_parent(self) -> PointRecord:
        if self.best is not None and self.policy == "greedy":
            return self.best
        parents = self._parents()
        if not parents:
            raise RuntimeError("no search parent available")
        if self.policy == "adaptive_ucb_aged":
            return min(parents, key=lambda record: int(record.candidate_id.rsplit("-", 1)[-1]))
        return self.rng.choice(parents)

    def _depth(self, candidate_id: str) -> int:
        for record in reversed(self.population):
            if record.candidate_id == candidate_id:
                return record.depth
        return 0

    def _propose(self, operator: str) -> tuple[BitVector, tuple[str, ...], int]:
        parent = self._select_parent()
        if operator == "mutation":
            point, parents = mutate(parent.point, self.rng), (parent.candidate_id,)
        elif operator == "crossover":
            second = self.rng.choice(self._parents())
            point, parents = crossover(parent.point, second.point, self.rng), (parent.candidate_id, second.candidate_id)
        elif operator == "simplification":
            point, parents = simplify(parent.point, self.rng), (parent.candidate_id,)
        else:
            point, parents = radical(parent.point, self.rng), (parent.candidate_id,)
        return point, parents, max((self._depth(pid) for pid in parents), default=0) + 1

    def _observe(self, point: BitVector, operator: str, depth: int, initial: bool = False) -> None:
        started = time.perf_counter()
        score = self.landscape.score(point)
        record = PointRecord(point, score, depth, f"{self.policy}-{self.seed}-{self.current_step:04d}", operator)
        duplicate = point in self.seen
        self.seen.add(point)
        if not initial:
            self.duplicate_count += int(duplicate)
            self.valid_count += int(math.isfinite(score))
            if len(self.seen) > 1:
                distances = [hamming(point, old) for old in self.seen if old != point]
                self.novelty_sum += min(distances) / self.landscape.dimension if distances else 0.0
        self.population.append(record)
        self.max_depth = max(self.max_depth, depth)
        if math.isfinite(score):
            key = niche(point, self.landscape, self.collapsed_niches)
            existing = self.archive.get(key)
            if existing is None or score > existing.score:
                self.archive[key] = record
            if self.best is None or score > self.best_score:
                if not initial and operator in self.operator_improvements:
                    self.operator_improvements[operator] += 1
                self.best, self.best_score = record, score
        self.curve.append(_normal(self.best_score, self.landscape.optimum_score))
        self.proposal_times.append(time.perf_counter() - started)

    def step(self) -> None:
        operator = self._choose_operator()
        point, parents, depth = self._propose(operator)
        before = self.best_score
        old_niches = {niche(record.point, self.landscape, self.collapsed_niches) for record in self.population if math.isfinite(record.score)}
        self.operator_counts[operator] += 1
        self.operator_uses[operator] += 1
        self._observe(point, operator, depth)
        after = self.best_score
        improvement = max(0.0, _normal(after, self.landscape.optimum_score) - _normal(before, self.landscape.optimum_score))
        is_new_niche = math.isfinite(self.landscape.score(point)) and niche(point, self.landscape, self.collapsed_niches) not in old_niches
        reward = improvement + self.novelty_weight * float(is_new_niche)
        self.operator_credit[operator] += -reward if self.invert_credit else reward
        del parents
        self.current_step += 1

    def run(self, steps: int | None = None) -> dict[str, Any]:
        for _ in range(steps if steps is not None else self.budget):
            self.step()
        return self.metrics()

    def snapshot(self) -> dict[str, Any]:
        return {"rng": self.rng.getstate(), "population": [record.__dict__ for record in self.population], "archive": {key: record.__dict__ for key, record in self.archive.items()}, "seen": list(self.seen), "curve": self.curve, "proposal_times": self.proposal_times, "operator_counts": self.operator_counts, "operator_improvements": self.operator_improvements, "operator_credit": self.operator_credit, "operator_uses": self.operator_uses, "best_score": self.best_score, "best": self.best.__dict__ if self.best else None, "current_step": self.current_step, "valid_count": self.valid_count, "duplicate_count": self.duplicate_count, "novelty_sum": self.novelty_sum, "max_depth": self.max_depth}

    @staticmethod
    def _tuplify(value: Any) -> Any:
        return tuple(Trial._tuplify(item) for item in value) if isinstance(value, list) else value

    @classmethod
    def from_snapshot(cls, landscape: Landscape, policy: str, seed: int, budget: int, snapshot: dict[str, Any], **kwargs: Any) -> "Trial":
        trial = cls.__new__(cls)
        trial.landscape, trial.policy, trial.seed, trial.budget = landscape, policy, seed, budget
        trial.novelty_weight = kwargs.get("novelty_weight", 0.25); trial.invert_credit = kwargs.get("invert_credit", False); trial.collapsed_niches = kwargs.get("collapsed_niches", False)
        trial.rng = random.Random(); trial.rng.setstate(Trial._tuplify(snapshot["rng"]))
        def record(data: dict[str, Any]) -> PointRecord:
            return PointRecord(tuple(data["point"]), data["score"], data["depth"], data["candidate_id"], data["operator"])
        trial.population = [record(data) for data in snapshot["population"]]
        trial.archive = {key: record(data) for key, data in snapshot["archive"].items()}
        trial.seen = {tuple(point) for point in snapshot["seen"]}
        trial.curve, trial.proposal_times = list(snapshot["curve"]), list(snapshot["proposal_times"])
        trial.operator_counts, trial.operator_improvements = dict(snapshot["operator_counts"]), dict(snapshot["operator_improvements"])
        trial.operator_credit, trial.operator_uses = dict(snapshot["operator_credit"]), dict(snapshot["operator_uses"])
        trial.best_score, trial.best = snapshot["best_score"], record(snapshot["best"]) if snapshot["best"] else None
        trial.current_step, trial.valid_count = snapshot["current_step"], snapshot["valid_count"]
        trial.duplicate_count, trial.novelty_sum, trial.max_depth = snapshot["duplicate_count"], snapshot["novelty_sum"], snapshot["max_depth"]
        return trial

    def metrics(self) -> dict[str, Any]:
        best = _normal(self.best_score, self.landscape.optimum_score)
        return {"policy": self.policy, "seed": self.seed, "landscape": self.landscape.name, "family": self.landscape.family, "budget": self.budget, "proposals": max(0, len(self.population) - 1), "best_so_far": best, "best_score": _finite_score(self.best_score), "optimum_score": self.landscape.optimum_score, "regret": max(0.0, 1.0 - best), "success": bool(self.best_score == self.landscape.optimum_score), "auc_discovery": sum(self.curve) / len(self.curve) if self.curve else 0.0, "archive_coverage": len(self.archive), "qd_score": sum(_normal(r.score, self.landscape.optimum_score) for r in self.archive.values()), "novelty": self.novelty_sum / max(1, len(self.population) - 1), "valid_proposal_rate": self.valid_count / max(1, len(self.population) - 1), "duplicate_rate": self.duplicate_count / max(1, len(self.population) - 1), "operator_counts": self.operator_counts, "operator_improvements": self.operator_improvements, "operator_yield": {name: self.operator_improvements[name] / max(1, self.operator_counts[name]) for name in OPERATOR_WEIGHTS}, "lineage_depth": self.max_depth, "compute_overhead_seconds": sum(self.proposal_times), "curve": self.curve}


def run_trial(landscape: Landscape, policy: str, seed: int, budget: int, **kwargs: Any) -> dict[str, Any]:
    return Trial(landscape, policy, seed, budget, **kwargs).run()


def recovery_check(landscape: Landscape, policy: str, seed: int, budget: int, **kwargs: Any) -> dict[str, Any]:
    full = Trial(landscape, policy, seed, budget, **kwargs).run()
    split = max(1, budget // 2)
    partial = Trial(landscape, policy, seed, budget, **kwargs); partial.run(split)
    serialized = json.loads(json.dumps(partial.snapshot()))
    resumed = Trial.from_snapshot(landscape, policy, seed, budget, serialized, **kwargs); resumed_metrics = resumed.run(budget - split)
    return {"policy": policy, "recovery_resume_match": full["curve"] == resumed_metrics["curve"] and full["archive_coverage"] == resumed_metrics["archive_coverage"], "full_best": full["best_so_far"], "resumed_best": resumed_metrics["best_so_far"], "checkpoint_step": split}


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n"); handle.flush(); os.fsync(handle.fileno())


def _wsl_path(path: Path) -> str:
    raw = str(path.resolve()).replace("\\\\", "/")
    return "/mnt/" + raw[0].lower() + raw[2:] if len(raw) > 1 and raw[1] == ":" else raw


def _gpu_command(repo: Path, output: Path, config: dict[str, Any], seed: int, seconds: int, environment: str) -> list[str]:
    script = repo / "experiments/17_interpretable_humaneval/train_candidate.py"
    args = ["--config-json", json.dumps(config, sort_keys=True), "--seed", str(seed), "--seconds", str(seconds), "--output", str(output)]
    if environment == "wsl" and os.name == "nt":
        return ["wsl.exe", "-d", "Ubuntu", "--", "/home/rapha/ralytable-autoresearch-next/.venv/bin/python", _wsl_path(script), *args[:-1], _wsl_path(output)]
    if environment == "wsl":
        return ["/home/rapha/ralytable-autoresearch-next/.venv/bin/python", str(script), *args]
    return [sys.executable, str(script), *args]


def gpu_proxy(repo: Path, root: Path, environment: str, seed: int, seconds: int, label: str, config: dict[str, Any]) -> dict[str, Any]:
    output = root / "gpu" / f"{label}-{seed}.json"; output.parent.mkdir(parents=True, exist_ok=True)
    with gpu_owner(root / "gpu.owner.lock", timeout=seconds + 60):
        checked = subprocess.run(_gpu_command(repo, output, config, seed, seconds, environment), cwd=str(repo), capture_output=True, text=True, timeout=seconds + 45, check=False)
    if checked.returncode != 0:
        raise RuntimeError((checked.stderr or checked.stdout or "GPU proxy failed")[-2000:])
    payload = json.loads(output.read_text(encoding="utf-8")); payload.update({"label": label, "seed": seed, "config": config, "status": "completed"}); return payload


def gpu_validate(environment: str, lock_path: Path | None = None) -> dict[str, Any]:
    code = "import torch\n"
    code += "torch.cuda.init()\n"
    code += "device=torch.device('cuda:0')\n"
    code += "torch.cuda.reset_peak_memory_stats(device)\n"
    code += "model=torch.nn.Linear(8,4,device=device)\n"
    code += "opt=torch.optim.AdamW(model.parameters(),lr=0.01)\n"
    code += "x=torch.ones((4,8),device=device)\n"
    code += "with torch.autocast(device_type='cuda',dtype=torch.bfloat16,enabled=torch.cuda.is_bf16_supported()):\n"
    code += "    loss=model(x).square().mean()\n"
    code += "loss.backward(); opt.step()\n"
    code += "print({'torch':torch.__version__,'cuda':torch.cuda.is_available(),'device':torch.cuda.get_device_name(0),'bf16':torch.cuda.is_bf16_supported(),'loss':float(loss),'peak_bytes':torch.cuda.max_memory_allocated(device)})"
    if environment == "wsl" and os.name == "nt":
        command = ["wsl.exe", "-d", "Ubuntu", "--", "/home/rapha/ralytable-autoresearch-next/.venv/bin/python", "-c", code]
    elif environment == "wsl":
        command = ["/home/rapha/ralytable-autoresearch-next/.venv/bin/python", "-c", code]
    else:
        command = [sys.executable, "-c", code]
    if lock_path is None:
        checked = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    else:
        with gpu_owner(lock_path, timeout=90):
            checked = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    if checked.returncode != 0:
        raise RuntimeError((checked.stderr or checked.stdout)[-2000:])
    line = next(line for line in reversed(checked.stdout.splitlines()) if line.strip().startswith("{"))
    return {"validation": line, "raw_stdout": checked.stdout[-2000:]}


def _summarize(rows: list[dict[str, Any]], holdout_rows: list[dict[str, Any]], recovery: list[dict[str, Any]], gpu: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        grouped.setdefault(row["policy"], {}).setdefault("best_so_far", []).append(row["best_so_far"])
        grouped[row["policy"]].setdefault("auc_discovery", []).append(row["auc_discovery"])
    return {"policies": {policy: {key: sum(values) / len(values) for key, values in metrics.items()} for policy, metrics in grouped.items()}, "visible_rows": len(rows), "holdout_rows": len(holdout_rows), "holdout": holdout_rows, "recovery": recovery, "gpu": gpu}


def write_report(path: Path, run_id: str, config: dict[str, Any], summary: dict[str, Any], falsifications: list[dict[str, Any]]) -> None:
    lines = ["# Autoresearcher AR0 report", "", f"Run: {run_id}", "", "AR0 measures search policy quality on synthetic enumerable landscapes and a CUDA orchestration proxy. It does not train or score a Python coder and does not run HumanEval+.", "", "## Hypothesis and protocol", "", f"Current greedy mutation-only search, fixed-schedule MAP-Elites, and adaptive UCB operator credit were paired over seeds {config['seeds']} with {config['budget']} proposals per landscape. Visible landscapes: {', '.join(config['visible_landscapes'])}. The constraint-heavy family was held out until policy selection.", "", "## Visible deterministic results", "", "| policy | mean best-so-far | mean discovery AUC |", "|---|---:|---:|"]
    for policy, metrics in summary.get("policies", {}).items():
        lines.append(f"| {policy} | {metrics.get('best_so_far', 0.0):.3f} | {metrics.get('auc_discovery', 0.0):.3f} |")
    chosen = max(summary.get("policies", {}), key=lambda p: (summary["policies"][p].get("auc_discovery", 0.0), summary["policies"][p].get("best_so_far", 0.0))) if summary.get("policies") else None
    improved = summary.get("policies", {}).get("adaptive_ucb_aged", {})
    fixed = summary.get("policies", {}).get("map_elites_fixed", {})
    lines += ["", f"Chosen policy by visible AUC then best-so-far: {chosen}.", f"Promotion decision: {'do not promote adaptive_ucb_aged' if chosen != 'adaptive_ucb_aged' else 'promote adaptive_ucb_aged for the next preregistered study'}. Its visible AUC delta versus fixed MAP-Elites was {improved.get('auc_discovery', 0.0) - fixed.get('auc_discovery', 0.0):+.3f}.", "", "## Blind holdout", "", "| policy | landscape | best-so-far | AUC | coverage | valid proposals |", "|---|---|---:|---:|---:|---:|"]
    for row in summary.get("holdout", []):
        lines.append(f"| {row['policy']} | {row['landscape']} | {row['best_so_far']:.3f} | {row['auc_discovery']:.3f} | {row['archive_coverage']} | {row['valid_proposal_rate']:.3f} |")
    lines += ["", "## Falsification", ""]; lines.extend(f"- {row['name']}: {row['result']}" for row in falsifications)
    recovery = summary.get("recovery", [])
    lines += ["", "## Recovery, reproducibility, and compute", "", f"Recovery/resume checks: {sum(int(r['recovery_resume_match']) for r in recovery)}/{len(recovery)} exact matches. Each deterministic trial records best-so-far curves, archive coverage/QD score, novelty, valid and duplicate proposal rates, operator yields, lineage depth, and compute overhead in results.jsonl.", "", "## CUDA proxy", "", "The GPU section is an orchestration/calibration test of the existing nine-parameter typed-state proxy. It is not a coder result and is not HumanEval+ evidence."]
    for row in summary.get("gpu", []):
        lines.append(f"- {row.get('label')} seed {row.get('seed')}: device {row.get('device')}, raw proxy {row.get('dev_score')}, peak VRAM {row.get('peak_vram_gb')} GiB, status {row.get('status')}.")
    lines += ["", "## Limitations and go/no-go", "", "The synthetic landscapes are intentionally small and cannot establish downstream coding performance. One holdout family is not enough for a flagship claim, and the GPU proxy does not generate Python. Proceed to a larger preregistered researcher study only if the chosen policy improves paired visible AUC and does not lose the holdout, recovery, reproducibility, or constraint-validity checks. Any later HumanEval+ result must remain separately labeled HumanEval+-tuned.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def regenerate_report(root: Path) -> Path:
    run_id = (root / "AR0_ACTIVE_RUN").read_text(encoding="utf-8").strip()
    path = root / "ar0" / "runs" / run_id
    config = json.loads((path / "study_config.json").read_text(encoding="utf-8"))
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    write_report(path / "REPORT.md", run_id, config, summary, summary.get("falsifications", []))
    ledger = AppendOnlyLedger(path / "ledger.sqlite3")
    report_path = path / "REPORT.md"
    ledger.artifact(f"{run_id}-report-final", run_id, "ar0_report", str(report_path), hashlib.sha256(report_path.read_bytes()).hexdigest())
    ledger.event(run_id, "ar0_report_regenerated", {"path": str(report_path), "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest()})
    ledger.close()
    return report_path


def run_ar0(root: Path, repo: Path, seeds: tuple[int, ...] = DEFAULT_SEEDS, budget: int = 64, environment: str = "local", include_gpu: bool = True) -> tuple[str, Path]:
    root = root.resolve(); root.mkdir(parents=True, exist_ok=True)
    run_id = "ar0-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6]
    path = root / "ar0" / "runs" / run_id; path.mkdir(parents=True, exist_ok=False)
    (root / "AR0_ACTIVE_RUN").write_text(run_id + "\n", encoding="utf-8")
    ledger = AppendOnlyLedger(path / "ledger.sqlite3"); ledger.create_run(run_id, "ar0-meta-study", "autoresearch-next-ar0", str(root))
    kernel = TrustKernel(repo.resolve(), path / "artifacts")
    config = {"phase": "AR0", "seeds": list(seeds), "budget": budget, "visible_landscapes": list(VISIBLE_LANDSCAPES), "holdout_landscape": "constraint_heavy", "policies": list(POLICIES), "operator_weights": OPERATOR_WEIGHTS, "official_humaneval_plus": "not run"}
    (path / "study_config.json").write_text(json.dumps(config, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (path / "policy_baseline.json").write_text(json.dumps({"greedy": "mutation-only hill climber", "map_elites_fixed": OPERATOR_WEIGHTS, "adaptive_ucb": "UCB credit over the same four operators", "adaptive_ucb_aged": "UCB credit plus archive-aging/curiosity parent selection", "frozen_at": time.time()}, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    results_path, events_path = path / "results.jsonl", path / "events.jsonl"
    ledger.event(run_id, "ar0_baseline_frozen", config)
    landscapes = make_landscapes(); rows: list[dict[str, Any]] = []
    for landscape_name in VISIBLE_LANDSCAPES:
        for seed in seeds:
            for policy in POLICIES:
                started = time.perf_counter(); row = run_trial(landscapes[landscape_name], policy, seed, budget, novelty_weight=0.5 if policy == "adaptive_ucb_aged" else 0.25)
                row.update({"wall_seconds": time.perf_counter() - started, "phase": "visible"}); rows.append(row)
                _append_jsonl(results_path, row); _append_jsonl(events_path, {"event": "trial_completed", **row}); ledger.event(run_id, "ar0_trial_completed", row)
    visible_summary = _summarize(rows, [], [], [])
    chosen = max(visible_summary["policies"], key=lambda p: (visible_summary["policies"][p].get("auc_discovery", 0.0), visible_summary["policies"][p].get("best_so_far", 0.0)))
    holdout_rows: list[dict[str, Any]] = []
    for seed in seeds:
        for policy in POLICIES:
            row = run_trial(landscapes["constraint_heavy"], policy, seed, budget, novelty_weight=0.5 if policy == "adaptive_ucb_aged" else 0.25); row["phase"] = "blind_holdout"; holdout_rows.append(row)
            _append_jsonl(results_path, row); _append_jsonl(events_path, {"event": "holdout_completed", **row}); ledger.event(run_id, "ar0_holdout_completed", row)
    recovery = [recovery_check(landscapes["epistatic_crossover"], policy, seeds[0], budget, novelty_weight=0.5 if policy == "adaptive_ucb_aged" else 0.25) for policy in POLICIES]
    for check in recovery:
        ledger.event(run_id, "ar0_recovery_check", check)
    falsifications = []
    for name, kwargs in (("inverted_credit", {"invert_credit": True}), ("novelty_disabled", {"novelty_weight": 0.0}), ("niches_collapsed", {"collapsed_niches": True})):
        row = run_trial(landscapes["sparse_reward"], "adaptive_ucb", seeds[0], budget, **kwargs)
        falsifications.append({"name": name, "result": f"best={row['best_so_far']:.3f}, auc={row['auc_discovery']:.3f}, coverage={row['archive_coverage']}"}); ledger.event(run_id, "ar0_falsification", {"name": name, **row})
    reproducibility_a = run_trial(landscapes["neutral_plateau"], chosen, seeds[-1], budget); reproducibility_b = run_trial(landscapes["neutral_plateau"], chosen, seeds[-1], budget)
    reproducible = reproducibility_a["curve"] == reproducibility_b["curve"]; ledger.event(run_id, "ar0_reproducibility", {"match": reproducible, "seed": seeds[-1], "policy": chosen})
    gpu_rows: list[dict[str, Any]] = []
    if include_gpu:
        try:
            validation = gpu_validate(environment, path / "gpu.owner.lock"); (path / "gpu_validation.json").write_text(json.dumps(validation, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            for label, lr in (("gpu_proxy_greedy", 0.10), ("gpu_proxy_adaptive", 0.15)):
                row = gpu_proxy(repo, path, environment, seeds[0], min(30, max(1, budget)), label, {"learning_rate": lr, "epochs": 24, "policy_tag": label})
                gpu_rows.append(row); _append_jsonl(results_path, {"phase": "gpu_proxy", **row}); ledger.event(run_id, "ar0_gpu_proxy_completed", row)
        except Exception as exc:
            failure = {"status": "failed", "failure": f"{type(exc).__name__}: {exc}"}; gpu_rows.append(failure); ledger.event(run_id, "ar0_gpu_proxy_failed", failure)
    summary = _summarize(rows, holdout_rows, recovery, gpu_rows); summary.update({"chosen_policy": chosen, "reproducibility_match": reproducible, "falsifications": falsifications})
    (path / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8"); write_report(path / "REPORT.md", run_id, config, summary, falsifications)
    kernel.assert_artifact_outside_repo(path / "REPORT.md")
    ledger.artifact(f"{run_id}-summary", run_id, "ar0_summary", str(path / "summary.json"), hashlib.sha256((path / "summary.json").read_bytes()).hexdigest())
    ledger.event(run_id, "ar0_completed", {"chosen_policy": chosen, "visible_rows": len(rows), "holdout_rows": len(holdout_rows), "recovery": recovery, "reproducibility_match": reproducible}); ledger.close()
    return run_id, path


