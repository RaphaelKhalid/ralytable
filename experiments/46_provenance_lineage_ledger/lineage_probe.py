"""Probe source lineage through multi-step dataflow transformations."""

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
    inputs: tuple[int, ...]
    source: str | None = None
    reachable: bool = True


@dataclass(frozen=True)
class Graph:
    nodes: tuple[Node, ...]
    output: int


def base_graph() -> Graph:
    return Graph(
        nodes=(
            Node(0, "source", (), "file_a.py:1"),
            Node(1, "source", (), "file_b.py:4"),
            Node(2, "normalize", (0,)),
            Node(3, "join", (2, 1)),
            Node(4, "project", (3,)),
        ),
        output=4,
    )


def target_lineage(graph: Graph) -> frozenset[str]:
    by_id = {node.node_id: node for node in graph.nodes if node.reachable}
    memo: dict[int, frozenset[str]] = {}

    def lineage(node_id: int) -> frozenset[str]:
        if node_id in memo:
            return memo[node_id]
        node = by_id[node_id]
        if node.operation == "source":
            result = frozenset({node.source}) if node.source is not None else frozenset()
        else:
            result = frozenset().union(*(lineage(parent) for parent in node.inputs))
        memo[node_id] = result
        return result

    return lineage(graph.output)


def value_only(graph: Graph) -> frozenset[str]:
    del graph
    return frozenset()


def one_hop_metadata(graph: Graph) -> frozenset[str]:
    by_id = {node.node_id: node for node in graph.nodes if node.reachable}
    output = by_id[graph.output]
    return frozenset(
        by_id[parent].source
        for parent in output.inputs
        if by_id[parent].source is not None
    )


def lineage_ledger(graph: Graph) -> frozenset[str]:
    return target_lineage(graph)


ARCHITECTURES: dict[str, Callable[[Graph], frozenset[str]]] = {
    "value_only": value_only,
    "one_hop_metadata": one_hop_metadata,
    "lineage_ledger": lineage_ledger,
}


def reorder_nodes(graph: Graph, rng: random.Random) -> Graph:
    nodes = list(graph.nodes)
    rng.shuffle(nodes)
    return replace(graph, nodes=tuple(nodes))


def mutate_lineage(graph: Graph) -> Graph:
    nodes = tuple(replace(node, inputs=(1,)) if node.node_id == 2 else node for node in graph.nodes)
    return replace(graph, nodes=nodes)


def add_unreachable_node(graph: Graph) -> Graph:
    placebo = Node(99, "secret_source", (), "oracle.answer", reachable=False)
    return replace(graph, nodes=graph.nodes + (placebo,))


def change_decorative_source_label(graph: Graph) -> Graph:
    nodes = tuple(replace(node, source="renamed.py:99") if node.node_id == 0 else node for node in graph.nodes)
    return replace(graph, nodes=nodes)


def main() -> None:
    cases = {"original": 0, "reorder": 0, "lineage_sensitivity": 0, "placebo": 0, "label_change": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        graph = base_graph()
        variants = {
            "reorder": reorder_nodes(graph, rng),
            "lineage_sensitivity": mutate_lineage(graph),
            "placebo": add_unreachable_node(graph),
            "label_change": change_decorative_source_label(graph),
        }
        for architecture, run in ARCHITECTURES.items():
            row: dict[str, object] = {"seed": seed, "architecture": architecture}
            row["original_exact"] = run(graph) == target_lineage(graph)
            cases["original"] += int(row["original_exact"])
            for label, variant in variants.items():
                actual = run(variant)
                expected = target_lineage(variant)
                if label == "lineage_sensitivity":
                    ok = actual == expected and actual != target_lineage(graph)
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
        "base_lineage": sorted(target_lineage(base_graph())),
        "mutated_lineage": sorted(target_lineage(mutate_lineage(base_graph()))),
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates", "base_lineage", "mutated_lineage")}, indent=2))


if __name__ == "__main__":
    main()
