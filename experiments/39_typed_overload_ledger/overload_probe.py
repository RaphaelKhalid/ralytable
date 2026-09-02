"""Probe typed overload resolution and ambiguity rejection."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Overload:
    binder: int
    scope: int
    symbol: str
    argument: str
    result: str


@dataclass(frozen=True)
class Call:
    scope: int
    symbol: str
    argument: str
    expected_result: str | None


@dataclass(frozen=True)
class Program:
    overloads: tuple[Overload, ...]
    calls: tuple[Call, ...]


def base_program() -> Program:
    return Program(
        overloads=(
            Overload(0, 0, "map", "List[Int]", "List[Int]"),
            Overload(1, 0, "map", "Text", "Text"),
            Overload(2, 0, "parse", "Text", "Int"),
            Overload(3, 0, "parse", "Text", "Bool"),
        ),
        calls=(
            Call(0, "map", "List[Int]", "List[Int]"),
            Call(0, "map", "Text", "Text"),
            Call(0, "parse", "Text", "Bool"),
            Call(0, "parse", "Text", "Int"),
        ),
    )


def resolve(program: Program, policy: str) -> tuple[int | None, ...]:
    result: list[int | None] = []
    for call in program.calls:
        candidates = [
            overload for overload in program.overloads
            if overload.scope == call.scope and overload.symbol == call.symbol
        ]
        if policy == "name_only":
            result.append(candidates[-1].binder if candidates else None)
            continue
        if policy == "argument_only":
            candidates = [candidate for candidate in candidates if candidate.argument == call.argument]
            result.append(candidates[-1].binder if candidates else None)
            continue
        candidates = [candidate for candidate in candidates if candidate.argument == call.argument]
        if call.expected_result is not None:
            candidates = [candidate for candidate in candidates if candidate.result == call.expected_result]
        result.append(candidates[0].binder if len(candidates) == 1 else None)
    return tuple(result)


ARCHITECTURES: dict[str, Callable[[Program], tuple[int | None, ...]]] = {
    "name_only": lambda program: resolve(program, "name_only"),
    "argument_only": lambda program: resolve(program, "argument_only"),
    "typed_overload_ledger": lambda program: resolve(program, "typed_overload_ledger"),
}


def rename_family(program: Program, old: str, new: str) -> Program:
    overloads = tuple(replace(overload, symbol=new if overload.symbol == old else overload.symbol)
                      for overload in program.overloads)
    calls = tuple(replace(call, symbol=new if call.symbol == old else call.symbol) for call in program.calls)
    return replace(program, overloads=overloads, calls=calls)


def reorder_overloads(program: Program, rng: random.Random) -> Program:
    overloads = list(program.overloads)
    rng.shuffle(overloads)
    return replace(program, overloads=tuple(overloads))


def argument_edit(program: Program) -> Program:
    calls = list(program.calls)
    calls[0] = replace(calls[0], argument="Text", expected_result="Text")
    return replace(program, calls=tuple(calls))


def ambiguity_edit(program: Program) -> Program:
    calls = list(program.calls)
    calls[2] = replace(calls[2], expected_result=None)
    return replace(program, calls=tuple(calls))


def add_placebo_scope(program: Program) -> Program:
    overloads = program.overloads + (Overload(4, 1, "map", "List[Int]", "Bytes"),)
    return replace(program, overloads=overloads)


def main() -> None:
    cases = {"original": 0, "family_rename": 0, "reorder": 0, "argument_edit": 0, "ambiguity_rejection": 0, "placebo": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        program = base_program()
        variants = {
            "family_rename": rename_family(program, "map", "transform"),
            "reorder": reorder_overloads(program, rng),
            "argument_edit": argument_edit(program),
            "ambiguity_rejection": ambiguity_edit(program),
            "placebo": add_placebo_scope(program),
        }
        for architecture, run in ARCHITECTURES.items():
            row: dict[str, object] = {"seed": seed, "architecture": architecture}
            expected_original = resolve(program, "typed_overload_ledger")
            row["original_exact"] = run(program) == expected_original
            cases["original"] += int(row["original_exact"])
            for label, variant in variants.items():
                expected_variant = resolve(variant, "typed_overload_ledger")
                ok = run(variant) == expected_variant
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
        "typed_target": resolve(base_program(), "typed_overload_ledger"),
        "ambiguous_target": resolve(ambiguity_edit(base_program()), "typed_overload_ledger"),
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates")}, indent=2))


if __name__ == "__main__":
    main()
