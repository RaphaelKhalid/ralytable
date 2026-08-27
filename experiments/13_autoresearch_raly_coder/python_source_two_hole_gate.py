"""Two-hole ordinary Python source repair with a shared typed predicate gate."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import ast
import json
from pathlib import Path
import random
import re
import statistics
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
SOURCE = """def repair(values, threshold):
    inspected = list(values)
    # HOLE_1
    # HOLE_2
    return inspected
"""


@dataclass(frozen=True)
class TwoHoleTask:
    request: str
    threshold: int
    public: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]
    hidden: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]
    predicates: tuple[str, str]
    predicate_values: tuple[bool, bool]
    true_actions: tuple[str, str]
    false_actions: tuple[str, str]


def predicate_holds(values: tuple[int, ...], name: str) -> bool:
    if name == "duplicates":
        return len(set(values)) < len(values)
    if name == "negative":
        return any(value < 0 for value in values)
    if name == "long":
        return len(values) >= 6
    raise ValueError(name)


def apply_action(values: tuple[int, ...], action: str, threshold: int) -> tuple[int, ...]:
    if action == "sort_values":
        return tuple(sorted(values))
    if action == "unique_values":
        return tuple(dict.fromkeys(values))
    if action == "reverse_values":
        return tuple(reversed(values))
    if action == "drop_threshold":
        return tuple(value for value in values if value != threshold)
    raise ValueError(action)


def render_source(action_pair: tuple[str, str] | None) -> str:
    if action_pair is None:
        lines = ("    pass", "    pass")
    else:
        lines = tuple({
            "sort_values": "    inspected = sorted(inspected)",
            "unique_values": "    inspected = list(dict.fromkeys(inspected))",
            "reverse_values": "    inspected = list(reversed(inspected))",
            "drop_threshold": "    inspected = [value for value in inspected if value != threshold]",
        }[action] for action in action_pair)
    return SOURCE.replace("    # HOLE_1", lines[0]).replace("    # HOLE_2", lines[1])


def execute_source(action_pair: tuple[str, str] | None,
                   values: tuple[int, ...], threshold: int) -> tuple[bool, tuple[int, ...] | None, str]:
    try:
        tree = ast.parse(render_source(action_pair), mode="exec")
        code = compile(tree, "generated_two_hole_repair.py", "exec")
        namespace: dict[str, object] = {}
        exec(code, {"__builtins__": __builtins__}, namespace)
        result = namespace["repair"](values, threshold)
        if not isinstance(result, list) or not all(isinstance(x, int) for x in result):
            return False, None, "wrong return type"
        return True, tuple(result), ""
    except (SyntaxError, TypeError, ValueError, KeyError, NameError) as error:
        return False, None, str(error)


def compatible_predicates(rng: random.Random) -> tuple[tuple[str, str], tuple[bool, bool]]:
    first = rng.choice(PREDICATES)
    second = rng.choice(PREDICATES)
    first_value = bool(rng.randrange(2))
    second_value = bool(rng.randrange(2))
    if first == second and first_value != second_value:
        second_value = first_value
    return (first, second), (first_value, second_value)


def sampled_values(rng: random.Random, predicates: tuple[str, str],
                   wanted: tuple[bool, bool], case_index: int,
                   threshold: int) -> tuple[int, ...]:
    length = 7 if any(p == "long" and value for p, value in zip(predicates, wanted)) else 4
    for _ in range(2000):
        values = [threshold]
        while len(values) < length:
            values.append(rng.randrange(-10, 14))
        if any(p == "duplicates" and value for p, value in zip(predicates, wanted)):
            values[1] = threshold
        if any(p == "duplicates" and not value for p, value in zip(predicates, wanted)):
            values = list(dict.fromkeys(values))
            if len(values) != length:
                continue
        if any(p == "negative" and value for p, value in zip(predicates, wanted)):
            values[2] = -3 - (case_index % 4)
        if any(p == "negative" and not value for p, value in zip(predicates, wanted)):
            if any(value < 0 for value in values):
                continue
        candidate = tuple(values)
        if any(predicate_holds(candidate, p) != value
               for p, value in zip(predicates, wanted)):
            continue
        return candidate
    raise RuntimeError(f"unable to sample predicate pair {predicates}/{wanted}")


def make_task(rng: random.Random) -> TwoHoleTask:
    predicates, wanted = compatible_predicates(rng)
    threshold = 4
    for _ in range(200):
        true_actions = [rng.choice(CANDIDATES), rng.choice(CANDIDATES)]
        false_actions = [rng.choice(CANDIDATES), rng.choice(CANDIDATES)]
        target_pair = tuple(true if value else false
                            for true, false, value in zip(true_actions, false_actions, wanted))
        try:
            public_values = tuple(sampled_values(rng, predicates, wanted, i, threshold)
                                  for i in range(3))
            hidden_values = tuple(sampled_values(rng, predicates, wanted, i + 3, threshold)
                                  for i in range(4))
        except RuntimeError:
            continue
        public = tuple((values, execute_source(target_pair, values, threshold)[1])
                       for values in public_values)
        hidden = tuple((values, execute_source(target_pair, values, threshold)[1])
                       for values in hidden_values)
        target_signature = tuple(expected for _, expected in public)
        alternatives = [
            tuple(execute_source((a1, a2), values, threshold)[1]
                  for values, _ in public)
            for a1 in CANDIDATES for a2 in CANDIDATES
        ]
        if sum(int(signature == target_signature) for signature in alternatives) == 1:
            break
    else:
        raise RuntimeError("unable to distinguish two-hole target on public cases")
    request = (
        "Repair this Python function using two rules. For the first hole, if "
        f"{PREDICATE_DESCRIPTIONS[predicates[0]]}, then "
        f"{ACTION_DESCRIPTIONS[true_actions[0]]}; otherwise "
        f"{ACTION_DESCRIPTIONS[false_actions[0]]}. For the second hole, if "
        f"{PREDICATE_DESCRIPTIONS[predicates[1]]}, then "
        f"{ACTION_DESCRIPTIONS[true_actions[1]]}; otherwise "
        f"{ACTION_DESCRIPTIONS[false_actions[1]]}. Return a list of integers."
    )
    return TwoHoleTask(request, threshold, public, hidden, predicates, wanted,
                       tuple(true_actions), tuple(false_actions))


def make_dataset(rng: random.Random, count: int) -> list[TwoHoleTask]:
    return [make_task(rng) for _ in range(count)]


def parse_rule(task: TwoHoleTask) -> tuple[tuple[str, str], tuple[tuple[str, str], tuple[str, str]]]:
    predicates = [(match.start(), name)
                  for name, description in PREDICATE_DESCRIPTIONS.items()
                  for match in re.finditer(re.escape(description), task.request)]
    actions = [(match.start(), name)
               for name, description in ACTION_DESCRIPTIONS.items()
               for match in re.finditer(re.escape(description), task.request)]
    if len(predicates) != 2 or len(actions) != 4:
        raise ValueError("two-hole request parser ambiguity")
    predicates.sort()
    actions.sort()
    return (predicates[0][1], predicates[1][1]), (
        (actions[0][1], actions[1][1]), (actions[2][1], actions[3][1])
    )


def prefix_state(task: TwoHoleTask) -> tuple[int, ...]:
    ok, state, error = execute_source(None, task.public[0][0], task.threshold)
    if not ok or state is None:
        raise RuntimeError(error)
    return state


def selected_state(task: TwoHoleTask, hole: int, erase: bool = False) -> float:
    predicates, _ = parse_rule(task)
    return 0.0 if erase else float(predicate_holds(prefix_state(task), predicates[hole]))


class PredicateGate(nn.Module):
    def __init__(self):
        super().__init__()
        self.logit = nn.Linear(1, 1)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.logit(value).squeeze(-1)


def train(seed: int, tasks: list[TwoHoleTask], updates: int,
          device: torch.device) -> tuple[PredicateGate, list[float]]:
    torch.manual_seed(seed)
    model = PredicateGate().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-2)
    losses: list[float] = []
    for update in range(updates):
        batch = [tasks[(update * 7 + index * 17) % len(tasks)]
                 for index in range(min(64, len(tasks)))]
        inputs = torch.tensor([[selected_state(task, hole)]
                               for task in batch for hole in (0, 1)],
                              dtype=torch.float32, device=device)
        labels = torch.tensor([float(task.predicate_values[hole])
                               for task in batch for hole in (0, 1)],
                              dtype=torch.float32, device=device)
        loss = nn.functional.binary_cross_entropy_with_logits(model(inputs), labels)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return model, losses


@torch.no_grad()
def learned_pair(model: PredicateGate, task: TwoHoleTask,
                 device: torch.device, erase: bool = False) -> tuple[str, str]:
    _, actions = parse_rule(task)
    result = []
    for hole in (0, 1):
        value = torch.tensor([[selected_state(task, hole, erase)]],
                             dtype=torch.float32, device=device)
        truth = bool(model(value).item() >= 0.0)
        result.append(actions[hole][0] if truth else actions[hole][1])
    return tuple(result)


def symbolic_pair(task: TwoHoleTask) -> tuple[str, str]:
    _, actions = parse_rule(task)
    return tuple(actions[hole][0] if selected_state(task, hole)
                 else actions[hole][1] for hole in (0, 1))


def pair_public_pass(task: TwoHoleTask, pair: tuple[str, str]) -> bool:
    return all(execute_source(pair, values, task.threshold)[0:2] == (True, expected)
               for values, expected in task.public)


def hidden_counts(task: TwoHoleTask, pair: tuple[str, str]) -> tuple[int, int]:
    passed = sum(int(execute_source(pair, values, task.threshold)[0:2] == (True, expected))
                 for values, expected in task.hidden)
    return passed, len(task.hidden)


def learned_public_pair(model: PredicateGate, task: TwoHoleTask,
                        device: torch.device) -> tuple[tuple[str, str], int]:
    raw = learned_pair(model, task, device)
    ranked = [raw] + [(a1, a2) for a1 in CANDIDATES for a2 in CANDIDATES if (a1, a2) != raw]
    for expanded, pair in enumerate(ranked, start=1):
        if pair_public_pass(task, pair):
            return pair, expanded
    return raw, len(ranked)


def metrics(tasks: list[TwoHoleTask], model: PredicateGate | None,
            device: torch.device, direction: str) -> dict[str, object]:
    raw_pass = full_pass = raw_tests = full_tests = total = 0
    raw_syntax = full_syntax = raw_compile = full_compile = 0
    changes, preserves, expansions, latencies = [], [], [], []
    verify = direction.endswith("-public")
    for task in tasks:
        started = time.perf_counter()
        raw = learned_pair(model, task, device) if model else symbolic_pair(task)
        raw_status = [execute_source(raw, values, task.threshold) for values, _ in task.hidden]
        raw_syntax += sum(int(status[0]) for status in raw_status)
        raw_compile += sum(int(status[0]) for status in raw_status)
        ok, count = hidden_counts(task, raw)
        raw_tests += ok
        total += count
        raw_pass += int(ok == count)
        if direction == "twohole-symbolic":
            chosen, expanded = raw, 0
        elif direction == "twohole-learned-public":
            chosen, expanded = learned_public_pair(model, task, device)
        else:
            chosen, expanded = raw, 0
        full_status = [execute_source(chosen, values, task.threshold) for values, _ in task.hidden]
        full_syntax += sum(int(status[0]) for status in full_status)
        full_compile += sum(int(status[0]) for status in full_status)
        full_ok, _ = hidden_counts(task, chosen)
        full_tests += full_ok
        full_pass += int(full_ok == count)
        if model:
            base = learned_pair(model, task, device)
            altered = learned_pair(model, task, device, erase=True)
            changes.append(float(altered != base))
            preserves.append(float(learned_pair(model, task, device) == base))
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
        "twohole_state_relevant_changed_rate": statistics.mean(changes) if changes else 0.0,
        "twohole_state_irrelevant_preserved_rate": statistics.mean(preserves) if preserves else 0.0,
    }
    row["twohole_state_causal_rate"] = row["twohole_state_relevant_changed_rate"] * row["twohole_state_irrelevant_preserved_rate"]
    row["objective"] = 1.0 - float(row["heldout_pass_rate"]) + 0.01 * float(row["mean_search_expansions"]) / (len(CANDIDATES) ** 2)
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
        train_tasks = make_dataset(random.Random(730000 + seed), args.train_count)
        eval_tasks = make_dataset(random.Random(740000), args.eval_count)
        for direction, learned in (("twohole-symbolic", False), ("twohole-learned", True), ("twohole-learned-public", True)):
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
                        "checkpoint": f"twohole-seed-{seed}-u{args.updates}-{direction}",
                        "hypothesis": "a shared typed predicate gate should compose two ordinary Python repairs",
                        "change": direction, "train_updates": args.updates,
                        "train_loss_start": losses[0], "train_loss_end": losses[-1],
                        "status": "exploratory"})
            append(row)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
