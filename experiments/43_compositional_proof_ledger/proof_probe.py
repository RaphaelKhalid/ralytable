"""Probe compositional proof DAG validation and cycle rejection."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


Fact = tuple[int, str]


@dataclass(frozen=True)
class ProofNode:
    node_id: int
    rule: str
    premises: tuple[int, ...]
    conclusion: Fact
    reachable: bool = True


@dataclass(frozen=True)
class Program:
    axioms: frozenset[Fact]
    nodes: tuple[ProofNode, ...]
    obligations: frozenset[Fact]


def base_program() -> Program:
    return Program(
        axioms=frozenset({(0, "nonnegative"), (1, "nonnegative")}),
        nodes=(
            ProofNode(0, "axiom", (), (0, "nonnegative")),
            ProofNode(1, "axiom", (), (1, "nonnegative")),
            ProofNode(2, "inc_nonnegative", (0,), (2, "nonnegative")),
            ProofNode(3, "sum_nonnegative", (0, 1), (3, "nonnegative")),
        ),
        obligations=frozenset({(2, "nonnegative"), (3, "nonnegative")}),
    )


def node_map(program: Program) -> dict[int, ProofNode]:
    return {node.node_id: node for node in program.nodes if node.reachable}


def check_rule(node: ProofNode, premise_facts: tuple[Fact, ...], axioms: frozenset[Fact]) -> bool:
    if node.rule == "axiom":
        return not premise_facts and node.conclusion in axioms
    if node.rule == "inc_nonnegative":
        return len(premise_facts) == 1 and premise_facts[0][1] == "nonnegative" and node.conclusion[1] == "nonnegative"
    if node.rule == "sum_nonnegative":
        return len(premise_facts) == 2 and all(fact[1] == "nonnegative" for fact in premise_facts) and node.conclusion[1] == "nonnegative"
    return False


def compositional_target(program: Program) -> bool:
    nodes = node_map(program)
    verified: dict[int, Fact] = {}
    active: set[int] = set()

    def visit(node_id: int) -> bool:
        if node_id in verified:
            return True
        if node_id in active or node_id not in nodes:
            return False
        active.add(node_id)
        node = nodes[node_id]
        if any(not visit(premise) for premise in node.premises):
            return False
        premise_facts = tuple(verified[premise] for premise in node.premises)
        active.remove(node_id)
        if not check_rule(node, premise_facts, program.axioms):
            return False
        verified[node_id] = node.conclusion
        return True

    for node in nodes.values():
        if not visit(node.node_id):
            return False
    return program.obligations.issubset(set(verified.values()))


def conclusion_presence(program: Program) -> bool:
    return program.obligations.issubset({node.conclusion for node in program.nodes if node.reachable})


def shallow_rule_checker(program: Program) -> bool:
    nodes = node_map(program)
    for node in nodes.values():
        if any(premise not in nodes for premise in node.premises):
            return False
        premise_facts = tuple(nodes[premise].conclusion for premise in node.premises)
        if not check_rule(node, premise_facts, program.axioms):
            return False
    return program.obligations.issubset({node.conclusion for node in nodes.values()})


ARCHITECTURES: dict[str, Callable[[Program], bool]] = {
    "conclusion_presence": conclusion_presence,
    "shallow_rule_checker": shallow_rule_checker,
    "compositional_proof_ledger": compositional_target,
}


def reorder_nodes(program: Program, rng: random.Random) -> Program:
    nodes = list(program.nodes)
    rng.shuffle(nodes)
    return replace(program, nodes=tuple(nodes))


def forged_axiom(program: Program) -> Program:
    nodes = tuple(replace(node, rule="axiom", premises=()) if node.node_id == 3 else node for node in program.nodes)
    return replace(program, nodes=nodes)


def missing_premise(program: Program) -> Program:
    nodes = tuple(replace(node, premises=()) if node.node_id == 2 else node for node in program.nodes)
    return replace(program, nodes=nodes)


def cyclic_proof(program: Program) -> Program:
    nodes = tuple(
        replace(node, premises=(3,)) if node.node_id == 2 else
        replace(node, premises=(2, 1)) if node.node_id == 3 else node
        for node in program.nodes
    )
    return replace(program, nodes=nodes)


def add_placebo(program: Program) -> Program:
    placebo = ProofNode(99, "axiom", (), (99, "unreachable"), reachable=False)
    return replace(program, nodes=program.nodes + (placebo,))


def extend_chain(program: Program) -> Program:
    node = ProofNode(4, "inc_nonnegative", (3,), (4, "nonnegative"))
    return replace(program, nodes=program.nodes + (node,), obligations=program.obligations | {(4, "nonnegative")})


def main() -> None:
    cases = {"original": 0, "reorder": 0, "forged_rule_rejection": 0, "missing_premise_rejection": 0, "cycle_rejection": 0, "placebo": 0, "chain_extension": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        program = base_program()
        variants = {
            "reorder": reorder_nodes(program, rng),
            "forged_rule_rejection": forged_axiom(program),
            "missing_premise_rejection": missing_premise(program),
            "cycle_rejection": cyclic_proof(program),
            "placebo": add_placebo(program),
            "chain_extension": extend_chain(program),
        }
        for architecture, run in ARCHITECTURES.items():
            row: dict[str, object] = {"seed": seed, "architecture": architecture}
            row["original_exact"] = run(program) == compositional_target(program)
            cases["original"] += int(row["original_exact"])
            for label, variant in variants.items():
                ok = run(variant) == compositional_target(variant)
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
        "base_certificate_nodes": len(base_program().nodes),
        "extended_certificate_nodes": len(extend_chain(base_program()).nodes),
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates")}, indent=2))


if __name__ == "__main__":
    main()
