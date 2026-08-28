"""Cheap end-to-end gate for generation, privacy scanning, and evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile

from evaluator import evaluate_noop, evaluate_oracle
from generator import FAMILIES, generate_bundle
from leakage import scan_bundle


@dataclass(frozen=True)
class Check:
    task_id: str
    family: str
    oracle_passed: bool
    noop_passed: bool


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="raly-coder-benchmark-smoke-") as temp:
        bundle = Path(temp) / "bundle"
        manifest = generate_bundle(
            bundle, splits=["train"], repositories=1,
            tasks_per_repository=len(FAMILIES),
        )
        assert len(manifest["tasks"]) == len(FAMILIES)
        assert {entry["family"] for entry in manifest["tasks"]} == set(FAMILIES)
        leakage = scan_bundle(bundle)
        assert leakage["passed"] and leakage["tasks_scanned"] == len(FAMILIES)
        checks = []
        for entry in manifest["tasks"]:
            task_dir = bundle / entry["private_path"]
            oracle = evaluate_oracle(task_dir)
            noop = evaluate_noop(task_dir)
            assert oracle["success"]
            checks.append(Check(
                task_id=entry["task_id"], family=entry["family"],
                oracle_passed=oracle["success"], noop_passed=noop["success"],
            ))
        print(json.dumps({
            "status": "PASS", "tasks": len(checks),
            "families": [check.family for check in checks],
            "oracle_successes": sum(check.oracle_passed for check in checks),
            "noop_successes": sum(check.noop_passed for check in checks),
            "leakage": leakage,
        }, indent=2))


if __name__ == "__main__":
    main()
