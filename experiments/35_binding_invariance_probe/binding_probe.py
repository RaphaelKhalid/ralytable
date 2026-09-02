"""Test whether a typed graph preserves bindings under harmless renaming."""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Binding:
    name: str
    type_name: str


@dataclass(frozen=True)
class Program:
    bindings: tuple[Binding, ...]
    operation: str
    source: str
    target: str

    def renamed(self, seed: int) -> "Program":
        rng = random.Random(seed)
        names = [f"v{rng.randrange(10000)}" for _ in self.bindings]
        mapping = {old.name: new for old, new in zip(self.bindings, names)}
        return replace(self, bindings=tuple(Binding(mapping[b.name], b.type_name) for b in self.bindings),
                       source=mapping[self.source], target=mapping[self.target])

    def reordered(self, seed: int) -> "Program":
        rows = list(self.bindings)
        random.Random(seed).shuffle(rows)
        return replace(self, bindings=tuple(rows))

    def binding_edit(self) -> "Program":
        return replace(self, target=self.source if self.target != self.source else self.bindings[-1].name)

    def placebo(self) -> "Program":
        return replace(self, bindings=self.bindings + (Binding("unused", "Unused"),))


def make_program(seed: int) -> Program:
    rng = random.Random(seed)
    names = ["items", "filtered", "result", "scratch"]
    types = ["List[Int]", "List[Int]", "List[Int]", "Int"]
    bindings = tuple(Binding(n, t) for n, t in zip(names, types))
    return Program(bindings, rng.choice(("sort", "unique", "reverse")), "items", "result")


def signature(program: Program, architecture: str):
    if architecture == "surface_position":
        return tuple((b.name, b.type_name) for b in program.bindings) + (program.operation, program.source, program.target)
    if architecture == "name_normalized":
        return tuple((i, b.type_name) for i, b in enumerate(program.bindings)) + (program.operation, program.source, program.target)
    if architecture == "alpha_typed_graph":
        types = {b.name: b.type_name for b in program.bindings if b.type_name != "Unused"}
        # Alpha equivalence ignores lexical spelling and declaration order but
        # retains the semantic source/target roles and their type multiset.
        return (tuple(sorted(types.values())), program.operation,
                types[program.source], types[program.target],
                program.source == program.target)
    raise ValueError(architecture)


def evaluate(program: Program, architecture: str, seed: int) -> dict[str, object]:
    base = signature(program, architecture)
    renamed = signature(program.renamed(seed), architecture)
    reordered = signature(program.reordered(seed + 1), architecture)
    edited = signature(program.binding_edit(), architecture)
    placebo = signature(program.placebo(), architecture)
    return {"architecture": architecture,
            "rename_invariance": renamed == base,
            "reorder_invariance": reordered == base,
            "binding_change": edited != base,
            "placebo_preservation": placebo == base}


def main() -> None:
    architectures = ("surface_position", "name_normalized", "alpha_typed_graph")
    seeds = (11, 23, 37, 41, 53)
    runs = []
    for seed in seeds:
        for architecture in architectures:
            row = {"seed": seed, **evaluate(make_program(seed), architecture, seed)}
            runs.append(row)
            print(json.dumps(row, sort_keys=True))
    metrics = ("rename_invariance", "reorder_invariance", "binding_change", "placebo_preservation")
    aggregate = {architecture: {metric: statistics.mean(float(r[metric]) for r in runs if r["architecture"] == architecture)
                                for metric in metrics} for architecture in architectures}
    output = {"runs": runs, "aggregate": aggregate,
              "note": "Synthetic binding-invariance probe; no learned model or benchmark was run."}
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
