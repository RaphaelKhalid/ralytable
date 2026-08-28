"""Train one small named-state candidate; never reads official benchmark data."""

from __future__ import annotations

import argparse
import json
import platform
import random
import time
from pathlib import Path

try:
    from .proxy import exact_trace_replay, intervention_rate, make_examples, placebo_preservation, score_weights
except ImportError:
    from proxy import exact_trace_replay, intervention_rate, make_examples, placebo_preservation, score_weights

try:
    import torch
    import torch.nn as nn
except Exception:
    torch = None
    nn = None


def train(config: dict, seed: int, seconds: int) -> dict:
    if torch is not None and torch.cuda.is_available() and not config.get("force_cpu", False):
        return train_torch(config, seed, seconds)
    rng = random.Random(seed)
    learning_rate = float(config.get("learning_rate", 0.15))
    epochs = int(config.get("epochs", max(10, min(500, seconds * 2))))
    dropout = float(config.get("feature_dropout", 0.0))
    train_data = make_examples(seed, int(config.get("train_examples", 192)), "development")
    weights = [rng.uniform(-0.05, 0.05) for _ in range(9)]
    started = time.perf_counter()
    steps = 0
    for _ in range(max(1, epochs)):
        for features, target in train_data:
            observed = [0.0 if dropout and rng.random() < dropout else value for value in features]
            margin = weights[0] + sum(w * x for w, x in zip(weights[1:], observed))
            prediction = 1.0 / (1.0 + pow(2.718281828, max(-40.0, min(40.0, -margin))))
            error = prediction - target
            weights[0] -= learning_rate * error
            for i, x in enumerate(observed, start=1):
                weights[i] -= learning_rate * error * x
            steps += 1
    elapsed = time.perf_counter() - started
    dev = score_weights(weights, seed, "development")
    causal = intervention_rate(weights, seed)
    placebo = placebo_preservation(weights, seed)
    return {
        "candidate_format": 1, "weights": weights, "learned_parameters": len(weights),
        "dev_score": dev, "causal_intervention_rate": causal, "placebo_preservation": placebo,
        "exact_trace_replay": exact_trace_replay(weights, seed), "search_expansions": 0,
        "latency_ms": elapsed * 1000.0 / max(1, len(train_data)), "peak_vram_gb": 0.0,
        "throughput": steps / max(elapsed, 1e-9), "simplicity": 1.0 / len(weights),
        "training_seconds": elapsed, "device": "cpu_dependency_free",
        "python": platform.python_version(), "full_system_score": dev,
        "mechanism": "named_sparse_typed_monotonic_gate",
    }


def train_torch(config: dict, seed: int, seconds: int) -> dict:
    """The primary path on WSL: one sparse linear typed-state policy."""
    torch.manual_seed(seed)
    device = torch.device("cuda")
    features, targets = zip(*make_examples(seed, int(config.get("train_examples", 192)), "development"))
    x = torch.tensor(features, dtype=torch.float32, device=device)
    y = torch.tensor(targets, dtype=torch.float32, device=device).unsqueeze(1)
    model = nn.Linear(8, 1, bias=True).to(device)
    try:
        optimizer = torch.optim.AdamW(model.parameters(), lr=float(config.get("learning_rate", 0.01)), fused=True)
    except (TypeError, RuntimeError):
        optimizer = torch.optim.AdamW(model.parameters(), lr=float(config.get("learning_rate", 0.01)))
    epochs = int(config.get("epochs", max(10, min(500, seconds * 2))))
    started = time.perf_counter()
    steps = 0
    torch.cuda.reset_peak_memory_stats(device)
    for _ in range(max(1, epochs)):
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=torch.cuda.is_bf16_supported()):
            loss = nn.functional.binary_cross_entropy_with_logits(model(x), y)
        loss.backward()
        optimizer.step()
        steps += 1
    torch.cuda.synchronize(device)
    elapsed = time.perf_counter() - started
    weights = model.weight.detach().float().cpu().reshape(-1).tolist()
    bias = float(model.bias.detach().float().cpu().item())
    weights = [bias, *weights]
    return {
        "candidate_format": 1, "weights": weights, "learned_parameters": sum(p.numel() for p in model.parameters()),
        "dev_score": score_weights(weights, seed, "development"), "causal_intervention_rate": intervention_rate(weights, seed),
        "placebo_preservation": placebo_preservation(weights, seed), "exact_trace_replay": exact_trace_replay(weights, seed),
        "search_expansions": 0, "latency_ms": elapsed * 1000.0 / max(1, steps),
        "peak_vram_gb": torch.cuda.max_memory_allocated(device) / (1024 ** 3), "throughput": steps / max(elapsed, 1e-9),
        "simplicity": 1.0 / 9.0, "training_seconds": elapsed, "device": torch.cuda.get_device_name(device),
        "bf16": bool(torch.cuda.is_bf16_supported()), "full_system_score": score_weights(weights, seed, "development"),
        "mechanism": "named_sparse_typed_monotonic_gate",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-json", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = train(json.loads(args.config_json), args.seed, args.seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("dev_score", "learned_parameters", "training_seconds", "device")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
