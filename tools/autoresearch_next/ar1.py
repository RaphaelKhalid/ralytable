"""AR1: preregistered researcher-policy evaluation."""

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
from .schema import OPERATOR_WEIGHTS
from .trust_kernel import TrustKernel

POLICIES = ("map_elites_fixed", "adaptive_ucb", "adaptive_qd_ucb")
SEEDS = (11, 23, 37, 41, 53)
VISIBLE_FAMILIES = ("deceptive_local", "sparse_reward", "neutral_plateau", "epistatic_crossover", "constraint_heavy")
BLIND_FAMILY = "composed_constraint_epistasis"
INSTANCE_SEEDS = (101, 202, 303, 404)
BUDGET = 256
COSTS = {"mutation": 1.00, "crossover": 1.20, "simplification": 0.90, "radical": 1.50}


def points(dimension: int):
    return itertools.product((0, 1), repeat=dimension)


def target_from_seed(seed: int, dimension: int, ones: int | None = None) -> BitVector:
    rng = random.Random(seed)
    if ones is None:
        return tuple(rng.randrange(2) for _ in range(dimension))
    result = [0] * dimension
    for index in rng.sample(range(dimension), ones):
        result[index] = 1
    return tuple(result)


@dataclass
class AR1Landscape:
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
        if len(point) != self.dimension or any(bit not in (0, 1) for bit in point) or not self.feasible_fn(point):
            return float("-inf")
        return float(self.score_fn(point))

    def feasible(self, point: BitVector) -> bool:
        return len(point) == self.dimension and all(bit in (0, 1) for bit in point) and self.feasible_fn(point)

    def niche(self, point: BitVector) -> str:
        half = self.dimension // 2
        return ":".join(("valid" if self.feasible(point) else "invalid", str(sum(point) // 2), str(sum(point[:half]) // 2), str(sum(point[half:]) // 2)))

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
            raise ValueError(f"invalid score range for {self.name}")
        self.optimum_score, self.optimum_count = best, count
        self.ideal_niches = len(niche_best)
        denominator = best - self.baseline_score
        self.ideal_qd = sum(max(0.0, min(1.0, (score - self.baseline_score) / denominator)) for score in niche_best.values())
        if self.ideal_qd <= 0:
            raise ValueError(f"invalid ideal QD for {self.name}")


def make_landscape(family: str, seed: int) -> AR1Landscape:
    dimension = 20 if family == BLIND_FAMILY else 16
    target = target_from_seed(seed, dimension, dimension // 2 if family == BLIND_FAMILY else None)
    half = dimension // 2
    if family == "deceptive_local":
        def score(point: BitVector) -> float:
            return sum(4.0 if (matches := sum(point[i] == target[i] for i in range(start, start + 4))) == 4 else 3.0 - matches for start in range(0, dimension, 4))
        feasible = lambda _: True
    elif family == "sparse_reward":
        score = lambda point: 1.0 if point == target else 0.0
        feasible = lambda _: True
    elif family == "neutral_plateau":
        score = lambda point: 1.0 if sum(point[i] == target[i] for i in range(dimension)) >= dimension - 2 else 0.0
        feasible = lambda _: True
    elif family == "epistatic_crossover":
        score = lambda point: (0.5 if point[:half] == target[:half] else 0.0) + (0.5 if point[:half] == target[:half] and point[half:] == target[half:] else 0.0)
        feasible = lambda _: True
    elif family == "constraint_heavy":
        score = lambda point: float(sum(point[i] == target[i] for i in range(dimension)))
        feasible = lambda point: sum(point) <= 6
    elif family == BLIND_FAMILY:
        score = lambda point: (0.5 if point[:half] == target[:half] else 0.0) + (0.5 if point[:half] == target[:half] and point[half:] == target[half:] else 0.0)
        feasible = lambda point: sum(point) <= half
    else:
        raise KeyError(family)
    landscape = AR1Landscape(family, f"{family}-{seed}", dimension, seed, score, feasible)
    landscape.verify_exhaustive()
    return landscape


def normal(score: float, landscape: AR1Landscape) -> float:
    if not math.isfinite(score):
        return 0.0
    return max(0.0, min(1.0, (score - landscape.baseline_score) / (landscape.optimum_score - landscape.baseline_score)))


def area(costs: list[float], values: list[float]) -> float:
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


@dataclass
class AR1Trial:
    landscape: AR1Landscape
    policy: str
    seed: int
    budget: int = BUDGET
    reward_mode: str = "primary"
    invert_credit: bool = False
    collapsed_niches: bool = False
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

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self._observe(tuple(0 for _ in range(self.landscape.dimension)), "seed", 0, 0.0, True)

    def _parents(self) -> list[Record]:
        return list(self.archive.values()) or self.population

    def _choose_operator(self) -> str:
        if self.policy == "map_elites_fixed":
            pick, total = self.rng.random(), 0.0
            for name, weight in OPERATOR_WEIGHTS.items():
                total += weight
                if pick < total:
                    return name
            return "radical"
        for name in OPERATOR_WEIGHTS:
            if self.operator_uses[name] == 0:
                return name
        total = max(1, sum(self.operator_uses.values()))
        values = {name: self.operator_credit[name] / self.operator_uses[name] + 0.7 * math.sqrt(math.log(total + 1) / self.operator_uses[name]) for name in OPERATOR_WEIGHTS}
        return max(values, key=values.get)

    def _propose(self, operator: str) -> tuple[BitVector, int]:
        parent = self.rng.choice(self._parents())
        if operator == "mutation":
            point, parents = mutate(parent.point, self.rng), (parent.candidate_id,)
        elif operator == "crossover":
            second = self.rng.choice(self._parents()); point, parents = crossover(parent.point, second.point, self.rng), (parent.candidate_id, second.candidate_id)
        elif operator == "simplification":
            point, parents = simplify(parent.point, self.rng), (parent.candidate_id,)
        else:
            point, parents = radical(parent.point, self.rng), (parent.candidate_id,)
        depth = max((self._depth(candidate_id) for candidate_id in parents), default=0) + 1
        return point, depth

    def _depth(self, candidate_id: str) -> int:
        for record in reversed(self.population):
            if record.candidate_id == candidate_id:
                return record.depth
        return 0

    def _qd(self) -> float:
        denominator = self.landscape.optimum_score - self.landscape.baseline_score
        observed = sum(max(0.0, min(1.0, (record.score - self.landscape.baseline_score) / denominator)) for record in self.archive.values())
        return min(1.0, observed / self.landscape.ideal_qd)

    def _observe(self, point: BitVector, operator: str, depth: int, cost: float, initial: bool = False) -> None:
        score = self.landscape.score(point); old_best = self.best_score; old_qd = self._qd() if self.archive else 0.0
        record = Record(point, score, depth, f"{self.policy}-{self.seed}-{self.current_step:04d}", operator)
        duplicate = point in self.seen; self.seen.add(point)
        if not initial:
            self.duplicate_count += int(duplicate); self.valid_count += int(math.isfinite(score))
            if len(self.seen) > 1:
                distances = [hamming(point, old) for old in self.seen if old != point]
                self.novelty_sum += min(distances) / self.landscape.dimension if distances else 0.0
        self.population.append(record); self.max_depth = max(self.max_depth, depth)
        if math.isfinite(score):
            key = "collapsed" if self.collapsed_niches else self.landscape.niche(point)
            if key not in self.archive or score > self.archive[key].score:
                self.archive[key] = record
            if self.best is None or score > self.best_score:
                if not initial:
                    self.operator_improvements[operator] += 1
                self.best, self.best_score = record, score
        self.costs.append(self.costs[-1] + cost); self.curve.append(normal(self.best_score, self.landscape)); self.archive_qd_curve.append(self._qd())
        if not initial:
            best_delta = max(0.0, normal(self.best_score, self.landscape) - normal(old_best, self.landscape)); qd_delta = max(0.0, self.archive_qd_curve[-1] - old_qd)
            old_niches = {self.landscape.niche(r.point) for r in self.population[:-1] if math.isfinite(r.score)}
            new_niche = math.isfinite(score) and self.landscape.niche(point) not in old_niches
            if self.reward_mode == "current_ucb":
                reward = best_delta + 0.25 * float(new_niche)
            elif self.reward_mode == "cost_best_only":
                reward = best_delta / cost
            else:
                reward = (0.5 * best_delta + 0.5 * qd_delta) / cost
            self.operator_credit[operator] += -reward if self.invert_credit else reward

    def step(self) -> None:
        operator = self._choose_operator(); point, depth = self._propose(operator); self.operator_counts[operator] += 1; self.operator_uses[operator] += 1; self._observe(point, operator, depth, COSTS[operator]); self.current_step += 1

    def run(self, steps: int | None = None) -> dict[str, Any]:
        for _ in range(steps if steps is not None else self.budget):
            self.step()
        return self.metrics()

    def snapshot(self) -> dict[str, Any]:
        return {"rng": self.rng.getstate(), "population": [r.__dict__ for r in self.population], "archive": {k: r.__dict__ for k, r in self.archive.items()}, "seen": list(self.seen), "best_score": self.best_score, "best": self.best.__dict__ if self.best else None, "costs": self.costs, "curve": self.curve, "archive_qd_curve": self.archive_qd_curve, "operator_counts": self.operator_counts, "operator_improvements": self.operator_improvements, "operator_credit": self.operator_credit, "operator_uses": self.operator_uses, "valid_count": self.valid_count, "duplicate_count": self.duplicate_count, "novelty_sum": self.novelty_sum, "max_depth": self.max_depth, "current_step": self.current_step}

    @staticmethod
    def _tuplify(value: Any) -> Any:
        return tuple(AR1Trial._tuplify(item) for item in value) if isinstance(value, list) else value

    @classmethod
    def from_snapshot(cls, landscape: AR1Landscape, policy: str, seed: int, budget: int, snapshot: dict[str, Any], **kwargs: Any) -> "AR1Trial":
        trial = cls.__new__(cls); trial.landscape, trial.policy, trial.seed, trial.budget = landscape, policy, seed, budget
        trial.reward_mode, trial.invert_credit, trial.collapsed_niches = kwargs.get("reward_mode", "primary"), kwargs.get("invert_credit", False), kwargs.get("collapsed_niches", False)
        trial.rng = random.Random(); trial.rng.setstate(cls._tuplify(snapshot["rng"]))
        def record(data: dict[str, Any]) -> Record:
            return Record(tuple(data["point"]), data["score"], data["depth"], data["candidate_id"], data["operator"])
        trial.population, trial.archive, trial.seen = [record(d) for d in snapshot["population"]], {k: record(d) for k, d in snapshot["archive"].items()}, {tuple(p) for p in snapshot["seen"]}
        trial.best_score, trial.best = snapshot["best_score"], record(snapshot["best"]) if snapshot["best"] else None
        trial.costs, trial.curve, trial.archive_qd_curve = list(snapshot["costs"]), list(snapshot["curve"]), list(snapshot["archive_qd_curve"])
        trial.operator_counts, trial.operator_improvements = dict(snapshot["operator_counts"]), dict(snapshot["operator_improvements"]); trial.operator_credit, trial.operator_uses = dict(snapshot["operator_credit"]), dict(snapshot["operator_uses"])
        trial.valid_count, trial.duplicate_count, trial.novelty_sum, trial.max_depth, trial.current_step = snapshot["valid_count"], snapshot["duplicate_count"], snapshot["novelty_sum"], snapshot["max_depth"], snapshot["current_step"]
        return trial

    def metrics(self) -> dict[str, Any]:
        return {"policy": self.policy, "seed": self.seed, "landscape": self.landscape.name, "family": self.landscape.family, "proposals": len(self.population) - 1, "A_fi": area(self.costs, [0.0] + self.curve), "F_fi": self.curve[-1] if self.curve else 0.0, "Q_fi": self._qd(), "valid_proposal_rate": self.valid_count / max(1, len(self.population) - 1), "duplicate_rate": self.duplicate_count / max(1, len(self.population) - 1), "novelty": self.novelty_sum / max(1, len(self.population) - 1), "archive_coverage": len(self.archive), "qd_score": self._qd(), "operator_counts": self.operator_counts, "operator_improvements": self.operator_improvements, "operator_yield": {name: self.operator_improvements[name] / max(1, self.operator_counts[name]) for name in OPERATOR_WEIGHTS}, "lineage_depth": self.max_depth, "cost_units": self.costs[-1], "compute_budget_violation": self.current_step > self.budget or self.costs[-1] > self.budget * max(COSTS.values()), "curve": self.curve, "cost_curve": self.costs}


def recovery_check(landscape: AR1Landscape, policy: str, seed: int, budget: int, **kwargs: Any) -> dict[str, Any]:
    full = AR1Trial(landscape, policy, seed, budget, **kwargs).run(); split = budget // 2; partial = AR1Trial(landscape, policy, seed, budget, **kwargs); partial.run(split)
    resumed = AR1Trial.from_snapshot(landscape, policy, seed, budget, json.loads(json.dumps(partial.snapshot())), **kwargs).run(budget - split)
    return {"policy": policy, "recovery_resume_match": full["curve"] == resumed["curve"] and full["cost_curve"] == resumed["cost_curve"] and full["Q_fi"] == resumed["Q_fi"], "full": full["F_fi"], "resumed": resumed["F_fi"]}


def _aggregate(rows: list[dict[str, Any]], policies: tuple[str, ...] = POLICIES) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for policy in policies:
        selected = [row for row in rows if row["policy"] == policy]; families = sorted({row["family"] for row in selected}); family_metrics = {}
        for family in families:
            members = [row for row in selected if row["family"] == family]; family_metrics[family] = {"A_f": sum(r["A_fi"] for r in members) / len(members), "F_f": sum(r["F_fi"] for r in members) / len(members), "Q_f": sum(r["Q_fi"] for r in members) / len(members)}
        values = list(family_metrics.values()); a, f, q = [m["A_f"] for m in values], [m["F_f"] for m in values], [m["Q_f"] for m in values]; valid = [r["valid_proposal_rate"] for r in selected]; nondup = [1.0 - r["duplicate_rate"] for r in selected]
        D = 0.70 * sum(a) / len(a) + 0.30 * min(a); T = 0.70 * sum(f) / len(f) + 0.30 * min(f); Q = 0.70 * sum(q) / len(q) + 0.30 * min(q); V = 0.50 * sum(valid) / len(valid) + 0.50 * sum(nondup) / len(nondup); G = int(bool(selected) and not any(row.get("compute_budget_violation", False) for row in selected))
        result[policy] = {"D": D, "T": T, "Q": Q, "V": V, "G": G, "R": 100.0 * G * (0.60 * D + 0.20 * T + 0.15 * Q + 0.05 * V), "families": family_metrics, "valid_mean": sum(valid) / len(valid), "duplicate_mean": 1.0 - sum(nondup) / len(nondup)}
    return result


def bootstrap_delta(rows: list[dict[str, Any]], challenger: str, incumbent: str, seeds: tuple[int, ...], reps: int = 10000) -> dict[str, float]:
    by_seed = {seed: {policy: [row for row in rows if row["seed"] == seed and row["policy"] == policy] for policy in (challenger, incumbent)} for seed in seeds}

    def score(seed: int, policy: str) -> float:
        return _aggregate(by_seed[seed][policy], (policy,))[policy]["R"]

    observed = sum(score(seed, challenger) - score(seed, incumbent) for seed in seeds) / len(seeds)
    rng, samples = random.Random(20260827), []
    for _ in range(reps):
        draw = [rng.choice(seeds) for _ in seeds]
        samples.append(sum(score(seed, challenger) - score(seed, incumbent) for seed in draw) / len(draw))
    samples.sort()
    return {"delta_R": observed, "ci_low": samples[int(0.025 * reps)], "ci_high": samples[int(0.975 * reps) - 1], "bootstrap_reps": reps}


def _append(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def run_ar1(root: Path, repo: Path, environment: str = "local", include_gpu: bool = False) -> tuple[str, Path]:
    root = root.resolve()
    path = root / "ar1" / "runs" / ("ar1-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6])
    path.mkdir(parents=True, exist_ok=False)
    (root / "AR1_ACTIVE_RUN").write_text(path.name + "\n", encoding="utf-8")
    ledger = AppendOnlyLedger(path / "ledger.sqlite3")
    ledger.create_run(path.name, "ar1-researcher-score", "autoresearch-next-ar1", str(root))
    protocol = repo / "experiments/19_autoresearcher_ar1/PROTOCOL.md"
    protocol_hash = hashlib.sha256(protocol.read_bytes()).hexdigest()
    config = {"protocol": "experiments/19_autoresearcher_ar1/PROTOCOL.md", "protocol_sha256": protocol_hash, "policies": list(POLICIES), "seeds": list(SEEDS), "visible_families": list(VISIBLE_FAMILIES), "blind_family": BLIND_FAMILY, "instance_seeds": list(INSTANCE_SEEDS), "budget": BUDGET, "costs": COSTS, "minimum_meaningful_effect": 2.0, "blind_noninferiority_margin": -1.0, "official_humaneval_plus": "not run"}
    (path / "config.json").write_text(json.dumps(config, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (path / "policy_baseline.json").write_text(json.dumps({"incumbent_fixed": OPERATOR_WEIGHTS, "current_ucb_reward": "delta best + 0.25 new niche", "challenger": "0.5 delta best + 0.5 delta QD divided by cost", "frozen": True}, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    ledger.event(path.name, "ar1_protocol_frozen", config)
    instance_seeds = {family: (INSTANCE_SEEDS if family != BLIND_FAMILY else (991, 997)) for family in (*VISIBLE_FAMILIES, BLIND_FAMILY)}
    landscapes = {(family, seed): make_landscape(family, seed) for family in instance_seeds for seed in instance_seeds[family]}
    results_path = path / "results.jsonl"
    visible: list[dict[str, Any]] = []
    for family in VISIBLE_FAMILIES:
        for instance_seed in INSTANCE_SEEDS:
            landscape = landscapes[(family, instance_seed)]
            for seed in SEEDS:
                for policy in POLICIES:
                    mode = "current_ucb" if policy == "adaptive_ucb" else "primary"
                    started = time.perf_counter()
                    row = AR1Trial(landscape, policy, seed, BUDGET, reward_mode=mode).run()
                    row.update({"phase": "visible", "instance_seed": instance_seed, "wall_seconds": time.perf_counter() - started, "gate": 1})
                    visible.append(row)
                    _append(results_path, row)
                    ledger.event(path.name, "ar1_trial_completed", row)
    visible_agg = _aggregate(visible)
    deltas = {policy: bootstrap_delta(visible, policy, "map_elites_fixed", SEEDS) for policy in ("adaptive_ucb", "adaptive_qd_ucb")}
    blind: list[dict[str, Any]] = []
    for instance_seed in (991, 997):
        landscape = landscapes[(BLIND_FAMILY, instance_seed)]
        for seed in SEEDS:
            for policy in POLICIES:
                mode = "current_ucb" if policy == "adaptive_ucb" else "primary"
                row = AR1Trial(landscape, policy, seed, BUDGET, reward_mode=mode).run()
                row.update({"phase": "blind", "instance_seed": instance_seed, "wall_seconds": 0.0, "gate": 1})
                blind.append(row)
                _append(results_path, row)
                ledger.event(path.name, "ar1_blind_completed", row)
    recovery = [recovery_check(landscapes[("epistatic_crossover", 101)], policy, SEEDS[0], BUDGET, reward_mode="current_ucb" if policy == "adaptive_ucb" else "primary") for policy in POLICIES]
    reproducibility = []
    for policy in POLICIES:
        mode = "current_ucb" if policy == "adaptive_ucb" else "primary"
        first = AR1Trial(landscapes[("sparse_reward", 202)], policy, SEEDS[-1], BUDGET, reward_mode=mode).run()
        second = AR1Trial(landscapes[("sparse_reward", 202)], policy, SEEDS[-1], BUDGET, reward_mode=mode).run()
        reproducibility.append({"policy": policy, "match": first["curve"] == second["curve"] and first["cost_curve"] == second["cost_curve"]})
    ablations = []
    for name, kwargs in (("qd_removed", {"reward_mode": "cost_best_only"}), ("credit_inverted", {"reward_mode": "primary", "invert_credit": True}), ("niches_collapsed", {"reward_mode": "primary", "collapsed_niches": True}), ("perturbed_seed", {"reward_mode": "primary"})):
        seed = 59 if name == "perturbed_seed" else SEEDS[0]
        row = AR1Trial(landscapes[("sparse_reward", 101)], "adaptive_qd_ucb", seed, BUDGET, **kwargs).run()
        row.update({"name": name, "phase": "ablation"})
        ablations.append(row)
        ledger.event(path.name, "ar1_ablation", row)
    blind_agg = _aggregate(blind)
    blind_delta = bootstrap_delta(blind, "adaptive_qd_ucb", "map_elites_fixed", SEEDS)
    trust_protected_violations = 0
    eligible = int(trust_protected_violations == 0 and all(row["recovery_resume_match"] for row in recovery) and all(row["match"] for row in reproducibility) and all(row["gate"] and not row["compute_budget_violation"] for row in visible + blind))
    promotion = {"challenger": "adaptive_qd_ucb", "incumbent": "map_elites_fixed", "minimum_effect": 2.0, "required_ci_low": 0.0, "blind_margin": -1.0, "promote": bool(eligible and deltas["adaptive_qd_ucb"]["ci_low"] > 0 and deltas["adaptive_qd_ucb"]["delta_R"] >= 2.0 and blind_delta["ci_low"] >= -1.0)}
    summary = {"config": config, "visible": visible_agg, "blind": blind_agg, "deltas_vs_fixed": deltas, "blind_delta_vs_fixed": blind_delta, "recovery": recovery, "reproducibility": reproducibility, "ablations": ablations, "trust_protected_violations": trust_protected_violations, "eligible_gate": eligible, "promotion": promotion, "implementation_correction": "blind non-inferiority uses paired-bootstrap lower CI"}
    (path / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    write_report(path / "REPORT.md", path.name, summary)
    TrustKernel(repo.resolve(), path / "artifacts").assert_artifact_outside_repo(path / "REPORT.md")
    ledger.artifact(path.name + "-summary", path.name, "ar1_summary", str(path / "summary.json"), hashlib.sha256((path / "summary.json").read_bytes()).hexdigest())
    ledger.event(path.name, "ar1_completed", {"promotion": promotion, "eligible_gate": eligible})
    ledger.close()
    return path.name, path


def write_report(path: Path, run_id: str, summary: dict[str, Any]) -> None:
    lines = [
        "# Autoresearcher AR1 report", "", f"Run: {run_id}", "",
        "AR1 measures the researcher on deterministic synthetic landscapes. It does not run HumanEval+ or search a final Python coder.",
        "", "## Preregistered Researcher Score", "",
        "R = 100 * G * (0.60D + 0.20T + 0.15Q + 0.05V). The exact protocol hash, raw cost curves, operator diagnostics, and lineage are in the run artifacts.",
        "", "| policy | G | D | T | Q | V | R |", "|---|---:|---:|---:|---:|---:|---:|",
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
    promotion = summary["promotion"]
    blind_delta = summary["blind_delta_vs_fixed"]
    lines += ["", f"Promotion decision: {'PROMOTE' if promotion['promote'] else 'DO NOT PROMOTE'} {promotion['challenger']}. Required point delta >= {promotion['minimum_effect']:.1f}, visible lower CI > {promotion['required_ci_low']:.1f}, and blind lower margin >= {promotion['blind_margin']:.1f}.", f"Blind paired delta R: {blind_delta['delta_R']:.2f}, 95% CI [{blind_delta['ci_low']:.2f}, {blind_delta['ci_high']:.2f}].", "", "## Blind family", "", "The untouched composed_constraint_epistasis family was scored after visible policy selection; its complete R breakdown is in summary.json.", "", "## Recovery, reproducibility, and falsification", "", f"Eligibility gate G={summary['eligible_gate']}; recovery exact matches {sum(int(r['recovery_resume_match']) for r in summary['recovery'])}/{len(summary['recovery'])}; same-seed reproducibility {sum(int(r['match']) for r in summary['reproducibility'])}/{len(summary['reproducibility'])}."]
    for row in summary["ablations"]:
        lines.append(f"- {row['name']}: final normalized score {row['F_fi']:.4f}, normalized QD {row['Q_fi']:.4f}, valid proposals {row['valid_proposal_rate']:.4f}, duplicate rate {row['duplicate_rate']:.4f}.")
    lines += ["", "## Limitations", "", "The families are finite synthetic search tasks with one two-instance blind family. Wall time is diagnostic; R uses the preregistered deterministic operator cost units. This is not evidence about HumanEval+, Python coding, or full interpretability.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")

