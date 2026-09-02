"""Probe semantic-ID normalization and collision rejection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Node:
    operation: str
    parameter: int | None = None
    inputs: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()


def semantic_payload(node: Node) -> tuple[object, ...]:
    return node.operation, node.parameter, node.inputs


def raw_hash(node: Node) -> str:
    return hashlib.sha256(repr((semantic_payload(node), node.metadata)).encode("utf-8")).hexdigest()


def truncated_unchecked(node: Node) -> str:
    return hashlib.sha256(repr(semantic_payload(node)).encode("utf-8")).hexdigest()[:2]


def truncated_collision_checked(node: Node, registry: dict[str, tuple[object, ...]]) -> str | None:
    identifier = truncated_unchecked(node)
    payload = semantic_payload(node)
    previous = registry.get(identifier)
    if previous is not None and previous != payload:
        return None
    registry[identifier] = payload
    return identifier


def full_hash(node: Node) -> str:
    return hashlib.sha256(repr(semantic_payload(node)).encode("utf-8")).hexdigest()


def find_collision() -> tuple[Node, Node, str]:
    seen: dict[str, Node] = {}
    for parameter in range(1024):
        node = Node("literal", parameter)
        identifier = truncated_unchecked(node)
        if identifier in seen and semantic_payload(seen[identifier]) != semantic_payload(node):
            return seen[identifier], node, identifier
        seen[identifier] = node
    raise AssertionError("expected a 2-hex-digit collision")


def main() -> None:
    equivalent_a = Node("call", 7, ("input_a",), (("trace", "one"), ("note", "x")))
    equivalent_b = Node("call", 7, ("input_a",), (("note", "x"), ("trace", "one")))
    decorated = replace(equivalent_a, metadata=(("trace", "different"), ("note", "changed")))
    mutated = replace(equivalent_a, parameter=8)
    collision_a, collision_b, collision_id = find_collision()
    collision_checked_registry: dict[str, tuple[object, ...]] = {}

    def checked(node: Node) -> str | None:
        return truncated_collision_checked(node, collision_checked_registry)

    architectures: dict[str, Callable[[Node], str | None]] = {
        "raw_hash": raw_hash,
        "truncated_unchecked": truncated_unchecked,
        "truncated_collision_checked": checked,
        "full_hash": full_hash,
    }
    cases = {"equivalence": 0, "decorative_invariance": 0, "mutation_sensitivity": 0, "collision_safety": 0}
    rows: list[dict[str, object]] = []
    for architecture, run in architectures.items():
        first = run(equivalent_a)
        row = {
            "architecture": architecture,
            "equivalent_ids": first == run(equivalent_b),
            "decorative_invariant": first == run(decorated),
            "mutation_sensitive": first != run(mutated),
            "collision_safe": run(collision_a) != run(collision_b),
        }
        for key, field in (("equivalence", "equivalent_ids"), ("decorative_invariance", "decorative_invariant"), ("mutation_sensitivity", "mutation_sensitive"), ("collision_safety", "collision_safe")):
            cases[key] += int(row[field])
        rows.append(row)
    summary = {
        "architectures": list(architectures),
        "pass_counts": cases,
        "pass_rates": {key: round(value / len(architectures), 4) for key, value in cases.items()},
        "collision_id": collision_id,
        "collision_payloads": [semantic_payload(collision_a), semantic_payload(collision_b)],
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates", "collision_id")}, indent=2))


if __name__ == "__main__":
    main()
