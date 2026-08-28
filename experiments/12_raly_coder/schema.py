"""Minimal typed action vocabulary for the Raly Coder sandbox.

The model-facing surface is deliberately small. The evaluator, not the model,
owns filesystem safety, test execution, trace recording, and interventions.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Literal


SCHEMA_VERSION = "raly-coder-actions-v1"
ActionName = Literal[
    "find_symbol", "open_file", "read_region", "apply_patch",
    "run_tests", "inspect_failure",
]
ACTION_NAMES: tuple[ActionName, ...] = (
    "find_symbol", "open_file", "read_region", "apply_patch",
    "run_tests", "inspect_failure",
)


REQUIRED_FIELDS: dict[ActionName, tuple[str, ...]] = {
    "find_symbol": ("path", "name"),
    "open_file": ("path",),
    "read_region": ("path", "start_line", "end_line"),
    "apply_patch": ("path", "expected_sha256", "old_text", "new_text"),
    "run_tests": (),
    "inspect_failure": ("run_id",),
}


@dataclass(frozen=True)
class Action:
    op: ActionName
    args: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA_VERSION, "op": self.op, "args": self.args}

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


class ActionValidationError(ValueError):
    """Raised when a model action is not in the typed vocabulary."""


def parse_action(value: Action | str | dict[str, Any]) -> Action:
    if isinstance(value, Action):
        return value
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ActionValidationError(f"action is not JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ActionValidationError("action must be an object")
    if value.get("schema", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ActionValidationError("unsupported action schema")
    op = value.get("op")
    if op not in ACTION_NAMES:
        raise ActionValidationError(f"unknown operation: {op!r}")
    args = value.get("args", {})
    if not isinstance(args, dict):
        raise ActionValidationError("args must be an object")
    missing = [field for field in REQUIRED_FIELDS[op] if field not in args]
    if missing:
        raise ActionValidationError(f"{op} missing fields: {', '.join(missing)}")
    if op == "read_region":
        if not isinstance(args["start_line"], int) or not isinstance(args["end_line"], int):
            raise ActionValidationError("read_region line bounds must be integers")
        if args["start_line"] < 1 or args["end_line"] < args["start_line"]:
            raise ActionValidationError("read_region has invalid line bounds")
    if op == "run_tests" and set(args) - {"target"}:
        raise ActionValidationError("run_tests only accepts optional target")
    return Action(op=op, args=dict(args))

