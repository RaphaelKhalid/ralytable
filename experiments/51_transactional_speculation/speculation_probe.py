"""Probe proof-gated speculative execution and side-effect isolation."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Effect:
    kind: str  # memory or external
    payload: str


@dataclass(frozen=True)
class Candidate:
    candidate_id: int
    score: int
    effects: tuple[Effect, ...]
    proof_valid: bool


@dataclass(frozen=True)
class Program:
    candidates: tuple[Candidate, ...]


def base_program() -> Program:
    return Program(
        candidates=(
            Candidate(0, 100, (Effect("memory", "temp_bad"), Effect("external", "email_bad")), False),
            Candidate(1, 80, (Effect("memory", "answer"), Effect("external", "write_good")), True),
        )
    )


def target(program: Program) -> tuple[int | None, tuple[Effect, ...]]:
    valid = [candidate for candidate in program.candidates if candidate.proof_valid]
    if not valid:
        return None, ()
    selected = max(valid, key=lambda candidate: (candidate.score, -candidate.candidate_id))
    return selected.candidate_id, selected.effects


def eager_executor(program: Program) -> tuple[int | None, tuple[Effect, ...]]:
    valid = [candidate for candidate in program.candidates if candidate.proof_valid]
    selected = max(valid, key=lambda candidate: (candidate.score, -candidate.candidate_id)) if valid else None
    effects = tuple(effect for candidate in program.candidates for effect in candidate.effects)
    return (selected.candidate_id if selected else None), effects


def undo_log(program: Program) -> tuple[int | None, tuple[Effect, ...]]:
    valid = [candidate for candidate in program.candidates if candidate.proof_valid]
    selected = max(valid, key=lambda candidate: (candidate.score, -candidate.candidate_id)) if valid else None
    # Memory mutations can be undone, but external effects are irreversible.
    leaked = tuple(effect for candidate in program.candidates if not candidate.proof_valid for effect in candidate.effects if effect.kind == "external")
    committed = selected.effects if selected else ()
    return (selected.candidate_id if selected else None), leaked + committed


def transactional_ledger(program: Program) -> tuple[int | None, tuple[Effect, ...]]:
    # Speculation is isolated; the commit record is written only after proof
    # validation and candidate selection.
    return target(program)


ARCHITECTURES: dict[str, Callable[[Program], tuple[int | None, tuple[Effect, ...]]]] = {
    "eager_executor": eager_executor,
    "undo_log": undo_log,
    "transactional_ledger": transactional_ledger,
}


def reorder_candidates(program: Program, rng: random.Random) -> Program:
    candidates = list(program.candidates)
    rng.shuffle(candidates)
    return replace(program, candidates=tuple(candidates))


def late_failure(program: Program) -> Program:
    candidates = tuple(replace(candidate, proof_valid=False) if candidate.candidate_id == 1 else candidate for candidate in program.candidates)
    return replace(program, candidates=candidates)


def invalid_only(program: Program) -> Program:
    return replace(program, candidates=tuple(replace(candidate, proof_valid=False) for candidate in program.candidates))


def add_placebo(program: Program) -> Program:
    placebo = Candidate(99, 1000, (Effect("external", "oracle_leak"),), False)
    return replace(program, candidates=program.candidates + (placebo,))


def main() -> None:
    cases = {"original": 0, "reorder": 0, "late_failure_isolation": 0, "all_invalid": 0, "placebo_isolation": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        program = base_program()
        variants = {
            "reorder": reorder_candidates(program, rng),
            "late_failure_isolation": late_failure(program),
            "all_invalid": invalid_only(program),
            "placebo_isolation": add_placebo(program),
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
        "base_target": {"candidate": target(base_program())[0], "effects": [(effect.kind, effect.payload) for effect in target(base_program())[1]]},
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates", "base_target")}, indent=2))


if __name__ == "__main__":
    main()
