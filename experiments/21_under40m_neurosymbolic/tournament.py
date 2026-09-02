"""Recoverable HumanEval+-tuned tournament for the under-40M pipeline."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PIPELINE = ROOT / "pipeline.py"


def run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(cwd), text=True, capture_output=True, check=False)


def score(text: str) -> dict[str, float | None]:
    values: dict[str, float | None] = {"base": None, "plus": None}
    base = re.search(r"humaneval\s*\(base tests\).*?pass@1\s*:\s*([0-9]+(?:\.[0-9]+)?)", text, re.I | re.S)
    plus = re.search(r"humaneval\+\s*\(base \+ extra tests\).*?pass@1\s*:\s*([0-9]+(?:\.[0-9]+)?)", text, re.I | re.S)
    if base:
        values["base"] = float(base.group(1))
    if plus:
        values["plus"] = float(plus.group(1))
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-python", required=True)
    parser.add_argument("--eval-python", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--max-candidates", type=int, default=100)
    parser.add_argument("--start-index", type=int, default=0, help="first candidate index; use for recovery")
    parser.add_argument("--parallel", type=int, default=8, help="EvalPlus worker count")
    parser.add_argument("--stop-file", type=Path)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    manifest = args.root / "humaneval-plus-prompts.json"
    records = args.root / "tournament.jsonl"
    if not manifest.exists():
        exported = run([args.eval_python, str(PIPELINE), "export-prompts", "--output", str(manifest)], cwd=ROOT)
        if exported.returncode:
            raise SystemExit(exported.stderr or exported.stdout)
    configs = [
        {"lr": 1e-3, "dropout": 0.0, "layers": 6, "ff": 2048},
        {"lr": 5e-4, "dropout": 0.1, "layers": 8, "ff": 2048},
        {"lr": 3e-4, "dropout": 0.1, "layers": 8, "ff": 2048},
        {"lr": 2e-4, "dropout": 0.2, "layers": 8, "ff": 2048},
        {"lr": 3e-4, "dropout": 0.0, "layers": 10, "ff": 1536},
    ]
    lexical_weights = [1.0, 2.5, 4.0, 6.0]
    started = time.time()
    index = args.start_index
    processed = 0
    while processed < args.max_candidates and time.time() - started < args.hours * 3600:
        if args.stop_file and args.stop_file.exists():
            break
        config = dict(configs[index % len(configs)])
        config["heads"] = 8
        seed = 1100 + index
        checkpoint = args.root / "checkpoints" / f"candidate-{index:04d}.pt"
        samples = args.root / "samples" / f"candidate-{index:04d}.jsonl"
        metadata = args.root / "metadata" / f"candidate-{index:04d}.json"
        trained = run([args.train_python, str(PIPELINE), "train", "--output", str(checkpoint), "--seed", str(seed), "--examples", "4096", "--epochs", "10", "--config-json", json.dumps(config)], cwd=ROOT)
        row: dict[str, object] = {"candidate": index, "seed": seed, "config": config, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "train_returncode": trained.returncode}
        if trained.returncode == 0:
            row["training"] = json.loads(trained.stdout.strip().splitlines()[-1])
            weight = lexical_weights[index % len(lexical_weights)]
            generated = run([args.train_python, str(PIPELINE), "generate", "--manifest", str(manifest), "--checkpoint", str(checkpoint), "--output", str(samples), "--metadata", str(metadata), "--lexical-weight", str(weight)], cwd=ROOT)
            row["generation_returncode"] = generated.returncode
            row["lexical_weight"] = weight
            if generated.returncode == 0:
                audited = run([args.train_python, str(PIPELINE), "audit", "--manifest", str(manifest), "--checkpoint", str(checkpoint)], cwd=ROOT)
                row["audit_returncode"] = audited.returncode
                if audited.returncode == 0:
                    row["state_audit"] = json.loads(audited.stdout.strip().splitlines()[-1])
                evaluated = run([args.eval_python, str(PIPELINE), "evaluate", "--samples", str(samples), "--parallel", str(args.parallel)], cwd=ROOT)
                row["evaluation_returncode"] = evaluated.returncode
                row["scores"] = score(evaluated.stdout + "\n" + evaluated.stderr)
                row["evaluator_tail"] = (evaluated.stdout + "\n" + evaluated.stderr)[-4000:]
            else:
                row["generation_error"] = generated.stderr[-4000:]
        else:
            row["training_error"] = trained.stderr[-4000:]
        row["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with records.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        print(json.dumps(row, sort_keys=True), flush=True)
        index += 1
        processed += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
