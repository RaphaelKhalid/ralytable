"""Probe provenance sensitivity to literals and ordered dataflow edges."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Node:
    node_id: int
    operation: str
    inputs: tuple[int, ...]
    parameter: int | None = None
    source: str | None = None
    reachable: bool = True


@dataclass(frozen=True)
class Graph:
    nodes: tuple[Node, ...]
    output: int


def base_graph() -> Graph:
    return Graph(
        nodes=(
            Node(0, "source", (), source="a.py:1"),
            Node(1, "source", (), source="b.py:2"),
            Node(2, "add_constant", (0,), parameter=1),
            Node(3, "subtract", (2, 1)),
        ),
        output=3,
    )


def source_only(graph: Graph) -> tuple[str, ...]:
    by_id = {node.node_id: node for node in graph.nodes if node.reachable}
    seen: set[str] = set()

    def visit(node_id: int) -> None:
        node = by_id[node_id]
        if node.operation == "source" and node.source is not None:
            seen.add(node.source)
        for parent in node.inputs:
            visit(parent)

    visit(graph.output)
    return tuple(sorted(seen))


def operation_tags(graph: Graph) -> tuple[tuple[str, int | None], ...]:
    by_id = {node.node_id: node for node in graph.nodes if node.reachable}
    visited: set[int] = set()

    def visit(node_id: int) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        for parent in by_id[node_id].inputs:
            visit(parent)

    visit(graph.output)
    return tuple(sorted((by_id[node_id].operation, by_id[node_id].parameter) for node_id in visited))


def content_addressed(graph: Graph) -> str:
    by_id = {node.node_id: node for node in graph.nodes if node.reachable}
    memo: dict[int, str] = {}

    def address(node_id: int) -> str:
        if node_id in memo:
            return memo[node_id]
        node = by_id[node_id]
        if node.operation == "source":
            payload = (node.operation, node.source)
        else:
            payload = (node.operation, node.parameter, tuple(address(parent) for parent in node.inputs))
        result = hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()
        memo[node_id] = result
        return result

    return address(graph.output)


ARCHITECTURES: dict[str, Callable[[Graph], object]] = {
    "source_only": source_only,
    "operation_tags": operation_tags,
    "content_addressed": content_addressed,
}


def reorder_nodes(graph: Graph, rng: random.Random) -> Graph:
    nodes = list(graph.nodes)
    rng.shuffle(nodes)
    return replace(graph, nodes=tuple(nodes))


def parameter_edit(graph: Graph) -> Graph:
    nodes = tuple(replace(node, parameter=2) if node.node_id == 2 else node for node in graph.nodes)
    return replace(graph, nodes=nodes)


def operand_swap(graph: Graph) -> Graph:
    nodes = tuple(replace(node, inputs=(1, 2)) if node.node_id == 3 else node for node in graph.nodes)
    return replace(graph, nodes=nodes)


def add_placebo(graph: Graph) -> Graph:
    placebo = Node(99, "oracle", (), parameter=999, reachable=False)
    return replace(graph, nodes=graph.nodes + (placebo,))


def main() -> None:
    cases = {"original": 0, "reorder": 0, "parameter_sensitivity": 0, "operand_sensitivity": 0, "placebo": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        graph = base_graph()
        variants = {
            "reorder": reorder_nodes(graph, rng),
            "parameter_sensitivity": parameter_edit(graph),
            "operand_sensitivity": operand_swap(graph),
            "placebo": add_placebo(graph),
        }
        for architecture, run in ARCHITECTURES.items():
            row: dict[str, object] = {"seed": seed, "architecture": architecture}
            base_actual = run(graph)
            row["original_exact"] = base_actual == content_addressed(graph)
            cases["original"] += int(row["original_exact"])
            for label, variant in variants.items():
                actual = run(variant)
                expected = content_addressed(variant)
                if label in {"parameter_sensitivity", "operand_sensitivity"}:
                    ok = actual == expected and actual != base_actual
                else:
                    ok = actual == expected
                row[f"{label}_ok"] = ok
                cases[label] += int(ok)
            rows.append(row)
    total_runs = 5 * len(ARCHITECTURES)
    summary = {
        "seeds": 5,
        "architectures": list(ARCHITECTURES),
        "total_architecture_runs": total_runs,
        "pass_counts": cases,
        "pass_rates": {key: round(value / total_runs, 4) for key, value in cases.items()},
        "base_sources": source_only(base_graph()),
        "base_operation_tags": operation_tags(base_graph()),
        "base_address": content_addressed(base_graph()),
        "parameter_address": content_addressed(parameter_edit(base_graph())),
        "operand_address": content_addressed(operand_swap(base_graph())),
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates", "base_sources", "base_operation_tags")}, indent=2))


if __name__ == "__main__":
    main()
