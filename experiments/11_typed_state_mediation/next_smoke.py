"""Held-out-template smoke gate for the typed-state controller.

This remains exploratory. It checks that the state fix transfers beyond the
original task template and records raw generation separately from compiler-
constrained generation. It is not a confirmatory capability benchmark.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import random
from typing import Any

import torch

import dsl
import smoke


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "next_smoke"
TRAIN_TEMPLATES = ("filter_sort_unique", "sort_filter_unique", "filter_unique_count")
EVAL_TEMPLATE = "sort_unique_count"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")


def adapter_roundtrip(model, path: Path, mode: str) -> bool:
    adapter = {k: v.detach().cpu() for k, v in model.state_dict().items()
               if "lora_" in k}
    torch.save({"mode": mode, "state": adapter}, path)
    restored = torch.load(path, map_location="cpu", weights_only=True)["state"]
    _, unexpected = model.load_state_dict(restored, strict=False)
    return not unexpected and all(
        torch.equal(restored[k], model.state_dict()[k].detach().cpu())
        for k in restored
    )


def evaluate(model, tokenizer, device, tasks, mode: str, constrained: bool,
             enforce_result_type: bool = True):
    return [smoke.run_controller(model, tokenizer, device, task, mode,
                                 constrained=constrained,
                                 enforce_result_type=enforce_result_type)
            for task in tasks]


def mean(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(row[key]) for row in rows) / max(len(rows), 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--updates", type=int, default=100)
    ap.add_argument("--tasks", type=int, default=16)
    ap.add_argument("--train-tasks", type=int, default=24)
    ap.add_argument("--seeds", default="11,23,37")
    ap.add_argument("--model", default=smoke.MODEL_ID)
    args = ap.parse_args()
    seeds = [int(x.strip()) for x in args.seeds.split(",") if x.strip()]
    OUT.mkdir(exist_ok=True)
    # Send training metrics and checkpoints to this run's output directory.
    smoke.OUT = OUT
    smoke._METRICS = OUT / "metrics.jsonl"
    if smoke._METRICS.exists():
        smoke._METRICS.unlink()

    summaries: list[dict[str, Any]] = []
    for seed in seeds:
        random.seed(seed)
        torch.manual_seed(seed)
        train_rng = random.Random(seed)
        eval_rng = random.Random(seed + 100_000)
        train_tasks = [dsl.make_task(
            train_rng, template=TRAIN_TEMPLATES[i % len(TRAIN_TEMPLATES)]
        ) for i in range(args.train_tasks)]
        eval_tasks = [dsl.make_task(eval_rng, template=EVAL_TEMPLATE)
                      for _ in range(args.tasks)]
        write_jsonl(OUT / f"seed_{seed}_eval_tasks.jsonl",
                    [asdict(t) for t in eval_tasks])

        for mode in ("transcript", "mediated"):
            try:
                import wandb
                wb = wandb.init(
                    project="ralytable", group="typed-state-next-smoke",
                    name=f"next-smoke-seed-{seed}-{mode}", job_type="smoke",
                    reinit="finish_previous",
                )
                print(f"wandb ({seed}, {mode}): {wb.url}", flush=True)
            except Exception as exc:
                print(f"wandb unavailable for {seed}/{mode}: "
                      f"{type(exc).__name__}", flush=True)

            model, tokenizer, device = smoke.load_model(args.model)
            losses = smoke.train_smoke(
                model, tokenizer, device, smoke.examples(train_tasks, mode),
                args.updates,
            )
            roundtrip = adapter_roundtrip(
                model, OUT / f"seed_{seed}_{mode}_adapter.pt", mode
            )
            typed_rows = evaluate(
                model, tokenizer, device, eval_tasks, mode, constrained=True,
                enforce_result_type=True,
            )
            untyped_rows = evaluate(
                model, tokenizer, device, eval_tasks, mode, constrained=True,
                enforce_result_type=False,
            )
            raw_rows = evaluate(
                model, tokenizer, device, eval_tasks, mode, constrained=False
            )
            write_jsonl(OUT / f"seed_{seed}_{mode}_typed.jsonl", typed_rows)
            write_jsonl(OUT / f"seed_{seed}_{mode}_untyped.jsonl", untyped_rows)
            write_jsonl(OUT / f"seed_{seed}_{mode}_raw.jsonl", raw_rows)
            result = {
                "seed": seed,
                "mode": mode,
                "eval_template": EVAL_TEMPLATE,
                "initial_loss": losses[0],
                "final_loss": losses[-1],
                "typed_pass": sum(
                    smoke.hidden_tests(t, row["result"])
                    for t, row in zip(eval_tasks, typed_rows)
                ),
                "untyped_pass": sum(
                    smoke.hidden_tests(t, row["result"])
                    for t, row in zip(eval_tasks, untyped_rows)
                ),
                "typed_parse_rate": mean(typed_rows, "parse_rate"),
                "untyped_parse_rate": mean(untyped_rows, "parse_rate"),
                "raw_pass": sum(
                    smoke.hidden_tests(t, row["result"])
                    for t, row in zip(eval_tasks, raw_rows)
                ),
                "raw_parse_rate": mean(raw_rows, "parse_rate"),
                "errors_typed": sum(bool(x["errors"]) for x in typed_rows),
                "errors_untyped": sum(bool(x["errors"]) for x in untyped_rows),
                "errors_raw": sum(bool(x["errors"]) for x in raw_rows),
                "checkpoint_roundtrip": roundtrip,
            }
            summaries.append(result)
            print(json.dumps(result), flush=True)
            try:
                import wandb
                if wandb.run is not None:
                    wandb.log({k: v for k, v in result.items()
                               if isinstance(v, (int, float))})
                    wandb.finish()
            except Exception:
                pass
            del model, tokenizer
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    aggregate = {}
    for mode in ("transcript", "mediated"):
        rows = [x for x in summaries if x["mode"] == mode]
        aggregate[mode] = {
            "mean_typed_pass_rate": mean(rows, "typed_pass") / args.tasks,
            "mean_untyped_pass_rate": mean(rows, "untyped_pass") / args.tasks,
            "mean_raw_pass_rate": mean(rows, "raw_pass") / args.tasks,
            "mean_typed_parse_rate": mean(rows, "typed_parse_rate"),
            "mean_untyped_parse_rate": mean(rows, "untyped_parse_rate"),
            "mean_raw_parse_rate": mean(rows, "raw_parse_rate"),
            "all_checkpoints_roundtrip": all(x["checkpoint_roundtrip"]
                                               for x in rows),
        }
    output = {"seeds": seeds, "tasks_per_seed": args.tasks,
              "train_templates": TRAIN_TEMPLATES,
              "held_out_template": EVAL_TEMPLATE,
              "runs": summaries, "aggregate": aggregate}
    (OUT / "summary.json").write_text(json.dumps(output, indent=2),
                                      encoding="utf-8")
    print(json.dumps(output, indent=2), flush=True)


if __name__ == "__main__":
    main()
