"""Combinatorial scaling model for a typed primitive-module architecture."""

from __future__ import annotations

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TOKEN_DIM = 512
MODULE_DIM = 512


def row(primitives: int, depth: int, training_examples: int,
        module_accuracy: float = 0.99, type_compatibility: float = 0.25) -> dict[str, object]:
    total_programs = primitives ** depth
    flat_entries = min(training_examples, total_programs)
    flat_expected_unseen_success = flat_entries / total_programs
    seen_primitive_probability = 1.0 - (1.0 - 1.0 / primitives) ** (training_examples * depth)
    compositional_success = (seen_primitive_probability * module_accuracy) ** depth
    branch = max(1.0, primitives * type_compatibility)
    search_nodes = sum(branch ** level for level in range(depth + 1))
    return {
        "primitives": primitives,
        "depth": depth,
        "training_examples": training_examples,
        "program_space": total_programs,
        "flat_table_parameters": flat_entries * TOKEN_DIM,
        "compositional_library_parameters": primitives * MODULE_DIM,
        "flat_table_expected_exact_rate": flat_expected_unseen_success,
        "compositional_expected_exact_rate": compositional_success,
        "typed_search_nodes": search_nodes,
        "parameter_reduction": 1.0 - (primitives * MODULE_DIM) / max(1, flat_entries * TOKEN_DIM),
    }


def main() -> None:
    rows = [row(k, depth, examples)
            for k in (8, 16, 32)
            for depth in (2, 4, 6, 8)
            for examples in (100, 1_000, 10_000)]
    output = {
        "assumptions": {
            "token_dimension": TOKEN_DIM,
            "module_dimension": MODULE_DIM,
            "module_accuracy": 0.99,
            "type_compatibility": 0.25,
            "note": "Flat-table success models memorized whole programs; compositional success assumes primitive observations are independent and is not an empirical learning curve.",
        },
        "rows": rows,
        "note": "Combinatorial feasibility model only; no learned model or benchmark was run.",
    }
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for item in rows:
        if item["depth"] in (4, 8) and item["training_examples"] in (100, 10_000):
            print(json.dumps(item, sort_keys=True))
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
