"""Scan model-visible task material for private answer leakage."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


MIN_FRAGMENT_LENGTH = 12


def _private_task(task_dir: Path) -> dict[str, Any]:
    return json.loads((task_dir / "private" / "task.json").read_text(encoding="utf-8"))


def _visible_text(task: dict[str, Any]) -> str:
    parts = [task["request"]]
    parts.extend(task["files"].values())
    parts.extend(task["visible_tests"].values())
    return "\n".join(parts)


def _fragments(hidden: str, oracle: dict[str, str]) -> list[str]:
    tree = ast.parse(hidden)
    candidates = [oracle["new_text"]]
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            candidates.append(node.name)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            candidates.append(node.value)
    return sorted({x.strip() for x in candidates
                   if isinstance(x, str) and len(x.strip()) >= MIN_FRAGMENT_LENGTH})


def scan_task(task_dir: Path) -> list[dict[str, str]]:
    task = _private_task(task_dir)
    oracle = task["oracle_patch"]
    visible = _visible_text(task)
    findings = []
    for fragment in _fragments(task["hidden_tests"], oracle):
        if fragment in visible:
            findings.append({
                "task_id": task["task_id"],
                "kind": "private-fragment-in-visible-text",
                "fragment": fragment,
            })
    if str(task["repository_seed"]) in visible:
        findings.append({
            "task_id": task["task_id"], "kind": "seed-in-visible-text",
            "fragment": str(task["repository_seed"]),
        })
    return findings


def scan_bundle(bundle: Path) -> dict[str, Any]:
    task_dirs = sorted(
        path.parent.parent
        for path in bundle.glob("*/*/private/task.json")
    )
    findings = [finding for task_dir in task_dirs for finding in scan_task(task_dir)]
    return {
        "schema": "raly-coder-leakage-report-v1",
        "tasks_scanned": len(task_dirs),
        "findings": findings,
        "passed": not findings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    report = scan_bundle(args.bundle)
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
