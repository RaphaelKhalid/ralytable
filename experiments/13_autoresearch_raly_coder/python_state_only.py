"""Executable-Python port of the causal abstract-state controller."""

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

import abstract_value_state
import python_surface
import state_policy


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.jsonl"
CANDIDATES = ("sort_asc", "unique")
ACTION_TO_ID = {action: index for index, action in enumerate(CANDIDATES)}
FAMILIES = ("filter_then_normalize", "reverse_then_normalize")
ABSTRACT_DIM = 7
STATE_DIM = state_policy.STATE_DIM + ABSTRACT_DIM


@dataclass(frozen=True)
class PythonStateTask:
    base: state_policy.Task
    request: str
    public_values: tuple[int, ...]
    prefix: tuple[str, ...]
    prefix_values: tuple[int, ...]
    corrupted: tuple[str, ...]
    gap: int
    missing: str


def execute_prefix(values: tuple[int, ...], threshold: int,
                   take_k: int, prefix: tuple[str, ...]) -> tuple[int, ...]:
    current = list(values)
    for action in prefix:
        if action == "input":
            current = list(values)
        elif action == "filter_gt":
            current = [x for x in current if x > threshold]
        elif action == "reverse":
            current = list(reversed(current))
        elif action == "sort_asc":
            current = sorted(current)
        elif action == "unique":
            seen: set[int] = set()
            current = [x for x in current if not (x in seen or seen.add(x))]
        elif action == "take":
            current = current[:take_k]
    return tuple(current)


def apply_target(values: tuple[int, ...], threshold: int, take_k: int,
                 actions: tuple[str, ...]) -> tuple[int, ...]:
    ok, result, error = state_policy.execute(values, threshold, take_k, actions)
    if not ok or not isinstance(result, tuple):
        raise RuntimeError(f"invalid generated target: {error}")
    return result


def make_task(rng: random.Random, family: str) -> PythonStateTask:
    threshold = rng.randrange(-5, 6)
    take_k = rng.randrange(2, 4)
    prefix = ("input", "filter_gt" if family.startswith("filter") else "reverse")
    desired_sorted = bool(rng.randrange(2))
    for _ in range(1000):
        if desired_sorted:
            values = tuple(sorted(
                (rng.randrange(-9, 10) for _ in range(8)),
                reverse=family.startswith("reverse"),
            ))
        else:
            values_list = [rng.randrange(-9, 10) for _ in range(8)]
            rng.shuffle(values_list)
            values = tuple(values_list)
        after_prefix = execute_prefix(values, threshold, take_k, prefix)
        is_sorted = list(after_prefix) == sorted(after_prefix)
        if is_sorted != desired_sorted or len(set(after_prefix)) == len(after_prefix):
            continue
        sort_out = apply_target(
            values, threshold, take_k,
            prefix + ("sort_asc", "take", "return"),
        )
        unique_out = apply_target(
            values, threshold, take_k,
            prefix + ("unique", "take", "return"),
        )
        if sort_out == unique_out:
            continue
        missing = "unique" if is_sorted else "sort_asc"
        target = prefix + (missing, "take", "return")
        public = ((values, apply_target(values, threshold, take_k, target)),)
        hidden = tuple(rng.randrange(-9, 10) for _ in range(8))
        expected = apply_target(hidden, threshold, take_k, target)
        request = (
            "Write a typed Python microtask. Choose the canonical operation "
            "from sort_asc or unique using the current executable list state; "
            f"prefix_family={family}; threshold={threshold}; take={take_k}; "
            "return_type=List[Int]."
        )
        base = state_policy.Task(
            "python_state_microtask", request, threshold, take_k, public,
            hidden, expected, target, "List[Int]",
        )
        return PythonStateTask(
            base, request, values, prefix, after_prefix,
            prefix + ("take", "return"), len(prefix), missing,
        )
    raise RuntimeError("could not construct balanced Python state task")


def abstract_facts(task: PythonStateTask,
                   *, corrupt: str | None = None) -> list[float]:
    values = list(task.prefix_values)
    if corrupt == "erase_value":
        return [0.0] * ABSTRACT_DIM
    if not values:
        return [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    return [
        0.0,
        float(values == sorted(values)),
        float(len(set(values)) == len(values)),
        float(any(x < 0 for x in values)),
        float(len(values) <= 2),
        float(len(values) >= 5),
        float(sum(values) >= 0),
    ]


def features(task: PythonStateTask, *, corrupt: str | None = None) -> list[float]:
    return state_policy.state_features(
        task.base, task.prefix, corrupt=corrupt
    ) + abstract_facts(task, corrupt=corrupt)


class PythonStateOnlyPolicy(nn.Module):
    def __init__(self):
        super().__init__()
        self.controller = abstract_value_state.StateOnlyPolicy()

    def logits(self, tokens: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        return self.controller.logits(tokens, state)


def train(seed: int, tasks: list[PythonStateTask], updates: int,
          device: torch.device) -> tuple[PythonStateOnlyPolicy, list[float]]:
    torch.manual_seed(seed)
    model = PythonStateOnlyPolicy().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)
    losses: list[float] = []
    for update in range(updates):
        batch = [tasks[(update * 5 + i * 11) % len(tasks)]
                 for i in range(min(32, len(tasks)))]
        tokens = torch.zeros((len(batch), 1), dtype=torch.long, device=device)
        state = torch.tensor([features(task) for task in batch],
                             dtype=torch.float32, device=device)
        erased = torch.tensor([features(task, corrupt="erase_value") for task in batch],
                              dtype=torch.float32, device=device)
        labels = torch.tensor([ACTION_TO_ID[task.missing] for task in batch],
                              dtype=torch.long, device=device)
        logits = model.logits(tokens, state)
        erased_logits = model.logits(tokens, erased)
        loss = nn.functional.cross_entropy(logits, labels)
        target = logits.gather(1, labels[:, None]).squeeze(1)
        erased_target = erased_logits.gather(1, labels[:, None]).squeeze(1)
        loss = loss + 0.35 * nn.functional.relu(
            0.5 - target + erased_target
        ).mean()
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return model, losses


@torch.no_grad()
def logits_for(model: PythonStateOnlyPolicy, task: PythonStateTask,
               device: torch.device, corrupt: str | None = None) -> torch.Tensor:
    tokens = torch.zeros((1, 1), dtype=torch.long, device=device)
    state = torch.tensor([features(task, corrupt=corrupt)],
                         dtype=torch.float32, device=device)
    return model.logits(tokens, state)[0]


def candidate(task: PythonStateTask, action: str) -> tuple[str, ...]:
    return task.corrupted[:task.gap] + (action,) + task.corrupted[task.gap:]


def public_pass(task: PythonStateTask, actions: tuple[str, ...]) -> bool:
    if not python_surface.compile_only(actions):
        return False
    for values, expected in task.base.public:
        ok, got, _ = python_surface.python_execute(task.base, values, actions)
        if not ok or got != expected:
            return False
    return True


def choose(model: PythonStateOnlyPolicy | None, task: PythonStateTask,
           device: torch.device, *, verify: bool,
           corrupt: str | None = None) -> tuple[tuple[str, ...] | None, int]:
    if model is None:
        ranked = list(CANDIDATES)
    else:
        scores = logits_for(model, task, device, corrupt=corrupt)
        ranked = sorted(CANDIDATES,
                        key=lambda action: float(scores[ACTION_TO_ID[action]]),
                        reverse=True)
    for expanded, action in enumerate(ranked, start=1):
        program = candidate(task, action)
        if not verify or public_pass(task, program):
            return program, expanded
    return None, len(ranked)


def causal_rates(model: PythonStateOnlyPolicy, tasks: list[PythonStateTask],
                 device: torch.device, *, verify: bool) -> dict[str, float]:
    changed, preserved = [], []
    for task in tasks:
        baseline, _ = choose(model, task, device, verify=verify)
        altered, _ = choose(model, task, device, verify=verify,
                            corrupt="erase_value")
        placebo, _ = choose(model, task, device, verify=verify,
                            corrupt="noise")
        changed.append(float(altered != baseline))
        preserved.append(float(placebo == baseline))
    return {
        "python_state_relevant_changed_rate": statistics.mean(changed),
        "python_state_irrelevant_preserved_rate": statistics.mean(preserved),
        "python_state_causal_rate": statistics.mean(
            float(a and b) for a, b in zip(changed, preserved)
        ),
    }


def metrics(tasks: list[PythonStateTask], model: PythonStateOnlyPolicy | None,
            device: torch.device, direction: str) -> dict[str, object]:
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    raw_pass = raw_compile = full_pass = full_compile = 0
    expansions, latencies = [], []
    verify = direction in {"py-state-only-public", "py-state-null"}
    for task in tasks:
        started = time.perf_counter()
        raw, _ = choose(model, task, device, verify=False)
        raw_compile += int(raw is not None and python_surface.compile_only(raw))
        raw_pass += int(raw is not None and
                        python_surface.hidden_pass(task.base, raw))
        if direction == "py-state-only":
            chosen, expanded = raw, 0
        else:
            chosen, expanded = choose(model, task, device, verify=verify)
        full_compile += int(chosen is not None and python_surface.compile_only(chosen))
        full_pass += int(chosen is not None and
                         python_surface.hidden_pass(task.base, chosen))
        expansions.append(expanded)
        latencies.append((time.perf_counter() - started) * 1000)
    n = len(tasks)
    row: dict[str, object] = {
        "direction": direction, "tasks": n,
        "raw_pass_rate": raw_pass / n, "raw_compile_rate": raw_compile / n,
        "heldout_pass_rate": full_pass / n, "compile_rate": full_compile / n,
        "mean_search_expansions": statistics.mean(expansions),
        "latency_ms": statistics.mean(latencies),
        "vram_gb": (torch.cuda.max_memory_allocated(device) / 1024**3
                    if device.type == "cuda" else 0.0),
        "python_state_relevant_changed_rate": 0.0,
        "python_state_irrelevant_preserved_rate": 0.0,
        "python_state_causal_rate": 0.0,
    }
    if model is not None and direction in {"py-state-only", "py-state-only-public"}:
        row.update(causal_rates(model, tasks, device, verify=verify))
    row["objective"] = (1.0 - float(row["heldout_pass_rate"]) +
                         0.05 * min(float(row["mean_search_expansions"]) /
                                    len(CANDIDATES), 1.0))
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
    parser.add_argument("--directions", default="py-state-null,py-state-only,py-state-only-public")
    args = parser.parse_args()
    device = torch.device(
        "cuda" if args.device == "cuda" or
        (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )
    allowed = {"py-state-null", "py-state-only", "py-state-only-public"}
    directions = tuple(args.directions.split(","))
    if set(directions) - allowed:
        raise ValueError(f"unknown directions: {sorted(set(directions) - allowed)}")
    for seed_text in args.seeds.split(","):
        seed = int(seed_text)
        train_rng = random.Random(260000 + seed)
        eval_rng = random.Random(270000)
        train_tasks = [make_task(train_rng, FAMILIES[i % len(FAMILIES)])
                       for i in range(args.train_count)]
        eval_tasks = [make_task(eval_rng, FAMILIES[i % len(FAMILIES)])
                      for i in range(args.eval_count)]
        for direction in directions:
            if direction == "py-state-null":
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
                "checkpoint": f"py-state-seed-{seed}-u{args.updates}-{direction}",
                "hypothesis": (
                    "a state-only controller over abstract executable Python state "
                    "will choose a hidden normalization edit causally"
                ),
                "change": direction, "train_updates": args.updates,
                "train_loss_start": losses[0], "train_loss_end": losses[-1],
                "status": "exploratory",
            })
            append(row)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
