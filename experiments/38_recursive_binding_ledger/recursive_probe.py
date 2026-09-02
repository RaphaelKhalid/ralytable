"""Probe legality and identity of recursive binding groups."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Definition:
    binder: int
    scope: int
    name: str
    recursive_group: int


@dataclass(frozen=True)
class Reference:
    origin: int
    target_name: str


@dataclass(frozen=True)
class Program:
    definitions: tuple[Definition, ...]
    references: tuple[Reference, ...]
    parent: tuple[tuple[int, int], ...]


def base_program() -> Program:
    # f and g are mutually recursive. h is non-recursive but can use the
    # earlier f. All definitions share a scope so a scope-only map cannot
    # enforce recursive-group legality.
    return Program(
        definitions=(
            Definition(0, 0, "f", 1),
            Definition(1, 0, "g", 1),
            Definition(2, 0, "h", 0),
        ),
        references=(
            Reference(0, "f"),
            Reference(0, "g"),
            Reference(1, "f"),
            Reference(2, "f"),
        ),
        parent=(),
    )


def lookup_scope(program: Program, scope: int, name: str) -> Definition | None:
    scopes = {definition.scope for definition in program.definitions}
    by_scope: dict[tuple[int, str], Definition] = {}
    for definition in program.definitions:
        by_scope[(definition.scope, definition.name)] = definition
    current: int | None = scope
    parents = dict(program.parent)
    while current is not None:
        if (current, name) in by_scope:
            return by_scope[(current, name)]
        current = parents.get(current)
    del scopes
    return None


def result(program: Program, policy: str) -> tuple[tuple[int | None, bool], ...]:
    positions = {definition.binder: index for index, definition in enumerate(program.definitions)}
    by_binder = {definition.binder: definition for definition in program.definitions}
    output: list[tuple[int | None, bool]] = []
    for reference in program.references:
        origin = by_binder[reference.origin]
        target = lookup_scope(program, origin.scope, reference.target_name)
        if target is None:
            output.append((None, False))
            continue
        if policy == "prior_decl_sequence":
            legal = positions[target.binder] < positions[origin.binder]
        elif policy == "scope_name_map":
            legal = True
        else:
            same_recursive_group = (
                origin.recursive_group != 0
                and origin.recursive_group == target.recursive_group
            )
            prior_definition = positions[target.binder] < positions[origin.binder]
            legal = same_recursive_group or prior_definition
        output.append((target.binder, legal))
    return tuple(output)


ARCHITECTURES: dict[str, Callable[[Program], tuple[tuple[int | None, bool], ...]]] = {
    "prior_decl_sequence": lambda program: result(program, "prior_decl_sequence"),
    "scope_name_map": lambda program: result(program, "scope_name_map"),
    "recursive_group_ledger": lambda program: result(program, "recursive_group_ledger"),
}


def legal_target(program: Program) -> tuple[tuple[int | None, bool], ...]:
    return result(program, "recursive_group_ledger")


def alpha_rename(program: Program, rng: random.Random) -> Program:
    names = {definition.binder: f"d{rng.randrange(100_000)}_{definition.binder}" for definition in program.definitions}
    definitions = tuple(replace(definition, name=names[definition.binder]) for definition in program.definitions)
    references = tuple(
        replace(reference, target_name=names[next(
            definition.binder
            for definition in program.definitions
            if definition.name == reference.target_name
        )])
        for reference in program.references
    )
    return replace(program, definitions=definitions, references=references)


def reorder_recursive_group(program: Program, rng: random.Random) -> Program:
    recursive = [definition for definition in program.definitions if definition.recursive_group == 1]
    nonrecursive = [definition for definition in program.definitions if definition.recursive_group == 0]
    rng.shuffle(recursive)
    return replace(program, definitions=tuple(recursive + nonrecursive))


def illegal_nonrecursive_self(program: Program) -> Program:
    definitions = program.definitions + (Definition(3, 0, "k", 0),)
    references = program.references + (Reference(3, "k"),)
    return replace(program, definitions=definitions, references=references)


def add_unreachable_group(program: Program) -> Program:
    definitions = program.definitions + (
        Definition(4, 2, "f", 2),
        Definition(5, 2, "g", 2),
    )
    return replace(program, definitions=definitions, parent=((2, 2),))


def main() -> None:
    totals = {"original": 0, "alpha_rename": 0, "group_reorder": 0, "illegal_rejection": 0, "placebo": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        program = base_program()
        variants = {
            "alpha_rename": alpha_rename(program, rng),
            "group_reorder": reorder_recursive_group(program, rng),
            "illegal_rejection": illegal_nonrecursive_self(program),
            "placebo": add_unreachable_group(program),
        }
        for architecture, run in ARCHITECTURES.items():
            row: dict[str, object] = {"seed": seed, "architecture": architecture}
            expected_original = legal_target(program)
            row["original_exact"] = run(program) == expected_original
            totals["original"] += int(row["original_exact"])
            for label, variant in variants.items():
                expected_variant = legal_target(variant)
                actual = run(variant)
                if label == "illegal_rejection":
                    # The final k self-reference must be rejected while the
                    # prior four legal references remain unchanged.
                    ok = actual == expected_variant and actual[-1][1] is False
                else:
                    ok = actual == expected_variant
                row[f"{label}_ok"] = ok
                totals[label] += int(ok)
            rows.append(row)
    total_runs = 5 * len(ARCHITECTURES)
    summary = {
        "seeds": 5,
        "architectures": list(ARCHITECTURES),
        "total_architecture_runs": total_runs,
        "pass_counts": totals,
        "pass_rates": {key: round(value / total_runs, 4) for key, value in totals.items()},
        "legal_original": legal_target(base_program()),
        "illegal_self_reference": legal_target(illegal_nonrecursive_self(base_program())),
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates")}, indent=2))


if __name__ == "__main__":
    main()
