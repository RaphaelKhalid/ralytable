"""Natural-language conditional repair proxy over executable Python state."""

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

import python_repair_suite as suite
import python_surface
import run
import state_policy


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.jsonl"
PREDICATES = ("duplicates", "negative", "long")
ACTION_DESCRIPTIONS = {
    "sort_asc": "put the values in ascending order",
    "unique": "keep only the first occurrence of each value",
    "reverse": "read the values from right to left",
    "filter_gt": "keep only values greater than the threshold",
}
PREDICATE_DESCRIPTIONS = {
    "duplicates": "the inspected list contains repeated values",
    "negative": "the inspected list contains a negative value",
    "long": "the inspected list contains at least six values",
}
STATE_DIM = suite.STATE_DIM


@dataclass(frozen=True)
class SemanticTask:
    base: run.Task
    prefix: tuple[str, ...]
    public_values: tuple[tuple[int, ...], ...]
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


def candidate(task: SemanticTask, action: str) -> tuple[str, ...]:
    return task.prefix + (action, "take", "return")


def run_candidate(task: SemanticTask, values: tuple[int, ...],
                  action: str) -> tuple[int, ...]:
    ok, result, error = python_surface.python_execute(
        task.base, values, candidate(task, action)
    )
    if not ok or not isinstance(result, tuple):
        raise RuntimeError(error)
    return result


def semantic_input(threshold: int, family: str, predicate: str,
                   predicate_value: bool, case_index: int) -> tuple[int, ...]:
    shift = 2 * (case_index % 5)
    duplicate_prefix = (
        threshold + 13 + shift, threshold + 13 + shift,
        threshold + 5 + shift, threshold + 12 + shift,
        threshold + 6 + shift, threshold + 11 + shift,
        threshold + 7 + shift, threshold + 10 + shift,
    )
    if predicate == "negative":
        prefix_values = list(duplicate_prefix)
        if predicate_value:
            prefix_values[2] = threshold + 1
        else:
            prefix_values[2] = threshold + 5 + shift
    elif predicate == "long":
        prefix_values = list(duplicate_prefix if predicate_value
                             else duplicate_prefix[:4])
    elif predicate == "duplicates":
        if predicate_value:
            prefix_values = list(duplicate_prefix)
        else:
            prefix_values = [
                threshold + 13 + shift, threshold + 5 + shift,
                threshold + 12 + shift, threshold + 6 + shift,
                threshold + 11 + shift, threshold + 7 + shift,
                threshold + 10 + shift, threshold + 8 + shift,
            ]
            prefix_values[2] = threshold - 4
    else:
        raise ValueError(predicate)
    prefix = tuple(prefix_values)
    if family == "filter_prefix":
        return prefix + (threshold - 9, threshold - 8)
    if family == "reverse_prefix":
        return tuple(reversed(prefix))
    return prefix + (threshold - 9, threshold + 4)


def make_task(rng: random.Random, family: str) -> SemanticTask:
    threshold = -5
    take_k = 4 if family == "take_prefix" else 3
    prefix = suite.prefix_for(family)
    allowed_predicates = (
        ("negative", "long") if family == "filter_prefix" else
        ("negative", "duplicates") if family == "take_prefix" else
        PREDICATES
    )
    predicate = allowed_predicates[rng.randrange(len(allowed_predicates))]
    predicate_value = bool(rng.randrange(2))
    actions = list(suite.CANDIDATES)
    rng.shuffle(actions)
    true_action, false_action = actions[:2]
    public_values = [
        semantic_input(threshold, family, predicate, predicate_value, index)
        for index in range(3)
    ]
    for values in public_values:
        prefix_values = suite.run_program(values, threshold, take_k, prefix)
        if predicate_holds(prefix_values, predicate) != predicate_value:
            raise RuntimeError(f"predicate construction failed: {family}/{predicate}")
        outputs = [
            suite.run_program(
                values, threshold, take_k, prefix + (action, "take", "return")
            ) for action in suite.CANDIDATES
        ]
        if len(set(outputs)) != len(suite.CANDIDATES):
            raise RuntimeError(f"candidate collision: {family}/{predicate}")
    prefix_values = suite.run_program(public_values[0], threshold, take_k, prefix)
    target_action = true_action if predicate_value else false_action
    target = prefix + (target_action, "take", "return")
    public = tuple(
        (values, suite.run_program(values, threshold, take_k, target))
        for values in public_values
    )
    hidden_values = [
        semantic_input(threshold, family, predicate, predicate_value,
                        3 + index + rng.randrange(0, 3))
        for index in range(4)
    ]
    hidden = [
        (values, suite.run_program(values, threshold, take_k, target))
        for values in hidden_values
    ]
    request = (
        "Repair the inspected typed Python list according to this rule: if "
        f"{PREDICATE_DESCRIPTIONS[predicate]}, then "
        f"{ACTION_DESCRIPTIONS[true_action]}; otherwise "
        f"{ACTION_DESCRIPTIONS[false_action]}. The prefix family is "
        f"{family}; threshold={threshold}; take={take_k}; return a list of integers."
    )
    base = run.Task(
        "python_semantic_repair", request, threshold, take_k, public,
        hidden[0][0], hidden[0][1], target, "List[Int]",
    )
    return SemanticTask(
        base, prefix, tuple(public_values), tuple(hidden), predicate,
        predicate_value, true_action, false_action,
    )


def make_dataset(rng: random.Random, count: int) -> list[SemanticTask]:
    return [make_task(rng, suite.FAMILIES[index % len(suite.FAMILIES)])
            for index in range(count)]


def state_features(task: SemanticTask, corrupt: str | None = None) -> list[float]:
    values = suite.run_program(
        task.public_values[0], task.base.threshold, task.base.take_k, task.prefix
    )
    return state_policy.state_features(task.base, task.prefix, corrupt=corrupt) + suite.abstract_facts(values, corrupt=corrupt)


def vocab(tasks: list[SemanticTask]) -> dict[str, int]:
    return {word: index for index, word in enumerate(
        sorted(set(word.strip(".,;=0123456789-").lower()
                   for task in tasks for word in task.base.request.split())), start=1
    )}


def token_batch(tasks: list[SemanticTask], words: dict[str, int],
                device: torch.device) -> torch.Tensor:
    rows = [[words.get(word.strip(".,;=0123456789-").lower(), 0)
             for word in task.base.request.split()] for task in tasks]
    result = torch.zeros((len(rows), max(map(len, rows))), dtype=torch.long,
                         device=device)
    for index, row in enumerate(rows):
        result[index, :len(row)] = torch.tensor(row, device=device)
    return result


class SemanticPolicy(nn.Module):
    def __init__(self, vocab_size: int, mode: str):
        super().__init__()
        self.mode = mode
        self.embedding = nn.Embedding(vocab_size, 24)
        self.state_encoder = (
            nn.Sequential(nn.Linear(STATE_DIM, 16), nn.Tanh())
            if mode == "cross" else None
        )
        if mode == "cross":
            input_dim = 24 * 16
        elif mode == "hybrid":
            input_dim = 24 + STATE_DIM
        elif mode == "text-only":
            input_dim = 24
        else:
            input_dim = STATE_DIM
        self.head = nn.Sequential(
            nn.Linear(input_dim, 32), nn.Tanh(),
            nn.Linear(32, len(suite.CANDIDATES)),
        )

    def logits(self, tokens: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        if self.mode == "state-only":
            return self.head(state)
        embedded = self.embedding(tokens)
        mask = tokens.ne(0).unsqueeze(-1)
        text = (embedded * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1)
        if self.mode == "text-only":
            return self.head(text)
        if self.mode == "cross":
            state_latent = self.state_encoder(state)
            return self.head(torch.bmm(
                state_latent.unsqueeze(2), text.unsqueeze(1)
            ).flatten(1))
        return self.head(torch.cat([text, state], dim=-1))


def train(seed: int, tasks: list[SemanticTask], words: dict[str, int],
          updates: int, device: torch.device, mode: str) -> tuple[SemanticPolicy, list[float]]:
    torch.manual_seed(seed)
    model = SemanticPolicy(len(words) + 1, mode).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)
    losses: list[float] = []
    for update in range(updates):
        batch = [tasks[(update * 7 + index * 17) % len(tasks)]
                 for index in range(min(64, len(tasks)))]
        tokens = token_batch(batch, words, device)
        state = torch.tensor([state_features(task) for task in batch],
                             dtype=torch.float32, device=device)
        labels = torch.tensor([
            suite.ACTION_TO_ID[task.true_action if task.predicate_value
                               else task.false_action]
            for task in batch
        ], dtype=torch.long, device=device)
        loss = nn.functional.cross_entropy(model.logits(tokens, state), labels)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return model, losses


@torch.no_grad()
def score(model: SemanticPolicy, task: SemanticTask, words: dict[str, int],
          device: torch.device, corrupt: str | None = None) -> torch.Tensor:
    tokens = token_batch([task], words, device)
    state = torch.tensor([state_features(task, corrupt=corrupt)],
                         dtype=torch.float32, device=device)
    return model.logits(tokens, state)[0]


def public_pass(task: SemanticTask, action: str) -> bool:
    program = candidate(task, action)
    return python_surface.compile_only(program) and all(
        python_surface.python_execute(task.base, values, program)[1] == expected
        for values, expected in task.base.public
    )


def hidden_counts(task: SemanticTask, action: str) -> tuple[int, int]:
    program = candidate(task, action)
    passed = 0
    for values, expected in task.hidden:
        ok, got, _ = python_surface.python_execute(task.base, values, program)
        passed += int(ok and got == expected)
    return passed, len(task.hidden)


def choose(model: SemanticPolicy | None, task: SemanticTask,
           words: dict[str, int], device: torch.device,
           verify: bool, corrupt: str | None = None) -> tuple[str, int]:
    if model is None:
        ranked = list(suite.CANDIDATES)
    else:
        logits = score(model, task, words, device, corrupt)
        ranked = sorted(suite.CANDIDATES,
                        key=lambda action: float(logits[suite.ACTION_TO_ID[action]]),
                        reverse=True)
    for expanded, action in enumerate(ranked, start=1):
        if not verify or public_pass(task, action):
            return action, expanded
    return ranked[0], len(ranked)


def causal(model: SemanticPolicy, tasks: list[SemanticTask],
           words: dict[str, int], device: torch.device) -> dict[str, float]:
    changed, preserved = [], []
    for task in tasks:
        base, _ = choose(model, task, words, device, False)
        altered, _ = choose(model, task, words, device, False, "erase_value")
        placebo, _ = choose(model, task, words, device, False, "noise")
        changed.append(float(altered != base))
        preserved.append(float(placebo == base))
    return {
        "semantic_state_relevant_changed_rate": statistics.mean(changed),
        "semantic_state_irrelevant_preserved_rate": statistics.mean(preserved),
        "semantic_state_causal_rate": statistics.mean(
            float(a and b) for a, b in zip(changed, preserved)
        ),
    }


def metrics(tasks: list[SemanticTask], model: SemanticPolicy | None,
            words: dict[str, int], device: torch.device,
            direction: str) -> dict[str, object]:
    verify = direction.endswith("-public") or direction == "semantic-null"
    raw_pass = full_pass = raw_tests = full_tests = total = 0
    raw_compile = full_compile = 0
    expansions: list[int] = []
    latencies: list[float] = []
    for task in tasks:
        started = time.perf_counter()
        raw, _ = choose(model, task, words, device, False)
        raw_compile += int(python_surface.compile_only(candidate(task, raw)))
        raw_ok, raw_n = hidden_counts(task, raw)
        raw_tests += raw_ok
        total += raw_n
        raw_pass += int(raw_ok == raw_n)
        chosen, expanded = choose(model, task, words, device, verify)
        full_compile += int(python_surface.compile_only(candidate(task, chosen)))
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
        "semantic_state_relevant_changed_rate": 0.0,
        "semantic_state_irrelevant_preserved_rate": 0.0,
        "semantic_state_causal_rate": 0.0,
    }
    if model is not None and model.mode in {"state-only", "hybrid", "cross"}:
        row.update(causal(model, tasks, words, device))
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
    parser.add_argument("--directions", default="semantic-null,semantic-state-only,semantic-text-only,semantic-hybrid,semantic-hybrid-public,semantic-cross,semantic-cross-public")
    args = parser.parse_args()
    device = torch.device(
        "cuda" if args.device == "cuda" or
        (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )
    all_directions = {
        "semantic-null": (None, "semantic-null"),
        "semantic-state-only": ("state-only", "semantic-state-only"),
        "semantic-text-only": ("text-only", "semantic-text-only"),
        "semantic-hybrid": ("hybrid", "semantic-hybrid"),
        "semantic-hybrid-public": ("hybrid", "semantic-hybrid-public"),
        "semantic-cross": ("cross", "semantic-cross"),
        "semantic-cross-public": ("cross", "semantic-cross-public"),
    }
    directions = [all_directions[name] for name in args.directions.split(",")]
    for seed_text in args.seeds.split(","):
        seed = int(seed_text)
        train_tasks = make_dataset(random.Random(510000 + seed), args.train_count)
        eval_tasks = make_dataset(random.Random(520000), args.eval_count)
        words = vocab(train_tasks + eval_tasks)
        for mode, direction in directions:
            if mode is None:
                model = None
                losses = [0.0, 0.0]
            else:
                model, losses = train(seed, train_tasks, words, args.updates,
                                      device, mode)
                model.eval()
            row = metrics(eval_tasks, model, words, device, direction)
            params = (sum(p.numel() for p in model.parameters() if p.requires_grad)
                      if model is not None else 0)
            if params >= 9_000_000:
                raise RuntimeError(f"learned parameter gate exceeded: {params}")
            row.update({
                "learned_params": params, "seed": seed,
                "checkpoint": f"semantic-seed-{seed}-u{args.updates}-{direction}",
                "hypothesis": "natural-language conditional semantics and executable state jointly select repair",
                "change": direction, "train_updates": args.updates,
                "train_loss_start": losses[0], "train_loss_end": losses[-1],
                "status": "exploratory",
            })
            append(row)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
