"""One-minute deterministic gate for the Raly Coder action sandbox."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import time

from sandbox import Sandbox


APP = """def normalize(values):
    \"\"\"Return sorted unique nonnegative integers.\"\"\"
    return sorted(set(value for value in values if value > 0))
"""

TESTS = """import unittest
from app import normalize


class NormalizeTests(unittest.TestCase):
    def test_order_and_duplicates(self):
        self.assertEqual(normalize([3, 1, 3, 2]), [1, 2, 3])

    def test_zero_is_nonnegative(self):
        self.assertEqual(normalize([-2, 0, 2, 0]), [0, 2])


if __name__ == \"__main__\":
    unittest.main()
"""


def action(op: str, **args):
    return {"schema": "raly-coder-actions-v1", "op": op, "args": args}


def main() -> None:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="raly-coder-smoke-") as temp:
        root = Path(temp)
        (root / "tests").mkdir()
        (root / "app.py").write_text(APP, encoding="utf-8", newline="\n")
        (root / "tests" / "test_app.py").write_text(TESTS, encoding="utf-8", newline="\n")
        sandbox = Sandbox(root)

        symbol = sandbox.execute(action("find_symbol", path="app.py", name="normalize"))
        assert symbol["ok"] and symbol["matches"][0]["start_line"] == 1
        opened = sandbox.execute(action("open_file", path="app.py"))
        assert opened["ok"] and opened["sha256"] == hashlib.sha256(APP.encode()).hexdigest()
        region = sandbox.execute(action("read_region", path="app.py", start_line=1, end_line=3))
        assert region["ok"] and "def normalize" in region["content"]
        masked = sandbox.intervene(region["event_id"])
        assert masked["counterfactual_output"]["content"] == ""

        failed = sandbox.execute(action("run_tests"))
        assert failed["ok"] and not failed["passed"]
        failure = sandbox.execute(action("inspect_failure", run_id=failed["run_id"]))
        assert failure["ok"] and failure["summary_lines"]

        old_text = APP
        fixed = old_text.replace("value > 0", "value >= 0")
        patched = sandbox.execute(action(
            "apply_patch", path="app.py",
            expected_sha256=hashlib.sha256(old_text.encode()).hexdigest(),
            old_text=old_text, new_text=fixed,
        ))
        assert patched["ok"] and patched["type"] == "patch_applied"
        passed = sandbox.execute(action("run_tests"))
        assert passed["ok"] and passed["passed"]

        unsafe = sandbox.execute(action("open_file", path="../app.py"))
        assert not unsafe["ok"]
        stale = sandbox.execute(action(
            "apply_patch", path="app.py", expected_sha256=old_text,
            old_text=old_text, new_text=fixed,
        ))
        assert not stale["ok"]

        trace_path = root / "trace.jsonl"
        trace_path.write_text(sandbox.trace_jsonl(), encoding="utf-8")
        trace_rows = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").splitlines()
        ]
        assert len(trace_rows) == len(sandbox.events) and trace_rows[-1]["ok"] is False

        summary = {
            "status": "PASS",
            "events": len(sandbox.events),
            "failed_run": failed["run_id"],
            "passed_run": passed["run_id"],
            "intervention_event": region["event_id"],
            "trace_rows": len(trace_rows),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
