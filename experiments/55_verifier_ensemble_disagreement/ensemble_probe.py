"""Probe verifier disagreement as a structural uncertainty signal."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class Candidate:
    task_id: int
    type_pass: bool
    effect_pass: bool
    execution_pass: bool
    correct: bool


def base_batch() -> tuple[Candidate, ...]:
    return (
        Candidate(0, True, True, True, True),
        Candidate(1, True, True, False, False),
        Candidate(2, True, False, True, False),
        Candidate(3, False, True, True, False),
        Candidate(4, False, False, False, False),
        Candidate(5, True, True, True, True),
        Candidate(6, True, True, True, True),
        Candidate(7, True, False, False, False),
    )


def accepted(candidate: Candidate, policy: str) -> bool:
    votes = (candidate.type_pass, candidate.effect_pass, candidate.execution_pass)
    if policy == "single_execution":
        return candidate.execution_pass
    if policy == "majority":
        return sum(votes) >= 2
    return all(votes)


def metrics(batch: tuple[Candidate, ...], policy: str) -> dict[str, float | int]:
    selected = [candidate for candidate in batch if accepted(candidate, policy)]
    errors = sum(not candidate.correct for candidate in selected)
    disagreements = sum(len({candidate.type_pass, candidate.effect_pass, candidate.execution_pass}) > 1 for candidate in selected)
    return {
        "emitted": len(selected),
        "coverage": round(len(selected) / len(batch), 4),
        "errors": errors,
        "risk": round(errors / len(selected), 4) if selected else 0.0,
        "disagreements_emitted": disagreements,
    }


POLICIES = ("single_execution", "majority", "unanimous")


def main() -> None:
    aggregate = {policy: {"coverage": 0.0, "risk": 0.0, "disagreements_emitted": 0.0} for policy in POLICIES}
    rows: list[dict[str, object]] = []
    batch = base_batch()
    for seed in range(5):
        rng = random.Random(seed)
        shuffled = list(batch)
        rng.shuffle(shuffled)
        variant = tuple(shuffled)
        for policy in POLICIES:
            result = metrics(variant, policy)
            rows.append({"seed": seed, "policy": policy, **result})
            for key in aggregate[policy]:
                aggregate[policy][key] += float(result[key])
    averaged = {policy: {key: round(value / 5, 4) for key, value in result.items()} for policy, result in aggregate.items()}
    summary = {
        "policies": list(POLICIES),
        "base_metrics": {policy: metrics(batch, policy) for policy in POLICIES},
        "averaged_metrics": averaged,
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"base_metrics": summary["base_metrics"], "averaged_metrics": averaged}, indent=2))


if __name__ == "__main__":
    main()
