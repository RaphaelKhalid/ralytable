"""Experiment 13: typed sketch synthesis with proof-carrying search.

The learned component predicts a short operation sketch. A small typed
compiler masks illegal continuations and a bounded verifier searches programs
against public examples before hidden execution. This is a synthetic coding
benchmark, not a claim about general Python.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import heapq
import json
from pathlib import Path
import random
import statistics
import time
from typing import Iterable

import torch
from torch import nn


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.jsonl"
ACTION_NAMES = (
    "input", "filter_gt", "sort_asc", "unique", "reverse",
    "take", "count", "sum", "return", "eos",
)
ACTION_TO_ID = {name: i for i, name in enumerate(ACTION_NAMES)}
LIST_OPS = ("filter_gt", "sort_asc", "unique", "reverse", "take")
REDUCTIONS = ("count", "sum")
MAX_STEPS = 8
TRAIN_TEMPLATES = (
    "filter_sort_unique",
    "sort_filter_unique",
    "filter_unique_count",
    "reverse_take_count",
    "sort_unique_sum",
    "filter_sort_sum",
)
EVAL_TEMPLATES = ("sort_unique_count", "reverse_filter_sum")


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


def target_program(template: str) -> tuple[str, ...]:
    actions = ["input"]
    for part in template.split("_"):
        actions.append({"filter": "filter_gt", "sort": "sort_asc"}.get(part, part))
    actions.append("return")
    return tuple(actions)


def expected_for(template: str, values: Iterable[int], threshold: int,
                 take_k: int) -> tuple[tuple[int, ...] | int, tuple[str, ...], str]:
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
        return len(out), target_program(template), "Int"
    if "sum" in template:
        return sum(out), target_program(template), "Int"
    return tuple(out), target_program(template), "List[Int]"


def make_task(rng: random.Random, template: str) -> Task:
    threshold = rng.randrange(-7, 8)
    take_k = rng.randrange(1, 4)
    rows: list[tuple[tuple[int, ...], tuple[int, ...] | int]] = []
    for _ in range(2):
        values = tuple(rng.randrange(-12, 13) for _ in range(rng.randrange(5, 9)))
        expected, _, _ = expected_for(template, values, threshold, take_k)
        rows.append((values, expected))
    hidden = tuple(rng.randrange(-12, 13) for _ in range(rng.randrange(5, 10)))
    hidden_expected, target, result_type = expected_for(
        template, hidden, threshold, take_k
    )
    words = template.replace("_", " ")
    request = (
        f"Write a typed program that will {words}; threshold={threshold}; "
        f"take={take_k}; return_type={result_type}."
    )
    return Task(template, request, threshold, take_k, tuple(rows), hidden,
                hidden_expected, target, result_type)


def execute(values: tuple[int, ...], threshold: int, take_k: int,
            actions: tuple[str, ...] | list[str]) -> tuple[bool, tuple[int, ...] | int | None, str]:
    """Execute the tiny typed IR; returns (compiled, value, error)."""
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


def to_raly(actions: tuple[str, ...], threshold: int, take_k: int) -> str:
    lines = []
    for action in actions:
        if action == "filter_gt":
            lines.append(f"filter_gt {threshold}")
        elif action == "take":
            lines.append(f"take {take_k}")
        else:
            lines.append(action)
    return "\n".join(lines)


def compile_rate(task: Task, actions: tuple[str, ...]) -> bool:
    ok, _, _ = execute(task.hidden_values, task.threshold, task.take_k, actions)
    return ok


def hidden_pass(task: Task, actions: tuple[str, ...]) -> bool:
    ok, got, _ = execute(task.hidden_values, task.threshold, task.take_k, actions)
    return ok and got == task.hidden_expected


def public_pass(task: Task, actions: tuple[str, ...]) -> bool:
    for values, expected in task.public:
        ok, got, _ = execute(values, task.threshold, task.take_k, actions)
        if not ok or got != expected:
            return False
    return True


def abstract_type(actions: tuple[str, ...]) -> str:
    typ = "Input"
    for action in actions:
        if action == "input":
            typ = "List[Int]"
        elif action in REDUCTIONS:
            typ = "Int"
    return typ


def legal_actions(prefix: tuple[str, ...], result_type: str) -> tuple[str, ...]:
    if not prefix:
        return ("input",)
    if prefix[-1] == "return":
        return ("eos",)
    typ = abstract_type(prefix)
    if typ == "List[Int]":
        out = [x for x in LIST_OPS + REDUCTIONS if x not in prefix]
        if result_type == "List[Int]":
            out.append("return")
        return tuple(out)
    if typ == "Int" and result_type == "Int":
        return ("return",)
    return ()


def action_score(task: Task, action: str, step: int) -> float:
    # Null ordering is deliberately independent of target_program and hidden
    # expected values. It is only a stable enumeration order, never an oracle.
    order = {name: -index for index, name in enumerate(ACTION_NAMES)}
    return float(order[action])


def exhaustive_search(task: Task, logits: list[list[float]] | None,
                      beam: int = 24, budget: int = 400) -> tuple[tuple[str, ...] | None, int]:
    """Typed bounded search, verifying only against public examples."""
    frontier: list[tuple[float, tuple[str, ...]]] = [(0.0, ())]
    expanded = 0
    while frontier and expanded < budget:
        next_frontier: list[tuple[float, tuple[str, ...]]] = []
        for score, prefix in frontier:
            allowed = legal_actions(prefix, task.result_type)
            for action in allowed:
                expanded += 1
                if expanded > budget:
                    break
                step = len(prefix)
                bonus = action_score(task, action, step) if logits is None else logits[step][ACTION_TO_ID[action]]
                candidate = prefix + (action,)
                if action == "return":
                    if public_pass(task, candidate):
                        return candidate, expanded
                else:
                    next_frontier.append((score + bonus, candidate))
        next_frontier.sort(key=lambda x: x[0], reverse=True)
        frontier = next_frontier[:beam]
    return None, expanded


def local_repair_search(task: Task, logits: list[list[float]],
                        max_edits: int = 2, budget: int = 200) -> tuple[tuple[str, ...] | None, int]:
    """Verify only programs near the model's raw sketch.

    The neighborhood is generated without target or hidden-value access. The
    edit bound makes the declared sketch constrain which verified programs are
    reachable, unlike broad synthesis that can route around it.
    """
    base = raw_decode(logits)
    queue: list[tuple[int, float, tuple[str, ...]]] = [(0, 0.0, base)]
    seen = {base}
    expanded = 0
    while queue and expanded < budget:
        edits, neg_score, candidate = heapq.heappop(queue)
        if public_pass(task, candidate):
            return candidate, expanded
        if edits >= max_edits:
            continue
        neighbors: set[tuple[str, ...]] = set()
        for i in range(len(candidate)):
            neighbors.add(candidate[:i] + candidate[i + 1:])
            for action in ACTION_NAMES[:-1]:
                neighbors.add(candidate[:i] + (action,) + candidate[i + 1:])
        for i in range(len(candidate) + 1):
            for action in ACTION_NAMES[:-1]:
                neighbors.add(candidate[:i] + (action,) + candidate[i:])
        for i in range(len(candidate) - 1):
            swapped = list(candidate)
            swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
            neighbors.add(tuple(swapped))
        for neighbor in neighbors:
            if neighbor in seen or len(neighbor) > MAX_STEPS:
                continue
            seen.add(neighbor)
            expanded += 1
            if expanded > budget:
                break
            score = sum(
                logits[i][ACTION_TO_ID[action]]
                for i, action in enumerate(neighbor)
                if i < MAX_STEPS and action in ACTION_TO_ID
            )
            heapq.heappush(queue, (edits + 1, -score, neighbor))
    return None, expanded


def vocabulary() -> tuple[str, ...]:
    return (
        "write a typed program that will filter sort unique reverse take count "
        "sum threshold return type typed program".split()
    )


def tokenize(request: str) -> list[str]:
    return [word.strip(".,;=0123456789-").lower() for word in request.split()]


class SketchPolicy(nn.Module):
    def __init__(self, vocab_size: int, hidden: int = 96):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, 32)
        self.encoder = nn.GRU(32, hidden, batch_first=True)
        self.position = nn.Embedding(MAX_STEPS, 16)
        self.head = nn.Sequential(
            nn.Linear(hidden + 16 + 4, hidden),
            nn.Tanh(),
            nn.Linear(hidden, len(ACTION_NAMES)),
        )

    def forward(self, token_ids: torch.Tensor, numeric: torch.Tensor) -> torch.Tensor:
        _, state = self.encoder(self.embedding(token_ids))
        state = state[-1]
        positions = self.position(torch.arange(MAX_STEPS, device=state.device))
        repeated = state[:, None, :].expand(-1, MAX_STEPS, -1)
        nums = numeric[:, None, :].expand(-1, MAX_STEPS, -1)
        pos = positions[None, :, :].expand(state.size(0), -1, -1)
        return self.head(torch.cat([repeated, pos, nums], dim=-1))


def parameter_count(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def task_inputs(task: Task, word_to_id: dict[str, int]) -> tuple[torch.Tensor, torch.Tensor]:
    ids = [word_to_id.get(word, 0) for word in tokenize(task.request)]
    result_bit = 1.0 if task.result_type == "Int" else 0.0
    numeric = [task.threshold / 12.0, task.take_k / 3.0,
               len(task.public[0][0]) / 10.0, result_bit]
    return torch.tensor(ids, dtype=torch.long), torch.tensor(numeric, dtype=torch.float32)


def batch_inputs(tasks: list[Task], word_to_id: dict[str, int]) -> tuple[torch.Tensor, torch.Tensor]:
    encoded = [task_inputs(task, word_to_id) for task in tasks]
    max_len = max(len(x[0]) for x in encoded)
    tokens = torch.zeros((len(tasks), max_len), dtype=torch.long)
    nums = torch.stack([x[1] for x in encoded])
    for i, (ids, _) in enumerate(encoded):
        tokens[i, :len(ids)] = ids
    return tokens, nums


def target_tensor(tasks: list[Task]) -> torch.Tensor:
    targets = torch.full((len(tasks), MAX_STEPS), ACTION_TO_ID["eos"], dtype=torch.long)
    for row, task in enumerate(tasks):
        seq = list(task.target) + ["eos"]
        targets[row, :len(seq)] = torch.tensor([ACTION_TO_ID[x] for x in seq])
    return targets


def train(seed: int, tasks: list[Task], word_to_id: dict[str, int],
          updates: int, device: torch.device) -> tuple[SketchPolicy, list[float]]:
    torch.manual_seed(seed)
    # ID 0 is reserved for padding/unknown; the learned vocabulary starts at 1.
    model = SketchPolicy(len(word_to_id) + 1).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)
    losses: list[float] = []
    for step in range(updates):
        batch = [tasks[(step * 7 + i * 13) % len(tasks)]
                 for i in range(min(32, len(tasks)))]
        tokens, nums = batch_inputs(batch, word_to_id)
        logits = model(tokens.to(device), nums.to(device))
        targets = target_tensor(batch).to(device)
        loss = nn.functional.cross_entropy(
            logits.reshape(-1, logits.size(-1)), targets.reshape(-1)
        )
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return model, losses


@torch.no_grad()
def model_logits(model: SketchPolicy, task: Task, word_to_id: dict[str, int],
                 device: torch.device) -> list[list[float]]:
    tokens, nums = task_inputs(task, word_to_id)
    logits = model(tokens[None].to(device), nums[None].to(device))[0]
    return logits.float().cpu().tolist()


def raw_decode(logits: list[list[float]]) -> tuple[str, ...]:
    out: list[str] = []
    for row in logits:
        action = ACTION_NAMES[max(range(len(ACTION_NAMES)), key=lambda i: row[i])]
        if action in ("eos", "return"):
            if action == "return":
                out.append(action)
            break
        out.append(action)
    return tuple(out)


def typed_greedy_decode(task: Task, logits: list[list[float]]) -> tuple[str, ...]:
    """Greedy decoding with the compiler's type mask but without repair/search."""
    out: list[str] = []
    for step in range(MAX_STEPS):
        allowed = legal_actions(tuple(out), task.result_type)
        if not allowed:
            break
        action = max(allowed, key=lambda name: logits[step][ACTION_TO_ID[name]])
        if action == "eos":
            break
        out.append(action)
        if action == "return":
            break
    return tuple(out)


def intervention(task: Task, logits: list[list[float]], local: bool = False) -> dict[str, float | bool]:
    search = (lambda t, x: local_repair_search(t, x, max_edits=2, budget=200)
              if local else exhaustive_search(t, x, beam=24, budget=400))
    baseline, _ = search(task, logits)
    if baseline is None:
        return {"baseline_found": False, "sketch_changed": False,
                "relevant_changed": False,
                "irrelevant_preserved": False, "typed_causal": 0.0}
    relevant = [row[:] for row in logits]
    # Intervene on the first semantically non-commuting pair. This uses only
    # the declared request family, not the hidden expected value.
    if "reverse_filter" in task.template:
        left, right = "reverse", "filter_gt"
    else:
        left, right = "sort_asc", "unique"
    i = 1
    relevant[i][ACTION_TO_ID[left]], relevant[i][ACTION_TO_ID[right]] = (
        relevant[i][ACTION_TO_ID[right]], relevant[i][ACTION_TO_ID[left]]
    )
    raw_before = raw_decode(logits)
    raw_after = raw_decode(relevant)
    changed, _ = search(task, relevant)
    irrelevant = [row[:] for row in logits]
    for row in irrelevant:
        row[ACTION_TO_ID["eos"]] += 0.0001
    preserved, _ = search(task, irrelevant)
    changed_flag = changed != baseline
    preserved_flag = preserved == baseline
    return {
        "baseline_found": True,
        "sketch_changed": raw_after != raw_before,
        "relevant_changed": changed_flag,
        "irrelevant_preserved": preserved_flag,
        "typed_causal": float(changed_flag and preserved_flag),
    }


def metrics_for(tasks: list[Task], model: SketchPolicy | None,
                word_to_id: dict[str, int], device: torch.device,
                direction: str) -> dict[str, float | int | str]:
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    raw_pass = raw_compile = 0
    full_pass = full_compile = 0
    expansions: list[int] = []
    interventions: list[dict[str, float | bool]] = []
    inference_latencies: list[float] = []
    selection_latencies: list[float] = []
    scoring_latencies: list[float] = []
    for task in tasks:
        inference_started = time.perf_counter()
        logits = None if model is None else model_logits(model, task, word_to_id, device)
        inference_latencies.append((time.perf_counter() - inference_started) * 1000)

        selection_started = time.perf_counter()
        raw = task.target if model is None else raw_decode(logits)
        if direction == "raw-controller":
            chosen, expanded = raw, 0
        elif direction == "typed-greedy":
            chosen, expanded = typed_greedy_decode(task, logits), 0
        elif direction == "typed-local-repair":
            chosen, expanded = local_repair_search(task, logits, max_edits=2, budget=200)
        else:
            chosen, expanded = exhaustive_search(task, logits, beam=24, budget=400)
        selection_latencies.append((time.perf_counter() - selection_started) * 1000)

        scoring_started = time.perf_counter()
        raw_compile += int(compile_rate(task, raw))
        raw_pass += int(hidden_pass(task, raw))
        expansions.append(expanded)
        if chosen is not None:
            full_compile += int(compile_rate(task, chosen))
            full_pass += int(hidden_pass(task, chosen))
            if model is not None and direction in ("typed-sketch", "typed-local-repair"):
                interventions.append(intervention(task, logits, local=direction == "typed-local-repair"))
        scoring_latencies.append((time.perf_counter() - scoring_started) * 1000)
    n = len(tasks)
    out: dict[str, float | int | str] = {
        "direction": direction,
        "tasks": n,
        "raw_pass_rate": raw_pass / n,
        "raw_compile_rate": raw_compile / n,
        "heldout_pass_rate": full_pass / n,
        "compile_rate": full_compile / n,
        "mean_search_expansions": statistics.mean(expansions),
        # Historical rows called this `latency_ms`, but the old timer started
        # after model_logits() and also included hidden scoring. Keep the alias
        # for compatibility while making the timing boundary explicit for new
        # runs. End-to-end here means inference through candidate selection;
        # hidden scoring is reported separately and is not part of selection.
        "latency_ms": statistics.mean(selection_latencies),
        "model_inference_ms": statistics.mean(inference_latencies),
        "selection_latency_ms": statistics.mean(selection_latencies),
        "hidden_scoring_ms": statistics.mean(scoring_latencies),
        "end_to_end_latency_ms": statistics.mean(
            a + b for a, b in zip(inference_latencies, selection_latencies)
        ),
        "latency_semantics": "new: inference, selection, and hidden scoring are separate; latency_ms is selection alias",
        "vram_gb": (torch.cuda.max_memory_allocated(device) / 1024**3
                    if device.type == "cuda" else 0.0),
    }
    out["causal_intervention_rate"] = (
        statistics.mean(float(x["typed_causal"]) for x in interventions)
        if interventions else 0.0
    )
    out["sketch_changed_rate"] = (
        statistics.mean(float(x["sketch_changed"]) for x in interventions)
        if interventions else 0.0
    )
    out["relevant_changed_rate"] = (
        statistics.mean(float(x["relevant_changed"]) for x in interventions)
        if interventions else 0.0
    )
    out["irrelevant_preserved_rate"] = (
        statistics.mean(float(x["irrelevant_preserved"]) for x in interventions)
        if interventions else 0.0
    )
    return out


def objective(row: dict[str, float | int | str]) -> float:
    """Lower is better: hidden failure plus normalized search cost."""
    return (1.0 - float(row["heldout_pass_rate"])) + 0.05 * min(
        float(row["mean_search_expansions"]) / 400.0, 1.0
    )


def append_log(row: dict[str, object]) -> None:
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def run(seed: int, updates: int, train_count: int, eval_count: int,
        device: torch.device, checkpoint: str) -> dict[str, object]:
    train_rng = random.Random(81000 + seed)
    eval_rng = random.Random(91000)
    train_tasks = [make_task(train_rng, TRAIN_TEMPLATES[i % len(TRAIN_TEMPLATES)])
                   for i in range(train_count)]
    eval_tasks = [make_task(eval_rng, EVAL_TEMPLATES[i % len(EVAL_TEMPLATES)])
                  for i in range(eval_count)]
    words = set(vocabulary())
    for task in train_tasks + eval_tasks:
        words.update(tokenize(task.request))
    word_to_id = {word: i for i, word in enumerate(sorted(words), start=1)}
    null_row = metrics_for(eval_tasks, None, word_to_id, device, "deterministic-null")
    null_row.update({
        "learned_params": 0, "objective": objective(null_row), "seed": seed,
        "checkpoint": checkpoint + "-null",
        "hypothesis": "bounded typed enumeration is a sufficient null",
        "change": "no learned model", "status": "exploratory",
    })
    append_log(null_row)

    model, losses = train(seed, train_tasks, word_to_id, updates, device)
    params = parameter_count(model)
    if params > 9_000_000:
        raise RuntimeError(f"parameter gate failed: {params}")
    model.eval()
    rows = []
    for direction in ("raw-controller", "typed-greedy", "typed-local-repair", "typed-sketch"):
        row = metrics_for(eval_tasks, model, word_to_id, device, direction)
        row.update({
            "learned_params": params, "seed": seed,
            "checkpoint": checkpoint + "-" + direction,
            "hypothesis": "typed verification/search makes a tiny sketch policy effective",
            "change": direction, "train_updates": updates,
            "train_loss_start": losses[0], "train_loss_end": losses[-1],
            "status": "exploratory", "objective": objective(row),
        })
        append_log(row)
        rows.append(row)
    return {"seed": seed, "params": params, "loss_start": losses[0],
            "loss_end": losses[-1], "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--updates", type=int, default=180)
    parser.add_argument("--train-count", type=int, default=96)
    parser.add_argument("--eval-count", type=int, default=48)
    parser.add_argument("--seeds", default="11,23,37")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--fresh-log", action="store_true")
    args = parser.parse_args()
    device = torch.device(
        "cuda" if args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available())
        else "cpu"
    )
    if args.fresh_log and LOG.exists():
        LOG.unlink()
    print(json.dumps({
        "device": str(device),
        "cuda": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }, indent=2), flush=True)
    all_runs = []
    for seed in [int(x) for x in args.seeds.split(",") if x.strip()]:
        all_runs.append(run(seed, args.updates, args.train_count, args.eval_count,
                            device, f"seed-{seed}-u{args.updates}"))
    summary = {
        "device": str(device), "seeds": [x["seed"] for x in all_runs],
        "runs": all_runs, "gate": "<=9M learned parameters",
        "note": "Synthetic typed-program benchmark; not a general Python result.",
    }
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
