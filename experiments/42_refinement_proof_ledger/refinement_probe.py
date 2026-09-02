"""Probe refinement predicates as verified proof obligations."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Value:
    value_id: int
    type_name: str
    annotations: tuple[str, ...] = ()


@dataclass(frozen=True)
class Step:
    step_id: int
    operation: str
    inputs: tuple[int, ...]
    input_types: tuple[str, ...]
    requirements: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class Program:
    values: tuple[Value, ...]
    steps: tuple[Step, ...]
    proofs: frozenset[tuple[int, str]]


def base_program() -> Program:
    return Program(
        values=(
            Value(0, "Int", ("nonzero", "range_1_10")),
            Value(1, "Array[Int]", ("len_3",)),
            Value(2, "Int", ("index_0_2",)),
            Value(3, "Int"),
        ),
        steps=(
            Step(0, "divide", (3, 0), ("Int", "Int"), ((1, "nonzero"),)),
            Step(1, "index", (1, 2), ("Array[Int]", "Int"), ((0, "len_3"), (1, "index_0_2"))),
        ),
        proofs=frozenset({(0, "nonzero"), (1, "len_3"), (2, "index_0_2")}),
    )


def values_by_id(program: Program) -> dict[int, Value]:
    return {value.value_id: value for value in program.values}


def target(program: Program) -> bool:
    values = values_by_id(program)
    for step in program.steps:
        for value_id, expected_type in zip(step.inputs, step.input_types):
            if values[value_id].type_name != expected_type:
                return False
        for input_index, predicate in step.requirements:
            value_id = step.inputs[input_index]
            if (value_id, predicate) not in program.proofs:
                return False
    return True


def base_type_checker(program: Program) -> bool:
    values = values_by_id(program)
    return all(
        values[value_id].type_name == expected_type
        for step in program.steps
        for value_id, expected_type in zip(step.inputs, step.input_types)
    )


def predicate_tags(program: Program) -> bool:
    values = values_by_id(program)
    return all(
        predicate in values[step.inputs[input_index]].annotations
        for step in program.steps
        for input_index, predicate in step.requirements
    ) and base_type_checker(program)


def proof_ledger(program: Program) -> bool:
    return target(program)


ARCHITECTURES: dict[str, Callable[[Program], bool]] = {
    "base_type_checker": base_type_checker,
    "predicate_tags": predicate_tags,
    "proof_ledger": proof_ledger,
}


def erase_proof(program: Program) -> Program:
    return replace(program, proofs=frozenset(proof for proof in program.proofs if proof != (0, "nonzero")))


def wrong_proof(program: Program) -> Program:
    proofs = frozenset(proof for proof in program.proofs if proof != (0, "nonzero")) | {(3, "nonzero")}
    return replace(program, proofs=proofs)


def corrupt_annotation(program: Program) -> Program:
    values = tuple(replace(value, annotations=tuple(annotation for annotation in value.annotations if annotation != "nonzero"))
                   if value.value_id == 0 else value for value in program.values)
    return replace(program, values=values)


def reorder_steps(program: Program, rng: random.Random) -> Program:
    steps = list(program.steps)
    rng.shuffle(steps)
    return replace(program, steps=tuple(steps))


def add_placebo(program: Program) -> Program:
    values = program.values + (Value(99, "Secret", ("oracle",)),)
    proofs = program.proofs | {(99, "oracle")}
    return replace(program, values=values, proofs=proofs)


def main() -> None:
    cases = {"original": 0, "erase_proof": 0, "wrong_proof": 0, "annotation_corruption": 0, "step_reorder": 0, "placebo": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        program = base_program()
        variants = {
            "erase_proof": erase_proof(program),
            "wrong_proof": wrong_proof(program),
            "annotation_corruption": corrupt_annotation(program),
            "step_reorder": reorder_steps(program, rng),
            "placebo": add_placebo(program),
        }
        for architecture, run in ARCHITECTURES.items():
            row: dict[str, object] = {"seed": seed, "architecture": architecture}
            row["original_exact"] = run(program) == target(program)
            cases["original"] += int(row["original_exact"])
            for label, variant in variants.items():
                ok = run(variant) == target(variant)
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
        "base_target": target(base_program()),
        "erased_proof_target": target(erase_proof(base_program())),
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates")}, indent=2))


if __name__ == "__main__":
    main()
