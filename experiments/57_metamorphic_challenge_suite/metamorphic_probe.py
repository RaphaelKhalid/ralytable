"""Probe metamorphic tests and audit their metadata for oracle leakage."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Program:
    left: int
    right: int
    operation: str
    variable_name: str = "x"


@dataclass(frozen=True)
class TestCase:
    name: str
    program: Program
    relation: str  # preserve or change
    metadata: tuple[tuple[str, str], ...] = ()


def evaluate(program: Program) -> int:
    if program.operation == "add":
        return program.left + program.right
    if program.operation == "subtract":
        return program.left - program.right
    if program.operation == "multiply":
        return program.left * program.right
    raise ValueError(program.operation)


def constant_shortcut(program: Program) -> int:
    return 7


def surface_sensitive(program: Program) -> int:
    return evaluate(program) + (hashlib.sha256(program.variable_name.encode()).digest()[0] % 2)


def semantic_evaluator(program: Program) -> int:
    return evaluate(program)


ARCHITECTURES: dict[str, Callable[[Program], int]] = {
    "constant_shortcut": constant_shortcut,
    "surface_sensitive": surface_sensitive,
    "semantic_evaluator": semantic_evaluator,
}


def base_program() -> Program:
    return Program(3, 4, "add")


def suite() -> tuple[TestCase, ...]:
    base = base_program()
    return (
        TestCase("alpha_rename", replace(base, variable_name="renamed"), "preserve"),
        TestCase("declaration_reorder", replace(base, left=4, right=3), "preserve"),
        TestCase("literal_delta", replace(base, right=5), "change"),
        TestCase("operator_delta", replace(base, operation="multiply"), "change"),
        TestCase("operand_swap_noncommutative", replace(base, operation="subtract", left=3, right=4), "change"),
    )


def leaked_metadata(test_cases: tuple[TestCase, ...]) -> list[str]:
    forbidden = {"answer", "expected_output", "oracle", "hidden_test", "solution"}
    findings: list[str] = []
    for test in test_cases:
        for key, value in test.metadata:
            if key.lower() in forbidden or any(token in value.lower() for token in forbidden):
                findings.append(test.name)
    return findings


def leaky_suite() -> tuple[TestCase, ...]:
    tests = list(suite())
    tests[0] = replace(tests[0], metadata=(("expected_output", str(evaluate(tests[0].program))),))
    return tuple(tests)


def score(architecture: Callable[[Program], int], tests: tuple[TestCase, ...], base: Program) -> dict[str, int]:
    base_output = architecture(base)
    preserve_pass = 0
    change_pass = 0
    for test in tests:
        output = architecture(test.program)
        if test.relation == "preserve":
            preserve_pass += int(output == base_output)
        else:
            change_pass += int(output != base_output and output == evaluate(test.program))
    return {"preserve_pass": preserve_pass, "change_pass": change_pass, "total_preserve": sum(test.relation == "preserve" for test in tests), "total_change": sum(test.relation == "change" for test in tests)}


def main() -> None:
    tests = suite()
    leaky = leaky_suite()
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        shuffled = list(tests)
        rng.shuffle(shuffled)
        variant = tuple(shuffled)
        for architecture, run in ARCHITECTURES.items():
            result = score(run, variant, base_program())
            rows.append({"seed": seed, "architecture": architecture, **result})
    summary = {
        "architectures": list(ARCHITECTURES),
        "suite_size": len(tests),
        "base_output": evaluate(base_program()),
        "leak_findings_clean": leaked_metadata(tests),
        "leak_findings_contaminated": leaked_metadata(leaky),
        "base_scores": {architecture: score(run, tests, base_program()) for architecture, run in ARCHITECTURES.items()},
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"base_scores": summary["base_scores"], "clean_leaks": summary["leak_findings_clean"], "contaminated_leaks": summary["leak_findings_contaminated"]}, indent=2))


if __name__ == "__main__":
    main()
