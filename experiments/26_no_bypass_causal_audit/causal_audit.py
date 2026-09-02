"""Causal no-bypass audit for typed-state renderers."""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OPS = ("sort", "reverse", "unique", "count")


@dataclass(frozen=True)
class Case:
    raw_requirement: str
    state_op: str
    placebo: int

    def state_edit(self) -> "Case":
        return replace(self, state_op="reverse" if self.state_op != "reverse" else "sort")

    def raw_edit(self) -> "Case":
        # Swap the raw operation while holding the typed state fixed. A raw
        # bypass should be sensitive to it; a no-bypass renderer must preserve
        # its output. This catches a path that ignores the typed ledger.
        old = next(op for op in OPS if f"operation {op}" in self.raw_requirement)
        new = "reverse" if old != "reverse" else "sort"
        return replace(self, raw_requirement=self.raw_requirement.replace(f"operation {old}", f"operation {new}"))

    def placebo_edit(self) -> "Case":
        return replace(self, placebo=self.placebo + 1)


def make_cases(seed: int, count: int = 240) -> list[Case]:
    rng = random.Random(seed)
    return [Case(f"implement operation {op} distractor={rng.randrange(10)}", op, rng.randrange(10))
            for _ in range(count) for op in (rng.choice(OPS),)]


def render(case: Case, architecture: str) -> str:
    state = case.state_op
    raw = next((op for op in OPS if f"operation {op}" in case.raw_requirement), "unknown")
    if architecture == "raw_shortcut":
        return raw
    if architecture == "decorative_trace":
        return raw
    if architecture == "mixed":
        return state if case.placebo % 2 == 0 else raw
    if architecture == "ledger_only":
        return state
    raise ValueError(architecture)


def evaluate(cases: list[Case], architecture: str) -> dict[str, float | str]:
    state_change, raw_invariant, placebo_invariant, accepted = [], [], [], []
    for case in cases:
        baseline = render(case, architecture)
        state_change.append(render(case.state_edit(), architecture) != baseline)
        raw_invariant.append(render(case.raw_edit(), architecture) == baseline)
        placebo_invariant.append(render(case.placebo_edit(), architecture) == baseline)
        accepted.append(bool(state_change[-1] and raw_invariant[-1] and placebo_invariant[-1]))
    return {
        "architecture": architecture,
        "relevant_state_change": sum(state_change) / len(cases),
        "raw_path_invariance": sum(raw_invariant) / len(cases),
        "irrelevant_placebo_invariance": sum(placebo_invariant) / len(cases),
        "passes_no_bypass_gate": sum(accepted) / len(cases),
    }


def main() -> None:
    architectures = ("raw_shortcut", "decorative_trace", "mixed", "ledger_only")
    seeds = (11, 23, 37, 41, 53)
    runs = []
    for seed in seeds:
        for architecture in architectures:
            row = {"seed": seed, "tasks": 240, **evaluate(make_cases(seed), architecture)}
            runs.append(row)
            print(json.dumps(row, sort_keys=True), flush=True)
    aggregate = {}
    for architecture in architectures:
        rows = [r for r in runs if r["architecture"] == architecture]
        aggregate[architecture] = {
            key: {"mean": statistics.mean(float(r[key]) for r in rows),
                  "seed_sd": statistics.stdev(float(r[key]) for r in rows)}
            for key in ("relevant_state_change", "raw_path_invariance", "irrelevant_placebo_invariance", "passes_no_bypass_gate")
        }
    output = {"seeds": list(seeds), "runs": runs, "aggregate": aggregate,
              "note": "Synthetic causal audit; no learned model or coding benchmark was run."}
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
