"""Probe structured intermediate representations without ML dependencies.

This deliberately measures representational sufficiency, not learned coding
ability. The task generator is synthetic and the encoder receives exact task
facts. A positive result is a reason to test a learned parser, not a claim
about an end-to-end model.
"""

from __future__ import annotations

import hashlib
import json
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
OPS = ("input", "filter", "sort", "unique", "reverse", "count", "merge")


@dataclass(frozen=True)
class Node:
    node_id: int
    op: str
    inputs: tuple[int, ...]
    type_name: str = "List[Int]"


@dataclass(frozen=True)
class Task:
    nodes: tuple[Node, ...]
    surface_order: tuple[int, ...]
    shape: str

    def permuted(self, seed: int) -> "Task":
        order = list(self.surface_order)
        random.Random(seed).shuffle(order)
        return Task(self.nodes, tuple(order), self.shape)

    def altered(self) -> "Task":
        nodes = list(self.nodes)
        target = next(i for i, node in enumerate(nodes) if node.op != "input")
        old = nodes[target]
        replacement = {"sort": "reverse", "reverse": "sort", "count": "unique", "unique": "count",
                       "filter": "sort", "merge": "unique"}.get(old.op, "sort")
        nodes[target] = Node(old.node_id, replacement, old.inputs, old.type_name)
        return Task(tuple(nodes), self.surface_order, self.shape)

    def with_placebo(self) -> "Task":
        nodes = self.nodes + (Node(max(n.node_id for n in self.nodes) + 1, "input", (), "List[Int]"),)
        # The distractor exists in the surrounding record but is not part of
        # the presented active program. A representation should ignore it.
        return Task(nodes, self.surface_order, self.shape)


def make_task(rng: random.Random, shape: str, depth: int) -> Task:
    nodes = [Node(0, "input", ())]
    if shape == "linear":
        previous = 0
        choices = ("filter", "sort", "unique", "reverse", "count")
        for _ in range(depth):
            op = choices[rng.randrange(len(choices))]
            type_name = "Int" if op == "count" else "List[Int]"
            nodes.append(Node(len(nodes), op, (previous,), type_name))
            previous = nodes[-1].node_id
    elif shape == "branch_merge":
        for _ in range(max(2, depth // 2)):
            op = ("sort", "unique", "reverse")[rng.randrange(3)]
            nodes.append(Node(len(nodes), op, (0,)))
        left, right = nodes[-2].node_id, nodes[-1].node_id
        nodes.append(Node(len(nodes), "merge", (left, right)))
        if depth > 3:
            nodes.append(Node(len(nodes), "unique", (nodes[-1].node_id,)))
    else:
        raise ValueError(shape)
    return Task(tuple(nodes), tuple(n.node_id for n in nodes), shape)


def canonical(nodes: Iterable[Node] | None) -> tuple[tuple[int, str, tuple[int, ...], str], ...] | None:
    if nodes is None:
        return None
    return tuple((n.node_id, n.op, n.inputs, n.type_name) for n in sorted(nodes, key=lambda x: x.node_id))


class Architecture:
    name = "base"
    state_budget = 0
    learned_parameters = 0
    audit_surface = ""

    def encode_decode(self, task: Task) -> tuple[Node, ...] | None:
        raise NotImplementedError


class FlatSketch(Architecture):
    name = "flat_sketch"
    state_budget = 12
    learned_parameters = 39_600_000
    audit_surface = "dense vector; no named binding"

    @staticmethod
    def _bucket(node: Node) -> int:
        # Stable, deliberately tiny sketch. Collision means a fact is lost.
        return (node.node_id * 31 + OPS.index(node.op) * 17 + len(node.inputs) * 7) % FlatSketch.state_budget

    def encode_decode(self, task: Task) -> tuple[Node, ...] | None:
        buckets: dict[int, Node] = {}
        for node_id in task.surface_order:
            node = task.nodes[node_id]
            buckets[self._bucket(node)] = node
        decoded = tuple(sorted(buckets.values(), key=lambda n: n.node_id))
        return decoded if len(decoded) == len(task.nodes) else None


class EntitySlots(Architecture):
    name = "entity_slots"
    state_budget = 8
    learned_parameters = 12_700_000
    audit_surface = "named slots; sequence edges only"

    def encode_decode(self, task: Task) -> tuple[Node, ...] | None:
        active = tuple(task.nodes[node_id] for node_id in task.surface_order)
        if len(active) > self.state_budget:
            return None
        # Slots preserve identity and order but not arbitrary fan-in edges.
        if any(len(node.inputs) > 1 for node in active):
            return None
        return active


class TypedProgramGraph(Architecture):
    name = "typed_program_graph"
    state_budget = 16
    learned_parameters = 18_400_000
    audit_surface = "typed nodes + explicit edges"

    def encode_decode(self, task: Task) -> tuple[Node, ...] | None:
        active = tuple(task.nodes[node_id] for node_id in task.surface_order)
        return active if len(active) <= self.state_budget else None


class TypedProgramLedger(Architecture):
    name = "typed_program_ledger"
    state_budget = 24
    learned_parameters = 23_600_000
    audit_surface = "content-addressed typed nodes + reversible edges + provenance"

    def encode_decode(self, task: Task) -> tuple[Node, ...] | None:
        active = tuple(task.nodes[node_id] for node_id in task.surface_order)
        if len(active) > self.state_budget:
            return None
        # Hash-consing makes identity stable under surface permutation. The
        # explicit tuple is the inspectable IR; there is no latent bypass.
        entries = {
            hashlib.sha256(f"{n.node_id}|{n.op}|{n.inputs}|{n.type_name}".encode()).hexdigest(): n
            for n in active
        }
        return tuple(sorted(entries.values(), key=lambda n: n.node_id))


ARCHITECTURES = (FlatSketch(), EntitySlots(), TypedProgramGraph(), TypedProgramLedger())


def task_rows(seed: int, count: int = 120) -> list[Task]:
    rng = random.Random(seed)
    rows: list[Task] = []
    for i in range(count):
        shape = "linear" if i % 2 == 0 else "branch_merge"
        depth = 2 + (i % 8)
        rows.append(make_task(rng, shape, depth))
    return rows


def rate(values: list[bool]) -> float:
    return sum(values) / max(1, len(values))


def evaluate(architecture: Architecture, tasks: list[Task]) -> dict[str, object]:
    exact = []
    permuted = []
    relevant_changed = []
    placebo_preserved = []
    by_shape: dict[str, list[bool]] = {"linear": [], "branch_merge": []}
    by_depth: dict[str, list[bool]] = {}
    for index, task in enumerate(tasks):
        base = canonical(architecture.encode_decode(task))
        ok = base == canonical(task.nodes)
        exact.append(ok)
        by_shape[task.shape].append(ok)
        by_depth.setdefault(str(len(task.nodes)), []).append(ok)
        permuted.append(base == canonical(architecture.encode_decode(task.permuted(7000 + index))))
        altered = canonical(architecture.encode_decode(task.altered()))
        relevant_changed.append(ok and altered != base)
        placebo = canonical(architecture.encode_decode(task.with_placebo()))
        placebo_preserved.append(ok and placebo == base)
    return {
        "exact_recovery": rate(exact),
        "permutation_invariance": rate(permuted),
        "relevant_counterfactual_change": rate(relevant_changed),
        "irrelevant_placebo_preservation": rate(placebo_preserved),
        "linear_recovery": rate(by_shape["linear"]),
        "branch_merge_recovery": rate(by_shape["branch_merge"]),
        "recovery_by_node_count": {key: rate(value) for key, value in sorted(by_depth.items(), key=lambda item: int(item[0]))},
        "state_budget": architecture.state_budget,
        "learned_parameters": architecture.learned_parameters,
        "audit_surface": architecture.audit_surface,
    }


def main() -> None:
    seeds = (11, 23, 37, 41, 53)
    runs = []
    for seed in seeds:
        tasks = task_rows(seed)
        for architecture in ARCHITECTURES:
            row = evaluate(architecture, tasks)
            row.update({"seed": seed, "architecture": architecture.name, "tasks": len(tasks)})
            runs.append(row)
            print(json.dumps(row, sort_keys=True), flush=True)
    summary: dict[str, object] = {"seeds": list(seeds), "runs": runs, "note": "Synthetic representational probe; no model was trained."}
    for architecture in ARCHITECTURES:
        rows = [r for r in runs if r["architecture"] == architecture.name]
        summary.setdefault("aggregate", {})[architecture.name] = {
            key: statistics.mean(float(r[key]) for r in rows)
            for key in ("exact_recovery", "permutation_invariance", "relevant_counterfactual_change", "irrelevant_placebo_preservation", "linear_recovery", "branch_merge_recovery")
        }
    output = ROOT / "summary.json"
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
