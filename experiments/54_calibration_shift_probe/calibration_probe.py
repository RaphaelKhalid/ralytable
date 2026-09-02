"""Probe confidence-threshold drift under a shifted candidate distribution."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class Candidate:
    task_id: int
    confidence: int
    proof_valid: bool
    verifier_pass: bool
    correct: bool


def source_batch() -> tuple[Candidate, ...]:
    return (
        Candidate(0, 95, True, True, True),
        Candidate(1, 92, True, True, True),
        Candidate(2, 90, False, False, False),
        Candidate(3, 88, True, True, True),
        Candidate(4, 85, True, True, True),
        Candidate(5, 82, False, False, False),
        Candidate(6, 78, True, True, True),
        Candidate(7, 75, True, True, True),
        Candidate(8, 72, False, False, False),
        Candidate(9, 68, True, True, True),
    )


def shifted_batch() -> tuple[Candidate, ...]:
    # Confidence drifts upward on the shifted distribution; the verifier
    # remains an explicit, independently measured signal in this probe.
    return (
        Candidate(0, 95, False, False, False),
        Candidate(1, 92, False, False, False),
        Candidate(2, 90, True, True, True),
        Candidate(3, 88, False, False, False),
        Candidate(4, 85, True, True, True),
        Candidate(5, 82, False, False, False),
        Candidate(6, 80, True, True, True),
        Candidate(7, 78, True, True, True),
        Candidate(8, 76, False, False, False),
        Candidate(9, 74, True, True, True),
    )


def risk_metrics(candidates: tuple[Candidate, ...], threshold: int, verifier_gate: bool) -> dict[str, float | int]:
    selected = [
        candidate for candidate in candidates
        if candidate.confidence >= threshold
        and (not verifier_gate or (candidate.proof_valid and candidate.verifier_pass))
    ]
    errors = sum(not candidate.correct for candidate in selected)
    return {
        "emitted": len(selected),
        "coverage": round(len(selected) / len(candidates), 4),
        "errors": errors,
        "risk": round(errors / len(selected), 4) if selected else 0.0,
    }


def learn_threshold(candidates: tuple[Candidate, ...], target_risk: float) -> int:
    thresholds = sorted({candidate.confidence for candidate in candidates})
    acceptable = [
        threshold for threshold in thresholds
        if risk_metrics(candidates, threshold, False)["risk"] <= target_risk
    ]
    return min(acceptable) if acceptable else max(thresholds) + 1


def main() -> None:
    source = source_batch()
    shifted = shifted_batch()
    threshold = learn_threshold(source, 0.1)
    rows: list[dict[str, object]] = []
    policies = {
        "confidence_fixed_80": (80, False),
        "source_calibrated": (threshold, False),
        "source_calibrated_plus_verifier": (threshold, True),
    }
    aggregate: dict[str, dict[str, float]] = {policy: {"coverage": 0.0, "risk": 0.0, "shift_risk": 0.0} for policy in policies}
    for seed in range(5):
        rng = random.Random(seed)
        source_variant = list(source)
        shifted_variant = list(shifted)
        rng.shuffle(source_variant)
        rng.shuffle(shifted_variant)
        source_tuple = tuple(source_variant)
        shifted_tuple = tuple(shifted_variant)
        for policy, (policy_threshold, verifier_gate) in policies.items():
            source_metrics = risk_metrics(source_tuple, policy_threshold, verifier_gate)
            shift_metrics = risk_metrics(shifted_tuple, policy_threshold, verifier_gate)
            rows.append({"seed": seed, "policy": policy, "threshold": policy_threshold, "verifier_gate": verifier_gate, "source": source_metrics, "shifted": shift_metrics})
            aggregate[policy]["coverage"] += float(source_metrics["coverage"])
            aggregate[policy]["risk"] += float(source_metrics["risk"])
            aggregate[policy]["shift_risk"] += float(shift_metrics["risk"])
    averaged = {policy: {key: round(value / 5, 4) for key, value in metrics.items()} for policy, metrics in aggregate.items()}
    summary = {
        "source_threshold_for_10_percent_risk": threshold,
        "policies": policies,
        "source_metrics": {policy: risk_metrics(source, policy_threshold, verifier_gate) for policy, (policy_threshold, verifier_gate) in policies.items()},
        "shifted_metrics": {policy: risk_metrics(shifted, policy_threshold, verifier_gate) for policy, (policy_threshold, verifier_gate) in policies.items()},
        "averaged_metrics": averaged,
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source_threshold": threshold, "source_metrics": summary["source_metrics"], "shifted_metrics": summary["shifted_metrics"]}, indent=2))


if __name__ == "__main__":
    main()
