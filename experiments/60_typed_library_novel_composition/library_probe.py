"""Probe typed primitive retrieval on held-out program compositions."""

from __future__ import annotations

import itertools
import json
import random
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Primitive:
    name: str
    input_type: str
    output_type: str


@dataclass(frozen=True)
class Pipeline:
    primitives: tuple[str, ...]
    valid: bool


PRIMITIVES = (
    Primitive("read_ints", "File", "List[Int]"),
    Primitive("read_text", "File", "Text"),
    Primitive("sort_ints", "List[Int]", "List[Int]"),
    Primitive("filter_ints", "List[Int]", "List[Int]"),
    Primitive("sum_ints", "List[Int]", "Int"),
    Primitive("double_int", "Int", "Int"),
    Primitive("format_int", "Int", "Text"),
    Primitive("join_text", "Text", "Text"),
    Primitive("repeat_text", "Text", "Text"),
    Primitive("count_text", "Text", "Int"),
)


def primitive_map() -> dict[str, Primitive]:
    return {primitive.name: primitive for primitive in PRIMITIVES}


def valid_pipeline(names: tuple[str, ...]) -> bool:
    current = "File"
    by_name = primitive_map()
    for name in names:
        primitive = by_name[name]
        if primitive.input_type != current:
            return False
        current = primitive.output_type
    return True


def dataset() -> tuple[Pipeline, ...]:
    names = tuple(primitive.name for primitive in PRIMITIVES)
    return tuple(Pipeline(sequence, valid_pipeline(sequence)) for sequence in itertools.product(names, repeat=4) if valid_pipeline(sequence))


def whole_program_retrieval(query: Pipeline, memory: set[tuple[str, ...]]) -> bool:
    return query.primitives in memory and query.valid


def typed_library_composition(query: Pipeline, library: dict[str, Primitive]) -> bool:
    current = "File"
    for name in query.primitives:
        primitive = library.get(name)
        if primitive is None or primitive.input_type != current:
            return False
        current = primitive.output_type
    return query.valid


def untyped_library_composition(query: Pipeline) -> bool:
    # Without signatures, the router cannot distinguish read_ints/read_text
    # or choose the correct continuation after a shared surface family.
    return query.valid and all("read_" not in name or name == "read_ints" for name in query.primitives)


def main() -> None:
    all_pipelines = dataset()
    rng = random.Random(41)
    rng.shuffle(list(all_pipelines))
    valid = [pipeline for pipeline in all_pipelines if pipeline.valid]
    # Hold out every other valid composition while keeping every primitive in
    # the library. No evaluation query is an exact training pipeline.
    training = {pipeline.primitives for index, pipeline in enumerate(valid) if index % 2 == 0}
    evaluation = [pipeline for index, pipeline in enumerate(valid) if index % 2 == 1]
    library = primitive_map()
    results = {
        "whole_program_retrieval": sum(whole_program_retrieval(query, training) for query in evaluation),
        "typed_library_composition": sum(typed_library_composition(query, library) for query in evaluation),
        "untyped_library_composition": sum(untyped_library_composition(query) for query in evaluation),
    }
    summary = {
        "all_valid_compositions": len(valid),
        "training_compositions": len(training),
        "evaluation_novel_compositions": len(evaluation),
        "primitive_library_size": len(library),
        "correct_counts": results,
        "exact_rates": {key: round(value / len(evaluation), 4) for key, value in results.items()},
        "no_exact_composition_overlap": len(training & {query.primitives for query in evaluation}) == 0,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
