"""Small immutable records shared by the trust kernel and runner."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any


MAX_LEARNED_PARAMETERS = 9_000_000
POLICY_VERSION = "autoresearch-next-v1"
OPERATOR_WEIGHTS = {"mutation": 0.60, "crossover": 0.25, "simplification": 0.10, "radical": 0.05}


class Transparency(IntEnum):
    T0 = 0
    T1 = 1
    T2 = 2
    T3 = 3


@dataclass(frozen=True)
class CandidateContract:
    candidate_id: str
    parent_ids: tuple[str, ...] = ()
    hypothesis: str = ""
    operator: str = "mutation"
    mechanism_family: str = "typed_monotonic_gate"
    transparency: int = int(Transparency.T2)
    learned_parameters: int = 0
    declared_state: tuple[str, ...] = ("intent", "abstract_value", "confidence")
    files_changed: tuple[str, ...] = ()
    config: dict[str, Any] = field(default_factory=dict)

    def validate(self, protected: set[str] | None = None) -> None:
        if not self.candidate_id or any(c in self.candidate_id for c in "\\/\x00"):
            raise ValueError("invalid candidate id")
        if self.learned_parameters < 0 or self.learned_parameters > MAX_LEARNED_PARAMETERS:
            raise ValueError(f"learned parameter limit exceeded: {self.learned_parameters}")
        if self.operator not in OPERATOR_WEIGHTS:
            raise ValueError(f"unknown operator: {self.operator}")
        if not 0 <= int(self.transparency) <= 3:
            raise ValueError("transparency must be T0..T3")
        if int(self.transparency) >= int(Transparency.T2) and not self.declared_state:
            raise ValueError("structured transparency requires declared state")
        if int(self.transparency) >= int(Transparency.T3):
            if not self.config.get("named_sparse_rules"):
                raise ValueError("T3 requires named_sparse_rules")
        forbidden = {"answer", "expected_output", "reference_solution", "hidden_test", "oracle"}
        flat = json.dumps(self.config, sort_keys=True).lower()
        if any(token in flat for token in forbidden):
            raise ValueError("candidate config contains answer/oracle material")
        protected = protected or set()
        touched = {str(Path(p).as_posix()) for p in self.files_changed}
        if touched & {str(Path(p).as_posix()) for p in protected}:
            raise ValueError("candidate touches a protected path")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["parent_ids"] = list(self.parent_ids)
        payload["declared_state"] = list(self.declared_state)
        payload["files_changed"] = list(self.files_changed)
        return payload


@dataclass(frozen=True)
class MetricRecord:
    candidate_id: str
    arm: str
    status: str
    raw_learned_score: float | None = None
    full_system_score: float | None = None
    deterministic_null_score: float | None = 0.0
    code_validation_proxy: float | None = None
    transparency: int = 0
    causal_intervention_rate: float | None = None
    placebo_preservation: float | None = None
    exact_trace_replay: float | None = None
    search_expansions: float | None = None
    end_to_end_latency_ms: float | None = None
    peak_vram_gb: float | None = None
    throughput: float | None = None
    simplicity: float | None = None
    learned_parameters: int = 0
    failure_category: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

