"""Probe selective code emission with proof and verifier gates."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Candidate:
    task_id: int
    confidence: int  # integer percentage, avoiding floating-point policy drift
    proof_valid: bool
    verifier_pass: bool
    correct: bool


@dataclass(frozen=True)
class Batch:
    candidates: tuple[Candidate, ...]


def base_batch() -> Batch:
    return Batch(
        candidates=(
            Candidate(0, 95, True, True, True),
            Candidate(1, 91, False, False, False),
            Candidate(2, 89, True, True, True),
            Candidate(3, 86, True, False, False),
            Candidate(4, 79, True, True, True),
            Candidate(5, 75, True, True, True),
            Candidate(6, 93, True, True, True),
            Candidate(7, 97, False, False, False),
        )
    )


def emit(candidate: Candidate, policy: str) -> bool:
    if candidate.confidence < 80:
        return False
    if policy == "confidence_only":
        return True
    if policy == "proof_gated":
        return candidate.proof_valid
    return candidate.proof_valid and candidate.verifier_pass


def evaluate(batch: Batch, policy: str) -> dict[str, float | int]:
    emitted = [candidate for candidate in batch.candidates if emit(candidate, policy)]
    errors = sum(not candidate.correct for candidate in emitted)
    high_conf_invalid_emitted = sum(candidate.confidence >= 90 and not candidate.correct for candidate in emitted)
    return {
        "emitted": len(emitted),
        "coverage": round(len(emitted) / len(batch.candidates), 4),
        "errors": errors,
        "risk": round(errors / len(emitted), 4) if emitted else 0.0,
        "high_conf_invalid_emitted": high_conf_invalid_emitted,
    }


POLICIES = ("confidence_only", "proof_gated", "proof_selective")


def reorder(batch: Batch, rng: random.Random) -> Batch:
    candidates = list(batch.candidates)
    rng.shuffle(candidates)
    return replace(batch, candidates=tuple(candidates))


def verifier_improvement(batch: Batch) -> Batch:
    candidates = tuple(replace(candidate, verifier_pass=True, correct=True) if candidate.task_id == 3 else candidate for candidate in batch.candidates)
    return replace(batch, candidates=candidates)


def main() -> None:
    rows: list[dict[str, object]] = []
    aggregate: dict[str, dict[str, float]] = {policy: {"coverage": 0.0, "risk": 0.0, "high_conf_invalid_emitted": 0.0} for policy in POLICIES}
    for seed in range(5):
        rng = random.Random(seed)
        batch = base_batch()
        variants = {"original": batch, "reorder": reorder(batch, rng), "verifier_improvement": verifier_improvement(batch)}
        for variant_name, variant in variants.items():
            for policy in POLICIES:
                metrics = evaluate(variant, policy)
                rows.append({"seed": seed, "variant": variant_name, "policy": policy, **metrics})
                for key in aggregate[policy]:
                    aggregate[policy][key] += float(metrics[key])
    divisor = 5 * 3
    averaged = {policy: {key: round(value / divisor, 4) for key, value in metrics.items()} for policy, metrics in aggregate.items()}
    summary = {
        "seeds": 5,
        "policies": list(POLICIES),
        "averaged_metrics": averaged,
        "base_metrics": {policy: evaluate(base_batch(), policy) for policy in POLICIES},
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"base_metrics": summary["base_metrics"], "averaged_metrics": averaged}, indent=2))


if __name__ == "__main__":
    main()
