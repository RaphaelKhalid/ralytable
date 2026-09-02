"""Probe aliasing, borrow intervals, and move safety."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Lease:
    resource: str
    borrower: str
    kind: str  # shared, mut, or move
    start: int
    end: int
    reachable: bool = True


@dataclass(frozen=True)
class Use:
    resource: str
    at: int
    reachable: bool = True


@dataclass(frozen=True)
class Program:
    leases: tuple[Lease, ...]
    uses: tuple[Use, ...]


def base_program() -> Program:
    return Program(
        leases=(
            Lease("buf", "reader_a", "shared", 0, 2),
            Lease("buf", "reader_b", "shared", 0, 2),
            Lease("buf", "writer_a", "mut", 3, 5),
            Lease("buf", "writer_b", "mut", 6, 7),
            Lease("token", "consumer", "move", 1, 1),
        ),
        uses=(Use("buf", 4), Use("buf", 6), Use("buf", 7)),
    )


def overlaps(left: Lease, right: Lease) -> bool:
    return left.start <= right.end and right.start <= left.end


def ownership_target(program: Program) -> bool:
    leases = [lease for lease in program.leases if lease.reachable]
    uses = [use for use in program.uses if use.reachable]
    resources = {lease.resource for lease in leases} | {use.resource for use in uses}
    for resource in resources:
        current = [lease for lease in leases if lease.resource == resource]
        for index, left in enumerate(current):
            if left.kind == "move":
                if any(other is not left and overlaps(left, other) for other in current):
                    return False
                if any(use.resource == resource and use.at > left.start for use in uses):
                    return False
            for right in current[index + 1:]:
                if overlaps(left, right) and (left.kind != "shared" or right.kind != "shared"):
                    return False
    return True


def value_only(program: Program) -> bool:
    del program
    return True


def interval_borrow_checker(program: Program) -> bool:
    leases = [lease for lease in program.leases if lease.reachable and lease.kind != "move"]
    for index, left in enumerate(leases):
        for right in leases[index + 1:]:
            if left.resource == right.resource and overlaps(left, right):
                if left.kind != "shared" or right.kind != "shared":
                    return False
    return True


def ownership_ledger(program: Program) -> bool:
    return ownership_target(program)


ARCHITECTURES: dict[str, Callable[[Program], bool]] = {
    "value_only": value_only,
    "interval_borrow_checker": interval_borrow_checker,
    "ownership_ledger": ownership_ledger,
}


def rename_resource(program: Program) -> Program:
    leases = tuple(replace(lease, resource="buffer" if lease.resource == "buf" else "ticket")
                   for lease in program.leases)
    uses = tuple(replace(use, resource="buffer" if use.resource == "buf" else "ticket") for use in program.uses)
    return replace(program, leases=leases, uses=uses)


def reorder_resources(program: Program, rng: random.Random) -> Program:
    leases = list(program.leases)
    rng.shuffle(leases)
    uses = list(program.uses)
    rng.shuffle(uses)
    return replace(program, leases=tuple(leases), uses=tuple(uses))


def overlap_violation(program: Program) -> Program:
    leases = program.leases + (Lease("buf", "writer_bad", "mut", 1, 2),)
    return replace(program, leases=leases)


def move_use_violation(program: Program) -> Program:
    uses = program.uses + (Use("token", 2),)
    return replace(program, uses=uses)


def unreachable_placebo(program: Program) -> Program:
    leases = program.leases + (Lease("buf", "dead_writer", "mut", 0, 100, reachable=False),)
    uses = program.uses + (Use("buf", 50, reachable=False),)
    return replace(program, leases=leases, uses=uses)


def main() -> None:
    cases = {"original": 0, "rename": 0, "reorder": 0, "overlap_rejection": 0, "move_rejection": 0, "placebo": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        program = base_program()
        variants = {
            "rename": rename_resource(program),
            "reorder": reorder_resources(program, rng),
            "overlap_rejection": overlap_violation(program),
            "move_rejection": move_use_violation(program),
            "placebo": unreachable_placebo(program),
        }
        for architecture, run in ARCHITECTURES.items():
            row: dict[str, object] = {"seed": seed, "architecture": architecture}
            row["original_exact"] = run(program) == ownership_target(program)
            cases["original"] += int(row["original_exact"])
            for label, variant in variants.items():
                ok = run(variant) == ownership_target(variant)
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
        "base_target": ownership_target(base_program()),
        "overlap_target": ownership_target(overlap_violation(base_program())),
        "move_target": ownership_target(move_use_violation(base_program())),
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates")}, indent=2))


if __name__ == "__main__":
    main()
