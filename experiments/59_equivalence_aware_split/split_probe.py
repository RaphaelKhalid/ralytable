"""Probe semantic-group leakage in train/evaluation splits."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Example:
    example_id: int
    family_id: int
    surface: str
    semantic_signature: tuple[str, ...]


def make_dataset() -> tuple[Example, ...]:
    examples: list[Example] = []
    example_id = 0
    for family in range(12):
        signature = ("map", f"primitive_{family % 4}", "filter", f"predicate_{family % 3}")
        variants = (
            f"let x{family}=map(filter(input))",
            f"let renamed_{family}=map(filter(input))",
            f"filter_then_map(input, order={family % 2})",
        )
        for surface in variants:
            examples.append(Example(example_id, family, surface, signature))
            example_id += 1
    return tuple(examples)


def random_split(examples: tuple[Example, ...], rng: random.Random) -> tuple[set[int], set[int]]:
    ids = [example.example_id for example in examples]
    rng.shuffle(ids)
    cutoff = int(len(ids) * 0.7)
    return set(ids[:cutoff]), set(ids[cutoff:])


def grouped_split(examples: tuple[Example, ...], rng: random.Random) -> tuple[set[int], set[int]]:
    families = sorted({example.family_id for example in examples})
    rng.shuffle(families)
    cutoff = int(len(families) * 0.7)
    train_families = set(families[:cutoff])
    train = {example.example_id for example in examples if example.family_id in train_families}
    evaluation = {example.example_id for example in examples if example.family_id not in train_families}
    return train, evaluation


def semantic_overlap(examples: tuple[Example, ...], train: set[int], evaluation: set[int]) -> int:
    by_id = {example.example_id: example for example in examples}
    train_signatures = {by_id[example_id].semantic_signature for example_id in train}
    eval_signatures = {by_id[example_id].semantic_signature for example_id in evaluation}
    return len(train_signatures & eval_signatures)


def family_overlap(examples: tuple[Example, ...], train: set[int], evaluation: set[int]) -> int:
    by_id = {example.example_id: example for example in examples}
    train_families = {by_id[example_id].family_id for example_id in train}
    eval_families = {by_id[example_id].family_id for example_id in evaluation}
    return len(train_families & eval_families)


def main() -> None:
    examples = make_dataset()
    rows: list[dict[str, object]] = []
    aggregate = {"random_semantic_overlap": 0.0, "random_family_overlap": 0.0, "grouped_semantic_overlap": 0.0, "grouped_family_overlap": 0.0}
    for seed in range(5):
        random_train, random_eval = random_split(examples, random.Random(seed))
        grouped_train, grouped_eval = grouped_split(examples, random.Random(seed))
        row = {
            "seed": seed,
            "random_semantic_overlap": semantic_overlap(examples, random_train, random_eval),
            "random_family_overlap": family_overlap(examples, random_train, random_eval),
            "grouped_semantic_overlap": semantic_overlap(examples, grouped_train, grouped_eval),
            "grouped_family_overlap": family_overlap(examples, grouped_train, grouped_eval),
        }
        rows.append(row)
        for key in aggregate:
            aggregate[key] += float(row[key])
    summary = {
        "examples": len(examples),
        "semantic_families": len({example.semantic_signature for example in examples}),
        "surface_families": len({example.family_id for example in examples}),
        "averages": {key: round(value / 5, 4) for key, value in aggregate.items()},
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"examples": summary["examples"], "semantic_families": summary["semantic_families"], "averages": summary["averages"]}, indent=2))


if __name__ == "__main__":
    main()
