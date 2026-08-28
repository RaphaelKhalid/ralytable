"""Small deterministic typed-state DSL used by experiment 11.

This is deliberately boring. The point of the smoke test is to verify that
the executor owns persistence and that interventions change only the state we
intend to change. It is not a benchmark of Python or general coding ability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import random
import re
from typing import Any


OPS = ("input", "filter_gt", "sort_asc", "unique", "count", "return")


@dataclass
class Slot:
    type_name: str
    value: Any
    provenance: tuple[str, ...] = ()


@dataclass
class State:
    slots: dict[str, Slot] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    input_values: tuple[int, ...] = ()

    def clone(self) -> "State":
        return State(
            slots={k: Slot(v.type_name, _copy(v.value), v.provenance)
                   for k, v in self.slots.items()},
            errors=list(self.errors),
            input_values=self.input_values,
        )


@dataclass(frozen=True)
class Task:
    request: str
    values: tuple[int, ...]
    threshold: int
    expected: tuple[int, ...] | int
    result_type: str
    program: tuple[str, ...]


def _copy(value: Any) -> Any:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def make_task(rng: random.Random, *, distractors: bool = True,
              template: str = "filter_sort_unique") -> Task:
    values = [rng.randrange(-20, 21) for _ in range(rng.randrange(5, 10))]
    threshold = rng.randrange(-12, 13)
    if distractors:
        values.extend(rng.randrange(-20, 21) for _ in range(rng.randrange(0, 5)))
    filtered = sorted(set(v for v in values if v > threshold))
    if template == "filter_sort_unique":
        request = ("From the integer list, keep values greater than "
                   f"{threshold}, sort ascending, remove duplicates, and return it.")
        program = (
            "input values -> s0",
            f"filter_gt s0 {threshold} -> s1",
            "sort_asc s1 -> s2",
            "unique s2 -> s3",
            "return s3",
        )
        expected: tuple[int, ...] | int = tuple(filtered)
        result_type = "List[Int]"
    elif template == "sort_filter_unique":
        request = ("Sort the integer list ascending, then keep values greater "
                   f"than {threshold}, remove duplicates, and return it.")
        program = (
            "input values -> s0",
            "sort_asc s0 -> s1",
            f"filter_gt s1 {threshold} -> s2",
            "unique s2 -> s3",
            "return s3",
        )
        expected = tuple(filtered)
        result_type = "List[Int]"
    elif template == "filter_unique_count":
        request = (f"Keep values greater than {threshold}, remove duplicates, "
                   "count them, and return the count.")
        program = (
            "input values -> s0",
            f"filter_gt s0 {threshold} -> s1",
            "unique s1 -> s2",
            "count s2 -> s3",
            "return s3",
        )
        expected = len(filtered)
        result_type = "Int"
    elif template == "sort_unique_count":
        request = "Sort the integer list, remove duplicates, count them, and return the count."
        program = (
            "input values -> s0",
            "sort_asc s0 -> s1",
            "unique s1 -> s2",
            "count s2 -> s3",
            "return s3",
        )
        expected = len(set(values))
        result_type = "Int"
    else:
        raise ValueError(f"unknown task template: {template}")
    return Task(request=request, values=tuple(values), threshold=threshold,
                expected=expected, result_type=result_type, program=program)


def initial_state(task: Task) -> State:
    # Input is an explicit state transition. Keeping the input buffer separate
    # prevents a no-op `input` action from making a mediated prompt identical
    # before and after the action.
    return State(input_values=task.values)


def execute(line: str, state: State) -> tuple[State, Any | None]:
    """Execute exactly one line and reject malformed or ill-typed operations."""
    out = state.clone()
    text = " ".join(line.strip().split())
    if text.startswith("input values -> s0"):
        if "s0" in out.slots:
            out.errors.append("input has already been consumed")
        elif not out.input_values:
            out.errors.append("input requires the initial values")
        else:
            out.slots["s0"] = Slot(
                "List[Int]", list(out.input_values), ("input",)
            )
        return out, None

    m = re.fullmatch(r"filter_gt (s\d+) (-?\d+) -> (s\d+)", text)
    if m:
        source, threshold, target = m.group(1), int(m.group(2)), m.group(3)
        slot = out.slots.get(source)
        if slot is None or slot.type_name != "List[Int]":
            out.errors.append("filter_gt expects List[Int]")
        else:
            out.slots[target] = Slot(
                "List[Int]", [x for x in slot.value if x > threshold],
                slot.provenance + ("filter_gt",),
            )
        return out, None

    m = re.fullmatch(r"sort_asc (s\d+) -> (s\d+)", text)
    if m:
        source, target = m.groups()
        slot = out.slots.get(source)
        if slot is None or slot.type_name != "List[Int]":
            out.errors.append("sort_asc expects List[Int]")
        else:
            out.slots[target] = Slot(
                "List[Int]", sorted(slot.value), slot.provenance + ("sort_asc",)
            )
        return out, None

    m = re.fullmatch(r"unique (s\d+) -> (s\d+)", text)
    if m:
        source, target = m.groups()
        slot = out.slots.get(source)
        if slot is None or slot.type_name != "List[Int]":
            out.errors.append("unique expects List[Int]")
        else:
            seen: set[int] = set()
            value = [x for x in slot.value if not (x in seen or seen.add(x))]
            out.slots[target] = Slot(
                "List[Int]", value, slot.provenance + ("unique",)
            )
        return out, None

    m = re.fullmatch(r"count (s\d+) -> (s\d+)", text)
    if m:
        source, target = m.groups()
        slot = out.slots.get(source)
        if slot is None or slot.type_name != "List[Int]":
            out.errors.append("count expects List[Int]")
        else:
            out.slots[target] = Slot("Int", len(slot.value), slot.provenance + ("count",))
        return out, None

    m = re.fullmatch(r"return (s\d+)", text)
    if m:
        slot = out.slots.get(m.group(1))
        if slot is None:
            out.errors.append("return references an unknown slot")
        else:
            return out, _copy(slot.value)
        return out, None

    out.errors.append("unknown or malformed operation")
    return out, None


def run_program(task: Task, program: tuple[str, ...] | list[str] | None = None) -> tuple[State, Any | None]:
    state = initial_state(task)
    result = None
    for line in program or task.program:
        state, result = execute(line, state)
    return state, result


def hidden_tests(task: Task, result: Any | None) -> bool:
    """Deterministic property-style hidden test for the task's result."""
    if isinstance(task.expected, (tuple, list)):
        return result == list(task.expected) or result == task.expected
    return result == task.expected


def serialize_state(state: State, *, include_types: bool = True,
                    include_provenance: bool = False) -> str:
    slots = {}
    for name, slot in sorted(state.slots.items()):
        serialized = {
            "type": slot.type_name if include_types else "Value",
            "value": slot.value,
        }
        if include_provenance:
            serialized["from"] = list(slot.provenance)
        slots[name] = serialized
    return json.dumps({"input": list(state.input_values), "slots": slots,
                       "errors": state.errors}, separators=(",", ":"))


def corrupt_state(state: State, mode: str, relevant: str = "s3") -> State:
    out = state.clone()
    if mode == "relevant":
        if relevant in out.slots:
            value = out.slots[relevant].value
            if isinstance(value, list):
                out.slots[relevant].value = list(reversed(value))
            elif isinstance(value, int):
                out.slots[relevant].value += 1
    elif mode == "irrelevant":
        out.slots["noise"] = Slot("List[Int]", [999], ("intervention_noise",))
    elif mode == "erase_types":
        out.slots = {k: Slot("Value", v.value, v.provenance)
                     for k, v in out.slots.items()}
    elif mode == "shuffle":
        names = list(out.slots)
        if len(names) >= 2:
            out.slots[names[0]], out.slots[names[-1]] = (
                out.slots[names[-1]], out.slots[names[0]])
    elif mode == "blank":
        out.slots = {}
    else:
        raise ValueError(f"unknown corruption mode: {mode}")
    return out
