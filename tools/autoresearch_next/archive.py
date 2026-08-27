"""MAP-Elites archive with hard-gate filtering and Pareto-aware tie breaking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArchiveEntry:
    candidate_id: str
    metrics: dict[str, float]
    transparency: int
    mechanism: str
    accepted: bool = True

    @property
    def niche(self) -> str:
        m = self.metrics
        params = "small" if m.get("learned_parameters", 0) <= 100_000 else "medium" if m.get("learned_parameters", 0) <= 9_000_000 else "large"
        vram = "low" if m.get("peak_vram_gb", 0) <= 2 else "mid" if m.get("peak_vram_gb", 0) <= 7.2 else "high"
        speed = "slow" if m.get("throughput", 0) < 10 else "fast"
        return ":".join((params, vram, speed, self.mechanism, f"T{self.transparency}"))


def dominates(a: dict[str, float], b: dict[str, float]) -> bool:
    higher = ("full_system_score", "code_validation_proxy", "transparency", "throughput", "simplicity", "placebo_preservation", "causal_intervention_rate")
    lower = ("search_expansions", "end_to_end_latency_ms", "peak_vram_gb", "learned_parameters")
    def value(mapping: dict[str, float], key: str, missing: float) -> float:
        raw = mapping.get(key)
        return missing if raw is None else float(raw)
    ge = all(value(a, k, float("-inf")) >= value(b, k, float("-inf")) for k in higher)
    le = all(value(a, k, float("inf")) <= value(b, k, float("inf")) for k in lower)
    strict = any(value(a, k, 0.0) != value(b, k, 0.0) for k in (*higher, *lower))
    return ge and le and strict


class MapElitesArchive:
    def __init__(self):
        self.entries: dict[str, ArchiveEntry] = {}
        self.frontier: list[ArchiveEntry] = []

    def propose(self, entry: ArchiveEntry) -> bool:
        if not entry.accepted:
            return False
        previous = self.entries.get(entry.niche)
        if previous is not None and dominates(previous.metrics, entry.metrics):
            return False
        self.entries[entry.niche] = entry
        self.frontier = [x for x in [*self.entries.values()] if not any(dominates(y.metrics, x.metrics) for y in self.entries.values() if y is not x)]
        return True

    def leaders(self) -> list[ArchiveEntry]:
        return sorted(self.entries.values(), key=lambda x: (x.transparency, x.metrics.get("full_system_score", -1)), reverse=True)
