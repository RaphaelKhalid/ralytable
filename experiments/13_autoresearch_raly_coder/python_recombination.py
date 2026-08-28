"""Independent text/state recombination test for Experiment 13.

The target repair depends on an intent token and on executable prefix state.
The two controls deliberately receive only one factor; the hybrid receives
both. Candidate programs still cross the restricted Python parse/compile/exec
surface, and hidden cases are scoring-only.
"""

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
INTENTS = ("alpha", "beta", "gamma", "delta")
INTENT_TO_ID = {name: index for index, name in enumerate(INTENTS)}
STATE_DIM = suite.STATE_DIM


@dataclass(frozen=True)
class RecombTask:
    base: run.Task
    prefix: tuple[str, ...]
    public_values: tuple[tuple[int, ...], ...]
    hidden: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]
    missing: str
    intent: str


def target_label(intent: str, family: str, values: tuple[int, ...]) -> int:
    ordered = int(list(values) == sorted(values))
    unique = int(len(set(values)) == len(values))
    negative = int(any(value < 0 for value in values))
    family_id = suite.FAMILIES.index(family)
    return (INTENT_TO_ID[intent] + ordered + 2 * unique +
            3 * negative + family_id) % len(suite.CANDIDATES)


def candidate(task: RecombTask, action: str) -> tuple[str, ...]:
    return task.prefix + (action, "take", "return")


def execute(values: tuple[int, ...], task: RecombTask,
            program: tuple[str, ...]) -> tuple[bool, object, str]:
    return python_surface.python_execute(task.base, values, program)


def make_task(rng: random.Random, family: str) -> RecombTask:
    threshold = rng.randrange(-5, 6)
    take_k = 4 if family == "take_prefix" else 3
    intent = INTENTS[rng.randrange(len(INTENTS))]
    prefix = suite.prefix_for(family)
    public_values = tuple(
        suite.distinguishing_public_values(threshold, take_k, family, index)
        for index in range(3)
    )
    prefix_values = suite.run_program(public_values[0], threshold, take_k, prefix)
    missing = suite.CANDIDATES[target_label(intent, family, prefix_values)]
    target = prefix + (missing, "take", "return")
    public = tuple(
        (values, suite.run_program(values, threshold, take_k, target))
        for values in public_values
    )
    hidden_values = tuple(
        tuple(rng.randrange(-10, 11) for _ in range(rng.randrange(6, 11)))
        for _ in range(4)
    )
    hidden = tuple(
        (values, suite.run_program(values, threshold, take_k, target))
        for values in hidden_values
    )
    request = (
        f"intent {intent}. Repair a typed Python list pipeline for an "
        "independent request. Candidate edits are sort_asc, unique, reverse, and "
        f"filter_gt; prefix_family={family}; threshold={threshold}; "
        f"take={take_k}; return_type=List[Int]."
    )
    base = run.Task(
        "python_recombination", request, threshold, take_k, public,
        hidden[0][0], hidden[0][1], target, "List[Int]",
    )
    return RecombTask(base, prefix, public_values, hidden, missing, intent)


def make_dataset(rng: random.Random, count: int) -> list[RecombTask]:
    return [make_task(rng, suite.FAMILIES[index % len(suite.FAMILIES)])
            for index in range(count)]


def state_features(task: RecombTask, corrupt: str | None = None) -> list[float]:
    values = suite.run_program(
        task.public_values[0], task.base.threshold, task.base.take_k, task.prefix
    )
    return state_policy.state_features(
        task.base, task.prefix, corrupt=corrupt
    ) + suite.abstract_facts(values, corrupt=corrupt)


def tokens_for(task: RecombTask, word_to_id: dict[str, int]) -> list[int]:
    return [word_to_id.get(word.strip(".,;=0123456789-").lower(), 0)
            for word in task.base.request.split()]


def token_batch(tasks: list[RecombTask], word_to_id: dict[str, int],
                device: torch.device) -> torch.Tensor:
    rows = [tokens_for(task, word_to_id) for task in tasks]
    result = torch.zeros((len(rows), max(map(len, rows))), dtype=torch.long,
                         device=device)
    for index, row in enumerate(rows):
        result[index, :len(row)] = torch.tensor(row, device=device)
    return result


class RecombPolicy(nn.Module):
    def __init__(self, vocab_size: int, mode: str, hidden: int = 32):
        super().__init__()
        self.mode = mode
        if mode == "cyclic":
            self.embedding = nn.Embedding(vocab_size, 1)
            self.state_phase = nn.Parameter(torch.randn(STATE_DIM) * 0.05)
            self.log_scale = nn.Parameter(torch.tensor(1.0))
            self.register_buffer(
                "class_angles",
                torch.arange(len(suite.CANDIDATES), dtype=torch.float32)
                * (2.0 * torch.pi / len(suite.CANDIDATES)),
            )
            self.state_encoder = None
            self.state_add = None
            self.head = nn.Identity()
            return
        text_dim = 4 if mode == "additive" else 16
        self.embedding = nn.Embedding(vocab_size, text_dim)
        self.state_encoder = (
            nn.Sequential(nn.Linear(STATE_DIM, 16), nn.Tanh())
            if mode == "cross" else None
        )
        self.state_add = (
            nn.Linear(STATE_DIM, 4) if mode == "additive" else None
        )
        input_dim = text_dim if mode == "text-only" else (
            STATE_DIM if mode == "state-only" else hidden + STATE_DIM
        )
        if mode == "hybrid":
            input_dim = 16 + STATE_DIM
        if mode == "cross":
            input_dim = 16 * 16
        if mode == "additive":
            self.head = nn.Identity()
        else:
            self.head = nn.Sequential(
                nn.Linear(input_dim, 32), nn.Tanh(),
                nn.Linear(32, len(suite.CANDIDATES)),
            )

    def logits(self, tokens: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        if self.mode == "state-only":
            return self.head(state)
        embeddings = self.embedding(tokens)
        if self.mode == "cyclic":
            intent_phase = embeddings[:, 1, 0]
            phase = intent_phase + state @ self.state_phase
            scale = 2.0 + torch.nn.functional.softplus(self.log_scale)
            return scale * torch.cos(
                phase[:, None] - self.class_angles[None, :]
            )
        # The request grammar reserves position 1 for the intent token. This
        # keeps the text path inspectable and prevents common boilerplate from
        # washing out the independent factor.
        context = embeddings[:, 1, :]
        if self.mode == "additive":
            return context + self.state_add(state)
        if self.mode == "text-only":
            return self.head(context)
        if self.mode == "cross":
            state_latent = self.state_encoder(state)
            interaction = torch.bmm(
                state_latent.unsqueeze(2), context.unsqueeze(1)
            ).flatten(1)
            return self.head(interaction)
        return self.head(torch.cat([context, state], dim=-1))


def train(seed: int, tasks: list[RecombTask], word_to_id: dict[str, int],
          updates: int, device: torch.device, mode: str) -> tuple[RecombPolicy, list[float]]:
    torch.manual_seed(seed)
    model = RecombPolicy(len(word_to_id) + 1, mode).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)
    losses: list[float] = []
    for update in range(updates):
        batch = [tasks[(update * 7 + index * 17) % len(tasks)]
                 for index in range(min(64, len(tasks)))]
        tokens = token_batch(batch, word_to_id, device)
        state = torch.tensor([state_features(task) for task in batch],
                             dtype=torch.float32, device=device)
        labels = torch.tensor([suite.ACTION_TO_ID[task.missing] for task in batch],
                              dtype=torch.long, device=device)
        logits = model.logits(tokens, state)
        loss = nn.functional.cross_entropy(logits, labels)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return model, losses


@torch.no_grad()
def logits_for(model: RecombPolicy, task: RecombTask,
               word_to_id: dict[str, int], device: torch.device,
               corrupt_state: str | None = None,
               erase_text: bool = False) -> torch.Tensor:
    tokens = token_batch([task], word_to_id, device)
    if erase_text:
        tokens = torch.zeros_like(tokens)
    state = torch.tensor([state_features(task, corrupt=corrupt_state)],
                         dtype=torch.float32, device=device)
    return model.logits(tokens, state)[0]


def public_pass(task: RecombTask, program: tuple[str, ...]) -> bool:
    if not python_surface.compile_only(program):
        return False
    return all(execute(values, task, program)[0] and
               execute(values, task, program)[1] == expected
               for values, expected in task.base.public)


def hidden_counts(task: RecombTask, program: tuple[str, ...]) -> tuple[int, int]:
    passed = 0
    for values, expected in task.hidden:
        ok, got, _ = execute(values, task, program)
        passed += int(ok and got == expected)
    return passed, len(task.hidden)


def choose(model: RecombPolicy | None, task: RecombTask,
           word_to_id: dict[str, int], device: torch.device,
           verify: bool, corrupt_state: str | None = None,
           erase_text: bool = False) -> tuple[tuple[str, ...], int]:
    if model is None:
        ranked = list(suite.CANDIDATES)
    else:
        scores = logits_for(model, task, word_to_id, device, corrupt_state,
                            erase_text)
        ranked = sorted(suite.CANDIDATES,
                        key=lambda action: float(scores[suite.ACTION_TO_ID[action]]),
                        reverse=True)
    for expanded, action in enumerate(ranked, start=1):
        program = candidate(task, action)
        if not verify or public_pass(task, program):
            return program, expanded
    return candidate(task, ranked[0]), len(ranked)


def causal_state(model: RecombPolicy, tasks: list[RecombTask],
                 word_to_id: dict[str, int], device: torch.device) -> dict[str, float]:
    changed, preserved = [], []
    for task in tasks:
        base, _ = choose(model, task, word_to_id, device, False)
        altered, _ = choose(model, task, word_to_id, device, False,
                            corrupt_state="erase_value")
        placebo, _ = choose(model, task, word_to_id, device, False,
                            corrupt_state="noise")
        changed.append(float(altered != base))
        preserved.append(float(placebo == base))
    return {
        "recomb_state_relevant_changed_rate": statistics.mean(changed),
        "recomb_state_irrelevant_preserved_rate": statistics.mean(preserved),
        "recomb_state_causal_rate": statistics.mean(
            float(a and b) for a, b in zip(changed, preserved)
        ),
    }


def metrics(tasks: list[RecombTask], model: RecombPolicy | None,
            word_to_id: dict[str, int], device: torch.device,
            direction: str) -> dict[str, object]:
    raw_pass = full_pass = raw_tests = full_tests = total_tests = 0
    raw_compile = full_compile = 0
    expansions: list[int] = []
    latencies: list[float] = []
    verify = direction.endswith("-public") or direction == "recomb-null"
    for task in tasks:
        started = time.perf_counter()
        raw, _ = choose(model, task, word_to_id, device, False)
        raw_compile += int(python_surface.compile_only(raw))
        raw_ok, raw_n = hidden_counts(task, raw)
        raw_tests += raw_ok
        total_tests += raw_n
        raw_pass += int(raw_ok == raw_n)
        chosen, expanded = choose(model, task, word_to_id, device, verify)
        full_compile += int(python_surface.compile_only(chosen))
        full_ok, _ = hidden_counts(task, chosen)
        full_tests += full_ok
        full_pass += int(full_ok == raw_n)
        expansions.append(0 if direction == "recomb-state-only" or
                         direction == "recomb-text-only" or
                         direction == "recomb-hybrid" or
                         direction == "recomb-cross" or
                         direction == "recomb-additive" or
                         direction == "recomb-cyclic" else expanded)
        latencies.append((time.perf_counter() - started) * 1000)
    n = len(tasks)
    row: dict[str, object] = {
        "direction": direction, "tasks": n,
        "public_tests_per_task": 3, "hidden_tests_per_task": 4,
        "raw_pass_rate": raw_pass / n,
        "raw_hidden_test_rate": raw_tests / total_tests,
        "raw_compile_rate": raw_compile / n,
        "heldout_pass_rate": full_pass / n,
        "hidden_test_rate": full_tests / total_tests,
        "compile_rate": full_compile / n,
        "mean_search_expansions": statistics.mean(expansions),
        "latency_ms": statistics.mean(latencies),
        "vram_gb": (torch.cuda.max_memory_allocated(device) / 1024**3
                    if device.type == "cuda" else 0.0),
        "recomb_state_relevant_changed_rate": 0.0,
        "recomb_state_irrelevant_preserved_rate": 0.0,
        "recomb_state_causal_rate": 0.0,
    }
    if model is not None and model.mode in {"state-only", "hybrid", "cross", "additive", "cyclic"}:
        row.update(causal_state(model, tasks, word_to_id, device))
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
    parser.add_argument("--directions", default="recomb-null,recomb-state-only,recomb-text-only,recomb-hybrid,recomb-hybrid-public,recomb-cross,recomb-cross-public")
    args = parser.parse_args()
    device = torch.device(
        "cuda" if args.device == "cuda" or
        (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )
    directions = tuple(args.directions.split(","))
    allowed = {"recomb-null", "recomb-state-only", "recomb-text-only",
               "recomb-hybrid", "recomb-hybrid-public", "recomb-cross",
               "recomb-cross-public", "recomb-additive",
               "recomb-additive-public", "recomb-cyclic",
               "recomb-cyclic-public"}
    if set(directions) - allowed:
        raise ValueError(f"unknown directions: {sorted(set(directions) - allowed)}")
    for seed_text in args.seeds.split(","):
        seed = int(seed_text)
        train_tasks = make_dataset(random.Random(310000 + seed), args.train_count)
        eval_tasks = make_dataset(random.Random(320000), args.eval_count)
        word_to_id = {word: index for index, word in enumerate(
            sorted(set(word.strip(".,;=0123456789-").lower()
                       for task in train_tasks + eval_tasks
                       for word in task.base.request.split())), start=1
        )}
        for direction in directions:
            if direction == "recomb-null":
                model = None
                losses = [0.0, 0.0]
            else:
                mode = ("state-only" if direction == "recomb-state-only" else
                        "text-only" if direction == "recomb-text-only" else
                        "cross" if direction.startswith("recomb-cross") else
                        "additive" if direction.startswith("recomb-additive") else
                        "cyclic" if direction.startswith("recomb-cyclic") else
                        "hybrid")
                model, losses = train(seed, train_tasks, word_to_id,
                                      args.updates, device, mode)
                model.eval()
            row = metrics(eval_tasks, model, word_to_id, device, direction)
            params = (sum(p.numel() for p in model.parameters() if p.requires_grad)
                      if model is not None else 0)
            if params >= 9_000_000:
                raise RuntimeError(f"learned parameter gate exceeded: {params}")
            row.update({
                "learned_params": params, "seed": seed,
                "checkpoint": f"recomb-intentfirst-seed-{seed}-u{args.updates}-{direction}",
                "representation": "intent-first-token",
                "hypothesis": "independent text intent and executable state must both guide repair",
                "change": direction, "train_updates": args.updates,
                "train_loss_start": losses[0], "train_loss_end": losses[-1],
                "status": "exploratory",
            })
            append(row)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
