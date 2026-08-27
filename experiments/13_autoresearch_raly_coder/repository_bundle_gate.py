"""Two-parameter typed gate over a multi-module Python repository bundle."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import ast
import json
from pathlib import Path
import random
import statistics
import sys
import types
import time

import torch
from torch import nn


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.jsonl"
PREDICATES = ("duplicates", "negative", "long")
PREDICATE_DESCRIPTIONS = {
    "duplicates": "the inspected sequence contains repeated values",
    "negative": "the inspected sequence contains a negative number",
    "long": "the inspected sequence contains at least six values",
}
CANDIDATES = ("sort_values", "unique_values", "reverse_values", "drop_threshold")
ACTION_DESCRIPTIONS = {
    "sort_values": "sort the inspected values from smallest to largest",
    "unique_values": "keep the first occurrence of each inspected value",
    "reverse_values": "read the inspected values from right to left",
    "drop_threshold": "remove values equal to the threshold",
}
TRANSFORM_SOURCE = """def repair(values, threshold):
    inspected = list(values)
    # REPAIR
    return inspected
"""
REPO_FILES = {
    "__init__.py": "from .api import solve\n",
    "api.py": "from .transforms import repair\n\ndef solve(values, threshold):\n    return repair(values, threshold)\n",
}


@dataclass(frozen=True)
class RepoTask:
    request: str
    threshold: int
    public: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]
    hidden: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]
    predicate: str
    predicate_value: bool
    true_action: str
    false_action: str


def predicate_holds(values: tuple[int, ...], name: str) -> bool:
    if name == "duplicates":
        return len(set(values)) < len(values)
    if name == "negative":
        return any(value < 0 for value in values)
    if name == "long":
        return len(values) >= 6
    raise ValueError(name)


def patch_transform(action: str | None) -> str:
    line = "    pass" if action is None else {
        "sort_values": "    inspected = sorted(inspected)",
        "unique_values": "    inspected = list(dict.fromkeys(inspected))",
        "reverse_values": "    inspected = list(reversed(inspected))",
        "drop_threshold": "    inspected = [value for value in inspected if value != threshold]",
    }[action]
    return TRANSFORM_SOURCE.replace("    # REPAIR", line)


def run_repo(action: str | None, values: tuple[int, ...],
             threshold: int) -> tuple[bool, tuple[int, ...] | None, str]:
    package = f"raly_repo_{time.time_ns()}"
    module_names = [package, f"{package}.transforms", f"{package}.api"]
    try:
        package_module = types.ModuleType(package)
        package_module.__path__ = []
        package_module.__package__ = package
        sys.modules[package] = package_module
        files = dict(REPO_FILES)
        files["transforms.py"] = patch_transform(action)
        for filename, source in (("transforms.py", files["transforms.py"]),
                                 ("api.py", files["api.py"]),
                                 ("__init__.py", files["__init__.py"])):
            tree = ast.parse(source, filename=f"{package}/{filename}", mode="exec")
            code = compile(tree, f"{package}/{filename}", "exec")
            if filename == "transforms.py":
                module_name = f"{package}.transforms"
            elif filename == "api.py":
                module_name = f"{package}.api"
            else:
                module_name = package
            module = sys.modules.get(module_name, types.ModuleType(module_name))
            module.__package__ = package
            if filename == "__init__.py":
                module.__path__ = []
            sys.modules[module_name] = module
            exec(code, module.__dict__)
        result = sys.modules[package].solve(values, threshold)
        if not isinstance(result, list) or not all(isinstance(x, int) for x in result):
            return False, None, "wrong return type"
        return True, tuple(result), ""
    except (SyntaxError, TypeError, ValueError, KeyError, NameError, ImportError) as error:
        return False, None, str(error)
    finally:
        for module_name in module_names:
            sys.modules.pop(module_name, None)


def sampled_values(rng: random.Random, predicate: str, wanted: bool,
                   case_index: int, threshold: int) -> tuple[int, ...]:
    length = 7 if predicate == "long" and wanted else 4
    for _ in range(2000):
        values = [threshold]
        while len(values) < length:
            values.append(rng.randrange(-10, 14))
        if predicate == "duplicates":
            if wanted:
                values[1] = threshold
            else:
                values = list(dict.fromkeys(values))
                if len(values) != length:
                    continue
        if predicate == "negative":
            if wanted:
                values[1] = -3 - (case_index % 4)
            elif any(value < 0 for value in values):
                continue
        candidate = tuple(values)
        if predicate_holds(candidate, predicate) != wanted:
            continue
        outputs = [run_repo(action, candidate, threshold)[1] for action in CANDIDATES]
        if len(set(outputs)) == len(CANDIDATES):
            return candidate
    raise RuntimeError(f"unable to sample repository task {predicate}/{wanted}")


def make_task(rng: random.Random) -> RepoTask:
    predicate = rng.choice(PREDICATES)
    wanted = bool(rng.randrange(2))
    actions = list(CANDIDATES)
    rng.shuffle(actions)
    true_action, false_action = actions[:2]
    threshold = 4
    public_values = tuple(sampled_values(rng, predicate, wanted, i, threshold)
                          for i in range(3))
    hidden_values = tuple(sampled_values(rng, predicate, wanted, i + 3, threshold)
                          for i in range(4))
    target = true_action if wanted else false_action
    public = tuple((values, run_repo(target, values, threshold)[1])
                   for values in public_values)
    hidden = tuple((values, run_repo(target, values, threshold)[1])
                   for values in hidden_values)
    request = (
        "Repair this repository package. In transforms.py, if "
        f"{PREDICATE_DESCRIPTIONS[predicate]}, then "
        f"{ACTION_DESCRIPTIONS[true_action]}; otherwise "
        f"{ACTION_DESCRIPTIONS[false_action]}. The public API is imported by "
        "api.py and __init__.py and must return a list of integers."
    )
    return RepoTask(request, threshold, public, hidden, predicate, wanted,
                    true_action, false_action)


def make_dataset(rng: random.Random, count: int) -> list[RepoTask]:
    return [make_task(rng) for _ in range(count)]


def parse_rule(task: RepoTask) -> tuple[str, str, str]:
    predicates = [(task.request.index(description), name)
                  for name, description in PREDICATE_DESCRIPTIONS.items()
                  if description in task.request]
    actions = [(task.request.index(description), name)
               for name, description in ACTION_DESCRIPTIONS.items()
               if description in task.request]
    if len(predicates) != 1 or len(actions) != 2:
        raise ValueError("repository request parser ambiguity")
    actions.sort()
    return predicates[0][1], actions[0][1], actions[1][1]


def selected_state(task: RepoTask, erase: bool = False) -> float:
    ok, state, error = run_repo(None, task.public[0][0], task.threshold)
    if not ok or state is None:
        raise RuntimeError(error)
    return 0.0 if erase else float(predicate_holds(state, task.predicate))


class PredicateGate(nn.Module):
    def __init__(self):
        super().__init__()
        self.logit = nn.Linear(1, 1)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.logit(value).squeeze(-1)


def train(seed: int, tasks: list[RepoTask], updates: int,
          device: torch.device) -> tuple[PredicateGate, list[float]]:
    torch.manual_seed(seed)
    model = PredicateGate().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-2)
    losses: list[float] = []
    for update in range(updates):
        batch = [tasks[(update * 7 + index * 17) % len(tasks)]
                 for index in range(min(64, len(tasks)))]
        inputs = torch.tensor([[selected_state(task)] for task in batch],
                              dtype=torch.float32, device=device)
        labels = torch.tensor([float(task.predicate_value) for task in batch],
                              dtype=torch.float32, device=device)
        loss = nn.functional.binary_cross_entropy_with_logits(model(inputs), labels)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return model, losses


@torch.no_grad()
def learned_action(model: PredicateGate, task: RepoTask,
                   device: torch.device, erase: bool = False) -> str:
    _, true_action, false_action = parse_rule(task)
    value = torch.tensor([[selected_state(task, erase)]], dtype=torch.float32, device=device)
    return true_action if bool(model(value).item() >= 0.0) else false_action


def symbolic_action(task: RepoTask) -> str:
    _, true_action, false_action = parse_rule(task)
    return true_action if selected_state(task) else false_action


def public_pass(task: RepoTask, action: str) -> bool:
    return all(run_repo(action, values, task.threshold)[0:2] == (True, expected)
               for values, expected in task.public)


def hidden_counts(task: RepoTask, action: str) -> tuple[int, int]:
    passed = sum(int(run_repo(action, values, task.threshold)[0:2] == (True, expected))
                 for values, expected in task.hidden)
    return passed, len(task.hidden)


def learned_public_action(model: PredicateGate, task: RepoTask,
                          device: torch.device) -> tuple[str, int]:
    raw = learned_action(model, task, device)
    ranked = [raw] + [action for action in CANDIDATES if action != raw]
    for expanded, action in enumerate(ranked, start=1):
        if public_pass(task, action):
            return action, expanded
    return raw, len(ranked)


def metrics(tasks: list[RepoTask], model: PredicateGate | None,
            device: torch.device, direction: str) -> dict[str, object]:
    raw_pass = full_pass = raw_tests = full_tests = total = 0
    raw_syntax = raw_compile = full_syntax = full_compile = 0
    changes, preserves, expansions, latencies = [], [], [], []
    verify = direction.endswith("-public")
    for task in tasks:
        started = time.perf_counter()
        raw = learned_action(model, task, device) if model else symbolic_action(task)
        raw_status = [run_repo(raw, values, task.threshold) for values, _ in task.hidden]
        raw_syntax += sum(int(status[0]) for status in raw_status)
        raw_compile += sum(int(status[0]) for status in raw_status)
        ok, count = hidden_counts(task, raw)
        raw_tests += ok
        total += count
        raw_pass += int(ok == count)
        if direction == "repo-symbolic":
            chosen, expanded = raw, 0
        elif direction == "repo-learned-public":
            chosen, expanded = learned_public_action(model, task, device)
        else:
            chosen, expanded = raw, 0
        full_status = [run_repo(chosen, values, task.threshold) for values, _ in task.hidden]
        full_syntax += sum(int(status[0]) for status in full_status)
        full_compile += sum(int(status[0]) for status in full_status)
        full_ok, _ = hidden_counts(task, chosen)
        full_tests += full_ok
        full_pass += int(full_ok == count)
        if model:
            base = learned_action(model, task, device)
            altered = learned_action(model, task, device, erase=True)
            changes.append(float(altered != base))
            preserves.append(float(learned_action(model, task, device) == base))
        expansions.append(expanded if verify else 0)
        latencies.append((time.perf_counter() - started) * 1000)
    n = len(tasks)
    row: dict[str, object] = {
        "direction": direction, "tasks": n,
        "public_tests_per_task": 3, "hidden_tests_per_task": 4,
        "raw_pass_rate": raw_pass / n, "raw_hidden_test_rate": raw_tests / total,
        "raw_syntax_rate": raw_syntax / (n * 4), "raw_compile_rate": raw_compile / (n * 4),
        "heldout_pass_rate": full_pass / n, "hidden_test_rate": full_tests / total,
        "syntax_rate": full_syntax / (n * 4), "compile_rate": full_compile / (n * 4),
        "mean_search_expansions": statistics.mean(expansions),
        "latency_ms": statistics.mean(latencies),
        "vram_gb": (torch.cuda.max_memory_allocated(device) / 1024**3
                    if device.type == "cuda" else 0.0),
        "repo_state_relevant_changed_rate": statistics.mean(changes) if changes else 0.0,
        "repo_state_irrelevant_preserved_rate": statistics.mean(preserves) if preserves else 0.0,
    }
    row["repo_state_causal_rate"] = row["repo_state_relevant_changed_rate"] * row["repo_state_irrelevant_preserved_rate"]
    row["objective"] = 1.0 - float(row["heldout_pass_rate"]) + 0.01 * float(row["mean_search_expansions"]) / len(CANDIDATES)
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
        train_tasks = make_dataset(random.Random(750000 + seed), args.train_count)
        eval_tasks = make_dataset(random.Random(760000), args.eval_count)
        for direction, learned in (("repo-symbolic", False), ("repo-learned", True), ("repo-learned-public", True)):
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
                        "checkpoint": f"repo-seed-{seed}-u{args.updates}-{direction}",
                        "hypothesis": "the typed predicate gate should survive cross-file repository imports",
                        "change": direction, "train_updates": args.updates,
                        "train_loss_start": losses[0], "train_loss_end": losses[-1],
                        "status": "exploratory"})
            append(row)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
