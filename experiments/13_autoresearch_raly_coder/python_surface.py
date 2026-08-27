"""Python-surface replication of Experiment 13.

The task generator and learned policy are reused, but candidate programs are
lowered to restricted Python, parsed, compiled, and executed for both public
verification and hidden evaluation. The generated source is fixed-template
code; this is an executable Python surface, not a general Python benchmark.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import random
import statistics
import time

import torch

import run


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.jsonl"


def source_for(actions: tuple[str, ...]) -> str:
    lines = [
        "def solve(xs, threshold, take_k):",
        "    values = list(xs)",
    ]
    for action in actions:
        if action == "input":
            continue
        if action == "filter_gt":
            lines.append("    values = [x for x in values if x > threshold]")
        elif action == "sort_asc":
            lines.append("    values = sorted(values)")
        elif action == "unique":
            lines.extend([
                "    seen = set()",
                "    values = [x for x in values if not (x in seen or seen.add(x))]",
            ])
        elif action == "reverse":
            lines.append("    values = list(reversed(values))")
        elif action == "take":
            lines.append("    values = values[:take_k]")
        elif action == "count":
            lines.append("    values = len(values)")
        elif action == "sum":
            lines.append("    values = sum(values)")
        elif action == "return":
            lines.append("    return values")
        else:
            lines.append("    raise ValueError('unknown operation')")
    if not any(line.strip() == "return values" for line in lines):
        lines.append("    return None")
    return "\n".join(lines) + "\n"


def python_execute(task: run.Task, values: tuple[int, ...],
                   actions: tuple[str, ...]) -> tuple[bool, object, str]:
    source = source_for(actions)
    try:
        tree = ast.parse(source, mode="exec")
        code = compile(tree, "<raly-python-surface>", "exec")
        namespace: dict[str, object] = {}
        exec(code, {"__builtins__": __builtins__}, namespace)
        result = namespace["solve"](values, task.threshold, task.take_k)
        if isinstance(result, list):
            result = tuple(result)
        return True, result, ""
    except (SyntaxError, TypeError, NameError, ValueError, RuntimeError) as exc:
        return False, None, type(exc).__name__


def compile_only(actions: tuple[str, ...]) -> bool:
    try:
        compile(ast.parse(source_for(actions), mode="exec"),
                "<raly-python-surface>", "exec")
        return True
    except SyntaxError:
        return False


def public_pass(task: run.Task, actions: tuple[str, ...]) -> bool:
    if not compile_only(actions):
        return False
    for values, expected in task.public:
        ok, got, _ = python_execute(task, values, actions)
        if not ok or got != expected:
            return False
    return True


def hidden_pass(task: run.Task, actions: tuple[str, ...]) -> bool:
    ok, got, _ = python_execute(task, task.hidden_values, actions)
    return ok and got == task.hidden_expected


def action_score(task: run.Task, action: str, step: int) -> float:
    del task, step
    order = {name: -index for index, name in enumerate(run.ACTION_NAMES)}
    return float(order[action])


def search(task: run.Task, logits: list[list[float]] | None,
           beam: int = 24, budget: int = 400) -> tuple[tuple[str, ...] | None, int]:
    frontier: list[tuple[float, tuple[str, ...]]] = [(0.0, ())]
    expanded = 0
    while frontier and expanded < budget:
        next_frontier: list[tuple[float, tuple[str, ...]]] = []
        for score, prefix in frontier:
            for action in run.legal_actions(prefix, task.result_type):
                expanded += 1
                if expanded > budget:
                    break
                step = len(prefix)
                bonus = (action_score(task, action, step) if logits is None
                         else logits[step][run.ACTION_TO_ID[action]])
                candidate = prefix + (action,)
                if action == "return":
                    if public_pass(task, candidate):
                        return candidate, expanded
                else:
                    next_frontier.append((score + bonus, candidate))
        next_frontier.sort(key=lambda item: item[0], reverse=True)
        frontier = next_frontier[:beam]
    return None, expanded


def metrics(tasks: list[run.Task], model: run.SketchPolicy | None,
            word_to_id: dict[str, int], device: torch.device,
            direction: str) -> dict[str, object]:
    raw_pass = raw_compile = full_pass = full_compile = 0
    expansions: list[int] = []
    latencies: list[float] = []
    for task in tasks:
        logits = None if model is None else run.model_logits(
            model, task, word_to_id, device
        )
        started = time.perf_counter()
        raw = task.target if model is None else run.raw_decode(logits)
        raw_compile += int(compile_only(raw))
        raw_pass += int(hidden_pass(task, raw))
        if direction == "python-raw-controller":
            chosen, expanded = raw, 0
        else:
            chosen, expanded = search(task, logits, beam=24, budget=400)
        if chosen is not None:
            full_compile += int(compile_only(chosen))
            full_pass += int(hidden_pass(task, chosen))
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
        "causal_intervention_rate": 0.0,
        "relevant_changed_rate": 0.0,
        "irrelevant_preserved_rate": 0.0,
    }
    row["objective"] = (1.0 - float(row["heldout_pass_rate"]) +
                        0.05 * min(float(row["mean_search_expansions"]) / 400.0, 1.0))
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
    args = parser.parse_args()
    device = torch.device(
        "cuda" if args.device == "cuda" or
        (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )
    results = []
    for seed_text in args.seeds.split(","):
        seed = int(seed_text)
        train_rng = random.Random(81000 + seed)
        eval_rng = random.Random(91000)
        train_tasks = [
            run.make_task(train_rng, run.TRAIN_TEMPLATES[i % len(run.TRAIN_TEMPLATES)])
            for i in range(args.train_count)
        ]
        eval_tasks = [
            run.make_task(eval_rng, run.EVAL_TEMPLATES[i % len(run.EVAL_TEMPLATES)])
            for i in range(args.eval_count)
        ]
        words = set(run.vocabulary())
        for task in train_tasks + eval_tasks:
            words.update(run.tokenize(task.request))
        word_to_id = {word: i for i, word in enumerate(sorted(words), start=1)}
        for direction in ("python-deterministic-null", "python-raw-controller",
                          "python-typed-search"):
            if device.type == "cuda":
                torch.cuda.reset_peak_memory_stats(device)
            model = None
            losses = [0.0, 0.0]
            if direction != "python-deterministic-null":
                model, losses = run.train(
                    seed, train_tasks, word_to_id, args.updates, device
                )
                model.eval()
            row = metrics(
                eval_tasks, model, word_to_id, device, direction
            )
            row.update({
                "learned_params": (run.parameter_count(model) if model is not None else 0),
                "seed": seed,
                "checkpoint": f"python-seed-{seed}-u{args.updates}-{direction}",
                "hypothesis": (
                    "Python lowering preserves typed-search benefit at the executable surface"
                ),
                "change": direction,
                "train_updates": args.updates,
                "train_loss_start": losses[0],
                "train_loss_end": losses[-1],
                "status": "exploratory",
            })
            append(row)
            results.append(row)
            print(json.dumps(row), flush=True)
    summary = {"device": str(device), "runs": results,
               "note": "Restricted generated Python surface; not general Python."}
    (ROOT / "python_surface_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
