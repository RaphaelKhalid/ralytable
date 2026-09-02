"""Audit the data boundary for a no-answer-bits typed parser objective."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ALLOWED = {"prompt", "graph", "public_examples", "counterfactual"}
FORBIDDEN = {"answer", "solution", "hidden_test", "expected_output", "benchmark_test", "oracle"}


def valid_record(record: dict[str, object]) -> bool:
    if set(record) - ALLOWED or not {"prompt", "graph"} <= set(record):
        return False
    serialized = json.dumps(record, sort_keys=True).lower()
    return not any(term in serialized for term in FORBIDDEN)


def loss_contract() -> dict[str, object]:
    return {"graph": 1.0, "replay": 0.5, "counterfactual": 0.5, "unused_field": 0.25,
            "answer_bits": False, "hidden_tests": False, "raw_renderer_bypass": False}


def main() -> None:
    clean = [{"prompt": f"compose operation {i}", "graph": {"nodes": ["input", "map"], "edges": [[0, 1]]},
              "public_examples": [{"input": [i], "output": [i]}],
              "counterfactual": {"edit": "map -> filter", "dependent_nodes": [1]}}
             for i in range(100)]
    contaminated = [
        {"prompt": "x", "graph": {}, "answer": "leak"},
        {"prompt": "x", "graph": {}, "hidden_test": "oracle"},
        {"prompt": "x", "graph": {}, "metadata": {"expected_output": 1}},
        {"prompt": "x", "graph": {}, "public_examples": [], "solution": "return x"},
    ]
    output = {
        "clean_records": len(clean),
        "clean_accepted": sum(valid_record(row) for row in clean),
        "contaminated_records": len(contaminated),
        "contaminated_rejected": sum(not valid_record(row) for row in contaminated),
        "loss_contract": loss_contract(),
        "note": "Schema smoke audit only; no model was trained and no benchmark was run.",
    }
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
