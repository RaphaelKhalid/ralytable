"""Recurrent controller over typed executable state.

This is the next Experiment 13 hypothesis after the fixed sketch failed its
causal gate. The policy receives the request plus a serialized typed state
after every transition. Search is bounded and verifies public examples; the
hidden example is used only after selection.
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

import python_surface


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.jsonl"
PRIMITIVES = ("filter_gt", "sort_asc", "unique", "reverse", "take", "count", "sum")
ACTION_NAMES = ("input",) + PRIMITIVES + ("return", "eos")
ACTION_TO_ID = {name: index for index, name in enumerate(ACTION_NAMES)}
LIST_OPS = ("filter_gt", "sort_asc", "unique", "reverse", "take")
REDUCTIONS = ("count", "sum")
MAX_STEPS = 8
STATE_DIM = 3 + len(PRIMITIVES) + len(ACTION_NAMES) + 3
TRAIN_TEMPLATES = (
    "filter_take", "take_filter", "reverse_take", "take_reverse",
    "sort_take", "unique_take",
)
EVAL_TEMPLATES = ("take_filter_sort_unique", "reverse_filter_take_unique")


@dataclass(frozen=True)
class Task:
    template: str
    request: str
    threshold: int
    take_k: int
    public: tuple[tuple[tuple[int, ...], tuple[int, ...] | int], ...]
    hidden_values: tuple[int, ...]
    hidden_expected: tuple[int, ...] | int
    target: tuple[str, ...]
    result_type: str


def op_name(part: str) -> str:
    return {"filter": "filter_gt", "sort": "sort_asc"}.get(part, part)


def target_program(template: str) -> tuple[str, ...]:
    return tuple(["input"] + [op_name(x) for x in template.split("_")] + ["return"])


def apply_template(template: str, values: tuple[int, ...], threshold: int,
                   take_k: int) -> tuple[int, ...] | int:
    out = list(values)
    for part in template.split("_"):
        if part == "filter":
            out = [x for x in out if x > threshold]
        elif part == "sort":
            out = sorted(out)
        elif part == "unique":
            seen: set[int] = set()
            out = [x for x in out if not (x in seen or seen.add(x))]
        elif part == "reverse":
            out = list(reversed(out))
        elif part == "take":
            out = out[:take_k]
    if "count" in template:
        return len(out)
    if "sum" in template:
        return sum(out)
    return tuple(out)


def make_task(rng: random.Random, template: str, public_examples: int = 1) -> Task:
    threshold = rng.randrange(-7, 8)
    take_k = rng.randrange(1, 4)
    public: list[tuple[tuple[int, ...], tuple[int, ...] | int]] = []
    for _ in range(public_examples):
        values = tuple(rng.randrange(-12, 13) for _ in range(rng.randrange(5, 9)))
        public.append((values, apply_template(template, values, threshold, take_k)))
    hidden = tuple(rng.randrange(-12, 13) for _ in range(rng.randrange(5, 10)))
    expected = apply_template(template, hidden, threshold, take_k)
    result_type = "Int" if isinstance(expected, int) else "List[Int]"
    request = (
        "Write a typed Python function. Apply these operations in this exact "
        f"order: {template.replace('_', ', ')}. threshold={threshold}; "
        f"take={take_k}; return_type={result_type}."
    )
    return Task(template, request, threshold, take_k, tuple(public), hidden,
                expected, target_program(template), result_type)


def execute(values: tuple[int, ...], threshold: int, take_k: int,
            actions: tuple[str, ...]) -> tuple[bool, object, str]:
    typ = "Input"
    value: list[int] | int | None = None
    consumed = False
    for action in actions:
        if action == "input":
            if consumed:
                return False, None, "duplicate input"
            consumed = True
            value, typ = list(values), "List[Int]"
        elif action == "filter_gt":
            if typ != "List[Int]":
                return False, None, "filter_gt expects List[Int]"
            value = [x for x in value if x > threshold]
        elif action == "sort_asc":
            if typ != "List[Int]":
                return False, None, "sort_asc expects List[Int]"
            value = sorted(value)
        elif action == "unique":
            if typ != "List[Int]":
                return False, None, "unique expects List[Int]"
            seen: set[int] = set()
            value = [x for x in value if not (x in seen or seen.add(x))]
        elif action == "reverse":
            if typ != "List[Int]":
                return False, None, "reverse expects List[Int]"
            value = list(reversed(value))
        elif action == "take":
            if typ != "List[Int]":
                return False, None, "take expects List[Int]"
            value = value[:take_k]
        elif action in REDUCTIONS:
            if typ != "List[Int]":
                return False, None, f"{action} expects List[Int]"
            value = len(value) if action == "count" else sum(value)
            typ = "Int"
        elif action == "return":
            if value is None:
                return False, None, "return before input"
            return True, tuple(value) if isinstance(value, list) else value, ""
        else:
            return False, None, "unknown action"
    return False, None, "no return"


def legal_actions(prefix: tuple[str, ...], result_type: str) -> tuple[str, ...]:
    if not prefix:
        return ("input",)
    if prefix[-1] == "return":
        return ("eos",)
    typ = "Input"
    for action in prefix:
        if action == "input":
            typ = "List[Int]"
        elif action in REDUCTIONS:
            typ = "Int"
    if typ == "List[Int]":
        allowed = [x for x in LIST_OPS + REDUCTIONS if x not in prefix]
        if result_type == "List[Int]":
            allowed.append("return")
        return tuple(allowed)
    if typ == "Int" and result_type == "Int":
        return ("return",)
    return ()


def state_features(task: Task, prefix: tuple[str, ...], *,
                   corrupt: str | None = None) -> list[float]:
    typ = "Input"
    used = set(prefix)
    for action in prefix:
        if action == "input":
            typ = "List[Int]"
        elif action in REDUCTIONS:
            typ = "Int"
    type_bits = {"Input": [1.0, 0.0, 0.0],
                 "List[Int]": [0.0, 1.0, 0.0],
                 "Int": [0.0, 0.0, 1.0]}[typ]
    if corrupt == "erase_type":
        type_bits = [1.0, 0.0, 0.0]
    used_bits = [float(op in used) for op in PRIMITIVES]
    last_bits = [float(prefix[-1] == op) if prefix else 0.0
                 for op in ACTION_NAMES]
    features = type_bits + used_bits + last_bits + [
        len(prefix) / MAX_STEPS,
        float(task.result_type == "Int"),
        float(corrupt == "noise"),
    ]
    assert len(features) == STATE_DIM
    return features


class StatePolicy(nn.Module):
    def __init__(self, vocab_size: int, hidden: int = 64,
                 state_gate: bool = False):
        super().__init__()
        self.state_gate_enabled = state_gate
        self.embedding = nn.Embedding(vocab_size, 24)
        self.encoder = nn.GRU(24, hidden, batch_first=True)
        self.cell = nn.GRUCell(hidden + STATE_DIM, hidden)
        self.head = nn.Sequential(
            nn.Linear(hidden + STATE_DIM, hidden),
            nn.Tanh(),
            nn.Linear(hidden, len(ACTION_NAMES)),
        )
        self.state_gate = (
            nn.Sequential(
                nn.Linear(STATE_DIM, 32),
                nn.Tanh(),
                nn.Linear(32, len(ACTION_NAMES)),
            ) if state_gate else None
        )

    def encode(self, tokens: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        _, state = self.encoder(self.embedding(tokens))
        return state[-1], state[-1]

    def transition(self, context: torch.Tensor, hidden: torch.Tensor,
                   features: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        hidden = self.cell(torch.cat([context, features], dim=-1), hidden)
        logits = self.head(torch.cat([hidden, features], dim=-1))
        if self.state_gate is not None:
            logits = logits + self.state_gate(features)
        return hidden, logits


def tokens_for(task: Task, word_to_id: dict[str, int]) -> list[int]:
    return [word_to_id.get(word.strip(".,;=0123456789-").lower(), 0)
            for word in task.request.split()]


def batch_tokens(tasks: list[Task], word_to_id: dict[str, int]) -> torch.Tensor:
    rows = [tokens_for(task, word_to_id) for task in tasks]
    tensor = torch.zeros((len(rows), max(map(len, rows))), dtype=torch.long)
    for row, ids in enumerate(rows):
        tensor[row, :len(ids)] = torch.tensor(ids)
    return tensor


def train(seed: int, tasks: list[Task], word_to_id: dict[str, int],
          updates: int, device: torch.device,
          state_gate: bool = False) -> tuple[StatePolicy, list[float]]:
    torch.manual_seed(seed)
    model = StatePolicy(len(word_to_id) + 1, state_gate=state_gate).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)
    losses: list[float] = []
    for update in range(updates):
        batch = [tasks[(update * 5 + i * 11) % len(tasks)]
                 for i in range(min(32, len(tasks)))]
        token_batch = batch_tokens(batch, word_to_id).to(device)
        context, hidden = model.encode(token_batch)
        total = torch.zeros((), device=device)
        count = 0
        for step in range(MAX_STEPS):
            prefixes = [task.target[:min(step, len(task.target))] for task in batch]
            features = torch.tensor(
                [state_features(task, prefix) for task, prefix in zip(batch, prefixes)],
                dtype=torch.float32, device=device,
            )
            hidden_before = hidden
            hidden, logits = model.transition(context, hidden, features)
            labels = torch.tensor([
                ACTION_TO_ID[
                    task.target[step] if step < len(task.target) else "eos"
                ] for task in batch
            ], dtype=torch.long, device=device)
            active = torch.tensor(
                [step <= len(task.target) for task in batch],
                dtype=torch.bool, device=device,
            )
            if active.any():
                total = total + nn.functional.cross_entropy(
                    logits[active], labels[active]
                )
                if state_gate:
                    erased = torch.tensor(
                        [state_features(task, prefix, corrupt="erase_type")
                         for task, prefix in zip(batch, prefixes)],
                        dtype=torch.float32, device=device,
                    )
                    _, erased_logits = model.transition(context, hidden_before, erased)
                    type_changed = torch.tensor(
                        [state_features(task, prefix) !=
                         state_features(task, prefix, corrupt="erase_type")
                         for task, prefix in zip(batch, prefixes)],
                        dtype=torch.bool, device=device,
                    ) & active
                    if type_changed.any():
                        target_logit = logits.gather(1, labels[:, None]).squeeze(1)
                        erased_target = erased_logits.gather(
                            1, labels[:, None]
                        ).squeeze(1)
                        total = total + 0.35 * nn.functional.relu(
                            0.5 - target_logit[type_changed] +
                            erased_target[type_changed]
                        ).mean()
                count += 1
        loss = total / max(count, 1)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return model, losses


def encode_one(model: StatePolicy, task: Task, word_to_id: dict[str, int],
               device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    tokens = torch.tensor([tokens_for(task, word_to_id)], dtype=torch.long, device=device)
    return model.encode(tokens)


@torch.no_grad()
def next_logits(model: StatePolicy, context: torch.Tensor, hidden: torch.Tensor,
                task: Task, prefix: tuple[str, ...], device: torch.device,
                corrupt: str | None = None) -> tuple[torch.Tensor, torch.Tensor]:
    features = torch.tensor(
        [state_features(task, prefix, corrupt=corrupt)],
        dtype=torch.float32, device=device,
    )
    return model.transition(context, hidden, features)


def raw_decode(model: StatePolicy, task: Task, word_to_id: dict[str, int],
               device: torch.device, typed: bool = False,
               override_step: int | None = None,
               override_mode: str | None = None) -> tuple[str, ...]:
    context, hidden = encode_one(model, task, word_to_id, device)
    prefix: tuple[str, ...] = ()
    for step in range(MAX_STEPS):
        corrupt = override_mode if override_step == len(prefix) else None
        hidden_next, logits = next_logits(
            model, context, hidden, task, prefix, device, corrupt
        )
        allowed = legal_actions(prefix, task.result_type) if typed else ACTION_NAMES
        action = max(allowed, key=lambda name: float(logits[0, ACTION_TO_ID[name]]))
        if action in ("eos", "return"):
            return prefix + (("return",) if action == "return" else ())
        prefix = prefix + (action,)
        hidden = hidden_next
    return prefix


def public_pass(task: Task, actions: tuple[str, ...]) -> bool:
    for values, expected in task.public:
        ok, got, _ = python_surface.python_execute(task, values, actions)
        if not ok or got != expected:
            return False
    return True


def beam_search(model: StatePolicy | None, task: Task,
                word_to_id: dict[str, int], device: torch.device,
                beam: int = 4, budget: int = 120,
                override_step: int | None = None,
                override_mode: str | None = None) -> tuple[tuple[str, ...] | None, int]:
    if model is None:
        frontier: list[tuple[float, tuple[str, ...], None]] = [(0.0, (), None)]
    else:
        context, hidden = encode_one(model, task, word_to_id, device)
        frontier = [(0.0, (), hidden)]
    expanded = 0
    while frontier and expanded < budget:
        candidates: list[tuple[float, tuple[str, ...], torch.Tensor | None]] = []
        for score, prefix, hidden in frontier:
            allowed = legal_actions(prefix, task.result_type)
            if model is None:
                ranked = sorted(allowed, key=lambda name: ACTION_TO_ID[name])
                scored = [(score - ACTION_TO_ID[name], name, None) for name in ranked]
            else:
                context, _ = encode_one(model, task, word_to_id, device)
                hidden_next, logits = next_logits(
                    model, context, hidden, task, prefix, device,
                    corrupt=(override_mode if override_step == len(prefix)
                             else None)
                )
                log_probs = torch.log_softmax(logits[0], dim=-1)
                scored = [
                    (score + float(log_probs[ACTION_TO_ID[name]]), name, hidden_next)
                    for name in allowed
                ]
            for next_score, action, next_hidden in scored:
                expanded += 1
                if expanded > budget:
                    break
                candidate = prefix + (action,)
                if action == "return":
                    if public_pass(task, candidate):
                        return candidate, expanded
                else:
                    candidates.append((next_score, candidate, next_hidden))
        candidates.sort(key=lambda item: item[0], reverse=True)
        frontier = candidates[:beam]
    return None, expanded


def causal_beam_rate(model: StatePolicy, tasks: list[Task],
                     word_to_id: dict[str, int], device: torch.device) -> dict[str, float]:
    relevant = []
    irrelevant = []
    for task in tasks:
        baseline, _ = beam_search(model, task, word_to_id, device)
        changed, _ = beam_search(
            model, task, word_to_id, device,
            override_step=1, override_mode="erase_type"
        )
        placebo, _ = beam_search(
            model, task, word_to_id, device,
            override_step=1, override_mode="noise"
        )
        relevant.append(float(changed != baseline))
        irrelevant.append(float(placebo == baseline))
    return {
        "beam_state_relevant_changed_rate": statistics.mean(relevant),
        "beam_state_irrelevant_preserved_rate": statistics.mean(irrelevant),
        "beam_state_causal_rate": statistics.mean(
            float(a and b) for a, b in zip(relevant, irrelevant)
        ),
    }


def causal_state_rate(model: StatePolicy, tasks: list[Task],
                      word_to_id: dict[str, int], device: torch.device) -> dict[str, float]:
    relevant = []
    irrelevant = []
    for task in tasks:
        baseline = raw_decode(model, task, word_to_id, device, typed=True)
        changed = raw_decode(
            model, task, word_to_id, device, typed=True,
            override_step=1, override_mode="erase_type"
        )
        preserved = raw_decode(
            model, task, word_to_id, device, typed=True,
            override_step=1, override_mode="noise"
        )
        relevant.append(float(changed != baseline))
        irrelevant.append(float(preserved == baseline))
    return {
        "state_relevant_changed_rate": statistics.mean(relevant),
        "state_irrelevant_preserved_rate": statistics.mean(irrelevant),
        "state_causal_rate": statistics.mean(
            float(a and b) for a, b in zip(relevant, irrelevant)
        ),
    }


def metrics(tasks: list[Task], model: StatePolicy | None,
            word_to_id: dict[str, int], device: torch.device,
            direction: str) -> dict[str, object]:
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    raw_pass = raw_compile = full_pass = full_compile = 0
    expansions: list[int] = []
    latencies: list[float] = []
    for task in tasks:
        started = time.perf_counter()
        raw = task.target if model is None else raw_decode(
            model, task, word_to_id, device, typed=False
        )
        raw_compile += int(python_surface.compile_only(raw))
        raw_pass += int(python_surface.hidden_pass(task, raw))
        if direction in {"state-raw", "state-gated-raw"}:
            chosen, expanded = raw, 0
        elif direction in {"state-typed-greedy", "state-gated-greedy"}:
            chosen, expanded = raw_decode(
                model, task, word_to_id, device, typed=True
            ), 0
        else:
            chosen, expanded = beam_search(
                model, task, word_to_id, device, beam=4, budget=120
            )
        if chosen is not None:
            full_compile += int(python_surface.compile_only(chosen))
            full_pass += int(python_surface.hidden_pass(task, chosen))
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
        "state_relevant_changed_rate": 0.0,
        "state_irrelevant_preserved_rate": 0.0,
        "state_causal_rate": 0.0,
    }
    if model is not None and direction in {
        "state-typed-greedy", "state-gated-greedy"
    }:
        row.update(causal_state_rate(model, tasks, word_to_id, device))
    if model is not None and direction in {
        "state-typed-beam", "state-gated-beam"
    }:
        row.update(causal_beam_rate(model, tasks, word_to_id, device))
    row["objective"] = (1.0 - float(row["heldout_pass_rate"]) +
                        0.05 * min(float(row["mean_search_expansions"]) / 120.0, 1.0))
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
        default="state-null,state-raw,state-typed-greedy,state-typed-beam,state-gated-raw,state-gated-greedy,state-gated-beam",
        help="comma-separated directions to run",
    )
    args = parser.parse_args()
    device = torch.device(
        "cuda" if args.device == "cuda" or
        (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )
    directions = tuple(args.directions.split(","))
    allowed_directions = {
        "state-null", "state-raw", "state-typed-greedy", "state-typed-beam",
        "state-gated-raw", "state-gated-greedy", "state-gated-beam",
    }
    unknown = set(directions) - allowed_directions
    if unknown:
        raise ValueError(f"unknown directions: {sorted(unknown)}")
    for seed_text in args.seeds.split(","):
        seed = int(seed_text)
        train_rng = random.Random(120000 + seed)
        eval_rng = random.Random(130000)
        train_tasks = [
            make_task(train_rng, TRAIN_TEMPLATES[i % len(TRAIN_TEMPLATES)])
            for i in range(args.train_count)
        ]
        eval_tasks = [
            make_task(eval_rng, EVAL_TEMPLATES[i % len(EVAL_TEMPLATES)])
            for i in range(args.eval_count)
        ]
        words = set()
        for task in train_tasks + eval_tasks:
            words.update(
                word.strip(".,;=0123456789-").lower()
                for word in task.request.split()
            )
        word_to_id = {word: i for i, word in enumerate(sorted(words), start=1)}
        for direction in directions:
            if direction == "state-null":
                model = None
                losses = [0.0, 0.0]
            else:
                gated = direction.startswith("state-gated-")
                model, losses = train(
                    seed, train_tasks, word_to_id, args.updates, device,
                    state_gate=gated
                )
                model.eval()
            row = metrics(eval_tasks, model, word_to_id, device, direction)
            params = sum(p.numel() for p in model.parameters()
                         if p.requires_grad) if model is not None else 0
            row.update({
                "learned_params": params,
                "seed": seed,
                "checkpoint": f"state-seed-{seed}-u{args.updates}-{direction}",
                "hypothesis": (
                    "a recurrent policy conditioned on typed state will compose "
                    "held-out operations with a causal state intervention"
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
