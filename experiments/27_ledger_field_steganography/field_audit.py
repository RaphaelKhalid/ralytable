"""Find answer-bearing information hidden in nominally unused ledger fields."""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OPS = ("sort", "reverse", "unique", "count")


@dataclass(frozen=True)
class Ledger:
    declared_op: str
    arguments: tuple[str, ...]
    metadata: tuple[int, ...]
    provenance: tuple[str, ...]
    confidence: int

    def semantic_edit(self) -> "Ledger":
        new = "reverse" if self.declared_op != "reverse" else "sort"
        return replace(self, declared_op=new)

    def metadata_edit(self) -> "Ledger":
        return replace(self, metadata=tuple(reversed(self.metadata)))

    def provenance_edit(self) -> "Ledger":
        # Inject the hidden tag a provenance bypass would use, while the
        # declared semantics remain unchanged.
        tag = "secret" if "secret" not in self.provenance else "parser"
        return replace(self, provenance=(tag,) + tuple(x for x in self.provenance if x != "secret"))

    def confidence_edit(self) -> "Ledger":
        return replace(self, confidence=(self.confidence + 1) % 4)


def render(ledger: Ledger, architecture: str) -> str:
    if architecture == "semantic_renderer":
        return ledger.declared_op
    if architecture == "metadata_router":
        # Hidden answer channel: the first metadata bit selects the operation.
        return OPS[ledger.metadata[0] % len(OPS)]
    if architecture == "provenance_router":
        return "reverse" if "secret" in ledger.provenance else ledger.declared_op
    if architecture == "confidence_router":
        return "count" if ledger.confidence == 3 else ledger.declared_op
    raise ValueError(architecture)


def evaluate(architecture: str, seed: int, count: int = 320) -> dict[str, object]:
    rng = random.Random(seed)
    cases = [Ledger(rng.choice(OPS), ("xs",), (rng.randrange(4), rng.randrange(4)),
                    ("parser",), rng.randrange(4)) for _ in range(count)]
    baseline = [render(case, architecture) for case in cases]
    semantic = [render(case.semantic_edit(), architecture) != old for case, old in zip(cases, baseline)]
    metadata = [render(case.metadata_edit(), architecture) == old for case, old in zip(cases, baseline)]
    provenance = [render(case.provenance_edit(), architecture) == old for case, old in zip(cases, baseline)]
    confidence = [render(case.confidence_edit(), architecture) == old for case, old in zip(cases, baseline)]
    gate = [s and m and p and c for s, m, p, c in zip(semantic, metadata, provenance, confidence)]
    return {
        "architecture": architecture,
        "semantic_change": sum(semantic) / count,
        "metadata_invariance": sum(metadata) / count,
        "provenance_invariance": sum(provenance) / count,
        "confidence_invariance": sum(confidence) / count,
        "field_level_gate": sum(gate) / count,
        "tasks": count,
        "seed": seed,
    }


def main() -> None:
    architectures = ("semantic_renderer", "metadata_router", "provenance_router", "confidence_router")
    seeds = (11, 23, 37, 41, 53)
    runs = []
    for seed in seeds:
        for architecture in architectures:
            row = evaluate(architecture, seed)
            runs.append(row)
            print(json.dumps(row, sort_keys=True), flush=True)
    aggregate = {}
    metrics = ("semantic_change", "metadata_invariance", "provenance_invariance", "confidence_invariance", "field_level_gate")
    for architecture in architectures:
        rows = [r for r in runs if r["architecture"] == architecture]
        aggregate[architecture] = {metric: {"mean": statistics.mean(float(r[metric]) for r in rows),
                                             "seed_sd": statistics.stdev(float(r[metric]) for r in rows)}
                                   for metric in metrics}
    output = {"seeds": list(seeds), "runs": runs, "aggregate": aggregate,
              "note": "Synthetic ledger-field audit; no learned model or benchmark was run."}
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
