"""Sensitivity model for a compact typed coder with external leverage."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def score(module_coverage: float, retrieval_hit: float, parser_accuracy: float,
          beam: int, novel_accuracy: float = 0.18, module_accuracy: float = 0.99,
          execution_accuracy: float = 0.98, hypothesis_recall: float = 0.38) -> float:
    # A task either falls in the exact-module, retrievable, or novel bucket.
    # The buckets are disjoint by construction. Beam recall is a deliberately
    # optimistic independent-hypothesis upper model, not an empirical result.
    retrieved_success = retrieval_hit * parser_accuracy * execution_accuracy * (
        1.0 - (1.0 - hypothesis_recall) ** beam
    ) + (1.0 - retrieval_hit) * novel_accuracy
    return module_coverage * module_accuracy + (1.0 - module_coverage) * (
        0.75 * retrieved_success + 0.25 * novel_accuracy
    )


def minimum_coverage(target: float, retrieval_hit: float, parser_accuracy: float,
                     beam: int) -> float | None:
    for step in range(1001):
        coverage = step / 1000
        if score(coverage, retrieval_hit, parser_accuracy, beam) >= target:
            return coverage
    return None


def main() -> None:
    targets = (0.70, 0.80, 0.90)
    rows = []
    for beam in (1, 4, 8, 16):
        for parser_accuracy in (0.70, 0.85, 0.95):
            for retrieval_hit in (0.60, 0.80, 0.95):
                row = {"beam": beam, "parser_accuracy": parser_accuracy,
                       "retrieval_hit": retrieval_hit}
                for target in targets:
                    row[f"coverage_for_{target:.2f}"] = minimum_coverage(
                        target, retrieval_hit, parser_accuracy, beam
                    )
                row["score_at_coverage_0.60"] = score(
                    0.60, retrieval_hit, parser_accuracy, beam
                )
                rows.append(row)
    # Compact summary: the minimum exact-module coverage needed to reach 0.80
    # at the strongest declared settings, and the score ceiling at 60% cover.
    strongest = [r for r in rows if r["parser_accuracy"] == 0.95 and r["retrieval_hit"] == 0.95]
    output = {
        "assumptions": {
            "task_buckets": {"exact_module": 0.60, "retrievable": 0.30, "novel": 0.10},
            "novel_accuracy": 0.18,
            "module_accuracy": 0.99,
            "execution_accuracy": 0.98,
            "hypothesis_recall_per_beam": 0.38,
            "note": "The score function weights non-module tasks 75/25 retrievable/novel; module_coverage is varied and is not fixed to the illustrative bucket row.",
        },
        "rows": rows,
        "strongest_parser_retrieval": strongest,
        "note": "Feasibility sensitivity model only; no learned model, benchmark, or Qwen score was run.",
    }
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
