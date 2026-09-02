"""Measure reusable proof-DAG cost versus flat and opaque references."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class ProofNode:
    node_id: int
    rule: str
    premises: tuple[int, ...]


@dataclass(frozen=True)
class Family:
    branches: int
    depth: int
    common_depth: int
    nodes: tuple[ProofNode, ...]
    obligations: tuple[int, ...]


def make_family(branches: int, depth: int) -> Family:
    common_depth = max(1, depth // 2)
    nodes: list[ProofNode] = [ProofNode(0, "axiom", ())]
    previous = 0
    for node_id in range(1, common_depth):
        nodes.append(ProofNode(node_id, "extend", (previous,)))
        previous = node_id
    obligations: list[int] = []
    next_id = common_depth
    for branch in range(branches):
        branch_previous = previous
        for _ in range(depth - common_depth):
            nodes.append(ProofNode(next_id, f"branch_{branch}", (branch_previous,)))
            branch_previous = next_id
            next_id += 1
        obligations.append(branch_previous)
    return Family(branches, depth, common_depth, tuple(nodes), tuple(obligations))


def flat_cost(family: Family, obligations: int) -> int:
    # Every path repeats its common prefix and carries a rule plus premise
    # reference for each step.
    return obligations * (family.depth * 3 + max(0, family.depth - 1))


def shared_cost(family: Family, obligations: int) -> int:
    obligations = min(obligations, family.branches)
    common_nodes = family.common_depth
    branch_nodes = family.depth - family.common_depth
    # One rule token and one premise edge per node; branch roots also carry a
    # branch/obligation binding token.
    return common_nodes * 4 + obligations * (branch_nodes * 4 + 1)


def hash_only_cost(_: Family, obligations: int) -> int:
    # Intentionally non-auditable negative control: each obligation is a hash
    # reference with no local rule, premise, or type information.
    return obligations * 2


def verify_shared(family: Family) -> bool:
    by_id = {node.node_id: node for node in family.nodes}
    for node in family.nodes:
        if node.rule == "axiom" and node.premises:
            return False
        if node.rule != "axiom" and node.rule != "extend" and not node.rule.startswith("branch_"):
            return False
        if node.rule != "axiom" and len(node.premises) != 1:
            return False
        if any(premise not in by_id or premise >= node.node_id for premise in node.premises):
            return False
    return all(obligation in by_id for obligation in family.obligations)


def mutate_shared(family: Family) -> Family:
    nodes = tuple(replace(node, rule="forged") if node.node_id == family.common_depth else node for node in family.nodes)
    return replace(family, nodes=nodes)


def main() -> None:
    families = [make_family(branches, depth) for branches, depth in ((2, 4), (4, 4), (8, 4), (16, 4), (4, 8), (8, 8))]
    cost_rows: list[dict[str, int]] = []
    budget_rows: list[dict[str, int]] = []
    budgets = (64, 128, 256, 512)
    for family in families:
        full_flat = flat_cost(family, family.branches)
        full_shared = shared_cost(family, family.branches)
        cost_rows.append({
            "branches": family.branches,
            "depth": family.depth,
            "common_depth": family.common_depth,
            "flat_all_cost": full_flat,
            "shared_all_cost": full_shared,
            "hash_all_cost": hash_only_cost(family, family.branches),
            "shared_saves_percent": round((1 - full_shared / full_flat) * 100, 2),
        })
        for budget in budgets:
            max_flat = max((count for count in range(1, family.branches + 1) if flat_cost(family, count) <= budget), default=0)
            max_shared = max((count for count in range(1, family.branches + 1) if shared_cost(family, count) <= budget), default=0)
            max_hash = max((count for count in range(1, family.branches + 1) if hash_only_cost(family, count) <= budget), default=0)
            budget_rows.append({
                "branches": family.branches,
                "depth": family.depth,
                "budget": budget,
                "flat_obligations": max_flat,
                "shared_obligations": max_shared,
                "hash_obligations": max_hash,
            })
    family = make_family(8, 8)
    summary = {
        "families": [(family.branches, family.depth) for family in families],
        "cost_rows": cost_rows,
        "budget_rows": budget_rows,
        "proof_audit": {
            "valid_shared_graph": verify_shared(family),
            "mutated_shared_graph": verify_shared(mutate_shared(family)),
            "shared_nodes": len(family.nodes),
        },
        "interpretability_note": "hash_only is a cost lower bound, not an accepted architecture because it omits local premises and rules",
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cost_rows": cost_rows, "proof_audit": summary["proof_audit"]}, indent=2))


if __name__ == "__main__":
    main()
