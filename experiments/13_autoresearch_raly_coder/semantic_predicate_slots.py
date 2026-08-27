"""Typed predicate-slot controller for the semantic repair proxy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import statistics
import time

import torch
from torch import nn

import python_semantic_repair as semantic
import python_repair_suite as suite
import python_surface
from semantic_parser_controller import ParsedRule, parse_rule, rule_features


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.jsonl"
RULE_DIM = len(rule_features(ParsedRule("duplicates", "sort_asc", "unique")))
INPUT_DIM = RULE_DIM + len(semantic.PREDICATES) + 1


def prefix_values(task: semantic.SemanticTask) -> tuple[int, ...]:
    return suite.run_program(
        task.public_values[0], task.base.threshold, task.base.take_k, task.prefix
    )


def predicate_slots(task: semantic.SemanticTask,
                    corrupt: str | None = None) -> list[float]:
    values = prefix_values(task)
    slots = [float(semantic.predicate_holds(values, predicate))
             for predicate in semantic.PREDICATES]
    if corrupt == "erase_predicate":
        slots = [0.0] * len(slots)
    return slots + [float(corrupt == "noise")]


def features(task: semantic.SemanticTask, corrupt: str | None = None) -> list[float]:
    return rule_features(parse_rule(task)) + predicate_slots(task, corrupt)


class SlotPolicy(nn.Module):
    def __init__(self):
        super().__init__()
        self.head = nn.Sequential(
            nn.Linear(INPUT_DIM, 32), nn.Tanh(),
            nn.Linear(32, len(suite.CANDIDATES)),
        )

    def logits(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.head(inputs)


def train(seed: int, tasks: list[semantic.SemanticTask], updates: int,
          device: torch.device) -> tuple[SlotPolicy, list[float]]:
    torch.manual_seed(seed)
    model = SlotPolicy().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)
    losses: list[float] = []
    for update in range(updates):
        batch = [tasks[(update * 7 + index * 17) % len(tasks)]
                 for index in range(min(64, len(tasks)))]
        rng = random.Random(700000 + seed * 1000 + update)
        inputs = torch.tensor([
            features(task, "noise" if rng.randrange(2) else None)
            for task in batch
        ], dtype=torch.float32, device=device)
        labels = torch.tensor([
            suite.ACTION_TO_ID[task.true_action if task.predicate_value
                               else task.false_action]
            for task in batch
        ], dtype=torch.long, device=device)
        loss = nn.functional.cross_entropy(model.logits(inputs), labels)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return model, losses


def slot_symbolic_action(task: semantic.SemanticTask) -> str:
    rule = parse_rule(task)
    value = semantic.predicate_holds(prefix_values(task), rule.predicate)
    return rule.true_action if value else rule.false_action


@torch.no_grad()
def learned_action(model: SlotPolicy, task: semantic.SemanticTask,
                   device: torch.device, corrupt: str | None = None) -> str:
    inputs = torch.tensor([features(task, corrupt)], dtype=torch.float32,
                          device=device)
    index = int(model.logits(inputs)[0].argmax().cpu())
    return suite.CANDIDATES[index]


def public_pass(task: semantic.SemanticTask, action: str) -> bool:
    program = task.prefix + (action, "take", "return")
    return python_surface.compile_only(program) and all(
        python_surface.python_execute(task.base, values, program)[1] == expected
        for values, expected in task.base.public
    )


def hidden_counts(task: semantic.SemanticTask, action: str) -> tuple[int, int]:
    program = task.prefix + (action, "take", "return")
    passed = 0
    for values, expected in task.hidden:
        ok, got, _ = python_surface.python_execute(task.base, values, program)
        passed += int(ok and got == expected)
    return passed, len(task.hidden)


def learned_public_action(model: SlotPolicy, task: semantic.SemanticTask,
                          device: torch.device) -> tuple[str, int]:
    inputs = torch.tensor([features(task)], dtype=torch.float32, device=device)
    scores = model.logits(inputs)[0]
    ranked = sorted(suite.CANDIDATES,
                    key=lambda action: float(scores[suite.ACTION_TO_ID[action]]),
                    reverse=True)
    for expanded, action in enumerate(ranked, start=1):
        if public_pass(task, action):
            return action, expanded
    return ranked[0], len(ranked)


def causal(model: SlotPolicy, tasks: list[semantic.SemanticTask],
           device: torch.device) -> dict[str, float]:
    changed, preserved = [], []
    for task in tasks:
        base = learned_action(model, task, device)
        altered = learned_action(model, task, device, "erase_predicate")
        placebo = learned_action(model, task, device, "noise")
        changed.append(float(altered != base))
        preserved.append(float(placebo == base))
    return {
        "predicate_state_relevant_changed_rate": statistics.mean(changed),
        "predicate_state_irrelevant_preserved_rate": statistics.mean(preserved),
        "predicate_state_causal_rate": statistics.mean(
            float(a and b) for a, b in zip(changed, preserved)
        ),
    }


def metrics(tasks: list[semantic.SemanticTask], model: SlotPolicy | None,
            device: torch.device, direction: str) -> dict[str, object]:
    learned = model is not None
    verify = direction.endswith("-public")
    raw_pass = full_pass = raw_tests = full_tests = total = 0
    raw_compile = full_compile = 0
    expansions: list[int] = []
    latencies: list[float] = []
    for task in tasks:
        started = time.perf_counter()
        raw_action = (learned_action(model, task, device) if learned
                      else slot_symbolic_action(task))
        raw_program = task.prefix + (raw_action, "take", "return")
        raw_compile += int(python_surface.compile_only(raw_program))
        raw_ok, raw_n = hidden_counts(task, raw_action)
        raw_tests += raw_ok
        total += raw_n
        raw_pass += int(raw_ok == raw_n)
        if direction == "slot-symbolic":
            chosen, expanded = raw_action, 0
        elif direction == "slot-learned-public":
            chosen, expanded = learned_public_action(model, task, device)
        else:
            chosen, expanded = raw_action, 0
        full_program = task.prefix + (chosen, "take", "return")
        full_compile += int(python_surface.compile_only(full_program))
        full_ok, _ = hidden_counts(task, chosen)
        full_tests += full_ok
        full_pass += int(full_ok == raw_n)
        expansions.append(expanded if verify else 0)
        latencies.append((time.perf_counter() - started) * 1000)
    n = len(tasks)
    row: dict[str, object] = {
        "direction": direction, "tasks": n,
        "public_tests_per_task": 3, "hidden_tests_per_task": 4,
        "raw_pass_rate": raw_pass / n,
        "raw_hidden_test_rate": raw_tests / total,
        "raw_compile_rate": raw_compile / n,
        "heldout_pass_rate": full_pass / n,
        "hidden_test_rate": full_tests / total,
        "compile_rate": full_compile / n,
        "mean_search_expansions": statistics.mean(expansions),
        "latency_ms": statistics.mean(latencies),
        "vram_gb": (torch.cuda.max_memory_allocated(device) / 1024**3
                    if device.type == "cuda" else 0.0),
        "predicate_state_relevant_changed_rate": 0.0,
        "predicate_state_irrelevant_preserved_rate": 0.0,
        "predicate_state_causal_rate": 0.0,
    }
    if model is not None:
        row.update(causal(model, tasks, device))
    row["objective"] = 1.0 - float(row["heldout_pass_rate"]) + 0.01 * (
        float(row["mean_search_expansions"]) / len(suite.CANDIDATES)
    )
    return row


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
    args = parser.parse_args()
    device = torch.device(
        "cuda" if args.device == "cuda" or
        (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )
    for seed_text in args.seeds.split(","):
        seed = int(seed_text)
        train_tasks = semantic.make_dataset(random.Random(630000 + seed), args.train_count)
        eval_tasks = semantic.make_dataset(random.Random(640000), args.eval_count)
        for direction, model_mode in (("slot-symbolic", None),
                                      ("slot-learned", "learned"),
                                      ("slot-learned-public", "learned")):
            if model_mode is None:
                model = None
                losses = [0.0, 0.0]
            else:
                model, losses = train(seed, train_tasks, args.updates, device)
                model.eval()
            row = metrics(eval_tasks, model, device, direction)
            params = (sum(p.numel() for p in model.parameters() if p.requires_grad)
                      if model is not None else 0)
            if params >= 9_000_000:
                raise RuntimeError(f"learned parameter gate exceeded: {params}")
            row.update({
                "learned_params": params, "seed": seed,
                "checkpoint": f"slot-seed-{seed}-u{args.updates}-{direction}",
                "hypothesis": "explicit typed predicate slots should repair the missing state interface",
                "change": direction, "train_updates": args.updates,
                "train_loss_start": losses[0], "train_loss_end": losses[-1],
                "status": "exploratory",
            })
            append(row)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
