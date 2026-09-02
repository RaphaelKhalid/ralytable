"""Probe dependency-aware incremental recomputation on a ledger DAG."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Node:
    node_id: int
    operation: str
    inputs: tuple[int, ...] = ()
    parameter: str = ""


@dataclass(frozen=True)
class Graph:
    nodes: tuple[Node, ...]
    output: int


def base_graph() -> Graph:
    return Graph(
        nodes=(
            Node(0, "source", parameter="A"),
            Node(1, "source", parameter="B"),
            Node(2, "normalize", (0,)),
            Node(3, "normalize", (1,)),
            Node(4, "join", (2, 3)),
            Node(5, "render", (4,)),
            Node(6, "checksum", (1,)),
            Node(7, "package", (5, 6)),
        ),
        output=7,
    )


def compute(operation: str, parameter: str, inputs: tuple[str, ...]) -> str:
    if operation == "source":
        return parameter
    if operation == "normalize":
        return inputs[0].strip().lower()
    if operation == "join":
        return inputs[0] + "|" + inputs[1]
    if operation == "render":
        return "<" + inputs[0] + ">"
    if operation == "checksum":
        return "hash(" + inputs[0] + ")"
    if operation == "package":
        return inputs[0] + "#" + inputs[1]
    raise ValueError(operation)


def full_cache(graph: Graph) -> tuple[dict[int, str], int]:
    by_id = {node.node_id: node for node in graph.nodes}
    values: dict[int, str] = {}
    calls = 0

    def visit(node_id: int) -> str:
        nonlocal calls
        if node_id in values:
            return values[node_id]
        node = by_id[node_id]
        inputs = tuple(visit(parent) for parent in node.inputs)
        values[node_id] = compute(node.operation, node.parameter, inputs)
        calls += 1
        return values[node_id]

    visit(graph.output)
    # A full compilation materializes every ledger node, including independent
    # branches that may not be on the selected output path.
    for node in graph.nodes:
        visit(node.node_id)
    return values, calls


def descendants(graph: Graph, changed: set[int]) -> set[int]:
    result = set(changed)
    changed_again = True
    while changed_again:
        changed_again = False
        for node in graph.nodes:
            if node.node_id not in result and any(parent in result for parent in node.inputs):
                result.add(node.node_id)
                changed_again = True
    return result


def incremental_cache(graph: Graph, old_values: dict[int, str], invalidated: set[int]) -> tuple[str, int]:
    by_id = {node.node_id: node for node in graph.nodes}
    values: dict[int, str] = {}
    calls = 0

    def visit(node_id: int) -> str:
        nonlocal calls
        if node_id in values:
            return values[node_id]
        if node_id not in invalidated and node_id in old_values:
            values[node_id] = old_values[node_id]
            return values[node_id]
        node = by_id[node_id]
        inputs = tuple(visit(parent) for parent in node.inputs)
        values[node_id] = compute(node.operation, node.parameter, inputs)
        calls += 1
        return values[node_id]

    output = visit(graph.output)
    return output, calls


def run_architecture(name: str, graph: Graph, old_values: dict[int, str], changed: set[int]) -> tuple[str, int]:
    if name == "full_recompute":
        values, calls = full_cache(graph)
        return values[graph.output], calls
    if name == "no_invalidation_cache":
        invalidated = set()
    elif name == "suffix_cache":
        invalidated = set(range(min(changed), len(graph.nodes))) if changed else set()
    else:
        invalidated = descendants(graph, changed)
    return incremental_cache(graph, old_values, invalidated)


ARCHITECTURES = ("full_recompute", "no_invalidation_cache", "suffix_cache", "dependency_cache")


def parameter_edit(graph: Graph) -> Graph:
    nodes = tuple(replace(node, parameter="A2") if node.node_id == 0 else node for node in graph.nodes)
    return replace(graph, nodes=nodes)


def independent_edit(graph: Graph) -> Graph:
    nodes = tuple(replace(node, parameter="B2") if node.node_id == 1 else node for node in graph.nodes)
    return replace(graph, nodes=nodes)


def reorder_nodes(graph: Graph, rng: random.Random) -> Graph:
    nodes = list(graph.nodes)
    rng.shuffle(nodes)
    return replace(graph, nodes=tuple(nodes))


def main() -> None:
    cases = {"base_correct": 0, "local_edit_correct": 0, "independent_edit_correct": 0, "reorder_correct": 0, "local_recompute_savings": 0, "independent_recompute_savings": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        base = base_graph()
        base_values, base_calls = full_cache(base)
        variants = {
            "local_edit": (parameter_edit(base), {0}),
            "independent_edit": (independent_edit(base), {1}),
            "reorder": (reorder_nodes(base, rng), set()),
        }
        for architecture in ARCHITECTURES:
            row: dict[str, object] = {"seed": seed, "architecture": architecture, "base_full_calls": base_calls}
            base_output, base_run_calls = run_architecture(architecture, base, base_values, set())
            row["base_correct"] = base_output == base_values[base.output]
            cases["base_correct"] += int(row["base_correct"])
            for label, (variant, changed) in variants.items():
                fresh_values, fresh_calls = full_cache(variant)
                actual, calls = run_architecture(architecture, variant, base_values, changed)
                correct = actual == fresh_values[variant.output]
                row[f"{label}_correct"] = correct
                cases[f"{label}_correct"] += int(correct)
                if label == "local_edit":
                    saved = calls < fresh_calls
                    cases["local_recompute_savings"] += int(saved)
                    row["local_calls"] = calls
                    row["local_fresh_calls"] = fresh_calls
                if label == "independent_edit":
                    saved = calls < fresh_calls
                    cases["independent_recompute_savings"] += int(saved)
                    row["independent_calls"] = calls
                    row["independent_fresh_calls"] = fresh_calls
            rows.append(row)
    total_runs = 5 * len(ARCHITECTURES)
    summary = {
        "seeds": 5,
        "architectures": list(ARCHITECTURES),
        "total_architecture_runs": total_runs,
        "pass_counts": cases,
        "pass_rates": {key: round(value / total_runs, 4) for key, value in cases.items()},
        "base_calls": base_calls,
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates", "base_calls")}, indent=2))


if __name__ == "__main__":
    main()
