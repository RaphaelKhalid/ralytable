"""Common private-task evaluator and capability-free baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from sandbox import Sandbox


TEST_TIMEOUT_SECONDS = 10


def _load_task(task_dir: Path) -> dict[str, Any]:
    return json.loads((task_dir / "private" / "task.json").read_text(encoding="utf-8"))


def _hidden_result(repo: Path, hidden: Path) -> dict[str, Any]:
    target = repo / "tests" / "test_hidden_eval.py"
    target.write_text(hidden.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    env = {
        "PATH": sys.executable.rsplit("\\", 1)[0] + ";" + __import__("os").environ.get("PATH", ""),
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
    }
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
            cwd=repo, env=env, capture_output=True, text=True,
            timeout=TEST_TIMEOUT_SECONDS, check=False,
        )
        return {
            "passed": completed.returncode == 0,
            "returncode": completed.returncode,
            "timed_out": False,
            "stdout": completed.stdout[-64_000:],
            "stderr": completed.stderr[-64_000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "passed": False, "returncode": -1, "timed_out": True,
            "stdout": str(exc.stdout or ""), "stderr": str(exc.stderr or ""),
        }


def evaluate_actions(task_dir: Path, actions: list[Any]) -> dict[str, Any]:
    task = _load_task(task_dir)
    with tempfile.TemporaryDirectory(prefix="raly-coder-eval-") as temp:
        repo = Path(temp) / "repo"
        shutil.copytree(task_dir / "repo", repo)
        sandbox = Sandbox(repo)
        outputs = [sandbox.execute(action) for action in actions]
        hidden = _hidden_result(repo, task_dir / "private" / "hidden_tests.py")
        return {
            "task_id": task["task_id"],
            "success": hidden["passed"],
            "hidden": hidden,
            "actions": outputs,
            "trace": [event.__dict__ for event in sandbox.events],
            "action_count": len(outputs),
            "invalid_actions": sum(not output["ok"] for output in outputs),
        }


def evaluate_oracle(task_dir: Path) -> dict[str, Any]:
    task = _load_task(task_dir)
    patch = task["oracle_patch"]
    return evaluate_actions(task_dir, [{
        "schema": "raly-coder-actions-v1", "op": "apply_patch", "args": patch,
    }])


def evaluate_noop(task_dir: Path) -> dict[str, Any]:
    return evaluate_actions(task_dir, [])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--mode", choices=("oracle", "noop"), required=True)
    args = parser.parse_args()
    result = evaluate_oracle(args.task) if args.mode == "oracle" else evaluate_noop(args.task)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
