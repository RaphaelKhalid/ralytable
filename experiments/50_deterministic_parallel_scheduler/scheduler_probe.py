"""Probe deterministic scheduling of independent typed-ledger branches."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Task:
    task_id: int
    label: str
    dependencies: tuple[int, ...] = ()


@dataclass(frozen=True)
class Graph:
    tasks: tuple[Task, ...]


def base_graph() -> Graph:
    # 2 and 3 are independent in dataflow but their writes are explicitly
    # ordered. The package node depends on both.
    return Graph(
        tasks=(
            Task(0, "read_config"),
            Task(1, "read_schema"),
            Task(2, "write_config", (0,)),
            Task(3, "write_schema", (1, 2)),
            Task(4, "package", (2, 3)),
        )
    )


def schedule_fifo(graph: Graph, rng: random.Random | None = None) -> tuple[int, ...]:
    del rng
    tasks = {task.task_id: task for task in graph.tasks}
    done: set[int] = set()
    output: list[int] = []
    while len(done) < len(tasks):
        ready = [task for task in graph.tasks if task.task_id not in done and set(task.dependencies) <= done]
        if not ready:
            raise ValueError("cycle")
        task = ready[0]
        done.add(task.task_id)
        output.append(task.task_id)
    return tuple(output)


def schedule_random(graph: Graph, rng: random.Random | None = None) -> tuple[int, ...]:
    if rng is None:
        rng = random.Random(0)
    tasks = {task.task_id: task for task in graph.tasks}
    done: set[int] = set()
    output: list[int] = []
    while len(done) < len(tasks):
        ready = [task for task in tasks.values() if task.task_id not in done and set(task.dependencies) <= done]
        if not ready:
            raise ValueError("cycle")
        rng.shuffle(ready)
        task = ready[0]
        done.add(task.task_id)
        output.append(task.task_id)
    return tuple(output)


def schedule_semantic(graph: Graph, rng: random.Random | None = None) -> tuple[int, ...]:
    del rng
    tasks = {task.task_id: task for task in graph.tasks}
    done: set[int] = set()
    output: list[int] = []
    while len(done) < len(tasks):
        ready = [task for task in tasks.values() if task.task_id not in done and set(task.dependencies) <= done]
        if not ready:
            raise ValueError("cycle")
        task = min(ready, key=lambda candidate: (candidate.label, candidate.task_id))
        done.add(task.task_id)
        output.append(task.task_id)
    return tuple(output)


ARCHITECTURES: dict[str, Callable[[Graph, random.Random | None], tuple[int, ...]]] = {
    "input_fifo": schedule_fifo,
    "random_ready_queue": schedule_random,
    "semantic_topological": schedule_semantic,
}


def reorder_tasks(graph: Graph, rng: random.Random) -> Graph:
    tasks = list(graph.tasks)
    rng.shuffle(tasks)
    return replace(graph, tasks=tuple(tasks))


def valid_topological(graph: Graph, schedule: tuple[int, ...]) -> bool:
    positions = {task_id: index for index, task_id in enumerate(schedule)}
    return all(positions[dependency] < positions[task.task_id] for task in graph.tasks for dependency in task.dependencies)


def main() -> None:
    cases = {"original_valid": 0, "reorder_invariance": 0, "repeatability": 0, "ordering_constraint": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        graph = base_graph()
        reordered = reorder_tasks(graph, rng)
        expected = schedule_semantic(graph)
        for architecture, run in ARCHITECTURES.items():
            base = run(graph, random.Random(seed))
            row: dict[str, object] = {"seed": seed, "architecture": architecture, "base_schedule": base}
            original_valid = valid_topological(graph, base)
            cases["original_valid"] += int(original_valid)
            reorder_ok = run(reordered, random.Random(seed + 100)) == expected
            cases["reorder_invariance"] += int(reorder_ok)
            repeated = [run(graph, random.Random(seed + trial)) for trial in range(10)]
            repeat_ok = len(set(repeated)) == 1
            cases["repeatability"] += int(repeat_ok)
            constraint_ok = base.index(2) < base.index(3)
            cases["ordering_constraint"] += int(constraint_ok)
            row.update({"original_valid": original_valid, "reorder_invariant": reorder_ok, "repeatable": repeat_ok, "ordering_constraint": constraint_ok, "repeated_schedules": repeated})
            rows.append(row)
    total_runs = 5 * len(ARCHITECTURES)
    summary = {
        "seeds": 5,
        "architectures": list(ARCHITECTURES),
        "total_architecture_runs": total_runs,
        "semantic_expected_schedule": schedule_semantic(base_graph()),
        "pass_counts": cases,
        "pass_rates": {key: round(value / total_runs, 4) for key, value in cases.items()},
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("semantic_expected_schedule", "pass_counts", "pass_rates")}, indent=2))


if __name__ == "__main__":
    main()
