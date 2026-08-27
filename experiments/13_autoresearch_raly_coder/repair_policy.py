"""Typed-state controller for one-gap repair of executable sketches."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import random
import statistics
import time

import torch
from torch import nn

import python_surface
import state_policy


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.jsonl"
REPAIR_ACTIONS = state_policy.PRIMITIVES
REPAIR_ACTION_TO_ID = {name: index for index, name in enumerate(REPAIR_ACTIONS)}
TRAIN_TEMPLATES = (
    "filter_sum", "sort_count", "unique_sum", "reverse_count",
    "take_sum", "filter_take",
)
EVAL_TEMPLATES = (
    "sort_filter_count", "reverse_unique_sum",
    "take_filter_sum", "unique_sort_count",
)
STATE_DIM = state_policy.STATE_DIM + 1


@dataclass(frozen=True)
class RepairTask:
    base: state_policy.Task
    request: str
    corrupted: tuple[str, ...]
    gap: int
    missing: str


def make_repair_task(rng: random.Random, template: str) -> RepairTask:
    base = state_policy.make_task(rng, template)
    target = base.target
    operation_indices = list(range(1, len(target) - 1))
    target_gap = rng.choice(operation_indices)
    corrupted = target[:target_gap] + target[target_gap + 1:]
    gap = target_gap
    request = (
        base.request + " Repair exactly one missing operation in this sketch: "
        f"{','.join(corrupted)}; gap={gap}."
    )
    return RepairTask(base, request, corrupted, gap, target[target_gap])


def repair_features(task: RepairTask, *, corrupt: str | None = None) -> list[float]:
    prefix = task.corrupted[:task.gap]
    return state_policy.state_features(task.base, prefix, corrupt=corrupt) + [
        task.gap / max(len(task.base.target), 1)
    ]


class RepairPolicy(nn.Module):
    def __init__(self, vocab_size: int, hidden: int = 64):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, 24)
        self.encoder = nn.GRU(24, hidden, batch_first=True)
        self.head = nn.Sequential(
            nn.Linear(hidden + STATE_DIM, hidden),
            nn.Tanh(),
            nn.Linear(hidden, len(REPAIR_ACTIONS)),
        )
        self.state_gate = nn.Sequential(
            nn.Linear(STATE_DIM, 32),
            nn.Tanh(),
            nn.Linear(32, len(REPAIR_ACTIONS)),
        )

    def logits(self, tokens: torch.Tensor, features: torch.Tensor) -> torch.Tensor:
        _, hidden = self.encoder(self.embedding(tokens))
        hidden = hidden[-1]
        return self.head(torch.cat([hidden, features], dim=-1)) + self.state_gate(features)


def tokens_for(task: RepairTask, word_to_id: dict[str, int]) -> list[int]:
    return [
        word_to_id.get(word.strip(".,;=[]()=0123456789-").lower(), 0)
        for word in task.request.split()
    ]


def batch_tokens(tasks: list[RepairTask], word_to_id: dict[str, int]) -> torch.Tensor:
    rows = [tokens_for(task, word_to_id) for task in tasks]
    result = torch.zeros((len(rows), max(map(len, rows))), dtype=torch.long)
    for row, ids in enumerate(rows):
        result[row, :len(ids)] = torch.tensor(ids)
    return result


def train(seed: int, tasks: list[RepairTask], word_to_id: dict[str, int],
          updates: int, device: torch.device) -> tuple[RepairPolicy, list[float]]:
    torch.manual_seed(seed)
    model = RepairPolicy(len(word_to_id) + 1).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)
    losses: list[float] = []
    for update in range(updates):
        batch = [tasks[(update * 7 + i * 13) % len(tasks)]
                 for i in range(min(32, len(tasks)))]
        token_batch = batch_tokens(batch, word_to_id).to(device)
        features = torch.tensor(
            [repair_features(task) for task in batch],
            dtype=torch.float32, device=device,
        )
        erased = torch.tensor(
            [repair_features(task, corrupt="erase_type") for task in batch],
            dtype=torch.float32, device=device,
        )
        logits = model.logits(token_batch, features)
        erased_logits = model.logits(token_batch, erased)
        labels = torch.tensor(
            [REPAIR_ACTION_TO_ID[task.missing] for task in batch],
            dtype=torch.long, device=device,
        )
        loss = nn.functional.cross_entropy(logits, labels)
        changed = torch.tensor(
            [repair_features(task) != repair_features(task, corrupt="erase_type")
             for task in batch], dtype=torch.bool, device=device,
        )
        if changed.any():
            target = logits.gather(1, labels[:, None]).squeeze(1)
            erased_target = erased_logits.gather(1, labels[:, None]).squeeze(1)
            loss = loss + 0.35 * nn.functional.relu(
                0.5 - target[changed] + erased_target[changed]
            ).mean()
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return model, losses


@torch.no_grad()
def action_logits(model: RepairPolicy, task: RepairTask,
                  word_to_id: dict[str, int], device: torch.device,
                  corrupt: str | None = None) -> torch.Tensor:
    tokens = torch.tensor([tokens_for(task, word_to_id)], dtype=torch.long, device=device)
    features = torch.tensor([repair_features(task, corrupt=corrupt)],
                            dtype=torch.float32, device=device)
    return model.logits(tokens, features)[0]


def insert(task: RepairTask, action: str) -> tuple[str, ...]:
    return task.corrupted[:task.gap] + (action,) + task.corrupted[task.gap:]


def public_pass(task: RepairTask, actions: tuple[str, ...]) -> bool:
    for values, expected in task.base.public:
        ok, got, _ = python_surface.python_execute(task.base, values, actions)
        if not ok or got != expected:
            return False
    return True


def legal_insertions(task: RepairTask) -> tuple[str, ...]:
    prefix = task.corrupted[:task.gap]
    allowed = state_policy.legal_actions(prefix, task.base.result_type)
    return tuple(action for action in allowed if action in REPAIR_ACTION_TO_ID)


def choose(model: RepairPolicy | None, task: RepairTask,
           word_to_id: dict[str, int], device: torch.device,
           *, typed: bool, verify: bool, corrupt: str | None = None
           ) -> tuple[tuple[str, ...] | None, int]:
    if model is None:
        ranked = sorted(REPAIR_ACTIONS, key=lambda name: REPAIR_ACTION_TO_ID[name])
    else:
        logits = action_logits(model, task, word_to_id, device, corrupt=corrupt)
        ranked = sorted(
            REPAIR_ACTIONS,
            key=lambda name: float(logits[REPAIR_ACTION_TO_ID[name]]),
            reverse=True,
        )
    if typed:
        allowed = set(legal_insertions(task))
        ranked = [action for action in ranked if action in allowed]
    for expanded, action in enumerate(ranked, start=1):
        candidate = insert(task, action)
        if not verify or public_pass(task, candidate):
            return candidate, expanded
    return None, len(ranked)


def causal_rates(model: RepairPolicy, tasks: list[RepairTask],
                 word_to_id: dict[str, int], device: torch.device,
                 *, typed: bool, verify: bool) -> dict[str, float]:
    relevant = []
    placebo = []
    for task in tasks:
        baseline, _ = choose(model, task, word_to_id, device,
                             typed=typed, verify=verify)
        changed, _ = choose(model, task, word_to_id, device,
                            typed=typed, verify=verify,
                            corrupt="erase_type")
        preserved, _ = choose(model, task, word_to_id, device,
                              typed=typed, verify=verify,
                              corrupt="noise")
        relevant.append(float(changed != baseline))
        placebo.append(float(preserved == baseline))
    return {
        "repair_state_relevant_changed_rate": statistics.mean(relevant),
        "repair_state_irrelevant_preserved_rate": statistics.mean(placebo),
        "repair_state_causal_rate": statistics.mean(
            float(a and b) for a, b in zip(relevant, placebo)
        ),
    }


def metrics(tasks: list[RepairTask], model: RepairPolicy | None,
            word_to_id: dict[str, int], device: torch.device,
            direction: str) -> dict[str, object]:
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    raw_pass = raw_compile = full_pass = full_compile = 0
    expansions: list[int] = []
    latencies: list[float] = []
    typed = direction != "repair-raw"
    verify = direction == "repair-public" or direction == "repair-null"
    for task in tasks:
        started = time.perf_counter()
        raw, _ = choose(model, task, word_to_id, device,
                        typed=False, verify=False)
        raw_compile += int(raw is not None and python_surface.compile_only(raw))
        raw_pass += int(raw is not None and python_surface.hidden_pass(task.base, raw))
        if direction == "repair-raw":
            chosen, expanded = raw, 0
        elif direction == "repair-typed":
            chosen, expanded = choose(model, task, word_to_id, device,
                                      typed=True, verify=False)
        else:
            chosen, expanded = choose(
                model, task, word_to_id, device,
                typed=typed, verify=verify,
            )
        full_compile += int(
            chosen is not None and python_surface.compile_only(chosen)
        )
        full_pass += int(
            chosen is not None and python_surface.hidden_pass(task.base, chosen)
        )
        expansions.append(expanded)
        latencies.append((time.perf_counter() - started) * 1000)
    n = len(tasks)
    row: dict[str, object] = {
        "direction": direction,
        "tasks": n,
        "raw_pass_rate": raw_pass / n,
        "raw_compile_rate": raw_compile / n,
        "heldout_pass_rate": full_pass / n,
        "compile_rate": full_compile / n,
        "mean_search_expansions": statistics.mean(expansions),
        "latency_ms": statistics.mean(latencies),
        "vram_gb": (torch.cuda.max_memory_allocated(device) / 1024**3
                    if device.type == "cuda" else 0.0),
        "repair_state_relevant_changed_rate": 0.0,
        "repair_state_irrelevant_preserved_rate": 0.0,
        "repair_state_causal_rate": 0.0,
    }
    if model is not None and direction in {"repair-typed", "repair-public"}:
        row.update(causal_rates(model, tasks, word_to_id, device,
                                typed=typed, verify=verify))
    row["objective"] = (1.0 - float(row["heldout_pass_rate"]) +
                         0.05 * min(float(row["mean_search_expansions"]) /
                                    len(REPAIR_ACTIONS), 1.0))
    return row


def append(row: dict[str, object]) -> None:
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--updates", type=int, default=181)
    parser.add_argument("--train-count", type=int, default=96)
    parser.add_argument("--eval-count", type=int, default=48)
    parser.add_argument("--seeds", default="11,23,37")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument(
        "--directions",
        default="repair-null,repair-raw,repair-typed,repair-public",
    )
    args = parser.parse_args()
    device = torch.device(
        "cuda" if args.device == "cuda" or
        (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )
    directions = tuple(args.directions.split(","))
    allowed = {"repair-null", "repair-raw", "repair-typed", "repair-public"}
    if set(directions) - allowed:
        raise ValueError(f"unknown directions: {sorted(set(directions) - allowed)}")
    for seed_text in args.seeds.split(","):
        seed = int(seed_text)
        train_rng = random.Random(220000 + seed)
        eval_rng = random.Random(230000)
        train_tasks = [
            make_repair_task(train_rng, TRAIN_TEMPLATES[i % len(TRAIN_TEMPLATES)])
            for i in range(args.train_count)
        ]
        eval_tasks = [
            make_repair_task(eval_rng, EVAL_TEMPLATES[i % len(EVAL_TEMPLATES)])
            for i in range(args.eval_count)
        ]
        words = set()
        for task in train_tasks + eval_tasks:
            words.update(
                word.strip(".,;=[]()=0123456789-").lower()
                for word in task.request.split()
            )
        word_to_id = {word: i for i, word in enumerate(sorted(words), start=1)}
        for direction in directions:
            if direction in {"repair-null"}:
                model = None
                losses = [0.0, 0.0]
            else:
                model, losses = train(
                    seed, train_tasks, word_to_id, args.updates, device
                )
                model.eval()
            row = metrics(eval_tasks, model, word_to_id, device, direction)
            params = sum(p.numel() for p in model.parameters()
                         if p.requires_grad) if model is not None else 0
            if params >= 9_000_000:
                raise RuntimeError(f"learned parameter gate exceeded: {params}")
            row.update({
                "learned_params": params,
                "seed": seed,
                "checkpoint": f"repair-seed-{seed}-u{args.updates}-{direction}",
                "hypothesis": (
                    "a typed-state repair controller will rank one-gap executable "
                    "repairs and remain causally sensitive to the repair state"
                ),
                "change": direction,
                "train_updates": args.updates,
                "train_loss_start": losses[0],
                "train_loss_end": losses[-1],
                "status": "exploratory",
            })
            append(row)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
