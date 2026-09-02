"""Measure conservative type/invariant pruning without ML dependencies."""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OPS = ("sort", "unique", "reverse", "filter", "count")


@dataclass(frozen=True)
class AbstractState:
    type_name: str = "List"
    sorted: bool = False
    unique: bool = False


def transition(state: AbstractState, op: str) -> AbstractState | None:
    if state.type_name == "Int":
        return None
    if op == "count":
        return AbstractState("Int")
    if op == "sort":
        return AbstractState("List", True, state.unique)
    if op == "unique":
        return AbstractState("List", state.sorted, True)
    if op == "reverse":
        return AbstractState("List", False, state.unique)
    if op == "filter":
        return AbstractState("List", False, False)
    return None


def legal(state: AbstractState, op: str, mode: str) -> bool:
    if transition(state, op) is None:
        return False
    if mode != "invariant":
        return True
    # These are semantics-preserving no-op eliminations, not heuristics.
    if op == "sort" and state.sorted:
        return False
    if op == "unique" and state.unique:
        return False
    return True


def count_nodes(depth: int, mode: str) -> list[int]:
    frontier = [AbstractState()]
    counts = [1]
    for _ in range(depth):
        next_frontier = []
        for state in frontier:
            for op in OPS:
                if legal(state, op, mode):
                    next_frontier.append(transition(state, op))
        frontier = [state for state in next_frontier if state is not None]
        counts.append(len(frontier))
    return counts


def target_program(rng: random.Random, depth: int) -> tuple[str, ...]:
    state = AbstractState()
    program = []
    for position in range(depth):
        available = OPS if position == depth - 1 else OPS[:-1]
        choices = [op for op in available if legal(state, op, "invariant")]
        op = rng.choice(choices)
        program.append(op)
        state = transition(state, op)
    return tuple(program)


def survives(program: tuple[str, ...], mode: str) -> bool:
    state = AbstractState()
    for op in program:
        if not legal(state, op, mode):
            return False
        state = transition(state, op)
    return True


def main() -> None:
    depths = (4, 6, 8, 10)
    modes = ("unrestricted", "typed", "invariant")
    rows = []
    for depth in depths:
        for mode in modes:
            counts = count_nodes(depth, mode)
            rows.append({"depth": depth, "mode": mode, "nodes_by_level": counts,
                         "total_nodes": sum(counts)})
    seeds = (11, 23, 37, 41, 53)
    completeness = []
    for seed in seeds:
        rng = random.Random(seed)
        programs = [target_program(rng, depth=8) for _ in range(500)]
        completeness.append({"seed": seed, "typed": sum(survives(p, "typed") for p in programs) / len(programs),
                             "invariant": sum(survives(p, "invariant") for p in programs) / len(programs)})
    output = {"rows": rows, "target_completeness": completeness,
              "note": "Abstract-state search model only; no learned model or benchmark was run."}
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for row in rows:
        print(json.dumps(row, sort_keys=True))
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
