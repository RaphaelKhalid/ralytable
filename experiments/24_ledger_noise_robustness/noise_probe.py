"""Test one concrete claimed advantage of a content-addressed typed ledger."""

from __future__ import annotations

import json
import random
import statistics
import sys
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent.parent / "22_interpretable_40m_architecture"))
from architecture_probe import (  # type: ignore  # local experiment module
    ARCHITECTURES,
    Node,
    Task,
    canonical,
    task_rows,
)

ROOT = HERE.parent


def noisy(task: Task, mode: str, seed: int) -> Task:
    order = list(task.surface_order)
    nodes = list(task.nodes)
    rng = random.Random(seed)
    if mode == "reorder":
        rng.shuffle(order)
    elif mode == "duplicate":
        order.insert(rng.randrange(len(order) + 1), rng.choice(order))
    elif mode == "drop":
        del order[rng.randrange(len(order))]
    elif mode == "mutate":
        target = rng.choice([i for i, node in enumerate(nodes) if node.op != "input"])
        old = nodes[target]
        nodes[target] = replace(old, op="reverse" if old.op != "reverse" else "sort")
    else:
        raise ValueError(mode)
    return Task(tuple(nodes), tuple(order), task.shape)


def evaluate(architecture, tasks: list[Task], mode: str) -> float:
    values = []
    for index, task in enumerate(tasks):
        decoded = canonical(architecture.encode_decode(noisy(task, mode, 9000 + index)))
        values.append(decoded == canonical(task.nodes))
    return sum(values) / len(values)


def main() -> None:
    seeds = (11, 23, 37, 41, 53)
    modes = ("reorder", "duplicate", "drop", "mutate")
    runs = []
    for seed in seeds:
        tasks = task_rows(seed)
        for architecture in ARCHITECTURES:
            for mode in modes:
                row = {
                    "seed": seed,
                    "architecture": architecture.name,
                    "mode": mode,
                    "recovery": evaluate(architecture, tasks, mode),
                    "tasks": len(tasks),
                }
                runs.append(row)
                print(json.dumps(row, sort_keys=True), flush=True)
    aggregate = {}
    for architecture in ARCHITECTURES:
        aggregate[architecture.name] = {}
        for mode in modes:
            vals = [r["recovery"] for r in runs if r["architecture"] == architecture.name and r["mode"] == mode]
            aggregate[architecture.name][mode] = {
                "mean": statistics.mean(vals),
                "seed_sd": statistics.stdev(vals),
            }
    output = {"seeds": list(seeds), "modes": list(modes), "aggregate": aggregate,
              "note": "Synthetic supplied-fact noise probe; no learned model or benchmark was run."}
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
