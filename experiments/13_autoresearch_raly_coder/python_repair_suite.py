"""Larger executable-Python repair suite for the state-only controller."""

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
import run
import state_policy


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.jsonl"
CANDIDATES = ("sort_asc", "unique", "reverse", "filter_gt")
ACTION_TO_ID = {action: index for index, action in enumerate(CANDIDATES)}
FAMILIES = ("filter_prefix", "reverse_prefix", "take_prefix")
ABSTRACT_DIM = 8
STATE_DIM = state_policy.STATE_DIM + ABSTRACT_DIM


@dataclass(frozen=True)
class SuiteTask:
    base: state_policy.Task
    request: str
    prefix: tuple[str, ...]
    public_values: tuple[tuple[int, ...], ...]
    hidden_cases: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]
    missing: str


def run_program(values: tuple[int, ...], threshold: int, take_k: int,
                actions: tuple[str, ...]) -> tuple[int, ...]:
    executable_actions = actions if actions[-1:] == ("return",) else actions + ("return",)
    task = run.Task(
        "python_repair_suite", "", threshold, take_k, (), values, (),
        executable_actions, "List[Int]",
    )
    ok, result, error = python_surface.python_execute(
        task, values, executable_actions
    )
    if not ok or not isinstance(result, tuple):
        raise RuntimeError(f"invalid generated program: {error}")
    return result


def prefix_for(family: str) -> tuple[str, ...]:
    return ("input", {
        "filter_prefix": "filter_gt",
        "reverse_prefix": "reverse",
        "take_prefix": "take",
    }[family])


def abstract_facts(values: tuple[int, ...], *, corrupt: str | None = None) -> list[float]:
    if corrupt == "erase_value":
        return [0.0] * ABSTRACT_DIM
    if not values:
        return [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    return [
        0.0,
        float(list(values) == sorted(values)),
        float(len(set(values)) == len(values)),
        float(any(x < 0 for x in values)),
        float(len(values) % 4 == 0),
        float(len(values) % 4 == 1),
        float(len(values) % 4 == 2),
        float(len(values) % 4 == 3),
    ]


def distinguishing_public_values(
    threshold: int, take_k: int, family: str, case_index: int
) -> tuple[int, ...]:
    """Return a deterministic public case with four distinct candidate outputs."""
    shift = 2 * case_index
    prefix_values = tuple(
        threshold + shift + delta
        for delta in (9, 9, 1, 8, 2, 7, 3, 6)
    )
    if family == "reverse_prefix":
        return tuple(reversed(prefix_values))
    if family == "take_prefix":
        return prefix_values + (threshold - 3 - case_index, threshold + 4)
    return prefix_values + (threshold - 3 - case_index, threshold + 4)


def make_task(rng: random.Random, family: str) -> SuiteTask:
    threshold = rng.randrange(-5, 6)
    take_k = 4 if family == "take_prefix" else 3
    prefix = prefix_for(family)
    public_values = tuple(
        distinguishing_public_values(threshold, take_k, family, index)
        for index in range(3)
    )
    prefix_values = run_program(public_values[0], threshold, take_k, prefix)
    public_outputs = [
        [run_program(values, threshold, take_k,
                     prefix + (action, "take", "return"))
         for action in CANDIDATES]
        for values in public_values
    ]
    if any(len(set(outputs)) != len(CANDIDATES)
           for outputs in public_outputs):
        raise RuntimeError(f"invalid public construction for family {family}")
    label = (
        len(prefix_values)
        + 2 * int(list(prefix_values) == sorted(prefix_values))
        + 3 * int(len(set(prefix_values)) == len(prefix_values))
        + 5 * int(any(x < 0 for x in prefix_values))
    ) % len(CANDIDATES)
    missing = CANDIDATES[label]
    target = prefix + (missing, "take", "return")
    public = tuple(
        (values, run_program(values, threshold, take_k, target))
        for values in public_values
    )
    hidden_values = tuple(
        tuple(rng.randrange(-10, 11) for _ in range(rng.randrange(6, 11)))
        for _ in range(4)
    )
    hidden = tuple(
        (values, run_program(values, threshold, take_k, target))
        for values in hidden_values
    )
    request = (
        "Implement a typed Python list utility. The correct repair is "
        "determined by the current executable list state. Candidate edits "
        "are sort_asc, unique, reverse, and filter_gt; "
        f"prefix_family={family}; threshold={threshold}; take={take_k}; "
        "return_type=List[Int]."
    )
    base = state_policy.Task(
        "python_repair_suite", request, threshold, take_k, public,
        hidden[0][0], hidden[0][1], target, "List[Int]",
    )
    return SuiteTask(base, request, prefix, public_values, hidden, missing)


def make_dataset(rng: random.Random, count: int) -> list[SuiteTask]:
    return [make_task(rng, FAMILIES[index % len(FAMILIES)])
            for index in range(count)]


def features(task: SuiteTask, *, corrupt: str | None = None) -> list[float]:
    prefix_values = run_program(
        task.public_values[0], task.base.threshold, task.base.take_k, task.prefix
    )
    return state_policy.state_features(
        task.base, task.prefix, corrupt=corrupt
    ) + abstract_facts(prefix_values, corrupt=corrupt)


class SuiteStateOnlyPolicy(nn.Module):
    def __init__(self, hidden: int = 48):
        super().__init__()
        self.controller = nn.Sequential(
            nn.Linear(STATE_DIM, hidden), nn.Tanh(),
            nn.Linear(hidden, len(CANDIDATES)),
        )

    def logits(self, tokens: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        del tokens
        return self.controller(state)


def train(seed: int, tasks: list[SuiteTask], updates: int,
          device: torch.device) -> tuple[SuiteStateOnlyPolicy, list[float]]:
    torch.manual_seed(seed)
    model = SuiteStateOnlyPolicy().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)
    losses: list[float] = []
    for update in range(updates):
        batch = [tasks[(update * 7 + index * 17) % len(tasks)]
                 for index in range(min(64, len(tasks)))]
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
        loss = loss + 0.25 * nn.functional.relu(
            0.5 - target + erased_target
        ).mean()
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return model, losses


@torch.no_grad()
def logits_for(model: SuiteStateOnlyPolicy, task: SuiteTask,
               device: torch.device, corrupt: str | None = None) -> torch.Tensor:
    tokens = torch.zeros((1, 1), dtype=torch.long, device=device)
    state = torch.tensor([features(task, corrupt=corrupt)],
                         dtype=torch.float32, device=device)
    return model.logits(tokens, state)[0]


def candidate(task: SuiteTask, action: str) -> tuple[str, ...]:
    return task.prefix + (action, "take", "return")


def public_pass(task: SuiteTask, program: tuple[str, ...]) -> bool:
    if not python_surface.compile_only(program):
        return False
    for values, expected in task.base.public:
        ok, got, _ = python_surface.python_execute(task.base, values, program)
        if not ok or got != expected:
            return False
    return True


def hidden_test_pass(task: SuiteTask, program: tuple[str, ...]) -> tuple[int, int]:
    passed = 0
    for values, expected in task.hidden_cases:
        ok, got, _ = python_surface.python_execute(task.base, values, program)
        passed += int(ok and got == expected)
    return passed, len(task.hidden_cases)


def choose(model: SuiteStateOnlyPolicy | None, task: SuiteTask,
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


def causal_rates(model: SuiteStateOnlyPolicy, tasks: list[SuiteTask],
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
        "suite_state_relevant_changed_rate": statistics.mean(changed),
        "suite_state_irrelevant_preserved_rate": statistics.mean(preserved),
        "suite_state_causal_rate": statistics.mean(
            float(a and b) for a, b in zip(changed, preserved)
        ),
    }


def metrics(tasks: list[SuiteTask], model: SuiteStateOnlyPolicy | None,
            device: torch.device, direction: str) -> dict[str, object]:
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    raw_task_pass = full_task_pass = raw_compile = full_compile = 0
    raw_tests = full_tests = total_tests = 0
    expansions: list[int] = []
    latencies: list[float] = []
    verify = direction in {"suite-state-only-public", "suite-null"}
    for task in tasks:
        started = time.perf_counter()
        raw, _ = choose(model, task, device, verify=False)
        raw_compile += int(raw is not None and python_surface.compile_only(raw))
        if raw is not None:
            raw_ok, raw_n = hidden_test_pass(task, raw)
            raw_tests += raw_ok
            total_tests += raw_n
            raw_task_pass += int(raw_ok == raw_n)
        if direction == "suite-state-only":
            chosen, expanded = raw, 0
        else:
            chosen, expanded = choose(model, task, device, verify=verify)
        if chosen is not None:
            full_compile += int(python_surface.compile_only(chosen))
            full_ok, full_n = hidden_test_pass(task, chosen)
            full_tests += full_ok
            full_task_pass += int(full_ok == full_n)
        expansions.append(expanded)
        latencies.append((time.perf_counter() - started) * 1000)
    n = len(tasks)
    row: dict[str, object] = {
        "direction": direction, "tasks": n,
        "public_tests_per_task": 3, "hidden_tests_per_task": 4,
        "raw_pass_rate": raw_task_pass / n,
        "raw_hidden_test_rate": raw_tests / max(total_tests, 1),
        "raw_compile_rate": raw_compile / n,
        "heldout_pass_rate": full_task_pass / n,
        "hidden_test_rate": full_tests / max(total_tests, 1),
        "compile_rate": full_compile / n,
        "mean_search_expansions": statistics.mean(expansions),
        "latency_ms": statistics.mean(latencies),
        "vram_gb": (torch.cuda.max_memory_allocated(device) / 1024**3
                    if device.type == "cuda" else 0.0),
        "suite_state_relevant_changed_rate": 0.0,
        "suite_state_irrelevant_preserved_rate": 0.0,
        "suite_state_causal_rate": 0.0,
    }
    if model is not None and direction in {
        "suite-state-only", "suite-state-only-public"
    }:
        row.update(causal_rates(model, tasks, device, verify=verify))
    row["objective"] = (1.0 - float(row["heldout_pass_rate"]) +
                         0.02 * min(float(row["mean_search_expansions"]) /
                                    len(CANDIDATES), 1.0))
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
    parser.add_argument("--directions", default="suite-null,suite-state-only,suite-state-only-public")
    args = parser.parse_args()
    device = torch.device(
        "cuda" if args.device == "cuda" or
        (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )
    allowed = {"suite-null", "suite-state-only", "suite-state-only-public"}
    directions = tuple(args.directions.split(","))
    if set(directions) - allowed:
        raise ValueError(f"unknown directions: {sorted(set(directions) - allowed)}")
    for seed_text in args.seeds.split(","):
        seed = int(seed_text)
        train_tasks = make_dataset(random.Random(280000 + seed), args.train_count)
        eval_tasks = make_dataset(random.Random(290000), args.eval_count)
        for direction in directions:
            if direction == "suite-null":
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
                "checkpoint": f"suite-seed-{seed}-u{args.updates}-{direction}",
                "hypothesis": (
                    "a tiny state-only controller will repair larger executable "
                    "Python tasks from abstract runtime facts"
                ),
                "change": direction, "train_updates": args.updates,
                "train_loss_start": losses[0], "train_loss_end": losses[-1],
                "status": "exploratory",
            })
            append(row)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
