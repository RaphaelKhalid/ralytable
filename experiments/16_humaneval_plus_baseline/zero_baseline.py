"""Run an explicitly named, deterministic HumanEval+ pass baseline.

This is not a model adapter. It exists because the current Ralytable code does
not emit Python completions. Task IDs are read from EvalPlus at runtime; no
prompt, solution, or task list is inspected or hardcoded here.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


RESOURCE_STUB = """\nRLIMIT_AS = 9\nRLIMIT_DATA = 6\nRLIMIT_STACK = 3\ndef setrlimit(resource, limits):\n    return None\n"""


def write_samples(output: Path) -> int:
    from evalplus.data import get_human_eval_plus

    problems = get_human_eval_plus()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for task_id in problems:
            handle.write(json.dumps({"task_id": task_id, "completion": "pass"}) + "\n")
    return len(problems)


def append_event(record: Path | None, event: dict) -> None:
    if record is None:
        return
    record.parent.mkdir(parents=True, exist_ok=True)
    with record.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def event_template(run_id: str, version: str, total: int, status: str, started_at: str) -> dict:
    return {
        "record_version": 1,
        "run_id": run_id,
        "event": status,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark": "HumanEval+",
        "benchmark_version": f"EvalPlus {version}",
        "status": status,
        "started_at_utc": started_at,
        "completed_tasks": 0,
        "total_tasks": total,
        "provisional_pass_at_1": None,
        "compile_rate": None,
        "raw_controller_score": None,
        "full_system_score": None,
        "deterministic_null_score": None,
        "learned_parameters": 0,
        "generation_budget": {"samples": 1, "temperature": 0.0},
        "search_budget": {"expansions": 0, "seconds": 0.0},
        "mean_expansions": 0.0,
        "latency_ms": {"inference": None, "search": None, "total": None, "convention": "no model; total would be end-to-end"},
        "wall_seconds": None,
        "failure_categories": {},
        "current_task_id": None,
        "process": {"device": "cpu", "python": platform.python_version(), "pytorch": None, "allocator_memory_bytes": None, "allocator_only": True},
    }


def extract_pass_at_1(text: str) -> float | None:
    match = re.search(r"pass@1\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="load the official task map and report its size")
    parser.add_argument("--evaluate", action="store_true", help="run official EvalPlus base and plus evaluation")
    parser.add_argument("--output", type=Path, help="sample JSONL path outside the repository")
    parser.add_argument("--record", type=Path, help="append-only machine-readable run record outside the repository")
    args = parser.parse_args()

    if not args.smoke and not args.evaluate:
        parser.error("choose --smoke or --evaluate")

    version = importlib.metadata.version("evalplus")
    with tempfile.TemporaryDirectory(prefix="ralytable-evalplus-resource-") as shim_dir:
        shim = Path(shim_dir) / "resource.py"
        shim.write_text(RESOURCE_STUB, encoding="utf-8", newline="\n")
        env = os.environ.copy()
        env["PYTHONPATH"] = shim_dir + os.pathsep + env.get("PYTHONPATH", "")

        if args.smoke:
            from evalplus.data import get_human_eval_plus

            print(json.dumps({"arm": "deterministic_pass_baseline", "evalplus_version": version, "humaneval_plus_tasks": len(get_human_eval_plus())}))

        if args.evaluate:
            if args.output is None:
                parser.error("--evaluate requires --output outside the repository")
            output = args.output.resolve()
            repo_root = Path(__file__).resolve().parents[2]
            if repo_root == output or repo_root in output.parents:
                parser.error("--output must be outside the repository")
            record = args.record.resolve() if args.record else None
            if record and (repo_root == record or repo_root in record.parents):
                parser.error("--record must be outside the repository")
            count = write_samples(output)
            run_id = f"humaneval-plus-deterministic-pass-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            started_at = datetime.now(timezone.utc).isoformat()
            start_event = event_template(run_id, version, count, "running", started_at)
            start_event["artifacts"] = {"samples": str(output), "record": str(record) if record else None}
            append_event(record, start_event)
            started = time.perf_counter()
            command = [
                sys.executable,
                "-m",
                "evalplus.evaluate",
                "humaneval",
                "--samples",
                str(output),
                "--parallel",
                "1",
                "--i-just-wanna-run",
            ]
            completed = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
            elapsed = time.perf_counter() - started
            final_status = "completed" if completed.returncode == 0 else "failed"
            final_event = event_template(run_id, version, count, final_status, started_at)
            final_event["wall_seconds"] = round(elapsed, 3)
            final_event["evaluator_returncode"] = completed.returncode
            final_event["provisional_pass_at_1"] = extract_pass_at_1(completed.stdout)
            final_event["failure_categories"] = {} if completed.returncode == 0 else {"official_harness_environment": 1}
            if "SIGALRM" in completed.stderr or "setitimer" in completed.stderr or "resource" in completed.stderr:
                final_event["failure_categories"] = {"official_harness_posix_dependency": 1}
            final_event["artifacts"] = {"samples": str(output), "record": str(record) if record else None, "reproduction_command": " ".join(command)}
            append_event(record, final_event)
            print(json.dumps({
                "arm": "deterministic_pass_baseline",
                "evalplus_version": version,
                "humaneval_plus_tasks": count,
                "sample_path": str(output),
                "wall_seconds": round(elapsed, 3),
                "evaluator_returncode": completed.returncode,
                "record_path": str(record) if record else None,
            }))
            print(completed.stdout, end="")
            print(completed.stderr, end="", file=sys.stderr)
            return completed.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
