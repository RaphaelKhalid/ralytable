"""Held-out request paraphrase test for the typed predicate gate."""

from __future__ import annotations

import argparse
from dataclasses import replace
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
from semantic_parser_controller import ParsedRule
from semantic_predicate_slots import hidden_counts, prefix_values, public_pass


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.jsonl"
PREDICATE_ALIASES = {
    "duplicates": (
        "the inspected list contains repeated values",
        "the inspected list has a duplicate value",
        "the inspected sequence includes any repeated entry",
    ),
    "negative": (
        "the inspected list contains a negative value",
        "the inspected list has a value below zero",
        "the inspected sequence includes a negative number",
    ),
    "long": (
        "the inspected list contains at least six values",
        "the inspected list has six or more entries",
        "the inspected sequence includes at least six items",
    ),
}
ACTION_ALIASES = {
    "sort_asc": (
        "put the values in ascending order",
        "sort the values from smallest to largest",
        "order the values increasingly",
    ),
    "unique": (
        "keep only the first occurrence of each value",
        "retain the first copy of each value",
        "drop later duplicate occurrences",
    ),
    "reverse": (
        "read the values from right to left",
        "traverse the values in reverse order",
        "reverse the sequence",
    ),
    "filter_gt": (
        "keep only values greater than the threshold",
        "retain values above the threshold",
        "keep entries larger than the threshold",
    ),
}


def parse_rule(task: semantic.SemanticTask) -> ParsedRule:
    request = task.base.request
    predicates = [(request.index(phrase), name)
                  for name, phrases in PREDICATE_ALIASES.items()
                  for phrase in phrases if phrase in request]
    actions = [(request.index(phrase), name)
               for name, phrases in ACTION_ALIASES.items()
               for phrase in phrases if phrase in request]
    if len(predicates) != 1 or len(actions) != 2:
        raise ValueError(f"paraphrase parser ambiguity: {request}")
    actions.sort()
    return ParsedRule(predicates[0][1], actions[0][1], actions[1][1])


def paraphrase_task(task: semantic.SemanticTask, variant: int) -> semantic.SemanticTask:
    request = task.base.request
    for name, phrases in semantic.PREDICATE_DESCRIPTIONS.items():
        request = request.replace(phrases, PREDICATE_ALIASES[name][variant])
    for name, phrase in semantic.ACTION_DESCRIPTIONS.items():
        request = request.replace(phrase, ACTION_ALIASES[name][variant])
    return replace(task, base=replace(task.base, request=request))


def selected_slot(task: semantic.SemanticTask) -> float:
    rule = parse_rule(task)
    values = prefix_values(task)
    return float(semantic.predicate_holds(values, rule.predicate))


class PredicateGate(nn.Module):
    def __init__(self):
        super().__init__()
        self.logit = nn.Linear(1, 1)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.logit(value).squeeze(-1)


def train(seed: int, tasks: list[semantic.SemanticTask], updates: int,
          device: torch.device) -> tuple[PredicateGate, list[float]]:
    torch.manual_seed(seed)
    model = PredicateGate().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-2)
    losses: list[float] = []
    for update in range(updates):
        batch = [tasks[(update * 7 + index * 17) % len(tasks)]
                 for index in range(min(64, len(tasks)))]
        values = torch.tensor([[selected_slot(task)] for task in batch],
                              dtype=torch.float32, device=device)
        labels = torch.tensor([float(task.predicate_value) for task in batch],
                              dtype=torch.float32, device=device)
        loss = nn.functional.binary_cross_entropy_with_logits(
            model(values), labels
        )
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return model, losses


@torch.no_grad()
def learned_action(model: PredicateGate, task: semantic.SemanticTask,
                   device: torch.device, erase: bool = False) -> str:
    rule = parse_rule(task)
    value = torch.tensor([[0.0 if erase else selected_slot(task)]],
                         dtype=torch.float32, device=device)
    truth = bool(model(value).item() >= 0.0)
    return rule.true_action if truth else rule.false_action


def symbolic_action(task: semantic.SemanticTask) -> str:
    rule = parse_rule(task)
    return rule.true_action if selected_slot(task) else rule.false_action


def learned_public_action(model: PredicateGate, task: semantic.SemanticTask,
                          device: torch.device) -> tuple[str, int]:
    raw = learned_action(model, task, device)
    ranked = [raw] + [a for a in suite.CANDIDATES if a != raw]
    for expanded, action in enumerate(ranked, start=1):
        if public_pass(task, action):
            return action, expanded
    return raw, len(ranked)


def metrics(tasks: list[semantic.SemanticTask], model: PredicateGate | None,
            device: torch.device, direction: str) -> dict[str, object]:
    raw_pass = full_pass = raw_tests = full_tests = total = 0
    raw_compile = full_compile = 0
    changes, preserves, expansions, latencies = [], [], [], []
    verify = direction.endswith("-public")
    for task in tasks:
        started = time.perf_counter()
        raw = learned_action(model, task, device) if model else symbolic_action(task)
        program = task.prefix + (raw, "take", "return")
        raw_compile += int(python_surface.compile_only(program))
        ok, count = hidden_counts(task, raw)
        raw_tests += ok
        total += count
        raw_pass += int(ok == count)
        if direction == "para-symbolic":
            chosen, expanded = raw, 0
        elif direction == "para-learned-public":
            chosen, expanded = learned_public_action(model, task, device)
        else:
            chosen, expanded = raw, 0
        full_program = task.prefix + (chosen, "take", "return")
        full_compile += int(python_surface.compile_only(full_program))
        full_ok, _ = hidden_counts(task, chosen)
        full_tests += full_ok
        full_pass += int(full_ok == count)
        if model:
            altered = learned_action(model, task, device, erase=True)
            changes.append(float(altered != raw))
            preserves.append(float(learned_action(model, task, device) == raw))
        expansions.append(expanded if verify else 0)
        latencies.append((time.perf_counter() - started) * 1000)
    n = len(tasks)
    row: dict[str, object] = {
        "direction": direction, "tasks": n,
        "public_tests_per_task": 3, "hidden_tests_per_task": 4,
        "raw_pass_rate": raw_pass / n, "raw_hidden_test_rate": raw_tests / total,
        "raw_compile_rate": raw_compile / n, "heldout_pass_rate": full_pass / n,
        "hidden_test_rate": full_tests / total, "compile_rate": full_compile / n,
        "mean_search_expansions": statistics.mean(expansions),
        "latency_ms": statistics.mean(latencies),
        "vram_gb": (torch.cuda.max_memory_allocated(device) / 1024**3
                    if device.type == "cuda" else 0.0),
        "paraphrase_state_relevant_changed_rate": statistics.mean(changes) if changes else 0.0,
        "paraphrase_state_irrelevant_preserved_rate": statistics.mean(preserves) if preserves else 0.0,
    }
    row["paraphrase_state_causal_rate"] = row["paraphrase_state_relevant_changed_rate"] * row["paraphrase_state_irrelevant_preserved_rate"]
    row["objective"] = 1.0 - float(row["heldout_pass_rate"]) + 0.01 * float(row["mean_search_expansions"]) / len(suite.CANDIDATES)
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
    device = torch.device("cuda" if args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available()) else "cpu")
    for seed_text in args.seeds.split(","):
        seed = int(seed_text)
        train_tasks = semantic.make_dataset(random.Random(670000 + seed), args.train_count)
        eval_tasks = [paraphrase_task(task, 1) for task in semantic.make_dataset(random.Random(680000), args.eval_count)]
        for direction, learned in (("para-symbolic", False), ("para-learned", True), ("para-learned-public", True)):
            if learned:
                model, losses = train(seed, train_tasks, args.updates, device)
                model.eval()
            else:
                model, losses = None, [0.0, 0.0]
            row = metrics(eval_tasks, model, device, direction)
            params = sum(p.numel() for p in model.parameters() if p.requires_grad) if model else 0
            if params >= 9_000_000:
                raise RuntimeError(f"learned parameter gate exceeded: {params}")
            row.update({"learned_params": params, "seed": seed,
                        "checkpoint": f"para-seed-{seed}-u{args.updates}-{direction}",
                        "hypothesis": "the tiny typed gate should survive held-out request paraphrases",
                        "change": direction, "train_updates": args.updates,
                        "train_loss_start": losses[0], "train_loss_end": losses[-1],
                        "status": "exploratory"})
            append(row)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
