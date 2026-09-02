"""Probe beam search over typed program graphs with separate semantic tests."""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OPS = ("filter", "sort", "unique", "reverse", "count")


@dataclass(frozen=True)
class Task:
    target: tuple[str, ...]
    public: tuple[tuple[tuple[int, ...], int, int, object], ...]
    hidden: tuple[tuple[tuple[int, ...], int, int, object], ...]


def execute(values: tuple[int, ...], threshold: int, take: int, program: tuple[str, ...]) -> object:
    current: object = list(values)
    for op in program:
        if op == "filter":
            current = [x for x in current if x > threshold]
        elif op == "sort":
            current = sorted(current)
        elif op == "unique":
            seen: set[int] = set()
            current = [x for x in current if not (x in seen or seen.add(x))]
        elif op == "reverse":
            current = list(reversed(current))
        elif op == "count":
            current = len(current)
        else:
            raise ValueError(op)
        if isinstance(current, list) and op != "count":
            current = current[:take]
    return current


def make_task(rng: random.Random) -> Task:
    length = rng.randrange(3, 6)
    # count changes the value type and therefore must terminate a chain.
    target = tuple(rng.choice(OPS[:-1]) for _ in range(length - 1))
    if rng.randrange(2):
        target += ("count",)
    else:
        target += (rng.choice(OPS[:-1]),)
    # Public cases are intentionally small and can leave some equivalent
    # programs indistinguishable; hidden cases are the scoring-only check.
    def cases(count: int, salt: int) -> tuple[tuple[tuple[int, ...], int, int, object], ...]:
        local = random.Random(rng.randrange(1_000_000) + salt)
        rows = []
        for _ in range(count):
            values = tuple(local.randrange(-4, 5) for _ in range(local.randrange(3, 7)))
            threshold = local.randrange(-2, 3)
            take = local.randrange(2, 5)
            rows.append((values, threshold, take, execute(values, threshold, take, target)))
        return tuple(rows)
    return Task(target, cases(2, 17), cases(4, 71))


def type_valid(program: tuple[str, ...]) -> bool:
    # All operations accept/return List[Int] except count, which terminates the
    # chain. This catches malformed graphs but deliberately accepts many
    # semantically wrong yet well-typed alternatives.
    seen_count = False
    for op in program:
        if op not in OPS or seen_count:
            return False
        seen_count = op == "count"
    return bool(program)


def candidates(task: Task, seed: int, width: int = 8) -> list[tuple[str, ...]]:
    rng = random.Random(seed)
    rows = [task.target]
    for _ in range(width * 3):
        program = list(task.target)
        position = rng.randrange(len(program))
        program[position] = rng.choice([op for op in OPS if op != program[position]])
        candidate = tuple(program)
        if candidate not in rows:
            rows.append(candidate)
        if len(rows) >= width:
            break
    rng.shuffle(rows)
    return rows


def public_pass(task: Task, program: tuple[str, ...]) -> bool:
    try:
        return all(execute(values, threshold, take, program) == expected
                   for values, threshold, take, expected in task.public)
    except (TypeError, ValueError):
        return False


def hidden_pass(task: Task, program: tuple[str, ...]) -> bool:
    try:
        return all(execute(values, threshold, take, program) == expected
                   for values, threshold, take, expected in task.hidden)
    except (TypeError, ValueError):
        return False


def select(task: Task, ranked: list[tuple[str, ...]], beam: int, verifier: str) -> tuple[str, ...] | None:
    pool = ranked[:beam]
    if verifier == "none":
        return pool[0] if pool else None
    typed = [program for program in pool if type_valid(program)]
    if verifier == "type":
        return typed[0] if typed else None
    if verifier == "public_execution":
        return next((program for program in typed if public_pass(task, program)), None)
    raise ValueError(verifier)


def evaluate(seed: int, count: int = 160) -> list[dict[str, object]]:
    rng = random.Random(seed)
    tasks = [make_task(rng) for _ in range(count)]
    rows = []
    for beam in (1, 4, 8):
        for verifier in ("none", "type", "public_execution"):
            selected = [select(task, candidates(task, seed * 10000 + i), beam, verifier)
                        for i, task in enumerate(tasks)]
            hidden = [program is not None and hidden_pass(task, program)
                      for task, program in zip(tasks, selected)]
            exact = [program == task.target for task, program in zip(tasks, selected)]
            rows.append({"seed": seed, "beam": beam, "verifier": verifier,
                         "hidden_pass": sum(hidden) / len(hidden),
                         "exact_graph": sum(exact) / len(exact),
                         "selected": sum(program is not None for program in selected),
                         "tasks": len(tasks)})
    return rows


def main() -> None:
    seeds = (11, 23, 37, 41, 53)
    runs = []
    for seed in seeds:
        for row in evaluate(seed):
            runs.append(row)
            print(json.dumps(row, sort_keys=True), flush=True)
    aggregate = {}
    for beam in (1, 4, 8):
        for verifier in ("none", "type", "public_execution"):
            vals = [r["hidden_pass"] for r in runs if r["beam"] == beam and r["verifier"] == verifier]
            exact = [r["exact_graph"] for r in runs if r["beam"] == beam and r["verifier"] == verifier]
            aggregate[f"beam{beam}_{verifier}"] = {
                "hidden_pass_mean": statistics.mean(vals),
                "hidden_pass_seed_sd": statistics.stdev(vals),
                "exact_graph_mean": statistics.mean(exact),
            }
    output = {"seeds": list(seeds), "runs": runs, "aggregate": aggregate,
              "note": "Synthetic hypothesis beam; no learned model or benchmark was run."}
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
