"""Probe deterministic, proof-aware candidate ranking."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Candidate:
    candidate_id: int
    score_numerator: int
    score_denominator: int
    complexity: int
    signature: str
    proof_valid: bool = True


@dataclass(frozen=True)
class Search:
    candidates: tuple[Candidate, ...]


def base_search() -> Search:
    return Search(
        candidates=(
            Candidate(0, 10, 10, 3, "zeta"),
            Candidate(1, 10, 10, 2, "alpha"),
            Candidate(2, 9, 10, 1, "invalid", False),
        )
    )


def exact_target(search: Search) -> int | None:
    valid = [candidate for candidate in search.candidates if candidate.proof_valid]
    if not valid:
        return None
    selected = min(
        valid,
        key=lambda candidate: (
            -Fraction(candidate.score_numerator, candidate.score_denominator),
            candidate.complexity,
            candidate.signature,
        ),
    )
    return selected.candidate_id


def input_order_argmax(search: Search) -> int | None:
    valid = [candidate for candidate in search.candidates if candidate.proof_valid]
    if not valid:
        return None
    return max(valid, key=lambda candidate: candidate.score_numerator / candidate.score_denominator).candidate_id


def float_rank(search: Search) -> int | None:
    valid = [candidate for candidate in search.candidates if candidate.proof_valid]
    if not valid:
        return None
    return min(valid, key=lambda candidate: (-candidate.score_numerator / candidate.score_denominator, candidate.complexity, candidate.signature)).candidate_id


def deterministic_exact(search: Search) -> int | None:
    return exact_target(search)


ARCHITECTURES: dict[str, Callable[[Search], int | None]] = {
    "input_order_argmax": input_order_argmax,
    "float_rank": float_rank,
    "deterministic_exact": deterministic_exact,
}


def reorder(search: Search, rng: random.Random) -> Search:
    candidates = list(search.candidates)
    rng.shuffle(candidates)
    return replace(search, candidates=tuple(candidates))


def near_tie(search: Search) -> Search:
    candidates = tuple(replace(candidate, score_numerator=999_999, score_denominator=1_000_000)
                      if candidate.candidate_id == 0 else candidate for candidate in search.candidates)
    return replace(search, candidates=candidates)


def invalid_high_score(search: Search) -> Search:
    candidates = tuple(replace(candidate, score_numerator=100, score_denominator=1)
                      if candidate.candidate_id == 2 else candidate for candidate in search.candidates)
    return replace(search, candidates=candidates)


def equal_complexity_tie(search: Search) -> Search:
    candidates = tuple(replace(candidate, complexity=2) if candidate.candidate_id == 0 else candidate for candidate in search.candidates)
    return replace(search, candidates=candidates)


def main() -> None:
    cases = {"original": 0, "reorder": 0, "near_tie": 0, "invalid_filter": 0, "semantic_tie": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        search = base_search()
        variants = {
            "reorder": reorder(search, rng),
            "near_tie": near_tie(search),
            "invalid_filter": invalid_high_score(search),
            "semantic_tie": equal_complexity_tie(search),
        }
        for architecture, run in ARCHITECTURES.items():
            row: dict[str, object] = {"seed": seed, "architecture": architecture}
            row["original_exact"] = run(search) == exact_target(search)
            cases["original"] += int(row["original_exact"])
            for label, variant in variants.items():
                ok = run(variant) == exact_target(variant)
                row[f"{label}_ok"] = ok
                cases[label] += int(ok)
            rows.append(row)
    total_runs = 5 * len(ARCHITECTURES)
    summary = {
        "seeds": 5,
        "architectures": list(ARCHITECTURES),
        "total_architecture_runs": total_runs,
        "pass_counts": cases,
        "pass_rates": {key: round(value / total_runs, 4) for key, value in cases.items()},
        "base_target": exact_target(base_search()),
        "near_tie_target": exact_target(near_tie(base_search())),
        "invalid_high_score_target": exact_target(invalid_high_score(base_search())),
        "semantic_tie_target": exact_target(equal_complexity_tie(base_search())),
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates", "base_target", "near_tie_target")}, indent=2))


if __name__ == "__main__":
    main()
