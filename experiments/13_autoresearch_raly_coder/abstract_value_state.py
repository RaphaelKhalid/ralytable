"""State-dependent repair where the missing operation is hidden from text."""

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
CANDIDATES = ("sort_asc", "unique")
ACTION_TO_ID = {action: index for index, action in enumerate(CANDIDATES)}
ABSTRACT_DIM = 7
STATE_DIM = state_policy.STATE_DIM + ABSTRACT_DIM
EVAL_COUNT_DEFAULT = 48


@dataclass(frozen=True)
class ValueTask:
    base: state_policy.Task
    request: str
    public_values: tuple[int, ...]
    filtered_values: tuple[int, ...]
    corrupted: tuple[str, ...]
    gap: int
    missing: str


def apply_candidate(values: tuple[int, ...], threshold: int, take_k: int,
                    action: str) -> tuple[int, ...]:
    filtered = [x for x in values if x > threshold]
    if action == "sort_asc":
        filtered = sorted(filtered)
    elif action == "unique":
        seen: set[int] = set()
        filtered = [x for x in filtered if not (x in seen or seen.add(x))]
    return tuple(filtered[:take_k])


def make_task(rng: random.Random) -> ValueTask:
    threshold = rng.randrange(-5, 6)
    take_k = rng.randrange(2, 4)
    desired_sorted = bool(rng.randrange(2))
    for _ in range(1000):
        if desired_sorted:
            values = tuple(sorted(rng.randrange(-9, 10) for _ in range(8)))
        else:
            values_list = [rng.randrange(-9, 10) for _ in range(8)]
            rng.shuffle(values_list)
            values = tuple(values_list)
        filtered = tuple(x for x in values if x > threshold)
        is_sorted = list(filtered) == sorted(filtered)
        if is_sorted != desired_sorted or len(set(filtered)) == len(filtered):
            continue
        sort_out = apply_candidate(values, threshold, take_k, "sort_asc")
        unique_out = apply_candidate(values, threshold, take_k, "unique")
        if sort_out == unique_out:
            continue
        missing = "unique" if is_sorted else "sort_asc"
        target = ("input", "filter_gt", missing, "take", "return")
        public = ((values, apply_candidate(values, threshold, take_k, missing)),)
        hidden = tuple(rng.randrange(-9, 10) for _ in range(8))
        expected = apply_candidate(hidden, threshold, take_k, missing)
        request = (
            "Write a typed Python normalizer. Choose the canonical operation "
            "from sort_asc or unique using the current runtime list state; "
            f"threshold={threshold}; take={take_k}; return_type=List[Int]. "
            "The executable sketch is input,filter_gt,take,return."
        )
        base = state_policy.Task(
            "abstract_value_normalize", request, threshold, take_k, public,
            hidden, expected, target, "List[Int]",
        )
        return ValueTask(
            base, request, values, filtered,
            ("input", "filter_gt", "take", "return"), 2, missing,
        )
    raise RuntimeError("could not construct a balanced value-state task")


def abstract_facts(task: ValueTask, *, corrupt: str | None = None) -> list[float]:
    values = list(task.filtered_values)
    if corrupt == "erase_value":
        return [0.0] * ABSTRACT_DIM
    if not values:
        return [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    ordered = float(values == sorted(values))
    unique = float(len(set(values)) == len(values))
    negative = float(any(x < 0 for x in values))
    short = float(len(values) <= 2)
    long = float(len(values) >= 5)
    nonnegative_sum = float(sum(values) >= 0)
    return [0.0, ordered, unique, negative, short, long, nonnegative_sum]


def features(task: ValueTask, *, corrupt: str | None = None) -> list[float]:
    return state_policy.state_features(
        task.base, task.corrupted[:task.gap], corrupt=corrupt
    ) + abstract_facts(task, corrupt=corrupt)


class ValueStatePolicy(nn.Module):
    def __init__(self, vocab_size: int, hidden: int = 64):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, 24)
        self.encoder = nn.GRU(24, hidden, batch_first=True)
        self.head = nn.Sequential(
            nn.Linear(hidden + STATE_DIM, hidden),
            nn.Tanh(),
            nn.Linear(hidden, len(CANDIDATES)),
        )
        self.state_gate = nn.Sequential(
            nn.Linear(STATE_DIM, 32), nn.Tanh(),
            nn.Linear(32, len(CANDIDATES)),
        )

    def logits(self, tokens: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        _, hidden = self.encoder(self.embedding(tokens))
        hidden = hidden[-1]
        return self.head(torch.cat([hidden, state], dim=-1)) + self.state_gate(state)


class StateOnlyPolicy(nn.Module):
    """A deliberately inspectable controller with no request-text pathway."""

    def __init__(self, hidden: int = 32):
        super().__init__()
        self.state_gate = nn.Sequential(
            nn.Linear(STATE_DIM, hidden), nn.Tanh(),
            nn.Linear(hidden, len(CANDIDATES)),
        )

    def logits(self, tokens: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        del tokens
        return self.state_gate(state)


def tokens_for(task: ValueTask, vocab: dict[str, int]) -> list[int]:
    return [
        vocab.get(word.strip(".,;=[]()=:-0123456789").lower(), 0)
        for word in task.request.split()
    ]


def batch_tokens(tasks: list[ValueTask], vocab: dict[str, int]) -> torch.Tensor:
    rows = [tokens_for(task, vocab) for task in tasks]
    result = torch.zeros((len(rows), max(map(len, rows))), dtype=torch.long)
    for row, ids in enumerate(rows):
        result[row, :len(ids)] = torch.tensor(ids)
    return result


def train(seed: int, tasks: list[ValueTask], vocab: dict[str, int],
          updates: int, device: torch.device,
          state_only: bool = False) -> tuple[nn.Module, list[float]]:
    torch.manual_seed(seed)
    model: nn.Module = (StateOnlyPolicy().to(device) if state_only else
                        ValueStatePolicy(len(vocab) + 1).to(device))
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)
    losses: list[float] = []
    for update in range(updates):
        batch = [tasks[(update * 5 + i * 11) % len(tasks)]
                 for i in range(min(32, len(tasks)))]
        tokens = batch_tokens(batch, vocab).to(device)
        state = torch.tensor([features(task) for task in batch],
                             dtype=torch.float32, device=device)
        erased = torch.tensor([features(task, corrupt="erase_value") for task in batch],
                              dtype=torch.float32, device=device)
        logits = model.logits(tokens, state)
        erased_logits = model.logits(tokens, erased)
        labels = torch.tensor([ACTION_TO_ID[task.missing] for task in batch],
                              dtype=torch.long, device=device)
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
def logits_for(model: nn.Module, task: ValueTask,
               vocab: dict[str, int], device: torch.device,
               corrupt: str | None = None) -> torch.Tensor:
    tokens = torch.tensor([tokens_for(task, vocab)], dtype=torch.long, device=device)
    state = torch.tensor([features(task, corrupt=corrupt)],
                         dtype=torch.float32, device=device)
    return model.logits(tokens, state)[0]


def candidate(task: ValueTask, action: str) -> tuple[str, ...]:
    return task.corrupted[:task.gap] + (action,) + task.corrupted[task.gap:]


def public_pass(task: ValueTask, actions: tuple[str, ...]) -> bool:
    for values, expected in task.base.public:
        ok, got, _ = python_surface.python_execute(task.base, values, actions)
        if not ok or got != expected:
            return False
    return True


def choose(model: nn.Module | None, task: ValueTask,
           vocab: dict[str, int], device: torch.device,
           *, verify: bool, corrupt: str | None = None
           ) -> tuple[tuple[str, ...] | None, int]:
    if model is None:
        ranked = list(CANDIDATES)
    else:
        scores = logits_for(model, task, vocab, device, corrupt=corrupt)
        ranked = sorted(CANDIDATES,
                        key=lambda action: float(scores[ACTION_TO_ID[action]]),
                        reverse=True)
    for expanded, action in enumerate(ranked, start=1):
        program = candidate(task, action)
        if not verify or public_pass(task, program):
            return program, expanded
    return None, len(ranked)


def causal_rates(model: nn.Module, tasks: list[ValueTask],
                 vocab: dict[str, int], device: torch.device,
                 *, verify: bool) -> dict[str, float]:
    changed = []
    preserved = []
    for task in tasks:
        baseline, _ = choose(model, task, vocab, device, verify=verify)
        altered, _ = choose(model, task, vocab, device, verify=verify,
                            corrupt="erase_value")
        placebo, _ = choose(model, task, vocab, device, verify=verify,
                            corrupt="noise")
        changed.append(float(altered != baseline))
        preserved.append(float(placebo == baseline))
    return {
        "abstract_state_relevant_changed_rate": statistics.mean(changed),
        "abstract_state_irrelevant_preserved_rate": statistics.mean(preserved),
        "abstract_state_causal_rate": statistics.mean(
            float(a and b) for a, b in zip(changed, preserved)
        ),
    }


def metrics(tasks: list[ValueTask], model: nn.Module | None,
            vocab: dict[str, int], device: torch.device,
            direction: str) -> dict[str, object]:
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    raw_pass = raw_compile = full_pass = full_compile = 0
    expansions: list[int] = []
    latencies: list[float] = []
    verify = direction in {
        "value-public", "value-state-only-public", "value-null"
    }
    for task in tasks:
        started = time.perf_counter()
        raw, _ = choose(model, task, vocab, device, verify=False)
        raw_pass += int(raw is not None and python_surface.hidden_pass(task.base, raw))
        raw_compile += int(raw is not None and python_surface.compile_only(raw))
        if direction in {"value-raw", "value-state-only"}:
            chosen, expanded = raw, 0
        else:
            chosen, expanded = choose(model, task, vocab, device, verify=verify)
        full_pass += int(chosen is not None and python_surface.hidden_pass(task.base, chosen))
        full_compile += int(chosen is not None and python_surface.compile_only(chosen))
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
        "abstract_state_relevant_changed_rate": 0.0,
        "abstract_state_irrelevant_preserved_rate": 0.0,
        "abstract_state_causal_rate": 0.0,
    }
    if model is not None and direction in {
        "value-public", "value-state-only-public"
    }:
        row.update(causal_rates(model, tasks, vocab, device, verify=True))
    if model is not None and direction == "value-state-only":
        row.update(causal_rates(model, tasks, vocab, device, verify=False))
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
    parser.add_argument("--eval-count", type=int, default=EVAL_COUNT_DEFAULT)
    parser.add_argument("--seeds", default="11,23,37")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument(
        "--directions",
        default="value-null,value-raw,value-public,value-state-only,value-state-only-public",
    )
    args = parser.parse_args()
    device = torch.device(
        "cuda" if args.device == "cuda" or
        (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )
    allowed = {
        "value-null", "value-raw", "value-public",
        "value-state-only", "value-state-only-public",
    }
    directions = tuple(args.directions.split(","))
    if set(directions) - allowed:
        raise ValueError(f"unknown directions: {sorted(set(directions) - allowed)}")
    for seed_text in args.seeds.split(","):
        seed = int(seed_text)
        train_rng = random.Random(240000 + seed)
        eval_rng = random.Random(250000)
        train_tasks = [make_task(train_rng) for _ in range(args.train_count)]
        eval_tasks = [make_task(eval_rng) for _ in range(args.eval_count)]
        words = set()
        for task in train_tasks + eval_tasks:
            words.update(word.strip(".,;=[]()=:-0123456789").lower()
                         for word in task.request.split())
        vocab = {word: i for i, word in enumerate(sorted(words), start=1)}
        for direction in directions:
            if direction == "value-null":
                model = None
                losses = [0.0, 0.0]
            else:
                model, losses = train(
                    seed, train_tasks, vocab, args.updates, device,
                    state_only=direction.startswith("value-state-only")
                )
                model.eval()
            row = metrics(eval_tasks, model, vocab, device, direction)
            params = (sum(p.numel() for p in model.parameters() if p.requires_grad)
                      if model is not None else 0)
            if params >= 9_000_000:
                raise RuntimeError(f"learned parameter gate exceeded: {params}")
            row.update({
                "learned_params": params, "seed": seed,
                "checkpoint": f"value-seed-{seed}-u{args.updates}-{direction}",
                "hypothesis": (
                    "abstract executable value state will identify the hidden "
                    "repair operation and remain causally legible"
                ),
                "change": direction, "train_updates": args.updates,
                "train_loss_start": losses[0], "train_loss_end": losses[-1],
                "status": "exploratory",
            })
            append(row)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
