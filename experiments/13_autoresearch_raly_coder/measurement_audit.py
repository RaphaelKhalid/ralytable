"""Audit the overnight Experiment 13 record without producing new evidence.

This is deliberately a small, dependency-free check for the repository's
measurement boundaries. It treats the append-only valid log and the preserved
invalid oracle log as separate inputs, and checks that the base selector has no
path to hidden answers. It does not recompute or replace the overnight scores.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VALID_LOG = ROOT / "research_log.jsonl"
INVALID_LOG = ROOT / "research_log_invalidated_null_oracle.jsonl"
RUN_SOURCE = ROOT / "run.py"


def read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise AssertionError(f"{path}:{line_number}: invalid JSON: {error}") from error
        if not isinstance(value, dict):
            raise AssertionError(f"{path}:{line_number}: row is not an object")
        rows.append(value)
    return rows


def function_sources(path: Path) -> dict[str, str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return {
        node.name: ast.get_source_segment(source, node) or ""
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def audit(expected_valid: int | None = None) -> None:
    valid = read_jsonl(VALID_LOG)
    invalid = read_jsonl(INVALID_LOG)
    if expected_valid is not None and len(valid) != expected_valid:
        raise AssertionError(f"expected {expected_valid} valid rows, found {len(valid)}")
    if not invalid:
        raise AssertionError("the preserved invalid oracle log is empty")
    if any(row.get("status") == "invalidated" for row in valid):
        raise AssertionError("invalidated rows leaked into the valid aggregate log")

    selectors = function_sources(RUN_SOURCE)
    required = ("action_score", "exhaustive_search", "local_repair_search", "public_pass")
    for name in required:
        if name not in selectors:
            raise AssertionError(f"missing selection function: {name}")
        source = selectors[name]
        for forbidden in ("hidden_expected", "hidden_values", "hidden_pass"):
            if forbidden in source:
                raise AssertionError(f"{name} references hidden scoring data: {forbidden}")

    print(json.dumps({
        "valid_rows": len(valid),
        "invalid_oracle_rows_preserved": len(invalid),
        "invalid_rows_excluded": True,
        "selection_hidden_answer_check": "pass",
        "note": "historical latency_ms rows remain post-inference timings; no replacement scores computed",
    }, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-valid", type=int, default=None)
    args = parser.parse_args()
    audit(args.expected_valid)


if __name__ == "__main__":
    main()
