"""Probe effect ordering, capability checks, and exception obligations."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Operation:
    op_id: int
    name: str
    effects: tuple[str, ...]
    required_capability: str | None = None
    may_throw: bool = False
    reachable: bool = True


@dataclass(frozen=True)
class Program:
    operations: tuple[Operation, ...]
    capabilities: frozenset[str]
    catches_exceptions: bool


def base_program() -> Program:
    # Deliberately put write before read in the source trace; a value-only
    # canonicalizer that sorts IDs will erase this observable order.
    return Program(
        operations=(
            Operation(0, "parse", ()),
            Operation(2, "write_file", ("IO",), "write"),
            Operation(1, "read_file", ("IO",), "read", may_throw=True),
            Operation(3, "normalize", ()),
        ),
        capabilities=frozenset({"read", "write"}),
        catches_exceptions=True,
    )


def target_signature(program: Program) -> tuple[bool, tuple[int, ...]]:
    legal = all(
        operation.required_capability is None
        or operation.required_capability in program.capabilities
        for operation in program.operations
        if operation.reachable
    )
    legal = legal and (
        program.catches_exceptions
        or not any(operation.may_throw for operation in program.operations if operation.reachable)
    )
    effects = tuple(
        operation.op_id
        for operation in program.operations
        if operation.reachable and operation.effects
    )
    return legal, effects


def value_type_only(program: Program) -> tuple[bool, tuple[int, ...]]:
    # This deliberately models a compact value-only IR: it accepts all
    # operations and canonicalizes them by identifier, losing effect order.
    return True, tuple(sorted(operation.op_id for operation in program.operations if operation.effects))


def effect_tags(program: Program) -> tuple[bool, tuple[int, ...]]:
    operations = tuple(operation for operation in program.operations if operation.reachable)
    legal = all(
        operation.required_capability is None
        or operation.required_capability in program.capabilities
        for operation in operations
    )
    legal = legal and (program.catches_exceptions or not any(operation.may_throw for operation in operations))
    return legal, tuple(operation.op_id for operation in operations if operation.effects)


def capability_effect_ledger(program: Program) -> tuple[bool, tuple[int, ...]]:
    # The ledger retains source order for effectful operations and ignores
    # unreachable nodes after checking their explicit reachability boundary.
    return target_signature(program)


ARCHITECTURES: dict[str, Callable[[Program], tuple[bool, tuple[int, ...]]]] = {
    "value_type_only": value_type_only,
    "effect_tags": effect_tags,
    "capability_effect_ledger": capability_effect_ledger,
}


def pure_reorder(program: Program, rng: random.Random) -> Program:
    pure = [operation for operation in program.operations if not operation.effects]
    effectful = [operation for operation in program.operations if operation.effects]
    rng.shuffle(pure)
    # Reinsert pure operations around the unchanged effect trace. The exact
    # source positions are irrelevant; the effectful trace must remain [2, 1].
    return replace(program, operations=tuple(pure[:1] + effectful + pure[1:]))


def effect_swap(program: Program) -> Program:
    operations = list(program.operations)
    effect_positions = [index for index, operation in enumerate(operations) if operation.effects]
    first, second = effect_positions
    operations[first], operations[second] = operations[second], operations[first]
    return replace(program, operations=tuple(operations))


def capability_violation(program: Program) -> Program:
    return replace(program, capabilities=frozenset({"read"}))


def unhandled_throw(program: Program) -> Program:
    return replace(program, catches_exceptions=False)


def unreachable_placebo(program: Program) -> Program:
    placebo = Operation(99, "secret_write", ("IO",), "write", reachable=False)
    return replace(program, operations=program.operations + (placebo,))


def main() -> None:
    cases = {"original": 0, "pure_reorder": 0, "effect_order_sensitivity": 0, "capability_rejection": 0, "throw_rejection": 0, "placebo": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        program = base_program()
        variants = {
            "pure_reorder": pure_reorder(program, rng),
            "effect_order_sensitivity": effect_swap(program),
            "capability_rejection": capability_violation(program),
            "throw_rejection": unhandled_throw(program),
            "placebo": unreachable_placebo(program),
        }
        for architecture, run in ARCHITECTURES.items():
            row: dict[str, object] = {"seed": seed, "architecture": architecture}
            base_actual = run(program)
            row["original_exact"] = base_actual == target_signature(program)
            cases["original"] += int(row["original_exact"])
            for label, variant in variants.items():
                actual = run(variant)
                if label == "effect_order_sensitivity":
                    # This is a deliberate semantic change: a useful runtime
                    # must expose a changed effect trace, not normalize it.
                    ok = actual[0] and actual[1] != base_actual[1]
                else:
                    ok = actual == target_signature(variant)
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
        "base_target": target_signature(base_program()),
        "swapped_target": target_signature(effect_swap(base_program())),
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates")}, indent=2))


if __name__ == "__main__":
    main()
