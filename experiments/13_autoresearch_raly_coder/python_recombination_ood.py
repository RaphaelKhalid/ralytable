"""Held-out factor-combination test for the Experiment 13 cross controller."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random

import torch

import python_recombination as recomb
import python_repair_suite as suite


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.jsonl"
HELDOUT_INTENT = "delta"


def state_bucket(task: recomb.RecombTask) -> int:
    values = suite.run_program(
        task.public_values[0], task.base.threshold, task.base.take_k, task.prefix
    )
    return int(any(value < 0 for value in values))


def make_split(seed: int, train_count: int, eval_count: int) -> tuple[list[recomb.RecombTask], list[recomb.RecombTask]]:
    train_rng = random.Random(410000 + seed)
    eval_rng = random.Random(420000)
    train: list[recomb.RecombTask] = []
    while len(train) < train_count:
        family = suite.FAMILIES[len(train) % len(suite.FAMILIES)]
        task = recomb.make_task(train_rng, family)
        if not (task.intent == HELDOUT_INTENT and state_bucket(task) == 1):
            train.append(task)
    evaluation: list[recomb.RecombTask] = []
    while len(evaluation) < eval_count:
        family = suite.FAMILIES[len(evaluation) % len(suite.FAMILIES)]
        task = recomb.make_task(eval_rng, family)
        if task.intent == HELDOUT_INTENT and state_bucket(task) == 1:
            evaluation.append(task)
    return train, evaluation


def vocabulary(tasks: list[recomb.RecombTask]) -> dict[str, int]:
    return {word: index for index, word in enumerate(
        sorted(set(word.strip(".,;=0123456789-").lower()
                   for task in tasks for word in task.base.request.split())), start=1
    )}


def append(row: dict[str, object]) -> None:
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--updates", type=int, default=181)
    parser.add_argument("--train-count", type=int, default=512)
    parser.add_argument("--eval-count", type=int, default=256)
    parser.add_argument("--seeds", default="11,23,37")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--directions", default="ood-null,ood-state-only,ood-hybrid,ood-cross,ood-additive")
    args = parser.parse_args()
    device = torch.device(
        "cuda" if args.device == "cuda" or
        (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )
    for seed_text in args.seeds.split(","):
        seed = int(seed_text)
        train_tasks, eval_tasks = make_split(
            seed, args.train_count, args.eval_count
        )
        words = vocabulary(train_tasks + eval_tasks)
        all_directions = {
            "ood-null": (None, "recomb-null"),
            "ood-state-only": ("state-only", "recomb-state-only"),
            "ood-hybrid": ("hybrid", "recomb-hybrid"),
            "ood-cross": ("cross", "recomb-cross"),
            "ood-additive": ("additive", "recomb-additive"),
            "ood-cyclic": ("cyclic", "recomb-cyclic"),
        }
        directions = (
            (direction, *all_directions[direction])
            for direction in args.directions.split(",")
        )
        for direction, mode, metric_direction in directions:
            if mode is None:
                model = None
                losses = [0.0, 0.0]
            else:
                model, losses = recomb.train(
                    seed, train_tasks, words, args.updates, device, mode
                )
                model.eval()
            row = recomb.metrics(
                eval_tasks, model, words, device, metric_direction
            )
            row["direction"] = direction
            params = (sum(p.numel() for p in model.parameters() if p.requires_grad)
                      if model is not None else 0)
            if params >= 9_000_000:
                raise RuntimeError(f"learned parameter gate exceeded: {params}")
            row.update({
                "learned_params": params, "seed": seed,
                "checkpoint": f"ood-heldout-{HELDOUT_INTENT}-negative1-seed-{seed}-u{args.updates}-{direction}",
                "hypothesis": "an explicit state-intent interaction should compose an unseen factor pair",
                "change": direction, "train_updates": args.updates,
                "train_loss_start": losses[0], "train_loss_end": losses[-1],
                "heldout_factor_intent": HELDOUT_INTENT,
                "heldout_factor_negative": 1,
                "status": "exploratory",
            })
            append(row)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
