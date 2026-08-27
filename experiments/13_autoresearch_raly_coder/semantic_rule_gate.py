"""Two-parameter learned predicate gate with a fixed typed rule multiplexer."""

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
from semantic_parser_controller import parse_rule
from semantic_predicate_slots import hidden_counts, prefix_values, public_pass


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.jsonl"


class PredicateGate(nn.Module):
    def __init__(self):
        super().__init__()
        self.logit = nn.Linear(1, 1)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.logit(value).squeeze(-1)


def selected_slot(task: semantic.SemanticTask,
                  corrupt: str | None = None) -> float:
    rule = parse_rule(task)
    values = prefix_values(task)
    if corrupt == "erase_predicate":
        return 0.0
    return float(semantic.predicate_holds(values, rule.predicate))


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
                   device: torch.device, corrupt: str | None = None) -> str:
    rule = parse_rule(task)
    value = torch.tensor([[selected_slot(task, corrupt)]],
                         dtype=torch.float32, device=device)
    truth = bool(model(value).item() >= 0.0)
    return rule.true_action if truth else rule.false_action


def learned_public_action(model: PredicateGate, task: semantic.SemanticTask,
                          device: torch.device) -> tuple[str, int]:
    raw = learned_action(model, task, device)
    alternatives = [raw] + [candidate for candidate in suite.CANDIDATES
                            if candidate != raw]
    for expanded, action in enumerate(alternatives, start=1):
        if public_pass(task, action):
            return action, expanded
    return raw, len(alternatives)


def symbolic_action(task: semantic.SemanticTask) -> str:
    rule = parse_rule(task)
    value = semantic.predicate_holds(prefix_values(task), rule.predicate)
    return rule.true_action if value else rule.false_action


def causal(model: PredicateGate, tasks: list[semantic.SemanticTask],
           device: torch.device) -> dict[str, float]:
    changed, preserved = [], []
    for task in tasks:
        base = learned_action(model, task, device)
        altered = learned_action(model, task, device, "erase_predicate")
        placebo = learned_action(model, task, device, "noise")
        changed.append(float(altered != base))
        preserved.append(float(placebo == base))
    return {
        "gate_state_relevant_changed_rate": statistics.mean(changed),
        "gate_state_irrelevant_preserved_rate": statistics.mean(preserved),
        "gate_state_causal_rate": statistics.mean(
            float(a and b) for a, b in zip(changed, preserved)
        ),
    }


def metrics(tasks: list[semantic.SemanticTask], model: PredicateGate | None,
            device: torch.device, direction: str) -> dict[str, object]:
    learned = model is not None
    verify = direction.endswith("-public")
    raw_pass = full_pass = raw_tests = full_tests = total = 0
    raw_compile = full_compile = 0
    expansions: list[int] = []
    latencies: list[float] = []
    for task in tasks:
        started = time.perf_counter()
        raw_action = learned_action(model, task, device) if learned else symbolic_action(task)
        raw_program = task.prefix + (raw_action, "take", "return")
        raw_compile += int(python_surface.compile_only(raw_program))
        raw_ok, raw_n = hidden_counts(task, raw_action)
        raw_tests += raw_ok
        total += raw_n
        raw_pass += int(raw_ok == raw_n)
        if direction == "gate-symbolic":
            chosen, expanded = raw_action, 0
        elif direction == "gate-learned-public":
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
        "gate_state_relevant_changed_rate": 0.0,
        "gate_state_irrelevant_preserved_rate": 0.0,
        "gate_state_causal_rate": 0.0,
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
        train_tasks = semantic.make_dataset(random.Random(650000 + seed), args.train_count)
        eval_tasks = semantic.make_dataset(random.Random(660000), args.eval_count)
        for direction, model_mode in (("gate-symbolic", None),
                                      ("gate-learned", "learned"),
                                      ("gate-learned-public", "learned")):
            if model_mode is None:
                model = None
                losses = [0.0, 0.0]
            else:
                model, losses = train(seed, train_tasks, args.updates, device)
                model.eval()
            row = metrics(eval_tasks, model, device, direction)
            params = sum(p.numel() for p in model.parameters() if p.requires_grad) if model else 0
            if params >= 9_000_000:
                raise RuntimeError(f"learned parameter gate exceeded: {params}")
            row.update({
                "learned_params": params, "seed": seed,
                "checkpoint": f"gate-seed-{seed}-u{args.updates}-{direction}",
                "hypothesis": "a tiny learned predicate gate plus fixed rule multiplexer should preserve causal state use",
                "change": direction, "train_updates": args.updates,
                "train_loss_start": losses[0], "train_loss_end": losses[-1],
                "status": "exploratory",
            })
            append(row)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
