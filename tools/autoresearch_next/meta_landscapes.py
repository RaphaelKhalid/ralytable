"""Deterministic researcher testbeds with enumerable optima.

These landscapes are deliberately synthetic.  They exercise search behavior,
not Python generation, and contain no benchmark answers or hidden tests.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from typing import Callable, Iterable


BitVector = tuple[int, ...]


@dataclass(frozen=True)
class Landscape:
    name: str
    family: str
    dimension: int
    score_fn: Callable[[BitVector], float]
    feasible_fn: Callable[[BitVector], bool]
    optimum_score: float
    optimum_count: int

    def score(self, point: BitVector) -> float:
        if len(point) != self.dimension or any(bit not in (0, 1) for bit in point):
            return float("-inf")
        if not self.feasible_fn(point):
            return float("-inf")
        return float(self.score_fn(point))

    def feasible(self, point: BitVector) -> bool:
        return len(point) == self.dimension and all(bit in (0, 1) for bit in point) and self.feasible_fn(point)

    def enumerate_optima(self) -> list[BitVector]:
        return [point for point in enumerate_points(self.dimension) if self.score(point) == self.optimum_score]


def enumerate_points(dimension: int) -> Iterable[BitVector]:
    return itertools.product((0, 1), repeat=dimension)


def _trap(point: BitVector) -> float:
    total = 0.0
    for start in range(0, len(point), 4):
        ones = sum(point[start:start + 4])
        total += 4.0 if ones == 4 else 3.0 - ones
    return total


def _sparse(point: BitVector) -> float:
    return 1.0 if point == (1,) * len(point) else 0.0


def _neutral(point: BitVector) -> float:
    return 1.0 if sum(point) >= len(point) - 2 else 0.0


def _epistatic(point: BitVector) -> float:
    half = len(point) // 2
    left = point[:half]
    right = point[half:]
    left_block = 1.0 if left == (1,) * half else 0.0
    right_block = 1.0 if right == (1,) * half else 0.0
    # The second block is valuable only after the first block is complete.
    return left_block * 0.5 + left_block * right_block * 0.5


def _constraint_score(point: BitVector) -> float:
    return float(sum(point))


def make_landscapes() -> dict[str, Landscape]:
    """Return small landscapes whose optima can be exhaustively checked."""
    landscapes = {
        "deceptive_local": Landscape("deceptive_local", "deceptive", 8, _trap, lambda _: True, 8.0, 1),
        "sparse_reward": Landscape("sparse_reward", "sparse_reward", 8, _sparse, lambda _: True, 1.0, 1),
        "neutral_plateau": Landscape("neutral_plateau", "neutral", 8, _neutral, lambda _: True, 1.0, 37),
        "epistatic_crossover": Landscape("epistatic_crossover", "epistatic", 8, _epistatic, lambda _: True, 1.0, 1),
        "constraint_heavy": Landscape("constraint_heavy", "constraint", 8, _constraint_score, lambda p: sum(p) <= 3, 3.0, 56),
    }
    # Guard the declared optima against accidental changes in a scoring rule.
    for landscape in landscapes.values():
        scores = [landscape.score(point) for point in enumerate_points(landscape.dimension)]
        if max(scores) != landscape.optimum_score or sum(score == landscape.optimum_score for score in scores) != landscape.optimum_count:
            raise AssertionError(f"incorrect declared optimum for {landscape.name}")
    return landscapes


def hamming(a: BitVector, b: BitVector) -> int:
    return sum(x != y for x, y in zip(a, b))


def random_point(rng: random.Random, dimension: int) -> BitVector:
    return tuple(rng.randrange(2) for _ in range(dimension))


def mutate(point: BitVector, rng: random.Random) -> BitVector:
    index = rng.randrange(len(point))
    result = list(point)
    result[index] = 1 - result[index]
    return tuple(result)


def crossover(a: BitVector, b: BitVector, rng: random.Random) -> BitVector:
    cut = rng.randrange(1, len(a))
    return a[:cut] + b[cut:]


def simplify(point: BitVector, rng: random.Random) -> BitVector:
    result = list(point)
    ones = [i for i, bit in enumerate(result) if bit]
    if ones:
        result[rng.choice(ones)] = 0
    return tuple(result)


def radical(point: BitVector, rng: random.Random) -> BitVector:
    dimension = len(point)
    return random_point(rng, dimension)
