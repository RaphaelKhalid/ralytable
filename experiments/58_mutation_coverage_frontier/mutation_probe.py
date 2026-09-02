"""Measure metamorphic-suite mutation coverage against shortcut families."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Program:
    left: int
    right: int
    operation: str
    variable_name: str = "x"
    dead_code: int = 0


@dataclass(frozen=True)
class TestCase:
    name: str
    program: Program
    relation: str


def evaluate(program: Program) -> int:
    if program.operation == "add":
        return program.left + program.right
    if program.operation == "subtract":
        return program.left - program.right
    if program.operation == "multiply":
        return program.left * program.right
    raise ValueError(program.operation)


def base() -> Program:
    return Program(3, 4, "add")


def shortcuts() -> dict[str, Callable[[Program], int]]:
    return {
        "constant": lambda program: 7,
        "first_argument": lambda program: program.left,
        "commutative_add_only": lambda program: program.left + program.right,
        "surface_sensitive": lambda program: evaluate(program) + len(program.variable_name),
        "semantic": evaluate,
    }


def surface_suite(program: Program) -> tuple[TestCase, ...]:
    return (
        TestCase("alpha_rename", replace(program, variable_name="renamed"), "preserve"),
        TestCase("declaration_reorder", replace(program, left=program.right, right=program.left), "preserve"),
    )


def typed_core_suite(program: Program) -> tuple[TestCase, ...]:
    return surface_suite(program) + (
        TestCase("literal_delta", replace(program, right=program.right + 1), "change"),
        TestCase("operator_delta", replace(program, operation="multiply"), "change"),
        TestCase("operand_swap_noncommutative", replace(program, operation="subtract"), "change"),
    )


def structural_suite(program: Program) -> tuple[TestCase, ...]:
    return typed_core_suite(program) + (
        TestCase("dead_code_placebo", replace(program, dead_code=99), "preserve"),
        TestCase("large_literal_delta", replace(program, left=20, right=1), "change"),
    )


def passes_suite(run: Callable[[Program], int], tests: tuple[TestCase, ...], program: Program) -> bool:
    base_output = run(program)
    return all(
        (run(test.program) == base_output if test.relation == "preserve" else run(test.program) != base_output and run(test.program) == evaluate(test.program))
        for test in tests
    )


def main() -> None:
    program = base()
    suites = {
        "surface_only": surface_suite(program),
        "typed_core": typed_core_suite(program),
        "structural_plus": structural_suite(program),
    }
    mutation_matrix: dict[str, dict[str, bool]] = {}
    for suite_name, tests in suites.items():
        mutation_matrix[suite_name] = {name: not passes_suite(run, tests, program) for name, run in shortcuts().items()}
    summary = {
        "suite_sizes": {name: len(tests) for name, tests in suites.items()},
        "mutations": list(shortcuts()),
        "killed_matrix": mutation_matrix,
        "killed_counts": {name: sum(row.values()) for name, row in mutation_matrix.items()},
        "surviving_mutants": {name: [mutant for mutant, killed in row.items() if not killed] for name, row in mutation_matrix.items()},
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"suite_sizes": summary["suite_sizes"], "killed_counts": summary["killed_counts"], "surviving_mutants": summary["surviving_mutants"]}, indent=2))


if __name__ == "__main__":
    main()
