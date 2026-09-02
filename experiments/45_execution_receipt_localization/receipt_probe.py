"""Probe replayable execution receipts and first-divergence localization."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Step:
    step_id: int
    operation: str
    argument: int


@dataclass(frozen=True)
class Receipt:
    step_id: int
    input_digest: str
    output_digest: str


@dataclass(frozen=True)
class Trace:
    steps: tuple[Step, ...]
    receipts: tuple[Receipt, ...]


def digest(value: int) -> str:
    return hashlib.sha256(str(value).encode("ascii")).hexdigest()


def execute_step(state: int, step: Step) -> int:
    if step.operation == "add":
        return state + step.argument
    if step.operation == "mul":
        return state * step.argument
    raise ValueError(step.operation)


def make_trace(seed: int) -> Trace:
    rng = random.Random(seed)
    steps = (
        Step(0, "add", rng.randrange(1, 5)),
        Step(1, "mul", rng.randrange(2, 5)),
        Step(2, "add", rng.randrange(1, 5)),
    )
    state = 0
    receipts: list[Receipt] = []
    for step in steps:
        next_state = execute_step(state, step)
        receipts.append(Receipt(step.step_id, digest(state), digest(next_state)))
        state = next_state
    return Trace(steps, tuple(receipts))


def expected_first_divergence(trace: Trace) -> int | None:
    state = 0
    by_id = {receipt.step_id: receipt for receipt in trace.receipts}
    for step in trace.steps:
        receipt = by_id.get(step.step_id)
        if receipt is None or receipt.input_digest != digest(state):
            return step.step_id
        next_state = execute_step(state, step)
        if receipt.output_digest != digest(next_state):
            return step.step_id
        state = next_state
    return None


def final_only(trace: Trace) -> tuple[bool, int | None]:
    if not trace.receipts:
        return False, 0
    state = 0
    for step in trace.steps:
        state = execute_step(state, step)
    claimed = trace.receipts[-1]
    # Final-only validation intentionally ignores all intermediate receipts.
    return claimed.output_digest == digest(state), None


def hash_chain(trace: Trace) -> tuple[bool, int | None]:
    receipts = {receipt.step_id: receipt for receipt in trace.receipts}
    current_digest = digest(0)
    for step in trace.steps:
        receipt = receipts.get(step.step_id)
        if receipt is None:
            return False, step.step_id
        if receipt.input_digest != current_digest:
            return False, step.step_id
        # A chain validates links but does not independently recompute the
        # operation's semantic output.
        current_digest = receipt.output_digest
        if step.step_id + 1 < len(trace.steps):
            next_receipt = receipts.get(step.step_id + 1)
            if next_receipt is None or next_receipt.input_digest != receipt.output_digest:
                return False, step.step_id + 1
    return True, None


def replay_receipt_ledger(trace: Trace) -> tuple[bool, int | None]:
    state = 0
    receipts = {receipt.step_id: receipt for receipt in trace.receipts}
    for step in trace.steps:
        receipt = receipts.get(step.step_id)
        if receipt is None or receipt.input_digest != digest(state):
            return False, step.step_id
        next_state = execute_step(state, step)
        if receipt.output_digest != digest(next_state):
            return False, step.step_id
        state = next_state
    return True, None


ARCHITECTURES: dict[str, Callable[[Trace], tuple[bool, int | None]]] = {
    "final_only": final_only,
    "hash_chain": hash_chain,
    "replay_receipt_ledger": replay_receipt_ledger,
}


def alter_output(trace: Trace) -> Trace:
    receipts = tuple(replace(receipt, output_digest="0" * 64) if receipt.step_id == 1 else receipt for receipt in trace.receipts)
    return replace(trace, receipts=receipts)


def change_argument(trace: Trace) -> Trace:
    steps = tuple(replace(step, argument=step.argument + 1) if step.step_id == 1 else step for step in trace.steps)
    return replace(trace, steps=steps)


def drop_receipt(trace: Trace) -> Trace:
    return replace(trace, receipts=tuple(receipt for receipt in trace.receipts if receipt.step_id != 1))


def main() -> None:
    cases = {"original": 0, "altered_output_detection": 0, "changed_argument_detection": 0, "dropped_receipt_detection": 0, "first_step_localization": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        trace = make_trace(seed)
        variants = {
            "altered_output_detection": alter_output(trace),
            "changed_argument_detection": change_argument(trace),
            "dropped_receipt_detection": drop_receipt(trace),
        }
        for architecture, run in ARCHITECTURES.items():
            row: dict[str, object] = {"seed": seed, "architecture": architecture}
            row["original_exact"] = run(trace) == (True, None)
            cases["original"] += int(row["original_exact"])
            for label, variant in variants.items():
                actual = run(variant)
                expected = expected_first_divergence(variant)
                detected = actual[0] is False
                cases[label] += int(detected)
                if label == "altered_output_detection":
                    cases["first_step_localization"] += int(detected and actual[1] == expected)
                row[f"{label}_detected"] = detected
                row[f"{label}_reported_step"] = actual[1]
                row[f"{label}_expected_step"] = expected
            rows.append(row)
    total_runs = 5 * len(ARCHITECTURES)
    summary = {
        "seeds": 5,
        "architectures": list(ARCHITECTURES),
        "total_architecture_runs": total_runs,
        "pass_counts": cases,
        "pass_rates": {key: round(value / total_runs, 4) for key, value in cases.items()},
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates")}, indent=2))


if __name__ == "__main__":
    main()
