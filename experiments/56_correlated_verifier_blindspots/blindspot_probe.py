"""Probe correlated verifier failures and independent challenge tests."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Candidate:
    task_id: int
    type_pass: bool
    effect_pass: bool
    execution_pass: bool
    challenge_pass: bool
    correct: bool


def base_batch() -> tuple[Candidate, ...]:
    return (
        Candidate(0, True, True, True, True, True),
        Candidate(1, True, True, True, False, False),  # shared blind spot
        Candidate(2, True, False, True, False, False),
        Candidate(3, False, False, False, False, False),
        Candidate(4, True, True, True, True, True),
        Candidate(5, True, True, True, False, False),  # second shared blind spot
        Candidate(6, True, True, False, False, False),
        Candidate(7, True, True, True, True, True),
    )


def accepts(candidate: Candidate, policy: str) -> bool:
    standard = candidate.type_pass and candidate.effect_pass and candidate.execution_pass
    if policy == "unanimous_standard":
        return standard
    return standard and candidate.challenge_pass


def metrics(batch: tuple[Candidate, ...], policy: str) -> dict[str, float | int]:
    selected = [candidate for candidate in batch if accepts(candidate, policy)]
    errors = sum(not candidate.correct for candidate in selected)
    shared_errors = sum(candidate.task_id in {1, 5} for candidate in selected)
    return {
        "emitted": len(selected),
        "coverage": round(len(selected) / len(batch), 4),
        "errors": errors,
        "risk": round(errors / len(selected), 4) if selected else 0.0,
        "correlated_blindspot_errors": shared_errors,
    }


POLICIES = ("unanimous_standard", "unanimous_plus_challenge")


def main() -> None:
    batch = base_batch()
    rows: list[dict[str, object]] = []
    aggregate = {policy: {"coverage": 0.0, "risk": 0.0, "correlated_blindspot_errors": 0.0} for policy in POLICIES}
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
