"""Frozen official-evaluator contract; scoring stays outside candidate context."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .schema import canonical_json


@dataclass(frozen=True)
class EvaluatorContract:
    name: str = "EvalPlus HumanEval+"
    version: str = "0.3.1"
    task_count: int = 164
    command: tuple[str, ...] = ("python", "-m", "evalplus.evaluate", "humaneval", "--parallel", "1", "--i-just-wanna-run")
    score_fields: tuple[str, ...] = ("base_pass_at_1", "plus_pass_at_1")
    benchmark_tuning_label: str = "HumanEval+-tuned"

    def digest(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict())).hexdigest()

    def to_dict(self) -> dict:
        return {"name": self.name, "version": self.version, "task_count": self.task_count,
                "command": list(self.command), "score_fields": list(self.score_fields),
                "benchmark_tuning_label": self.benchmark_tuning_label,
                "hidden_scores": "never passed to candidate or proposal worker"}

    def write(self, path: Path) -> str:
        path.write_text(json.dumps(self.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return self.digest()

