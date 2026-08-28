"""Iterative typed-state controller over an on-disk multi-file Python package."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import json
from pathlib import Path
import random
import shutil
import statistics
import sys
import tempfile
import time

import torch
from torch import nn


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.jsonl"
NORMALIZE_ACTIONS = ("sort_values", "unique_values", "reverse_values", "drop_threshold")
SUMMARY_ACTIONS = ("sum_as_list", "mean_as_list", "count_as_list", "first_as_list")
PREDICATES = ("duplicates", "negative", "long")
SUMMARY_PREDICATES = ("odd_sum",)
PREDICATE_TEXT = {
    "duplicates": "the input contains repeated values",
    "negative": "the input contains a negative number",
    "long": "the input contains at least six values",
    "odd_sum": "the inspected values have an odd sum",
    "contains_threshold": "the inspected values contain the threshold",
    "all_positive": "all inspected values are positive",
}
ACTION_TEXT = {
    "sort_values": "sort the values from smallest to largest",
    "unique_values": "keep only the first occurrence of each value",
    "reverse_values": "reverse the order of the values",
    "drop_threshold": "remove values equal to the threshold",
    "sum_as_list": "replace the values with a one-item list containing their sum",
    "mean_as_list": "replace the values with a one-item list containing their integer mean",
    "count_as_list": "replace the values with a one-item list containing their count",
    "first_as_list": "replace the values with a one-item list containing the first value",
}
NORMALIZE_SOURCE = """def normalize(values, threshold):
    inspected = list(values)
    # REPAIR_NORMALIZE
    return inspected
"""
SUMMARY_SOURCE = """def summarize(values, threshold):
    inspected = list(values)
    # REPAIR_SUMMARIZE
    return inspected
"""
API_SOURCE = """from .transforms import normalize
from .summaries import summarize

def solve(values, threshold):
    normalized = normalize(values, threshold)
    return summarize(normalized, threshold)
"""
INIT_SOURCE = "from .api import solve\n"


@dataclass(frozen=True)
class Task:
    request: str
    threshold: int
    public: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]
    hidden: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]
    normalize_predicate: str
    normalize_value: bool
    normalize_true: str
    normalize_false: str
    summary_predicate: str
    summary_value: bool
    summary_true: str
    summary_false: str


def holds(values: tuple[int, ...], predicate: str, threshold: int) -> bool:
    if predicate == "duplicates":
        return len(set(values)) < len(values)
    if predicate == "negative":
        return any(value < 0 for value in values)
    if predicate == "long":
        return len(values) >= 6
    if predicate == "odd_sum":
        return sum(values) % 2 == 1
    if predicate == "contains_threshold":
        return threshold in values
    if predicate == "all_positive":
        return all(value > 0 for value in values)
    raise ValueError(predicate)


def patch_source(kind: str, action: str | None) -> str:
    if kind == "normalize":
        source = NORMALIZE_SOURCE
        lines = {
            None: "    pass",
            "sort_values": "    inspected = sorted(inspected)",
            "unique_values": "    inspected = list(dict.fromkeys(inspected))",
            "reverse_values": "    inspected = list(reversed(inspected))",
            "drop_threshold": "    inspected = [value for value in inspected if value != threshold]",
        }
        return source.replace("    # REPAIR_NORMALIZE", lines[action])
    source = SUMMARY_SOURCE
    lines = {
        None: "    pass",
        "sum_as_list": "    inspected = [sum(inspected)]",
        "mean_as_list": "    inspected = [sum(inspected) // len(inspected)] if inspected else [0]",
        "count_as_list": "    inspected = [len(inspected)]",
        "first_as_list": "    inspected = [inspected[0]] if inspected else [0]",
    }
    return source.replace("    # REPAIR_SUMMARIZE", lines[action])


def apply_normalize(action: str | None, values: tuple[int, ...], threshold: int) -> tuple[int, ...]:
    inspected = list(values)
    if action == "sort_values":
        inspected = sorted(inspected)
    elif action == "unique_values":
        inspected = list(dict.fromkeys(inspected))
    elif action == "reverse_values":
        inspected = list(reversed(inspected))
    elif action == "drop_threshold":
        inspected = [value for value in inspected if value != threshold]
    return tuple(inspected)


def apply_summary(action: str | None, values: tuple[int, ...], threshold: int) -> tuple[int, ...]:
    inspected = list(values)
    if action == "sum_as_list":
        inspected = [sum(inspected)]
    elif action == "mean_as_list":
        inspected = [sum(inspected) // len(inspected)] if inspected else [0]
    elif action == "count_as_list":
        inspected = [len(inspected)]
    elif action == "first_as_list":
        inspected = [inspected[0]] if inspected else [0]
    return tuple(inspected)


class RepoSession:
    """One file-backed package build reused across all cases for an action pair."""

    def __init__(self, normalize_action: str | None, summary_action: str | None):
        self.normalize_action = normalize_action
        self.summary_action = summary_action
        self.temp = tempfile.TemporaryDirectory(prefix="raly_iter_repo_", dir=ROOT)
        self.root = Path(self.temp.name)
        self.package_dir = self.root / "repair_pkg"
        self.package_dir.mkdir()
        self.module_names = ("repair_pkg", "repair_pkg.api", "repair_pkg.transforms", "repair_pkg.summaries")
        files = {
            "__init__.py": INIT_SOURCE,
            "api.py": API_SOURCE,
            "transforms.py": patch_source("normalize", normalize_action),
            "summaries.py": patch_source("summary", summary_action),
        }
        for filename, source in files.items():
            path = self.package_dir / filename
            path.write_text(source, encoding="utf-8")
            tree = ast.parse(source, filename=str(path), mode="exec")
            compile(tree, str(path), "exec")
        sys.path.insert(0, str(self.root))
        for name in self.module_names:
            sys.modules.pop(name, None)
        self.module = __import__("repair_pkg", fromlist=["solve"])
        self.transforms = __import__("repair_pkg.transforms", fromlist=["normalize"])

    def run(self, values: tuple[int, ...], threshold: int) -> tuple[bool, tuple[int, ...] | None, str, float]:
        started = time.perf_counter()
        try:
            result = self.module.solve(values, threshold)
            if not isinstance(result, list) or not all(isinstance(x, int) for x in result):
                return False, None, "wrong return type", time.perf_counter() - started
            return True, tuple(result), "", time.perf_counter() - started
        except (TypeError, ValueError, KeyError, NameError, ImportError, ZeroDivisionError) as error:
            return False, None, str(error), time.perf_counter() - started

    def normalize(self, values: tuple[int, ...], threshold: int) -> tuple[int, ...]:
        return tuple(self.transforms.normalize(values, threshold))

    def close(self) -> None:
        sys.path[:] = [entry for entry in sys.path if entry != str(self.root)]
        for name in self.module_names:
            sys.modules.pop(name, None)
        self.temp.cleanup()

    def __enter__(self) -> "RepoSession":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def run_repo(normalize_action: str | None, summary_action: str | None,
             values: tuple[int, ...], threshold: int) -> tuple[bool, tuple[int, ...] | None, str, float]:
    with RepoSession(normalize_action, summary_action) as session:
        return session.run(values, threshold)


def intermediate(normalize_action: str | None, values: tuple[int, ...], threshold: int) -> tuple[bool, tuple[int, ...] | None]:
    """Execute the transform module from the same on-disk package boundary."""
    try:
        with RepoSession(normalize_action, None) as session:
            return True, session.normalize(values, threshold)
    except (SyntaxError, TypeError, ValueError, KeyError, NameError, ImportError) as error:
        return False, None


def distinct_values(rng: random.Random, length: int, threshold: int) -> tuple[int, ...]:
    for _ in range(2000):
        values = tuple(rng.randrange(-9, 13) for _ in range(length))
        if len(set(values)) == length and threshold in values:
            return values
    raise RuntimeError("unable to sample distinct values")


def sample_values(rng: random.Random, predicate: str, wanted: bool,
                  threshold: int, index: int) -> tuple[int, ...]:
    length = 7 if predicate == "long" and wanted else 4
    for _ in range(3000):
        values = [rng.randrange(-9, 13) for _ in range(length)]
        if predicate == "duplicates" and wanted:
            values[1] = values[0]
        if predicate == "duplicates" and not wanted:
            candidate = distinct_values(rng, length, threshold)
            values = list(candidate)
        if predicate == "negative" and wanted:
            values[index % length] = -2 - (index % 5)
        if predicate == "negative" and not wanted:
            values = [abs(value) + 1 for value in values]
        if predicate == "long" and not wanted:
            values = values[:4]
        candidate = tuple(values)
        if holds(candidate, predicate, threshold) != wanted:
            continue
        if len({run_repo(a, None, candidate, threshold)[1] for a in NORMALIZE_ACTIONS}) < 3:
            continue
        return candidate
    raise RuntimeError(f"unable to sample {predicate}/{wanted}")


def sample_summary_values(rng: random.Random, predicate: str, wanted: bool,
                          threshold: int, index: int) -> tuple[int, ...]:
    for _ in range(3000):
        values = tuple(rng.randrange(1, 12) for _ in range(4 + index % 3))
        if predicate == "odd_sum" and wanted:
            values = values[:-1] + (values[-1] + (1 if sum(values) % 2 == 0 else 0),)
        if predicate == "odd_sum" and not wanted and sum(values) % 2:
            values = values[:-1] + (values[-1] + 1,)
        if predicate == "contains_threshold":
            if wanted:
                values = (threshold,) + values[1:]
            else:
                values = tuple(value if value != threshold else threshold + 1 for value in values)
        if predicate == "all_positive":
            if wanted:
                values = tuple(abs(value) + 1 for value in values)
            else:
                values = (-1,) + values[1:]
        if predicate == "long":
            values = values[:7] if wanted else values[:4]
        candidate = tuple(values)
        if holds(candidate, predicate, threshold) != wanted:
            continue
        outputs = {apply_summary(action, candidate, threshold) for action in SUMMARY_ACTIONS}
        if len(outputs) == len(SUMMARY_ACTIONS):
            return candidate
    raise RuntimeError(f"unable to sample summary {predicate}/{wanted}")


def make_task(rng: random.Random) -> Task:
    threshold = 5
    npredicate = rng.choice(PREDICATES)
    nvalue = bool(rng.randrange(2))
    nactions = list(NORMALIZE_ACTIONS)
    rng.shuffle(nactions)
    ntrue, nfalse = nactions[:2]
    spredicate = rng.choice(SUMMARY_PREDICATES)
    svalue = bool(rng.randrange(2))
    sactions = list(SUMMARY_ACTIONS)
    rng.shuffle(sactions)
    strue, sfalse = sactions[:2]
    n_target = ntrue if nvalue else nfalse
    s_target = strue if svalue else sfalse
    public_values = []
    hidden_values = []
    for index in range(3):
        raw = sample_values(rng, npredicate, nvalue, threshold, index)
        normalized = apply_normalize(n_target, raw, threshold)
        if normalized is None or holds(normalized, spredicate, threshold) != svalue:
            continue
        public_values.append((raw, apply_summary(s_target, normalized, threshold)))
    for index in range(3, 7):
        raw = sample_values(rng, npredicate, nvalue, threshold, index)
        normalized = apply_normalize(n_target, raw, threshold)
        if normalized is None or holds(normalized, spredicate, threshold) != svalue:
            continue
        hidden_values.append((raw, apply_summary(s_target, normalized, threshold)))
    # If the first predicate does not naturally produce the desired second
    # predicate often enough, create the summary examples independently and
    # then use them as the frozen repository cases. This preserves the staged
    # dependency while avoiding biased filtering by the learned model.
    while len(public_values) < 3:
        raw = sample_values(rng, npredicate, nvalue, threshold, len(public_values))
        normalized = apply_normalize(n_target, raw, threshold)
        if normalized is None:
            continue
        if holds(normalized, spredicate, threshold) != svalue:
            continue
        public_values.append((raw, apply_summary(s_target, normalized, threshold)))
    while len(hidden_values) < 4:
        raw = sample_values(rng, npredicate, nvalue, threshold, len(hidden_values) + 4)
        normalized = apply_normalize(n_target, raw, threshold)
        if normalized is None or holds(normalized, spredicate, threshold) != svalue:
            continue
        hidden_values.append((raw, apply_summary(s_target, normalized, threshold)))
    request = (
        "Repair this on-disk Python repository. In transforms.py, if "
        f"{PREDICATE_TEXT[npredicate]}, then {ACTION_TEXT[ntrue]}; otherwise "
        f"{ACTION_TEXT[nfalse]}. After that file is repaired, in summaries.py, "
        f"if {PREDICATE_TEXT[spredicate]}, then {ACTION_TEXT[strue]}; otherwise "
        f"{ACTION_TEXT[sfalse]}. The API imports both modules through api.py "
        "and __init__.py; return a list of integers."
    )
    return Task(request, threshold, tuple(public_values), tuple(hidden_values),
                npredicate, nvalue, ntrue, nfalse, spredicate, svalue, strue, sfalse)


def make_dataset(seed: int, count: int) -> list[Task]:
    return [make_task(random.Random(seed + index * 7919)) for index in range(count)]


def parse_rule(task: Task) -> tuple[str, str, str, str, str, str]:
    found = []
    for name, description in PREDICATE_TEXT.items():
        if description in task.request:
            found.append((task.request.index(description), name))
    if len(found) != 2:
        raise ValueError("request predicate parse ambiguity")
    found.sort()
    actions = []
    for name, description in ACTION_TEXT.items():
        if description in task.request:
            actions.append((task.request.index(description), name))
    if len(actions) != 4:
        raise ValueError("request action parse ambiguity")
    actions.sort()
    return found[0][1], actions[0][1], actions[1][1], found[1][1], actions[2][1], actions[3][1]


def state_bit(task: Task, stage: int, normalize_action: str | None,
              erase: bool = False) -> float:
    if erase:
        return 0.0
    raw = task.public[0][0]
    if stage == 0:
        return float(holds(raw, task.normalize_predicate, task.threshold))
    ok, normalized = intermediate(normalize_action, raw, task.threshold)
    if not ok or normalized is None:
        raise RuntimeError("unable to collect staged executable state")
    return float(holds(normalized, task.summary_predicate, task.threshold))


class PredicateGate(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.logit = nn.Linear(1, 1)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.logit(value).squeeze(-1)


def train(seed: int, tasks: list[Task], updates: int, device: torch.device) -> PredicateGate:
    torch.manual_seed(seed)
    model = PredicateGate().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-2)
    for update in range(updates):
        batch = [tasks[(update * 7 + index * 17) % len(tasks)] for index in range(min(64, len(tasks)))]
        states = []
        labels = []
        for task in batch:
            states.extend([[state_bit(task, 0, None)], [state_bit(task, 1, task.normalize_true if task.normalize_value else task.normalize_false)]])
            labels.extend([float(task.normalize_value), float(task.summary_value)])
        inputs = torch.tensor(states, dtype=torch.float32, device=device)
        targets = torch.tensor(labels, dtype=torch.float32, device=device)
        loss = nn.functional.binary_cross_entropy_with_logits(model(inputs), targets)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
    return model


@torch.no_grad()
def branch(model: PredicateGate, state: float, true_action: str,
           false_action: str, device: torch.device) -> str:
    value = torch.tensor([[state]], dtype=torch.float32, device=device)
    return true_action if bool(model(value).item() >= 0.0) else false_action


def learned_pair(model: PredicateGate, task: Task, device: torch.device,
                 erase: bool = False, placebo: tuple[float, float] | None = None) -> tuple[str, str]:
    _, ntrue, nfalse, _, strue, sfalse = parse_rule(task)
    nstate = state_bit(task, 0, None, erase) if placebo is None else placebo[0]
    naction = branch(model, nstate, ntrue, nfalse, device)
    sstate = state_bit(task, 1, naction, erase) if placebo is None else placebo[1]
    saction = branch(model, sstate, strue, sfalse, device)
    return naction, saction


def symbolic_pair(task: Task) -> tuple[str, str]:
    _, ntrue, nfalse, _, strue, sfalse = parse_rule(task)
    naction = ntrue if state_bit(task, 0, None) else nfalse
    saction = strue if state_bit(task, 1, naction) else sfalse
    return naction, saction


def passes(task: Task, pair: tuple[str, str], hidden: bool = False) -> bool:
    cases = task.hidden if hidden else task.public
    for values, expected in cases:
        ok, output, _, _ = run_repo(pair[0], pair[1], values, task.threshold)
        if not ok or output != expected:
            return False
    return True


def verified_pair(task: Task, first: tuple[str, str]) -> tuple[tuple[str, str], int]:
    candidates = [first]
    for normalize_action in NORMALIZE_ACTIONS:
        for summary_action in SUMMARY_ACTIONS:
            pair = (normalize_action, summary_action)
            if pair not in candidates:
                candidates.append(pair)
    for index, pair in enumerate(candidates[:16], start=1):
        if passes(task, pair):
            return pair, index
    return first, min(16, len(candidates))


def metric_row(label: str, tasks: list[Task], model: PredicateGate | None,
               device: torch.device, public_verify: bool = False,
               state_mode: str = "normal") -> dict[str, object]:
    raw_pass = hidden_pass = syntax = compile_rate = 0
    causal_changed = placebo_changed = 0
    expansions: list[int] = []
    latencies: list[float] = []
    for index, task in enumerate(tasks):
        if label == "symbolic":
            pair = symbolic_pair(task)
        elif label == "null":
            pair = (None, None)
        else:
            if state_mode == "erase":
                pair = learned_pair(model, task, device, erase=True)
            elif state_mode == "placebo":
                other = tasks[(index * 19 + 3) % len(tasks)]
                placebo = (state_bit(other, 0, None), state_bit(other, 1, symbolic_pair(other)[0]))
                pair = learned_pair(model, task, device, placebo=placebo)
            else:
                pair = learned_pair(model, task, device)
        if pair[0] is None:
            actual_pair = (None, None)
        elif public_verify:
            actual_pair, count = verified_pair(task, pair)
            expansions.append(count)
        else:
            actual_pair = pair
        started = time.perf_counter()
        public_ok = passes(task, actual_pair)
        hidden_ok = passes(task, actual_pair, hidden=True)
        elapsed = time.perf_counter() - started
        raw_pass += int(public_ok)
        hidden_pass += int(hidden_ok)
        compile_ok = all(run_repo(actual_pair[0], actual_pair[1], values, task.threshold)[0] for values, _ in task.public)
        syntax += int(compile_ok)
        compile_rate += int(compile_ok)
        latencies.append(elapsed * 1000.0)
        if model is not None and state_mode == "normal":
            normal = learned_pair(model, task, device)
            erased = learned_pair(model, task, device, erase=True)
            causal_changed += int(normal != erased)
            other = tasks[(index * 19 + 3) % len(tasks)]
            placebo = (state_bit(other, 0, None), state_bit(other, 1, symbolic_pair(other)[0]))
            placebo_changed += int(normal != learned_pair(model, task, device, placebo=placebo))
    count = max(1, len(tasks))
    return {
        "label": label,
        "tasks": len(tasks),
        "raw_task_pass": raw_pass / count,
        "hidden_task_pass": hidden_pass / count,
        "syntax_rate": syntax / count,
        "compile_rate": compile_rate / count,
        "params": 0 if model is None else sum(parameter.numel() for parameter in model.parameters()),
        "latency_ms": statistics.mean(latencies) if latencies else 0.0,
        "expansions": statistics.mean(expansions) if expansions else 0.0,
        "causal_changed": causal_changed / count,
        "placebo_changed": placebo_changed / count,
    }


def append_rows(rows: list[dict[str, object]]) -> None:
    with LOG.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--updates", type=int, default=181)
    parser.add_argument("--train-count", type=int, default=512)
    parser.add_argument("--eval-count", type=int, default=256)
    parser.add_argument("--seeds", default="11,23,37")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    device = torch.device(args.device)
    seeds = [int(value) for value in args.seeds.split(",") if value]
    train_tasks = make_dataset(13014, args.train_count)
    eval_tasks = make_dataset(23014, args.eval_count)
    audit = {"train": len(train_tasks), "eval": len(eval_tasks), "parse": 0}
    for task in train_tasks[: min(100, len(train_tasks))]:
        parse_rule(task)
        audit["parse"] += 1
    print(json.dumps({"generator_audit": audit}, sort_keys=True))
    rows: list[dict[str, object]] = []
    smoke_seeds = seeds[:1] if args.smoke else seeds
    for seed in smoke_seeds:
        model = train(seed, train_tasks, args.updates, device)
        for label, verify, state_mode in (("symbolic", False, "normal"), ("learned", False, "normal"), ("learned-public", True, "normal"), ("null", False, "normal")):
            selected = None if label in ("symbolic", "null") else model
            row = metric_row(label, eval_tasks, selected, device, verify, state_mode)
            row.update({"seed": seed, "updates": args.updates, "device": str(device), "experiment": "14_iterative_repo_repair"})
            rows.append(row)
        erased = metric_row("learned-erased", eval_tasks, model, device, False, "erase")
        placebo = metric_row("learned-placebo", eval_tasks, model, device, False, "placebo")
        for row in (erased, placebo):
            row.update({"seed": seed, "updates": args.updates, "device": str(device), "experiment": "14_iterative_repo_repair"})
            rows.append(row)
        print(json.dumps({"seed": seed, "rows": rows[-6:]}, sort_keys=True))
    append_rows(rows)


if __name__ == "__main__":
    main()
