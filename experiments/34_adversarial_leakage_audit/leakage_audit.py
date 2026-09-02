"""Adversarial recursive and encoded leakage checks for parser records."""

from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FORBIDDEN_KEYS = {"answer", "solution", "hidden_test", "expected_output", "oracle", "benchmark_test"}


def suspicious_value(value: str) -> bool:
    compact = "".join(value.split())
    if len(compact) < 8 or len(compact) % 4:
        return False
    try:
        decoded = base64.b64decode(compact, validate=True).decode("utf-8").lower()
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return False
    return any(term in decoded for term in FORBIDDEN_KEYS)


def safe_record(record: object, path: str = "root") -> bool:
    if isinstance(record, dict):
        for key, value in record.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                return False
            if not safe_record(value, f"{path}.{key}"):
                return False
        return True
    if isinstance(record, list):
        return all(safe_record(value, f"{path}[]") for value in record)
    if isinstance(record, str) and not path.endswith(".prompt"):
        return not suspicious_value(record)
    # Prompt prose is not keyword-scanned.
    return True


def safe_structured_fields(record: dict[str, object]) -> bool:
    for key, value in record.items():
        if key == "prompt":
            continue
        if isinstance(value, str) and suspicious_value(value):
            return False
        serialized = json.dumps(value, sort_keys=True)
        if suspicious_value(serialized):
            return False
    return True


def accepted(record: dict[str, object]) -> bool:
    return safe_record(record) and safe_structured_fields(record)


def main() -> None:
    clean = [
        {"prompt": "Explain why this solution is correct.", "graph": {"nodes": ["input", "map"]}},
        {"prompt": "Implement a solution for sorting values.", "graph": {"nodes": ["input", "sort"]}, "notes": ["public example"]},
    ]
    contaminated = [
        {"prompt": "x", "graph": {"metadata": {"answer": 1}}},
        {"prompt": "x", "graph": {"metadata": {"payload": "c29sdXRpb24="}}},
        {"prompt": "x", "graph": {"nested": [{"oracle": "yes"}]}},
    ]
    output = {
        "clean_accepted": sum(accepted(row) for row in clean),
        "clean_records": len(clean),
        "contaminated_rejected": sum(not accepted(row) for row in contaminated),
        "contaminated_records": len(contaminated),
        "note": "Adversarial schema audit only; no model or benchmark was run.",
    }
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
