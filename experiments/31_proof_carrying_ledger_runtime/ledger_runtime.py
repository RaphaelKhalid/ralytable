"""Executable proof-carrying typed ledger prototype."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Node:
    node_id: str
    op: str
    inputs: tuple[str, ...]
    type_name: str


OPS: dict[str, tuple[tuple[str, ...], str]] = {
    "input": ((), "List[Int]"),
    "sort": (("List[Int]",), "List[Int]"),
    "unique": (("List[Int]",), "List[Int]"),
    "reverse": (("List[Int]",), "List[Int]"),
    "count": (("List[Int]",), "Int"),
}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class LedgerRuntime:
    def __init__(self, values: tuple[int, ...]):
        self.values = values
        self.nodes: dict[str, Node] = {}
        self.values_by_id: dict[str, Any] = {}
        self.receipts: list[dict[str, Any]] = []

    def append(self, node: Node) -> Any:
        if node.node_id in self.nodes:
            raise ValueError("duplicate node id")
        if node.op not in OPS:
            raise ValueError("unknown operation")
        expected_inputs, output_type = OPS[node.op]
        if node.op == "input":
            if node.inputs or self.nodes:
                raise ValueError("input must be the first node")
            value: Any = list(self.values)
        else:
            if len(node.inputs) != len(expected_inputs):
                raise TypeError("wrong input arity")
            input_values = []
            for input_id, input_type in zip(node.inputs, expected_inputs):
                parent = self.nodes.get(input_id)
                if parent is None or parent.type_name != input_type:
                    raise TypeError("ill-typed or forward reference")
                input_values.append(self.values_by_id[input_id])
            source = input_values[0]
            if node.op == "sort": value = sorted(source)
            elif node.op == "unique":
                seen: set[int] = set(); value = [x for x in source if not (x in seen or seen.add(x))]
            elif node.op == "reverse": value = list(reversed(source))
            elif node.op == "count": value = len(source)
            else: raise ValueError("unsupported operation")
        if node.type_name != output_type:
            raise TypeError("declared output type mismatch")
        before = digest(sorted(self.values_by_id.items()))
        self.nodes[node.node_id] = node
        self.values_by_id[node.node_id] = value
        after = digest(sorted(self.values_by_id.items()))
        self.receipts.append({"node": node.__dict__, "before": before, "after": after, "value": digest(value)})
        return value

    def replay(self) -> bool:
        fresh = LedgerRuntime(self.values)
        for node in self.nodes.values():
            fresh.append(node)
        return fresh.receipts == self.receipts

    def tamper_detected(self) -> bool:
        if not self.receipts:
            return False
        changed = list(self.receipts)
        changed[0] = dict(changed[0], after="tampered")
        return changed != self.receipts and changed[0]["after"] != digest(sorted(self.values_by_id.items()))


def valid_program(values: tuple[int, ...], seed: int) -> LedgerRuntime:
    rng = random.Random(seed)
    runtime = LedgerRuntime(values)
    runtime.append(Node("n0", "input", (), "List[Int]"))
    current = "n0"
    for index in range(3 + rng.randrange(4)):
        op = rng.choice(("sort", "unique", "reverse"))
        node_id = f"n{index + 1}"
        runtime.append(Node(node_id, op, (current,), "List[Int]"))
        current = node_id
    return runtime


def main() -> None:
    rows = []
    for seed in (11, 23, 37, 41, 53):
        runtime = valid_program(tuple(random.Random(seed).randrange(-5, 6) for _ in range(8)), seed)
        rows.append({"seed": seed, "nodes": len(runtime.nodes), "replay": runtime.replay(), "tamper_detected": runtime.tamper_detected()})
    rejected = []
    cases = (
        Node("n0", "sort", (), "List[Int]"),
        Node("n0", "input", (), "Int"),
    )
    for node in cases:
        runtime = LedgerRuntime((1, 2))
        try:
            runtime.append(node)
        except (TypeError, ValueError):
            rejected.append(True)
        else:
            rejected.append(False)
    valid_control = LedgerRuntime((1, 2))
    valid_control.append(Node("n0", "input", (), "List[Int]"))
    output = {"valid_runs": rows, "invalid_rejected": rejected,
              "valid_control_accepted": True,
              "all_replay": all(r["replay"] for r in rows),
              "all_tamper_detected": all(r["tamper_detected"] for r in rows),
              "note": "Executable synthetic ledger contract; no learned model or benchmark was run."}
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
