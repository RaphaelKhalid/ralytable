"""Compare explicit and opaque identity channels under distractor load."""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Task:
    entities: tuple[str, ...]
    query: int
    state_query: int
    placebo: str

    def state_edit(self) -> "Task":
        return replace(self, state_query=(self.state_query + 1) % len(self.entities))

    def raw_edit(self) -> "Task":
        # Held-out raw-text perturbation; the structured state is held fixed by
        # the evaluator when this intervention is applied.
        return replace(self, entities=tuple(name + "_raw" for name in self.entities))

    def placebo_edit(self) -> "Task":
        return replace(self, placebo=self.placebo + "_unused")


def render(task: Task, architecture: str, *, raw_override: tuple[str, ...] | None = None) -> str | None:
    entities = raw_override if raw_override is not None else task.entities
    if architecture == "opaque_residual":
        return entities[task.query]
    if architecture == "typed_copy_table":
        return task.entities[task.state_query]
    if architecture == "hashed_slots":
        slots: dict[int, str] = {}
        for entity in task.entities:
            bucket = sum(entity.encode()) % 8
            slots[bucket] = entity
        bucket = sum(task.entities[task.state_query].encode()) % 8
        return slots.get(bucket)
    raise ValueError(architecture)


def evaluate(task: Task, architecture: str) -> dict[str, object]:
    baseline = render(task, architecture)
    raw_invariant = render(task, architecture, raw_override=task.raw_edit().entities) == baseline
    state_changed = render(task.state_edit(), architecture) != baseline
    placebo_preserved = render(task.placebo_edit(), architecture) == baseline
    return {"identity_correct": baseline == task.entities[task.state_query],
            "raw_path_invariance": raw_invariant,
            "relevant_state_change": state_changed,
            "placebo_preservation": placebo_preserved}


def main() -> None:
    architectures = ("opaque_residual", "typed_copy_table", "hashed_slots")
    seeds = (11, 23, 37, 41, 53)
    lengths = (4, 8, 16, 32)
    runs = []
    metrics = ("identity_correct", "raw_path_invariance", "relevant_state_change", "placebo_preservation")
    for seed in seeds:
        for length in lengths:
            rng = random.Random(seed * 100 + length)
            tasks = []
            for _ in range(160):
                entities = tuple(f"entity_{i}_{rng.randrange(100000)}" for i in range(length))
                query = rng.randrange(length)
                tasks.append(Task(entities, query, query, "unused"))
            for architecture in architectures:
                values = [evaluate(task, architecture) for task in tasks]
                row = {"seed": seed, "length": length, "architecture": architecture,
                       "tasks": len(tasks), **{metric: statistics.mean(float(v[metric]) for v in values) for metric in metrics}}
                runs.append(row)
                print(json.dumps(row, sort_keys=True))
    aggregate = {}
    for architecture in architectures:
        aggregate[architecture] = {str(length): {metric: statistics.mean(r[metric] for r in runs
                                      if r["architecture"] == architecture and r["length"] == length)
                                                 for metric in metrics}
                                   for length in lengths}
    output = {"runs": runs, "aggregate": aggregate,
              "note": "Synthetic identity-channel probe; no learned model or benchmark was run."}
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
