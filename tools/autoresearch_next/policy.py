"""Mutable policy validation with append-only activation and rollback records."""

from __future__ import annotations

import hashlib
from typing import Any

from .ledger import AppendOnlyLedger
from .schema import OPERATOR_WEIGHTS, POLICY_VERSION, canonical_json


class PolicyManager:
    def __init__(self, ledger: AppendOnlyLedger, run_id: str):
        self.ledger = ledger
        self.run_id = run_id
        self.current: dict[str, Any] = {"version": POLICY_VERSION, "operator_weights": dict(OPERATOR_WEIGHTS), "epoch": 0}
        self._record("activated", self.current)

    def validate(self, proposal: dict[str, Any]) -> dict[str, Any]:
        candidate = {**self.current, **proposal}
        weights = candidate.get("operator_weights")
        if not isinstance(weights, dict) or set(weights) != set(OPERATOR_WEIGHTS):
            raise ValueError("policy must specify the four approved operators")
        if any(float(v) < 0 for v in weights.values()) or abs(sum(float(v) for v in weights.values()) - 1.0) > 1e-6:
            raise ValueError("operator weights must be nonnegative and sum to one")
        if any(k in proposal for k in ("trust_kernel", "evaluator", "partitions", "ledger")):
            raise ValueError("policy cannot target immutable trust components")
        return candidate

    def activate(self, proposal: dict[str, Any]) -> dict[str, Any]:
        next_policy = self.validate(proposal)
        next_policy["epoch"] = int(self.current.get("epoch", 0)) + 1
        self.current = next_policy
        self._record("activated", self.current)
        return self.current

    def rollback(self, reason: str) -> dict[str, Any]:
        self._record("rollback", {"reason": reason, "to": self.current})
        return self.current

    def _record(self, action: str, policy: dict[str, Any]) -> None:
        digest = hashlib.sha256(canonical_json(policy)).hexdigest()
        self.ledger.policy(self.run_id, digest, action, policy)

