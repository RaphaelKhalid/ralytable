"""Matched learned-parser smoke for the preregistered typed-graph objective."""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
OPS = ("identity", "sort", "reverse", "unique")
OP_INDEX = {name: index for index, name in enumerate(OPS)}
PROBES = ((3, 1, 3, 2), (2, 2, 1), (), (4, 1, 2, 1, 4))
HELD_OUT = {
    ("sort", "unique"),
    ("unique", "reverse"),
    ("reverse", "sort"),
    ("identity", "unique"),
}
TRAIN_PHRASES = {
    "identity": ("leave the values unchanged", "keep the current order"),
    "sort": ("sort the values ascending", "put the values in increasing order"),
    "reverse": ("reverse the current sequence", "flip the sequence order"),
    "unique": ("remove repeated values", "keep the first copy of each value"),
}
EVAL_PHRASES = {
    "identity": ("leave the sequence unchanged", "keep the values in their current order"),
    "sort": ("sort the sequence in ascending order", "put values in increasing order"),
    "reverse": ("reverse the sequence order", "flip the values into reverse order"),
    "unique": ("remove duplicate values", "keep only the first copy of every value"),
}


@dataclass(frozen=True)
class Row:
    prompt: str
    unused_prompt: str
    counterfactual_prompt: str
    graph: tuple[int, int]
    counterfactual_graph: tuple[int, int]
    replay: int


def apply_op(name: str, values: tuple[int, ...]) -> tuple[int, ...]:
    if name == "identity":
        return values
    if name == "sort":
        return tuple(sorted(values))
    if name == "reverse":
        return tuple(reversed(values))
    if name == "unique":
        return tuple(dict.fromkeys(values))
    raise ValueError(name)


def execute(graph: tuple[int, int], probe: tuple[int, ...]) -> tuple[int, ...]:
    values = probe
    for op in graph:
        values = apply_op(OPS[op], values)
    return values


def behavior(graph: tuple[int, int]) -> tuple[tuple[int, ...], ...]:
    return tuple(execute(graph, probe) for probe in PROBES)


BEHAVIORS = sorted({behavior((a, b)) for a in range(len(OPS)) for b in range(len(OPS))})
BEHAVIOR_INDEX = {signature: index for index, signature in enumerate(BEHAVIORS)}


def render_prompt(
    first_phrase: str,
    second_phrase: str,
    *,
    name: str,
    unused: str,
) -> str:
    return (
        f"Transform integer list {name}.\n"
        f"Step one: {first_phrase}.\n"
        f"Step two: {second_phrase}.\n"
        f"Declared type: List[Int] -> List[Int].\n"
        f"Unused note: {unused}."
    )


def make_rows(seed: int, *, train: bool, per_group: int) -> list[Row]:
    rng = random.Random(seed)
    phrases = TRAIN_PHRASES if train else EVAL_PHRASES
    groups = [
        (first, second)
        for first in OPS
        for second in OPS
        if ((first, second) not in HELD_OUT) == train
    ]
    rows: list[Row] = []
    for first, second in groups:
        for index in range(per_group):
            name = f"values_{rng.randrange(10_000):04d}"
            unused = rng.choice(("blue", "copper", "north", "quiet"))
            changed_unused = rng.choice(("amber", "silver", "south", "loud"))
            alternative = rng.choice(tuple(op for op in OPS if op != first))
            first_phrase = rng.choice(phrases[first])
            second_phrase = rng.choice(phrases[second])
            alternative_phrase = rng.choice(phrases[alternative])
            prompt = render_prompt(first_phrase, second_phrase, name=name, unused=unused)
            unused_prompt = render_prompt(
                first_phrase, second_phrase, name=name, unused=changed_unused
            )
            counterfactual_prompt = render_prompt(
                alternative_phrase, second_phrase, name=name, unused=unused
            )
            graph = (OP_INDEX[first], OP_INDEX[second])
            counterfactual = (OP_INDEX[alternative], OP_INDEX[second])
            rows.append(
                Row(
                    prompt,
                    unused_prompt,
                    counterfactual_prompt,
                    graph,
                    counterfactual,
                    BEHAVIOR_INDEX[behavior(graph)],
                )
            )
    rng.shuffle(rows)
    return rows


def encode(text: str, width: int = 256) -> list[int]:
    raw = text.encode("ascii", errors="replace")[:width]
    return [byte + 1 for byte in raw] + [0] * (width - len(raw))


def torch_modules():
    import torch
    import torch.nn as nn

    return torch, nn


def build_model():
    torch, nn = torch_modules()

    class Parser(nn.Module):
        def __init__(self):
            super().__init__()
            width = 64
            self.embedding = nn.Embedding(257, width, padding_idx=0)
            self.position = nn.Parameter(torch.zeros(1, 256, width))
            layer = nn.TransformerEncoderLayer(
                d_model=width,
                nhead=4,
                dim_feedforward=192,
                dropout=0.0,
                batch_first=True,
                norm_first=True,
                activation="gelu",
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=2)
            self.norm = nn.LayerNorm(width)
            self.first = nn.Linear(width, len(OPS))
            self.second = nn.Linear(width, len(OPS))
            self.replay = nn.Linear(width, len(BEHAVIORS))

        def forward(self, ids):
            mask = ids.eq(0)
            embedded = self.embedding(ids) + self.position[:, : ids.shape[1]]
            encoded = self.encoder(embedded, src_key_padding_mask=mask)
            valid = (~mask).unsqueeze(-1)
            state = self.norm((encoded * valid).sum(1) / valid.sum(1).clamp_min(1))
            return self.first(state), self.second(state), self.replay(state)

    return Parser()


def tensors(rows: Iterable[Row], device):
    torch, _ = torch_modules()
    rows = list(rows)
    prompts = torch.tensor([encode(row.prompt) for row in rows], dtype=torch.long, device=device)
    unused = torch.tensor(
        [encode(row.unused_prompt) for row in rows], dtype=torch.long, device=device
    )
    counterfactual = torch.tensor(
        [encode(row.counterfactual_prompt) for row in rows], dtype=torch.long, device=device
    )
    first = torch.tensor([row.graph[0] for row in rows], dtype=torch.long, device=device)
    second = torch.tensor([row.graph[1] for row in rows], dtype=torch.long, device=device)
    cf_first = torch.tensor(
        [row.counterfactual_graph[0] for row in rows], dtype=torch.long, device=device
    )
    replay = torch.tensor([row.replay for row in rows], dtype=torch.long, device=device)
    return prompts, unused, counterfactual, first, second, cf_first, replay


def train(seed: int, arm: str, train_rows: list[Row], steps: int = 320) -> tuple[object, dict]:
    torch, nn = torch_modules()
    torch.manual_seed(seed)
    random.seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3)
    data = tensors(train_rows, device)
    batch_size = 64
    generator = torch.Generator(device="cpu").manual_seed(seed)
    started = time.perf_counter()
    final_terms: dict[str, float] = {}
    model.train()
    for _ in range(steps):
        indices = torch.randint(0, len(train_rows), (batch_size,), generator=generator).to(device)
        prompts, unused, counterfactual, first, second, cf_first, replay = (
            value[indices] for value in data
        )
        optimizer.zero_grad(set_to_none=True)
        first_logits, second_logits, replay_logits = model(prompts)
        graph_loss = nn.functional.cross_entropy(first_logits, first) + nn.functional.cross_entropy(
            second_logits, second
        )
        loss = graph_loss
        replay_loss = torch.zeros((), device=device)
        counterfactual_loss = torch.zeros((), device=device)
        unused_loss = torch.zeros((), device=device)
        if arm == "structured":
            replay_loss = nn.functional.cross_entropy(replay_logits, replay)
            cf_first_logits, cf_second_logits, _ = model(counterfactual)
            changed_target = cf_first_logits.gather(1, cf_first[:, None]).squeeze(1)
            old_target = cf_first_logits.gather(1, first[:, None]).squeeze(1)
            counterfactual_loss = torch.relu(1.0 - changed_target + old_target).mean()
            counterfactual_loss = counterfactual_loss + 0.25 * nn.functional.cross_entropy(
                cf_second_logits, second
            )
            unused_first, unused_second, _ = model(unused)
            unused_loss = nn.functional.mse_loss(first_logits, unused_first) + nn.functional.mse_loss(
                second_logits, unused_second
            )
            loss = graph_loss + 0.5 * replay_loss + 0.5 * counterfactual_loss + 0.25 * unused_loss
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        final_terms = {
            "total": float(loss.detach()),
            "graph": float(graph_loss.detach()),
            "replay": float(replay_loss.detach()),
            "counterfactual": float(counterfactual_loss.detach()),
            "unused": float(unused_loss.detach()),
        }
    if device.type == "cuda":
        torch.cuda.synchronize()
    return model.eval(), {
        "seconds": time.perf_counter() - started,
        "device": str(device),
        "parameters": sum(parameter.numel() for parameter in model.parameters()),
        "final_loss_terms": final_terms,
    }


def predict(model, texts: list[str], device) -> list[tuple[int, int]]:
    torch, _ = torch_modules()
    ids = torch.tensor([encode(text) for text in texts], dtype=torch.long, device=device)
    with torch.no_grad():
        first, second, _ = model(ids)
    return list(zip(first.argmax(1).tolist(), second.argmax(1).tolist()))


def evaluate(model, rows: list[Row]) -> dict[str, float]:
    torch, _ = torch_modules()
    device = next(model.parameters()).device
    normal = predict(model, [row.prompt for row in rows], device)
    unused = predict(model, [row.unused_prompt for row in rows], device)
    changed = predict(model, [row.counterfactual_prompt for row in rows], device)
    exact = sum(prediction == row.graph for prediction, row in zip(normal, rows))
    replay = sum(behavior(prediction) == behavior(row.graph) for prediction, row in zip(normal, rows))
    relevant = sum(
        prediction[0] == row.counterfactual_graph[0]
        and prediction[1] == base[1]
        and prediction[0] != base[0]
        for base, prediction, row in zip(normal, changed, rows)
    )
    invariant = sum(base == placebo for base, placebo in zip(normal, unused))
    total = len(rows)
    return {
        "exact_graph_recovery": exact / total,
        "execution_equivalent_replay": replay / total,
        "relevant_intervention_change": relevant / total,
        "unused_field_invariance": invariant / total,
        "placebo_preservation": invariant / total,
    }


def aggregate(rows: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    keys = rows[0]
    return {
        key: {
            "mean": sum(row[key] for row in rows) / len(rows),
            "min": min(row[key] for row in rows),
            "max": max(row[key] for row in rows),
        }
        for key in keys
    }


def main() -> None:
    torch, _ = torch_modules()
    train_rows = make_rows(20260903, train=True, per_group=64)
    eval_rows = make_rows(20260904, train=False, per_group=96)
    train_groups = {row.graph for row in train_rows}
    eval_groups = {row.graph for row in eval_rows}
    if train_groups & eval_groups:
        raise RuntimeError("semantic group leakage")
    results: dict[str, list[dict[str, float]]] = {"null": [], "structured": []}
    run_records = []
    for seed in (11, 23, 37):
        for arm in ("null", "structured"):
            model, training = train(seed, arm, train_rows)
            metrics = evaluate(model, eval_rows)
            training["train_metrics"] = evaluate(model, train_rows)
            results[arm].append(metrics)
            run_records.append({"seed": seed, "arm": arm, "training": training, "metrics": metrics})
    summary = {
        "status": "executed exploratory smoke",
        "question": "Does the preregistered structured objective improve a learned typed parser over graph cross-entropy alone?",
        "null": "matched graph-token cross-entropy parser",
        "train_semantic_groups": len(train_groups),
        "eval_semantic_groups": len(eval_groups),
        "semantic_group_overlap": len(train_groups & eval_groups),
        "train_rows": len(train_rows),
        "eval_rows": len(eval_rows),
        "seeds": [11, 23, 37],
        "torch": torch.__version__,
        "cuda": torch.cuda.is_available(),
        "aggregate": {arm: aggregate(metrics) for arm, metrics in results.items()},
        "runs": run_records,
        "limitations": [
            "synthetic two-node list-operation graphs",
            "explicit step language rather than natural Python requirements",
            "three seeds are exploratory and no confidence interval is claimed",
            "no HumanEval+, code generation, 40M model, or Qwen comparison",
        ],
    }
    ROOT.joinpath("summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
