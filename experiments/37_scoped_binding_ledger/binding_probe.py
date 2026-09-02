"""Probe lexical identity channels under repeated names and shadowing."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Binding:
    binder: int
    scope: int
    name: str
    type_name: str


@dataclass(frozen=True)
class Program:
    bindings: tuple[Binding, ...]
    references: tuple[tuple[int, str], ...]
    parent: tuple[tuple[int, int], ...]


def base_program() -> Program:
    # Binder 0 is an outer list; binder 1 shadows its name with an integer.
    # Binder 2 is a sibling local. Scope 2 is nested in scope 1 and has no
    # local x, so its x must resolve to the shadowing binder 1.
    return Program(
        bindings=(
            Binding(0, 0, "x", "List[Int]"),
            Binding(1, 1, "x", "Int"),
            Binding(2, 1, "y", "Bool"),
            Binding(3, 2, "z", "String"),
        ),
        references=((0, "x"), (1, "x"), (1, "y"), (2, "x"), (2, "z")),
        parent=((1, 0), (2, 1)),
    )


def parent_map(program: Program) -> dict[int, int]:
    return dict(program.parent)


def expected(program: Program) -> tuple[int | None, ...]:
    by_scope: dict[tuple[int, str], Binding] = {}
    for binding in program.bindings:
        by_scope[(binding.scope, binding.name)] = binding
    parents = parent_map(program)
    result: list[int | None] = []
    for scope, name in program.references:
        current: int | None = scope
        target = None
        while current is not None:
            found = by_scope.get((current, name))
            if found is not None:
                target = found.binder
                break
            current = parents.get(current)
        result.append(target)
    return tuple(result)


def position_sequence(program: Program) -> tuple[int | None, ...]:
    names = [binding.name for binding in program.bindings]
    binders = [binding.binder for binding in program.bindings]
    return tuple(
        binders[names.index(name)] if name in names else None
        for _, name in program.references
    )


def flat_name_map(program: Program) -> tuple[int | None, ...]:
    by_name: dict[str, int] = {}
    for binding in program.bindings:
        by_name[binding.name] = binding.binder
    return tuple(by_name.get(name) for _, name in program.references)


def scoped_name_map(program: Program) -> tuple[int | None, ...]:
    by_scope: dict[tuple[int, str], int] = {}
    for binding in program.bindings:
        by_scope[(binding.scope, binding.name)] = binding.binder
    parents = parent_map(program)
    output: list[int | None] = []
    for scope, name in program.references:
        current: int | None = scope
        target = None
        while current is not None:
            if (current, name) in by_scope:
                target = by_scope[(current, name)]
                break
            current = parents.get(current)
        output.append(target)
    return tuple(output)


def scoped_typed_ledger(program: Program) -> tuple[tuple[int | None, str | None], ...]:
    by_scope: dict[tuple[int, str], Binding] = {}
    for binding in program.bindings:
        by_scope[(binding.scope, binding.name)] = binding
    parents = parent_map(program)
    output: list[tuple[int | None, str | None]] = []
    for scope, name in program.references:
        current: int | None = scope
        target = None
        while current is not None:
            found = by_scope.get((current, name))
            if found is not None:
                target = (found.binder, found.type_name)
                break
            current = parents.get(current)
        output.append(target or (None, None))
    return tuple(output)


ARCHITECTURES: dict[str, Callable[[Program], object]] = {
    "position_sequence": position_sequence,
    "flat_name_map": flat_name_map,
    "scoped_name_map": scoped_name_map,
    "scoped_typed_ledger": scoped_typed_ledger,
}


def alpha_rename(program: Program, rng: random.Random) -> Program:
    names = [f"v{rng.randrange(10_000)}_{binding.binder}" for binding in program.bindings]
    mapping = {(binding.scope, binding.name): names[binding.binder] for binding in program.bindings}
    renamed = tuple(replace(binding, name=names[binding.binder]) for binding in program.bindings)
    references = tuple((scope, mapping[(scope, name)]) if (scope, name) in mapping else (scope, name)
                      for scope, name in program.references)
    # References that resolve through a parent scope need the renamed parent
    # name, while a local name keeps its local spelling.
    fixed: list[tuple[int, str]] = []
    original_expected = expected(program)
    for (scope, name), binder in zip(program.references, original_expected):
        if binder is None:
            fixed.append((scope, name))
        else:
            fixed.append((scope, names[binder]))
    del references
    return replace(program, bindings=renamed, references=tuple(fixed))


def reorder_declarations(program: Program, rng: random.Random) -> Program:
    bindings = list(program.bindings)
    rng.shuffle(bindings)
    return replace(program, bindings=tuple(bindings))


def binding_change(program: Program) -> Program:
    refs = list(program.references)
    # In scope 2, x normally resolves to binder 1. Pointing that occurrence
    # at the outer spelling is a semantic binding edit, not a placebo.
    bindings = tuple(replace(binding, name="outer_x" if binding.binder == 0 else binding.name)
                     for binding in program.bindings)
    refs[0] = (0, "outer_x")
    refs[3] = (2, "outer_x")
    return replace(program, bindings=bindings, references=tuple(refs))


def add_placebo_scope(program: Program) -> Program:
    # An unreachable scope may repeat x without changing any live reference.
    # A global map should nevertheless be sensitive to this irrelevant entry.
    bindings = program.bindings + (Binding(4, 3, "x", "Bytes"),)
    return replace(program, bindings=bindings)


def score_outputs(actual: object, target: object) -> bool:
    return actual == target


def main() -> None:
    seeds = range(5)
    cases = {"original": 0, "alpha_rename": 0, "reorder": 0, "binding_change": 0, "placebo": 0}
    rows: list[dict[str, object]] = []
    for seed in seeds:
        rng = random.Random(seed)
        program = base_program()
        original_target = expected(program)
        changed_target = expected(binding_change(program))
        transformed = {
            "alpha_rename": alpha_rename(program, rng),
            "reorder": reorder_declarations(program, rng),
            "binding_change": binding_change(program),
            "placebo": add_placebo_scope(program),
        }
        for name, architecture in ARCHITECTURES.items():
            base = architecture(program)
            original_ok = score_outputs(base, original_target if name != "scoped_typed_ledger" else tuple((b, next(x.type_name for x in program.bindings if x.binder == b)) for b in original_target))
            cases["original"] += int(original_ok)
            row = {"seed": seed, "architecture": name, "original_exact": original_ok}
            for label, variant in transformed.items():
                target = changed_target if label == "binding_change" else original_target
                if name == "scoped_typed_ledger":
                    target_obj = tuple((b, next((x.type_name for x in variant.bindings if x.binder == b), None)) if b is not None else (None, None) for b in target)
                else:
                    target_obj = target
                ok = score_outputs(architecture(variant), target_obj)
                row[f"{label}_ok"] = ok
                cases[label] += int(ok)
            rows.append(row)
    totals = len(seeds) * len(ARCHITECTURES)
    summary = {
        "seeds": len(seeds),
        "architectures": list(ARCHITECTURES),
        "total_architecture_runs": totals,
        "pass_counts": cases,
        "pass_rates": {key: round(value / totals, 4) for key, value in cases.items()},
        "rows": rows,
        "targets": {
            "original": expected(base_program()),
            "binding_change": expected(binding_change(base_program())),
        },
    }
    output = Path(__file__).with_name("summary.json")
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates")}, indent=2))


if __name__ == "__main__":
    main()
