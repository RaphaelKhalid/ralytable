"""Dependency-free, non-official code-validation proxy.

The proxy tasks are generated repair-like feature records. They are not
HumanEval tasks and their scores must never be reported as HumanEval+ scores.
"""

from __future__ import annotations

import math
import random
from typing import Iterable


FEATURE_NAMES = ("loop", "branch", "numeric_request", "runtime_exception", "empty_output", "collection", "ordering", "boundary")


def make_examples(seed: int, count: int, split: str) -> list[tuple[list[float], int]]:
    rng = random.Random((seed * 1_000_003) ^ sum(map(ord, split)))
    examples: list[tuple[list[float], int]] = []
    for _ in range(count):
        x = [float(rng.random() > 0.5) for _ in FEATURE_NAMES]
        # A deterministic repair-family rule. The model only receives x; y is
        # supervision during development training and is hidden at scoring.
        margin = 1.2 * x[0] + 0.9 * x[2] + 0.7 * x[5] + 0.5 * x[7] - 0.9 * x[3] - 0.6 * x[4] + 0.15 * x[1] - 1.0
        y = int(margin > 0.0)
        examples.append((x, y))
    return examples


def sigmoid(value: float) -> float:
    value = max(-40.0, min(40.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def predict(weights: list[float], x: list[float], threshold: float = 0.5) -> int:
    return int(sigmoid(weights[0] + sum(w * f for w, f in zip(weights[1:], x))) >= threshold)


def score_weights(weights: list[float], seed: int, split: str, count: int = 128) -> float:
    data = make_examples(seed, count, split)
    return sum(predict(weights, x) == y for x, y in data) / len(data)


def intervention_rate(weights: list[float], seed: int, count: int = 128) -> float:
    changed = 0
    relevant = 0
    for x, _ in make_examples(seed, count, "causal"):
        base = predict(weights, x)
        intervention = list(x)
        intervention[0] = 1.0 - intervention[0]
        if x[0] != intervention[0]:
            relevant += 1
            changed += int(base != predict(weights, intervention))
    return changed / relevant if relevant else 0.0


def placebo_preservation(weights: list[float], seed: int, count: int = 128) -> float:
    preserved = 0
    for x, _ in make_examples(seed, count, "placebo"):
        placebo = list(x)
        placebo[1] = 1.0 - placebo[1]
        preserved += int(predict(weights, x) == predict(weights, placebo))
    return preserved / count


def exact_trace_replay(weights: list[float], seed: int) -> float:
    first = [predict(weights, x) for x, _ in make_examples(seed, 32, "trace")]
    second = [predict(weights, x) for x, _ in make_examples(seed, 32, "trace")]
    return float(first == second)

