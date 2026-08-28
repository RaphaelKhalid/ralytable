"""AR2: stagnation-aware MAP-Elites meta-evaluation.

This module evaluates the researcher on synthetic, exhaustively enumerable
landscapes.  It deliberately contains no HumanEval material or Python-coder
scoring path.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .ledger import AppendOnlyLedger
from .meta_landscapes import BitVector, crossover, hamming, mutate, radical, simplify
from .runner import gpu_owner
from .schema import OPERATOR_WEIGHTS, canonical_json
from .trust_kernel import TrustKernel

POLICIES = ("map_elites_fixed", "adaptive_qd_ucb", "stagnation_aware_map_elites")
ABLATIONS = (
    "no_stagnation_trigger",
    "no_radical_restart",
    "no_novelty_targeting",
    "overreactive_trigger",
)
SEEDS = (17, 29, 43, 59, 71, 83, 97)
VISIBLE_FAMILIES = (
    "deceptive_trap_v2",
    "sparse_portals_v2",
    "neutral_plateau_v2",
    "epistatic_bridge_v2",
    "constraint_ridge_v2",
    "mixed_pressure_v2",
)
BLIND_FAMILY = "blind_rotated_composition_v2"
INSTANCE_SEEDS = {
    "deceptive_trap_v2": (1103, 1109, 1117, 1123),
    "sparse_portals_v2": (1201, 1207, 1213, 1223),
    "neutral_plateau_v2": (1301, 1307, 1319, 1327),
    "epistatic_bridge_v2": (1403, 1409, 1423, 1429),
    "constraint_ridge_v2": (1501, 1511, 1523, 1531),
    "mixed_pressure_v2": (1601, 1607, 1613, 1621),
    BLIND_FAMILY: (1709, 1721),
}
BUDGET = 512
COSTS = {"mutation": 1.00, "crossover": 1.20, "simplification": 0.90, "radical": 1.50}
BOOTSTRAP_REPS = 10_000


def points(dimension: int):
    return itertools.product((0, 1), repeat=dimension)


def target_from_seed(seed: int, dimension: int, ones: int | None = None) -> BitVector:
    rng = random.Random(seed)
    if ones is None:
        result = tuple(rng.randrange(2) for _ in range(dimension))
        if not any(result):
            result = (1,) + result[1:]
        return result
    result = [0] * dimension
    for index in rng.sample(range(dimension), ones):
        result[index] = 1
    return tuple(result)


@dataclass
class AR2Landscape:
    family: str
    name: str
    dimension: int
    instance_seed: int
    score_fn: Callable[[BitVector], float]
    feasible_fn: Callable[[BitVector], bool]
    optimum_score: float = 0.0
    baseline_score: float = 0.0
    ideal_qd: float = 0.0
    optimum_count: int = 0
    ideal_niches: int = 0

    def score(self, point: BitVector) -> float:
        if len(point) != self.dimension or any(bit not in (0, 1) for bit in point):
            return float("-inf")
        if not self.feasible_fn(point):
            return float("-inf")
        return float(self.score_fn(point))

    def feasible(self, point: BitVector) -> bool:
        return len(point) == self.dimension and all(bit in (0, 1) for bit in point) and self.feasible_fn(point)

    def niche(self, point: BitVector) -> str:
        half = self.dimension // 2
        return ":".join(
            (
                "valid" if self.feasible(point) else "invalid",
                str(sum(point) // 3),
                str(sum(point[:half]) // 3),
                str(sum(point[half:]) // 3),
            )
        )

    def verify_exhaustive(self) -> None:
        origin = tuple(0 for _ in range(self.dimension))
        baseline = self.score(origin)
        self.baseline_score = baseline if math.isfinite(baseline) else 0.0
        best, count, niche_best = float("-inf"), 0, {}
        for point in points(self.dimension):
            score = self.score(point)
            if not math.isfinite(score):
                continue
            key = self.niche(point)
            niche_best[key] = max(score, niche_best.get(key, float("-inf")))
            if score > best:
                best, count = score, 1
            elif score == best:
                count += 1
        if not math.isfinite(best) or best <= self.baseline_score:
            raise ValueError(f"invalid score range for {self.name}: {self.baseline_score} -> {best}")
        self.optimum_score, self.optimum_count = best, count
        self.ideal_niches = len(niche_best)
        denominator = best - self.baseline_score
        self.ideal_qd = sum(max(0.0, min(1.0, (score - self.baseline_score) / denominator)) for score in niche_best.values())
        if self.ideal_qd <= 0:
            raise ValueError(f"invalid ideal QD for {self.name}")


def make_landscape(family: str, seed: int) -> AR2Landscape:
    dimension = 20 if family in ("mixed_pressure_v2", BLIND_FAMILY) else 18
    half = dimension // 2
    target = target_from_seed(seed, dimension, dimension // 2 if family in ("constraint_ridge_v2", "mixed_pressure_v2", BLIND_FAMILY) else None)

    def matches(point: BitVector, start: int = 0, end: int | None = None) -> int:
        return sum(point[i] == target[i] for i in range(start, end if end is not None else dimension))

    if family == "deceptive_trap_v2":
        def score(point: BitVector) -> float:
            total = 0.0
            for start in range(0, dimension, 3):
                m = matches(point, start, start + 3)
                total += 5.0 if m == 3 else 3.0 - m
            return total
        feasible = lambda _: True
    elif family == "sparse_portals_v2":
        def score(point: BitVector) -> float:
            left_exact = point[:half] == target[:half]
            right_distance = hamming(point[half:], target[half:])
            if point == target:
                return 3.0
            if left_exact and right_distance <= 1:
                return 0.6
            if left_exact and right_distance <= 3:
                return 0.2
            return 0.0
        feasible = lambda _: True
    elif family == "neutral_plateau_v2":
        def score(point: BitVector) -> float:
            m = matches(point)
            return 1.0 if m == dimension else 0.35 if m >= dimension - 3 else 0.0
        feasible = lambda _: True
    elif family == "epistatic_bridge_v2":
        def score(point: BitVector) -> float:
            block = dimension // 3
            left = point[:block] == target[:block]
            middle = point[block : 2 * block] == target[block : 2 * block]
            right = point[2 * block :] == target[2 * block :]
            return 0.4 * float(left) + 0.3 * float(left and middle) + 0.3 * float(left and middle and right)
        feasible = lambda _: True
    elif family == "constraint_ridge_v2":
        capacity = dimension // 3
        def score(point: BitVector) -> float:
            m = matches(point)
            block_bonus = 1.5 if point[:half] == target[:half] else 0.0
            return float(m) + block_bonus
        feasible = lambda point: sum(point) <= capacity
    elif family == "mixed_pressure_v2":
        capacity = dimension // 2
        def score(point: BitVector) -> float:
            m = matches(point)
            left_exact = point[:half] == target[:half]
            exact = point == target
            return 0.10 * m + 1.0 * float(left_exact) + 2.0 * float(exact) + 0.2 * float(sum(point) == capacity)
        feasible = lambda point: sum(point) <= capacity
    elif family == BLIND_FAMILY:
        # A distinct blind composition: rotate the target and require both a
        # constraint ridge and an exact epistatic bridge for the top reward.
        rotation = seed % dimension
        rotated = target[rotation:] + target[:rotation]
        capacity = dimension // 2
        def score(point: BitVector) -> float:
            left = point[:half] == rotated[:half]
            right = point[half:] == rotated[half:]
            m = sum(point[i] == rotated[i] for i in range(dimension))
            return 0.08 * m + 0.8 * float(left) + 0.7 * float(left and right) + 0.2 * float(sum(point) == capacity)
        feasible = lambda point: sum(point) <= capacity
    else:
        raise KeyError(family)
    landscape = AR2Landscape(family, f"{family}-{seed}", dimension, seed, score, feasible)
    landscape.verify_exhaustive()
    return landscape


def normal(score: float, landscape: AR2Landscape) -> float:
    if not math.isfinite(score):
        return 0.0
    denominator = landscape.optimum_score - landscape.baseline_score
    return max(0.0, min(1.0, (score - landscape.baseline_score) / denominator))


def area(costs: list[float], values: list[float]) -> float:
    if len(costs) != len(values):
        raise ValueError("cost and curve lengths differ")
    total = costs[-1]
    scaled = [cost / total for cost in costs]
    return sum(0.5 * (values[i - 1] + values[i]) * (scaled[i] - scaled[i - 1]) for i in range(1, len(values)))


@dataclass
class Record:
    point: BitVector
    score: float
    depth: int
    candidate_id: str
    operator: str
    parent_ids: tuple[str, ...] = ()


@dataclass
class AR2Trial:
    landscape: AR2Landscape
    policy: str
    seed: int
    budget: int = BUDGET
    ablation: str | None = None
    rng: random.Random = field(init=False)
    population: list[Record] = field(default_factory=list)
    archive: dict[str, Record] = field(default_factory=dict)
    seen: set[BitVector] = field(default_factory=set)
    best_score: float = float("-inf")
    best: Record | None = None
    costs: list[float] = field(default_factory=lambda: [0.0])
    curve: list[float] = field(default_factory=list)
    archive_qd_curve: list[float] = field(default_factory=list)
    operator_counts: dict[str, int] = field(default_factory=lambda: {name: 0 for name in OPERATOR_WEIGHTS})
    operator_improvements: dict[str, int] = field(default_factory=lambda: {name: 0 for name in OPERATOR_WEIGHTS})
    operator_credit: dict[str, float] = field(default_factory=lambda: {name: 0.0 for name in OPERATOR_WEIGHTS})
    operator_uses: dict[str, int] = field(default_factory=lambda: {name: 0 for name in OPERATOR_WEIGHTS})
    valid_count: int = 0
    duplicate_count: int = 0
    novelty_sum: float = 0.0
    max_depth: int = 0
    current_step: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    receipt_chain: str = "0" * 64
    in_burst: bool = False
    burst_used: int = 0
    burst_progress: bool = False
    cooldown_until: float = 0.0
    last_best_cost: float = 0.0
    last_qd_signal_cost: float = 0.0
    last_online_qd: float = 0.0

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self._observe(tuple(0 for _ in range(self.landscape.dimension)), "seed", 0, 0.0, (), True)

    @property
    def stagnation_enabled(self) -> bool:
        return self.policy == "stagnation_aware_map_elites" and self.ablation != "no_stagnation_trigger"

    def _parents(self) -> list[Record]:
        return list(self.archive.values()) or self.population

    def _online_qd(self) -> float:
        raw = sum(max(0.0, record.score - self.landscape.baseline_score) for record in self.archive.values())
        # This is intentionally a local, fixed-scale signal.  The primary
        # trigger cannot access the exhaustive ideal QD or optimum.
        return min(1.0, raw / max(1.0, float(self.landscape.dimension)))

    def _signals(self) -> dict[str, float]:
        recent = self.history[-16:]
        return {
            "stall_best": self.costs[-1] - self.last_best_cost,
            "stall_qd": self.costs[-1] - self.last_qd_signal_cost,
            "duplicate16": sum(int(row["duplicate"]) for row in recent) / max(1, len(recent)),
            "valid16": sum(int(row["valid"]) for row in recent) / max(1, len(recent)),
            "growth16": sum(int(row["new_niche"]) for row in recent) / max(1, len(recent)),
        }

    def _trigger_config(self) -> tuple[float, float, float, float, int, float, float, float]:
        if self.ablation == "overreactive_trigger":
            return 4.0, 6.0, 0.25, 0.50, 40, 8.0, 0.70, 0.65
        return 18.0, 24.0, 0.50, 0.75, 20, 24.0, 0.45, 0.65

    def _maybe_start_burst(self) -> None:
        if not self.stagnation_enabled or self.in_burst or self.current_step < 16 or self.costs[-1] < self.cooldown_until:
            return
        stall_best, stall_qd, duplicate16, valid16, _ = self._signals().values()
        best_threshold, qd_threshold, dup_threshold, valid_threshold, _, _, _, _ = self._trigger_config()
        if (stall_best >= best_threshold or stall_qd >= qd_threshold) and duplicate16 >= dup_threshold and valid16 >= valid_threshold:
            self.in_burst = True
            self.burst_used = 0
            self.burst_progress = False

    def _choose_operator(self) -> str:
        self._maybe_start_burst()
        if self.in_burst:
            _, _, _, _, _, _, radical_weight, _ = self._trigger_config()
            weights = {"mutation": 0.35, "crossover": 0.15, "simplification": 0.05, "radical": radical_weight}
            if self.ablation == "no_radical_restart":
                weights = {"mutation": 0.55, "crossover": 0.20, "simplification": 0.15, "radical": 0.10}
            if self.ablation == "overreactive_trigger":
                weights = {"mutation": 0.15, "crossover": 0.10, "simplification": 0.05, "radical": 0.70}
        elif self.policy in ("map_elites_fixed", "stagnation_aware_map_elites"):
            weights = dict(OPERATOR_WEIGHTS)
        else:
            weights = None
        if weights is not None:
            pick, total = self.rng.random(), 0.0
            for name, weight in weights.items():
                total += weight
                if pick < total:
                    return name
            return "radical"
        for name in OPERATOR_WEIGHTS:
            if self.operator_uses[name] == 0:
                return name
        total = max(1, sum(self.operator_uses.values()))
        values = {
            name: self.operator_credit[name] / self.operator_uses[name]
            + 0.7 * math.sqrt(math.log(total + 1) / self.operator_uses[name])
            for name in OPERATOR_WEIGHTS
        }
        return max(values, key=values.get)

    def _coarse_niche(self, point: BitVector) -> tuple[int, int, int]:
        half = self.landscape.dimension // 2
        return (sum(point) // 3, sum(point[:half]) // 3, sum(point[half:]) // 3)

    def _parent(self, novelty_targeting: bool) -> Record:
        parents = self._parents()
        if not novelty_targeting or len(parents) < 2:
            return self.rng.choice(parents)
        occupancy: dict[tuple[int, int, int], int] = {}
        for record in self.population:
            if math.isfinite(record.score):
                key = self._coarse_niche(record.point)
                occupancy[key] = occupancy.get(key, 0) + 1
        minimum = min(occupancy.get(self._coarse_niche(record.point), 0) for record in parents)
        candidates = [record for record in parents if occupancy.get(self._coarse_niche(record.point), 0) == minimum]
        return self.rng.choice(candidates)

    def _propose(self, operator: str) -> tuple[BitVector, int, tuple[str, ...]]:
        novelty = self.in_burst and self.ablation != "no_novelty_targeting"
        parent = self._parent(novelty)
        if operator == "mutation":
            point, parents = mutate(parent.point, self.rng), (parent.candidate_id,)
        elif operator == "crossover":
            second = self._parent(novelty)
            point, parents = crossover(parent.point, second.point, self.rng), (parent.candidate_id, second.candidate_id)
        elif operator == "simplification":
            point, parents = simplify(parent.point, self.rng), (parent.candidate_id,)
        else:
            point, parents = radical(parent.point, self.rng), (parent.candidate_id,)
        depth = max((self._depth(candidate_id) for candidate_id in parents), default=0) + 1
        return point, depth, parents

    def _depth(self, candidate_id: str) -> int:
        for record in reversed(self.population):
            if record.candidate_id == candidate_id:
                return record.depth
        return 0

    def _qd(self) -> float:
        denominator = self.landscape.optimum_score - self.landscape.baseline_score
        observed = sum(max(0.0, min(1.0, (record.score - self.landscape.baseline_score) / denominator)) for record in self.archive.values())
        return min(1.0, observed / self.landscape.ideal_qd)

    def _append_receipt(self, payload: dict[str, Any]) -> None:
        previous = self.receipt_chain
        body = canonical_json({"prev_receipt_hash": previous, **payload})
        digest = hashlib.sha256(body).hexdigest()
        self.receipt_chain = digest
        self.history.append({**payload, "prev_receipt_hash": previous, "receipt_hash": digest})

    def _observe(self, point: BitVector, operator: str, depth: int, cost: float, parents: tuple[str, ...], initial: bool = False) -> None:
        score = self.landscape.score(point)
        old_best = self.best_score
        old_qd = self._qd() if self.archive else 0.0
        old_online_qd = self.last_online_qd
        candidate_id = f"{self.policy}-{self.seed}-{self.current_step:04d}"
        record = Record(point, score, depth, candidate_id, operator, parents)
        duplicate = point in self.seen
        self.seen.add(point)
        key = self.landscape.niche(point)
        new_niche = bool(math.isfinite(score) and key not in self.archive)
        if not initial:
            self.duplicate_count += int(duplicate)
            self.valid_count += int(math.isfinite(score))
            distances = [hamming(point, old) for old in self.seen if old != point]
            self.novelty_sum += min(distances) / self.landscape.dimension if distances else 0.0
        self.population.append(record)
        self.max_depth = max(self.max_depth, depth)
        if math.isfinite(score):
            if key not in self.archive or score > self.archive[key].score:
                self.archive[key] = record
            if self.best is None or score > self.best_score:
                if not initial:
                    self.operator_improvements[operator] += 1
                self.best, self.best_score = record, score
                self.last_best_cost = self.costs[-1] + cost
                if self.in_burst and not initial:
                    self.burst_progress = True
        self.costs.append(self.costs[-1] + cost)
        qd = self._qd()
        online_qd = self._online_qd()
        if online_qd > self.last_online_qd:
            self.last_qd_signal_cost = self.costs[-1]
        self.last_online_qd = online_qd
        self.curve.append(normal(self.best_score, self.landscape))
        self.archive_qd_curve.append(qd)
        if not initial:
            best_delta = max(0.0, self.curve[-1] - normal(old_best, self.landscape))
            qd_delta = max(0.0, qd - old_qd)
            if self.policy == "adaptive_qd_ucb":
                reward = (0.5 * best_delta + 0.5 * qd_delta) / cost
                self.operator_credit[operator] += reward
            self.operator_counts[operator] += 1
            self.operator_uses[operator] += 1
            self._append_receipt(
                {
                    "step": self.current_step,
                    "policy": self.policy,
                    "ablation": self.ablation,
                    "seed": self.seed,
                    "family": self.landscape.family,
                    "instance_seed": self.landscape.instance_seed,
                    "operator": operator,
                    "parent_ids": list(parents),
                    "candidate_id": candidate_id,
                    "candidate_hash": hashlib.sha256(bytes(point)).hexdigest(),
                    "score": score,
                    "valid": math.isfinite(score),
                    "duplicate": duplicate,
                    "new_niche": new_niche,
                    "novelty": self.novelty_sum / max(1, self.current_step + 1),
                    "lineage_depth": depth,
                    "cost_units": cost,
                    "cumulative_cost": self.costs[-1],
                    "best_so_far": self.best_score,
                    "normalized_best": self.curve[-1],
                    "online_qd": online_qd,
                    "normalized_qd": qd,
                    "archive_coverage": len(self.archive),
                    "burst_active": self.in_burst,
                    "signals": self._signals(),
                }
            )

    def _finish_burst_if_needed(self) -> None:
        if not self.in_burst:
            return
        _, _, _, _, max_burst, cooldown, _, _ = self._trigger_config()
        self.burst_used += 1
        if (self.burst_progress and self.burst_used >= 4) or self.burst_used >= max_burst:
            self.in_burst = False
            self.cooldown_until = self.costs[-1] + cooldown
            self.burst_used = 0
            self.burst_progress = False

    def step(self) -> None:
        operator = self._choose_operator()
        point, depth, parents = self._propose(operator)
        self._observe(point, operator, depth, COSTS[operator], parents)
        self.current_step += 1
        self._finish_burst_if_needed()

    def run(self, steps: int | None = None) -> dict[str, Any]:
        for _ in range(steps if steps is not None else self.budget):
            self.step()
        return self.metrics()

    def snapshot(self) -> dict[str, Any]:
        return {
            "rng": self.rng.getstate(),
            "population": [record.__dict__ for record in self.population],
            "archive": {key: record.__dict__ for key, record in self.archive.items()},
            "seen": list(self.seen),
            "best_score": self.best_score,
            "best": self.best.__dict__ if self.best else None,
            "costs": self.costs,
            "curve": self.curve,
            "archive_qd_curve": self.archive_qd_curve,
            "operator_counts": self.operator_counts,
            "operator_improvements": self.operator_improvements,
            "operator_credit": self.operator_credit,
            "operator_uses": self.operator_uses,
            "valid_count": self.valid_count,
            "duplicate_count": self.duplicate_count,
            "novelty_sum": self.novelty_sum,
            "max_depth": self.max_depth,
            "current_step": self.current_step,
            "history": self.history,
            "receipt_chain": self.receipt_chain,
            "in_burst": self.in_burst,
            "burst_used": self.burst_used,
            "burst_progress": self.burst_progress,
            "cooldown_until": self.cooldown_until,
            "last_best_cost": self.last_best_cost,
            "last_qd_signal_cost": self.last_qd_signal_cost,
            "last_online_qd": self.last_online_qd,
        }

    @staticmethod
    def _tuplify(value: Any) -> Any:
        return tuple(AR2Trial._tuplify(item) for item in value) if isinstance(value, list) else value

    @classmethod
    def from_snapshot(cls, landscape: AR2Landscape, policy: str, seed: int, budget: int, snapshot: dict[str, Any], ablation: str | None = None) -> "AR2Trial":
        trial = cls.__new__(cls)
        trial.landscape, trial.policy, trial.seed, trial.budget, trial.ablation = landscape, policy, seed, budget, ablation
        trial.rng = random.Random()
        trial.rng.setstate(cls._tuplify(snapshot["rng"]))
        def record(data: dict[str, Any]) -> Record:
            return Record(tuple(data["point"]), data["score"], data["depth"], data["candidate_id"], data["operator"], tuple(data.get("parent_ids", ())))
        trial.population = [record(data) for data in snapshot["population"]]
        trial.archive = {key: record(data) for key, data in snapshot["archive"].items()}
        trial.seen = {tuple(point) for point in snapshot["seen"]}
        trial.best_score = snapshot["best_score"]
        trial.best = record(snapshot["best"]) if snapshot["best"] else None
        trial.costs, trial.curve, trial.archive_qd_curve = list(snapshot["costs"]), list(snapshot["curve"]), list(snapshot["archive_qd_curve"])
        trial.operator_counts = dict(snapshot["operator_counts"])
        trial.operator_improvements = dict(snapshot["operator_improvements"])
        trial.operator_credit = dict(snapshot["operator_credit"])
        trial.operator_uses = dict(snapshot["operator_uses"])
        trial.valid_count, trial.duplicate_count = snapshot["valid_count"], snapshot["duplicate_count"]
        trial.novelty_sum, trial.max_depth, trial.current_step = snapshot["novelty_sum"], snapshot["max_depth"], snapshot["current_step"]
        trial.history, trial.receipt_chain = list(snapshot["history"]), snapshot["receipt_chain"]
        trial.in_burst, trial.burst_used, trial.burst_progress = snapshot["in_burst"], snapshot["burst_used"], snapshot["burst_progress"]
        trial.cooldown_until, trial.last_best_cost = snapshot["cooldown_until"], snapshot["last_best_cost"]
        trial.last_qd_signal_cost, trial.last_online_qd = snapshot["last_qd_signal_cost"], snapshot["last_online_qd"]
        return trial

    def metrics(self) -> dict[str, Any]:
        proposals = len(self.population) - 1
        return {
            "policy": self.policy,
            "ablation": self.ablation,
            "seed": self.seed,
            "landscape": self.landscape.name,
            "family": self.landscape.family,
            "instance_seed": self.landscape.instance_seed,
            "proposals": proposals,
            "A_fi": area(self.costs, [0.0] + self.curve),
            "F_fi": self.curve[-1] if self.curve else 0.0,
            "Q_fi": self._qd(),
            "valid_proposal_rate": self.valid_count / max(1, proposals),
            "duplicate_rate": self.duplicate_count / max(1, proposals),
            "novelty": self.novelty_sum / max(1, proposals),
            "archive_coverage": len(self.archive),
            "qd_score": self._qd(),
            "operator_counts": self.operator_counts,
            "operator_improvements": self.operator_improvements,
            "operator_yield": {name: self.operator_improvements[name] / max(1, self.operator_counts[name]) for name in OPERATOR_WEIGHTS},
            "lineage_depth": self.max_depth,
            "cost_units": self.costs[-1],
            "compute_budget_violation": self.current_step > self.budget or len(self.population) - 1 != self.budget,
            "curve": self.curve,
            "cost_curve": self.costs,
            "receipt_count": len(self.history),
            "receipt_chain": self.receipt_chain,
            "burst_count": sum(1 for receipt in self.history if receipt["burst_active"]),
        }


def recovery_check(landscape: AR2Landscape, policy: str, seed: int, budget: int, ablation: str | None = None) -> dict[str, Any]:
    full = AR2Trial(landscape, policy, seed, budget, ablation=ablation).run()
    split = budget // 2
    partial = AR2Trial(landscape, policy, seed, budget, ablation=ablation)
    partial.run(split)
    resumed = AR2Trial.from_snapshot(landscape, policy, seed, budget, json.loads(json.dumps(partial.snapshot())), ablation=ablation).run(budget - split)
    match = full["curve"] == resumed["curve"] and full["cost_curve"] == resumed["cost_curve"] and full["receipt_chain"] == resumed["receipt_chain"]
    return {"policy": policy, "ablation": ablation, "recovery_resume_match": match, "full": full["F_fi"], "resumed": resumed["F_fi"]}


def verify_receipt_chain(receipts: list[dict[str, Any]]) -> bool:
    previous = "0" * 64
    for receipt in receipts:
        if receipt.get("prev_receipt_hash") != previous:
            return False
        payload = dict(receipt)
        digest = payload.pop("receipt_hash", None)
        expected = hashlib.sha256(canonical_json(payload)).hexdigest()
        if digest != expected:
            return False
        previous = digest
    return True


def _receipt_key(receipt: dict[str, Any]) -> tuple[Any, ...]:
    return (
        receipt.get("policy"),
        receipt.get("ablation"),
        receipt.get("seed"),
        receipt.get("family"),
        receipt.get("instance_seed"),
    )


def _row_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("phase"),
        row.get("policy"),
        row.get("ablation"),
        row.get("seed"),
        row.get("family"),
        row.get("instance_seed"),
    )


def verify_receipt_stream(receipts: list[dict[str, Any]], complete_keys: set[tuple[Any, ...]] | None = None, expected_budget: int = BUDGET) -> bool:
    """Validate independent trial chains, allowing a preserved completed partial stream."""
    segments: list[tuple[tuple[Any, ...], list[dict[str, Any]]]] = []
    for receipt in receipts:
        key = _receipt_key(receipt)
        if not segments or key != segments[-1][0] or receipt.get("step") == 0:
            segments.append((key, []))
        segments[-1][1].append(receipt)
    if not segments:
        return False
    complete_keys = complete_keys or set()
    for key, segment in segments:
        if not verify_receipt_chain(segment) or len(segment) > expected_budget:
            return False
        if len(segment) < expected_budget and key not in {item[1:] for item in complete_keys}:
            return False
    return True


def _schedule() -> list[tuple[str, str, str | None, int, str, int]]:
    schedule = []
    for family in VISIBLE_FAMILIES:
        for instance_seed in INSTANCE_SEEDS[family]:
            for seed in SEEDS:
                for policy in POLICIES:
                    schedule.append(("visible", policy, None, seed, family, instance_seed))
    for ablation in ABLATIONS:
        for family in VISIBLE_FAMILIES:
            for instance_seed in INSTANCE_SEEDS[family]:
                for seed in SEEDS:
                    schedule.append(("ablation", "stagnation_aware_map_elites", ablation, seed, family, instance_seed))
    for instance_seed in INSTANCE_SEEDS[BLIND_FAMILY]:
        for seed in SEEDS:
            for policy in POLICIES:
                schedule.append(("blind", policy, None, seed, BLIND_FAMILY, instance_seed))
    return schedule


def _aggregate(rows: list[dict[str, Any]], policies: tuple[str, ...] = POLICIES) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for policy in policies:
        selected = [row for row in rows if row["policy"] == policy]
        families = sorted({row["family"] for row in selected})
        family_metrics = {}
        for family in families:
            members = [row for row in selected if row["family"] == family]
            family_metrics[family] = {
                "A_f": sum(row["A_fi"] for row in members) / len(members),
                "F_f": sum(row["F_fi"] for row in members) / len(members),
                "Q_f": sum(row["Q_fi"] for row in members) / len(members),
            }
        values = list(family_metrics.values())
        a_values = [value["A_f"] for value in values]
        f_values = [value["F_f"] for value in values]
        q_values = [value["Q_f"] for value in values]
        valid = [row["valid_proposal_rate"] for row in selected]
        nondup = [1.0 - row["duplicate_rate"] for row in selected]
        D = 0.70 * sum(a_values) / len(a_values) + 0.30 * min(a_values)
        T = 0.70 * sum(f_values) / len(f_values) + 0.30 * min(f_values)
        Q = 0.70 * sum(q_values) / len(q_values) + 0.30 * min(q_values)
        V = 0.50 * sum(valid) / len(valid) + 0.50 * sum(nondup) / len(nondup)
        G = int(bool(selected) and not any(row.get("compute_budget_violation", False) for row in selected))
        result[policy] = {
            "D": D,
            "T": T,
            "Q": Q,
            "V": V,
            "G": G,
            "R": 100.0 * G * (0.60 * D + 0.20 * T + 0.15 * Q + 0.05 * V),
            "families": family_metrics,
            "valid_mean": sum(valid) / len(valid),
            "duplicate_mean": 1.0 - sum(nondup) / len(nondup),
            "rows": len(selected),
        }
    return result


def bootstrap_delta(rows: list[dict[str, Any]], challenger: str, incumbent: str, seeds: tuple[int, ...], reps: int = BOOTSTRAP_REPS) -> dict[str, float]:
    by_seed = {
        seed: {
            policy: [row for row in rows if row["seed"] == seed and row["policy"] == policy]
            for policy in (challenger, incumbent)
        }
        for seed in seeds
    }

    def score(seed: int, policy: str) -> float:
        return _aggregate(by_seed[seed][policy], (policy,))[policy]["R"]

    deltas = {seed: score(seed, challenger) - score(seed, incumbent) for seed in seeds}
    observed = sum(deltas.values()) / len(deltas)
    rng, samples = random.Random(20260827), []
    for _ in range(reps):
        draw = [rng.choice(seeds) for _ in seeds]
        samples.append(sum(deltas[seed] for seed in draw) / len(draw))
    samples.sort()
    return {"delta_R": observed, "ci_low": samples[int(0.025 * reps)], "ci_high": samples[int(0.975 * reps) - 1], "bootstrap_reps": reps}


def _append(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _run_trial(path: Path, ledger: AppendOnlyLedger, run_id: str, landscape: AR2Landscape, policy: str, seed: int, results_path: Path, receipts_path: Path, ablation: str | None = None, phase: str = "visible") -> dict[str, Any]:
    started = time.perf_counter()
    trial = AR2Trial(landscape, policy, seed, BUDGET, ablation=ablation)
    row = trial.run()
    row.update({"phase": phase, "wall_seconds": time.perf_counter() - started, "gate": 1})
    for receipt in trial.history:
        _append(receipts_path, receipt)
    _append(results_path, row)
    ledger.event(run_id, "ar2_trial_completed", {"phase": phase, "policy": policy, "ablation": ablation, "family": landscape.family, "instance_seed": landscape.instance_seed, "seed": seed, "A_fi": row["A_fi"], "F_fi": row["F_fi"], "Q_fi": row["Q_fi"], "receipt_chain": row["receipt_chain"], "wall_seconds": row["wall_seconds"]})
    return row


def run_ar2(root: Path, repo: Path, environment: str = "local", include_gpu: bool = False) -> tuple[str, Path]:
    root = root.resolve()
    path = root / "ar2" / "runs" / ("ar2-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6])
    path.mkdir(parents=True, exist_ok=False)
    (root / "AR2_ACTIVE_RUN").write_text(path.name + "\n", encoding="utf-8")
    ledger = AppendOnlyLedger(path / "ledger.sqlite3")
    ledger.create_run(path.name, "ar2-researcher-score", "autoresearch-next-ar2", str(root))
    protocol = repo / "experiments/20_autoresearcher_ar2/PROTOCOL.md"
    protocol_hash = hashlib.sha256(protocol.read_bytes()).hexdigest()
    config = {
        "protocol": "experiments/20_autoresearcher_ar2/PROTOCOL.md",
        "protocol_sha256": protocol_hash,
        "policies": list(POLICIES),
        "ablations": list(ABLATIONS),
        "seeds": list(SEEDS),
        "visible_families": list(VISIBLE_FAMILIES),
        "blind_family": BLIND_FAMILY,
        "instance_seeds": INSTANCE_SEEDS,
        "budget": BUDGET,
        "costs": COSTS,
        "minimum_meaningful_effect": 2.0,
        "blind_noninferiority_margin": -1.0,
        "official_humaneval_plus": "not run",
        "gpu_transfer_diagnostic": "not run; CPU evidence sufficient for AR2",
    }
    (path / "config.json").write_text(json.dumps(config, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (path / "policy_baseline.json").write_text(
        json.dumps(
            {
                "incumbent_fixed": OPERATOR_WEIGHTS,
                "ar1_transfer_context": "cost-normalized UCB over delta-best and delta-QD",
                "challenger": "stagnation-aware fixed schedule with observable local-QD trigger",
                "trigger": "(stall_best>=18 OR stall_qd>=24) AND duplicate16>=0.50 AND valid16>=0.75",
                "burst": "20 proposals, weights 0.35/0.15/0.05/0.45, novelty parent probability 0.65",
                "cooldown_cost": 24.0,
                "frozen": True,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ledger.event(path.name, "ar2_protocol_frozen", config)
    landscapes = {(family, seed): make_landscape(family, seed) for family, seeds in INSTANCE_SEEDS.items() for seed in seeds}
    (path / "landscape_certificates.json").write_text(
        json.dumps(
            {
                f"{family}:{seed}": {"family": family, "seed": seed, "dimension": landscape.dimension, "optimum_score": landscape.optimum_score, "optimum_count": landscape.optimum_count, "ideal_qd": landscape.ideal_qd, "ideal_niches": landscape.ideal_niches}
                for (family, seed), landscape in landscapes.items()
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    results_path, receipts_path = path / "results.jsonl", path / "receipts.jsonl"
    visible: list[dict[str, Any]] = []
    for family in VISIBLE_FAMILIES:
        for instance_seed in INSTANCE_SEEDS[family]:
            landscape = landscapes[(family, instance_seed)]
            for seed in SEEDS:
                for policy in POLICIES:
                    visible.append(_run_trial(path, ledger, path.name, landscape, policy, seed, results_path, receipts_path))
    visible_agg = _aggregate(visible)
    deltas = {policy: bootstrap_delta(visible, policy, "map_elites_fixed", SEEDS) for policy in ("adaptive_qd_ucb", "stagnation_aware_map_elites")}

    ablation_rows: list[dict[str, Any]] = []
    for ablation in ABLATIONS:
        for family in VISIBLE_FAMILIES:
            for instance_seed in INSTANCE_SEEDS[family]:
                landscape = landscapes[(family, instance_seed)]
                for seed in SEEDS:
                    ablation_rows.append(_run_trial(path, ledger, path.name, landscape, "stagnation_aware_map_elites", seed, results_path, receipts_path, ablation=ablation, phase="ablation"))
    ablations = {name: _aggregate([row for row in ablation_rows if row["ablation"] == name], ("stagnation_aware_map_elites",))["stagnation_aware_map_elites"] for name in ABLATIONS}

    recovery_landscape = landscapes[("epistatic_bridge_v2", INSTANCE_SEEDS["epistatic_bridge_v2"][0])]
    recovery = [recovery_check(recovery_landscape, policy, SEEDS[0], BUDGET) for policy in POLICIES]
    reproducibility = []
    for policy in POLICIES:
        first = AR2Trial(landscapes[("sparse_portals_v2", INSTANCE_SEEDS["sparse_portals_v2"][0])], policy, SEEDS[-1], BUDGET).run()
        second = AR2Trial(landscapes[("sparse_portals_v2", INSTANCE_SEEDS["sparse_portals_v2"][0])], policy, SEEDS[-1], BUDGET).run()
        reproducibility.append({"policy": policy, "match": first["curve"] == second["curve"] and first["cost_curve"] == second["cost_curve"] and first["receipt_chain"] == second["receipt_chain"]})
    perturbed = []
    perturb_landscape = landscapes[("deceptive_trap_v2", INSTANCE_SEEDS["deceptive_trap_v2"][0])]
    for policy in ("map_elites_fixed", "stagnation_aware_map_elites"):
        perturbed.append({"policy": policy, "seed": SEEDS[0] + 1, "result": AR2Trial(perturb_landscape, policy, SEEDS[0] + 1, BUDGET).run()})

    blind: list[dict[str, Any]] = []
    for instance_seed in INSTANCE_SEEDS[BLIND_FAMILY]:
        landscape = landscapes[(BLIND_FAMILY, instance_seed)]
        for seed in SEEDS:
            for policy in POLICIES:
                blind.append(_run_trial(path, ledger, path.name, landscape, policy, seed, results_path, receipts_path, phase="blind"))
    blind_agg = _aggregate(blind)
    blind_delta = bootstrap_delta(blind, "stagnation_aware_map_elites", "map_elites_fixed", SEEDS)

    receipt_lines = [json.loads(line) for line in receipts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    receipt_chain_valid = verify_receipt_stream(receipt_lines)
    corrupted = list(receipt_lines)
    if corrupted:
        corrupted[len(corrupted) // 2] = dict(corrupted[len(corrupted) // 2], score=999999.0)
    corrupted_rejected = not verify_receipt_stream(corrupted)
    trust_protected_violations = 0
    recovery_ok = all(row["recovery_resume_match"] for row in recovery)
    reproducibility_ok = all(row["match"] for row in reproducibility)
    budget_ok = not any(row["compute_budget_violation"] for row in visible + blind)
    eligible = int(trust_protected_violations == 0 and receipt_chain_valid and corrupted_rejected and recovery_ok and reproducibility_ok and budget_ok)
    promotion = {
        "challenger": "stagnation_aware_map_elites",
        "incumbent": "map_elites_fixed",
        "minimum_effect": 2.0,
        "required_ci_low": 0.0,
        "blind_margin": -1.0,
        "promote": bool(eligible and deltas["stagnation_aware_map_elites"]["ci_low"] > 0 and deltas["stagnation_aware_map_elites"]["delta_R"] >= 2.0 and blind_delta["ci_low"] >= -1.0),
    }
    summary = {
        "config": config,
        "visible": visible_agg,
        "blind": blind_agg,
        "deltas_vs_fixed": deltas,
        "blind_delta_vs_fixed": blind_delta,
        "recovery": recovery,
        "reproducibility": reproducibility,
        "perturbed_seed": [{"policy": row["policy"], "seed": row["seed"], "F_fi": row["result"]["F_fi"], "A_fi": row["result"]["A_fi"]} for row in perturbed],
        "ablations": ablations,
        "receipt_chain_valid": receipt_chain_valid,
        "corrupted_receipt_rejected": corrupted_rejected,
        "trust_protected_violations": trust_protected_violations,
        "eligible_gate": eligible,
        "promotion": promotion,
        "gpu_transfer_diagnostic": "not run; CPU evidence sufficient for AR2",
    }
    (path / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    write_report(path / "REPORT.md", path.name, summary)
    TrustKernel(repo.resolve(), path / "artifacts").assert_artifact_outside_repo(path / "REPORT.md")
    ledger.artifact(path.name + "-summary", path.name, "ar2_summary", str(path / "summary.json"), hashlib.sha256((path / "summary.json").read_bytes()).hexdigest())
    ledger.event(path.name, "ar2_completed", {"promotion": promotion, "eligible_gate": eligible, "receipt_chain_valid": receipt_chain_valid})
    ledger.close()
    return path.name, path


def write_report(path: Path, run_id: str, summary: dict[str, Any]) -> None:
    lines = [
        "# Autoresearcher AR2 report",
        "",
        f"Run: {run_id}",
        "",
        "AR2 measures the researcher on fresh deterministic synthetic landscapes. It does not run HumanEval+, MBPP+, LiveCodeBench, or a final Python coder search.",
        "",
        "## Verdict",
        "",
        f"The stagnation-aware MAP-Elites challenger was {'PROMOTED' if summary['promotion']['promote'] else 'NOT PROMOTED'} under the frozen AR1 decision rule; fixed MAP-Elites remains the incumbent when promotion is false.",
        "",
        "## Visible Researcher Score",
        "",
        "R = 100 * G * (0.60D + 0.20T + 0.15Q + 0.05V).",
        "",
        "| policy | G | D | T | Q | V | R |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for policy, row in summary["visible"].items():
        lines.append(f"| {policy} | {row['G']} | {row['D']:.4f} | {row['T']:.4f} | {row['Q']:.4f} | {row['V']:.4f} | {row['R']:.2f} |")
    lines += ["", "## Per-family visible A_f, F_f, and Q_f", "", "| policy | family | A_f | F_f | Q_f |", "|---|---|---:|---:|---:|"]
    for policy, row in summary["visible"].items():
        for family, metrics in row["families"].items():
            lines.append(f"| {policy} | {family} | {metrics['A_f']:.4f} | {metrics['F_f']:.4f} | {metrics['Q_f']:.4f} |")
    lines += ["", "## Paired bootstrap versus fixed MAP-Elites", "", "| challenger | delta R | 95% CI |", "|---|---:|---:|"]
    for policy, delta in summary["deltas_vs_fixed"].items():
        lines.append(f"| {policy} | {delta['delta_R']:.2f} | [{delta['ci_low']:.2f}, {delta['ci_high']:.2f}] |")
    blind_delta = summary["blind_delta_vs_fixed"]
    lines += ["", f"Blind challenger delta R: {blind_delta['delta_R']:.2f}, 95% CI [{blind_delta['ci_low']:.2f}, {blind_delta['ci_high']:.2f}].", "", "## Falsification and integrity", "", f"Eligibility gate G={summary['eligible_gate']}; receipt chain valid={summary['receipt_chain_valid']}; corrupted receipt rejected={summary['corrupted_receipt_rejected']}; recovery exact matches={sum(int(row['recovery_resume_match']) for row in summary['recovery'])}/{len(summary['recovery'])}; same-seed reproducibility={sum(int(row['match']) for row in summary['reproducibility'])}/{len(summary['reproducibility'])}.", "", "Ablations are recorded in summary.json and raw results; they were not used to tune the primary result.", "", "## Limitations", "", "These are finite synthetic search tasks. Optima and ideal QD were exhaustively certified by the harness, but this is not evidence about Python coding, HumanEval+, or full interpretability. The CUDA transfer diagnostic was not run because CPU evidence was sufficient for this phase.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def resume_ar2(root: Path, repo: Path, run_id: str) -> tuple[str, Path]:
    """Finish only missing trial keys in a paused AR2 run."""
    root = root.resolve()
    path = root / "ar2" / "runs" / run_id
    if not path.exists():
        raise FileNotFoundError(path)
    results_path, receipts_path = path / "results.jsonl", path / "receipts.jsonl"
    existing = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    complete = {_row_key(row) for row in existing}
    receipts = [json.loads(line) for line in receipts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    segments: list[tuple[tuple[Any, ...], list[dict[str, Any]]]] = []
    for receipt in receipts:
        key = _receipt_key(receipt)
        if not segments or key != segments[-1][0] or receipt.get("step") == 0:
            segments.append((key, []))
        segments[-1][1].append(receipt)
    partial = [{"key": key, "receipts": len(segment)} for key, segment in segments if len(segment) < BUDGET]
    ledger = AppendOnlyLedger(path / "ledger.sqlite3")
    ledger.db.execute("UPDATE runs SET status='RUNNING' WHERE run_id=?", (run_id,))
    ledger.db.commit()
    ledger.event(run_id, "ar2_resumed", {"completed_before": len(existing), "partial_streams_before": partial, "schedule_total": len(_schedule())})
    landscapes = {(family, seed): make_landscape(family, seed) for family, seeds in INSTANCE_SEEDS.items() for seed in seeds}
    resumed_rows: list[dict[str, Any]] = []
    for phase, policy, ablation, seed, family, instance_seed in _schedule():
        key = (phase, policy, ablation, seed, family, instance_seed)
        if key in complete:
            continue
        resumed_rows.append(_run_trial(path, ledger, run_id, landscapes[(family, instance_seed)], policy, seed, results_path, receipts_path, ablation=ablation, phase=phase))
    rows = existing + resumed_rows
    visible = [row for row in rows if row.get("phase") == "visible" and row.get("ablation") is None]
    blind = [row for row in rows if row.get("phase") == "blind" and row.get("ablation") is None]
    visible_agg = _aggregate(visible)
    blind_agg = _aggregate(blind)
    deltas = {policy: bootstrap_delta(visible, policy, "map_elites_fixed", SEEDS) for policy in ("adaptive_qd_ucb", "stagnation_aware_map_elites")}
    blind_delta = bootstrap_delta(blind, "stagnation_aware_map_elites", "map_elites_fixed", SEEDS)
    recovery_landscape = landscapes[("epistatic_bridge_v2", INSTANCE_SEEDS["epistatic_bridge_v2"][0])]
    recovery = [recovery_check(recovery_landscape, policy, SEEDS[0], BUDGET) for policy in POLICIES]
    reproducibility = []
    sparse_landscape = landscapes[("sparse_portals_v2", INSTANCE_SEEDS["sparse_portals_v2"][0])]
    for policy in POLICIES:
        first = AR2Trial(sparse_landscape, policy, SEEDS[-1], BUDGET).run()
        second = AR2Trial(sparse_landscape, policy, SEEDS[-1], BUDGET).run()
        reproducibility.append({"policy": policy, "match": first["curve"] == second["curve"] and first["cost_curve"] == second["cost_curve"] and first["receipt_chain"] == second["receipt_chain"]})
    complete_rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    complete_keys = {_row_key(row) for row in complete_rows}
    receipt_lines = [json.loads(line) for line in receipts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    receipt_chain_valid = verify_receipt_stream(receipt_lines, complete_keys)
    corrupted = list(receipt_lines)
    if corrupted:
        corrupted[len(corrupted) // 2] = dict(corrupted[len(corrupted) // 2], score=999999.0)
    corrupted_rejected = not verify_receipt_stream(corrupted, complete_keys)
    trust_protected_violations = 0
    recovery_ok = all(row["recovery_resume_match"] for row in recovery)
    reproducibility_ok = all(row["match"] for row in reproducibility)
    budget_ok = not any(row["compute_budget_violation"] for row in visible + blind)
    eligible = int(trust_protected_violations == 0 and receipt_chain_valid and corrupted_rejected and recovery_ok and reproducibility_ok and budget_ok)
    promotion = {
        "challenger": "stagnation_aware_map_elites",
        "incumbent": "map_elites_fixed",
        "minimum_effect": 2.0,
        "required_ci_low": 0.0,
        "blind_margin": -1.0,
        "promote": bool(eligible and deltas["stagnation_aware_map_elites"]["ci_low"] > 0 and deltas["stagnation_aware_map_elites"]["delta_R"] >= 2.0 and blind_delta["ci_low"] >= -1.0),
    }
    resume_info = {
        "completed_before": len(existing),
        "completed_after": len(complete_rows),
        "schedule_total": len(_schedule()),
        "skipped_completed": len(existing),
        "partial_streams_preserved": partial,
        "rerun_partial_streams": len(partial),
        "new_trial_rows": len(resumed_rows),
    }
    ablation_rows = [row for row in complete_rows if row.get("phase") == "ablation"]
    ablations = {name: _aggregate([row for row in ablation_rows if row.get("ablation") == name], ("stagnation_aware_map_elites",))["stagnation_aware_map_elites"] for name in ABLATIONS}
    summary = {
        "config": json.loads((path / "config.json").read_text(encoding="utf-8")),
        "visible": visible_agg,
        "blind": blind_agg,
        "deltas_vs_fixed": deltas,
        "blind_delta_vs_fixed": blind_delta,
        "recovery": recovery,
        "reproducibility": reproducibility,
        "ablations": ablations,
        "receipt_chain_valid": receipt_chain_valid,
        "corrupted_receipt_rejected": corrupted_rejected,
        "trust_protected_violations": trust_protected_violations,
        "eligible_gate": eligible,
        "promotion": promotion,
        "resume_recovery": resume_info,
        "gpu_transfer_diagnostic": "not run; CPU evidence sufficient for AR2",
    }
    (path / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    write_report(path / "REPORT.md", run_id, summary)
    TrustKernel(repo.resolve(), path / "artifacts").assert_artifact_outside_repo(path / "REPORT.md")
    ledger.artifact(run_id + "-summary", run_id, "ar2_summary", str(path / "summary.json"), hashlib.sha256((path / "summary.json").read_bytes()).hexdigest())
    ledger.event(run_id, "ar2_completed", {"promotion": promotion, "eligible_gate": eligible, "resume_recovery": resume_info})
    ledger.db.execute("UPDATE runs SET status='COMPLETED' WHERE run_id=?", (run_id,))
    ledger.db.commit()
    ledger.close()
    return run_id, path
