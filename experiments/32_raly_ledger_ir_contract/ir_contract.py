"""Raly-aligned typed ledger IR validation and canonical replay probe."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FAMILIES = {"hrr", "fhr", "map", "unknown"}


@dataclass(frozen=True)
class LedgerType:
    dimension: str
    family: str
    load_low: int
    load_high: int
    capacity: int
    roles: tuple[str, ...]


@dataclass(frozen=True)
class LedgerNode:
    node_id: str
    op: str
    inputs: tuple[str, ...]
    output: LedgerType
    provenance: tuple[str, ...]


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def node_payload(node: LedgerNode) -> dict:
    payload = asdict(node)
    payload["output"]["roles"] = list(node.output.roles)
    payload["inputs"] = list(node.inputs)
    payload["provenance"] = list(node.provenance)
    return payload


def valid_type(ty: LedgerType) -> bool:
    return (ty.family in FAMILIES and ty.dimension != "" and 0 <= ty.load_low <= ty.load_high <= ty.capacity
            and len(set(ty.roles)) == len(ty.roles))


def validate(nodes: tuple[LedgerNode, ...]) -> bool:
    seen: dict[str, LedgerNode] = {}
    for node in nodes:
        if node.node_id in seen or not valid_type(node.output):
            return False
        if any(input_id not in seen for input_id in node.inputs):
            return False
        if node.op not in {"input", "map", "filter", "fold", "return"}:
            return False
        if node.op == "input" and node.inputs:
            return False
        if node.op != "input" and not node.inputs:
            return False
        seen[node.node_id] = node
    return bool(nodes) and nodes[-1].op == "return"


def digest(nodes: tuple[LedgerNode, ...]) -> str:
    return hashlib.sha256(canonical([node_payload(node) for node in nodes]).encode()).hexdigest()


def valid_graph(seed: int) -> tuple[LedgerNode, ...]:
    rng = random.Random(seed)
    ty = LedgerType("S^1", rng.choice(("hrr", "fhr")), 1, 1 + rng.randrange(3), 8, ("value",))
    nodes = [LedgerNode("n0", "input", (), ty, ("prompt:0",))]
    previous = "n0"
    for index in range(2 + rng.randrange(3)):
        nodes.append(LedgerNode(f"n{index + 1}", rng.choice(("map", "filter", "fold")), (previous,), ty, (f"prompt:{index + 1}",)))
        previous = nodes[-1].node_id
    nodes.append(LedgerNode(f"n{len(nodes)}", "return", (previous,), ty, ("renderer",)))
    return tuple(nodes)


def invalid_graphs() -> list[tuple[LedgerNode, ...]]:
    good = valid_graph(11)
    return [
        (replace_node(good[1], inputs=("future",)),) + good[2:],
        (replace_node(good[1], output=LedgerType("S^1", "hrr", 0, 9, 8, ("value",))),) + good[2:],
        (replace_node(good[1], output=LedgerType("", "hrr", 0, 1, 8, ("value",))),) + good[2:],
        (replace_node(good[-1], op="map"),),
    ]


def replace_node(node: LedgerNode, **changes) -> LedgerNode:
    values = asdict(node)
    values.update(changes)
    if isinstance(values.get("output"), dict):
        values["output"] = LedgerType(**values["output"])
    values["inputs"] = tuple(values["inputs"])
    values["provenance"] = tuple(values["provenance"])
    return LedgerNode(**values)


def main() -> None:
    graphs = [valid_graph(seed) for seed in (11, 23, 37, 41, 53)]
    roundtrips = []
    tamper = []
    for graph in graphs:
        payload = json.loads(canonical([node_payload(node) for node in graph]))
        restored = tuple(LedgerNode(item["node_id"], item["op"], tuple(item["inputs"]),
                                    LedgerType(**item["output"]), tuple(item["provenance"])) for item in payload)
        roundtrips.append(validate(restored) and digest(graph) == digest(restored))
        replacement_op = "filter" if graph[1].op != "filter" else "map"
        tampered = graph[:1] + (replace_node(graph[1], op=replacement_op),) + graph[2:]
        tamper.append(digest(graph) != digest(tampered))
    rejected = [not validate(graph) for graph in invalid_graphs()]
    output = {"valid_graphs": len(graphs), "all_roundtrips": all(roundtrips),
              "all_tamper_changes": all(tamper), "invalid_rejected": rejected,
              "note": "Raly-aligned synthetic IR contract; no compiler or learned model was run."}
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
