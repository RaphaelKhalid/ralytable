"""Deterministic, restricted local executor for Raly Coder actions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

from schema import Action, ActionValidationError, parse_action


MAX_FILE_BYTES = 256_000
MAX_REGION_LINES = 200
MAX_OUTPUT_BYTES = 64_000
TEST_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class TraceEvent:
    event_id: int
    action: dict[str, Any]
    state_before: str
    state_after: str
    ok: bool
    output: dict[str, Any]
    elapsed_ms: float


@dataclass(frozen=True)
class FailureRecord:
    run_id: str
    returncode: int
    timed_out: bool
    stdout: str
    stderr: str


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _clip(text: str) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return text
    return encoded[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace") + "\n[truncated]"


class Sandbox:
    """Execute actions inside one repository snapshot.

    The sandbox never accepts a model-provided shell command. Tests are run by
    one fixed Python unittest command and every action is recorded before the
    next action can execute.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"sandbox root is not a directory: {self.root}")
        self.events: list[TraceEvent] = []
        self.failures: dict[str, FailureRecord] = {}

    def _path(self, raw: Any) -> Path:
        if not isinstance(raw, str) or not raw or "\x00" in raw:
            raise ActionValidationError("path must be a non-empty string")
        candidate = Path(raw)
        if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
            raise ActionValidationError("path must be relative and cannot contain ..")
        resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ActionValidationError("path escapes sandbox root") from exc
        return resolved

    def _state_hash(self) -> str:
        entries: list[tuple[str, str]] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(self.root).as_posix()
            data = path.read_bytes()
            if len(data) <= MAX_FILE_BYTES:
                entries.append((rel, _sha256_bytes(data)))
            else:
                entries.append((rel, f"oversize:{len(data)}"))
        return _sha256_text(json.dumps(entries, separators=(",", ":")))

    def _read_text(self, raw_path: Any) -> tuple[Path, str]:
        path = self._path(raw_path)
        if path.suffix != ".py":
            raise ActionValidationError("only Python files are exposed")
        if not path.is_file():
            raise ActionValidationError(f"file does not exist: {raw_path}")
        data = path.read_bytes()
        if len(data) > MAX_FILE_BYTES:
            raise ActionValidationError("file exceeds sandbox size limit")
        try:
            return path, data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ActionValidationError("file is not UTF-8") from exc

    def execute(self, value: Action | str | dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        before = self._state_hash()
        try:
            action = parse_action(value)
            output = self._dispatch(action)
            ok = True
        except (ActionValidationError, OSError, SyntaxError, ValueError) as exc:
            action = value.as_dict() if isinstance(value, Action) else {"raw": value}
            output = {"error": str(exc), "error_type": type(exc).__name__}
            ok = False
        after = self._state_hash()
        event = TraceEvent(
            event_id=len(self.events), action=action if isinstance(action, dict) else action.as_dict(),
            state_before=before, state_after=after, ok=ok, output=output,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )
        self.events.append(event)
        return {"event_id": event.event_id, **output, "ok": ok}

    def _dispatch(self, action: Action) -> dict[str, Any]:
        return {
            "find_symbol": self._find_symbol,
            "open_file": self._open_file,
            "read_region": self._read_region,
            "apply_patch": self._apply_patch,
            "run_tests": self._run_tests,
            "inspect_failure": self._inspect_failure,
        }[action.op](action.args)

    def _find_symbol(self, args: dict[str, Any]) -> dict[str, Any]:
        path, text = self._read_text(args["path"])
        name = args["name"]
        if not isinstance(name, str) or not name:
            raise ActionValidationError("symbol name must be a non-empty string")
        tree = ast.parse(text, filename=str(path))
        found: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            node_name = getattr(node, "name", None)
            if node_name != name:
                continue
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            found.append({
                "name": name,
                "kind": type(node).__name__,
                "path": path.relative_to(self.root).as_posix(),
                "start_line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "source": ast.get_source_segment(text, node) or "",
            })
        return {"type": "symbol_matches", "matches": found}

    def _open_file(self, args: dict[str, Any]) -> dict[str, Any]:
        path, text = self._read_text(args["path"])
        return {
            "type": "file",
            "path": path.relative_to(self.root).as_posix(),
            "sha256": _sha256_text(text),
            "line_count": len(text.splitlines()),
            "content": text,
        }

    def _read_region(self, args: dict[str, Any]) -> dict[str, Any]:
        path, text = self._read_text(args["path"])
        start, end = args["start_line"], args["end_line"]
        if end - start + 1 > MAX_REGION_LINES:
            raise ActionValidationError("read_region exceeds line limit")
        lines = text.splitlines(keepends=True)
        if start > len(lines):
            raise ActionValidationError("read_region starts past end of file")
        content = "".join(lines[start - 1:min(end, len(lines))])
        return {
            "type": "region",
            "path": path.relative_to(self.root).as_posix(),
            "start_line": start,
            "end_line": min(end, len(lines)),
            "sha256": _sha256_text(content),
            "content": content,
        }

    def _apply_patch(self, args: dict[str, Any]) -> dict[str, Any]:
        path, old = self._read_text(args["path"])
        expected = args["expected_sha256"]
        if _sha256_text(old) != expected:
            raise ActionValidationError("patch precondition hash does not match")
        old_text, new_text = args["old_text"], args["new_text"]
        if not isinstance(old_text, str) or not isinstance(new_text, str):
            raise ActionValidationError("patch text must be strings")
        if not old_text:
            raise ActionValidationError("empty old_text is not an allowed patch")
        if old.count(old_text) != 1:
            raise ActionValidationError("old_text must match exactly once")
        updated = old.replace(old_text, new_text, 1)
        path.write_text(updated, encoding="utf-8", newline="")
        return {
            "type": "patch_applied",
            "path": path.relative_to(self.root).as_posix(),
            "before_sha256": _sha256_text(old),
            "after_sha256": _sha256_text(updated),
        }

    def _run_tests(self, args: dict[str, Any]) -> dict[str, Any]:
        target = args.get("target", "all")
        if target != "all":
            raise ActionValidationError("v1 run_tests target must be 'all'")
        run_id = f"run-{len(self.failures):04d}"
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONHASHSEED": "0",
            "PYTHONIOENCODING": "utf-8",
        }
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
                cwd=self.root, env=env, capture_output=True, text=True,
                timeout=TEST_TIMEOUT_SECONDS, check=False,
            )
            record = FailureRecord(run_id, completed.returncode, False,
                                   _clip(completed.stdout), _clip(completed.stderr))
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            record = FailureRecord(run_id, -1, True, _clip(stdout), _clip(stderr))
        self.failures[run_id] = record
        return {
            "type": "test_run",
            "run_id": run_id,
            "passed": record.returncode == 0 and not record.timed_out,
            "returncode": record.returncode,
            "timed_out": record.timed_out,
            "stdout": record.stdout,
            "stderr": record.stderr,
        }

    def _inspect_failure(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = args["run_id"]
        record = self.failures.get(run_id)
        if record is None:
            raise ActionValidationError(f"unknown test run: {run_id}")
        failing_lines = [
            line for line in (record.stdout + "\n" + record.stderr).splitlines()
            if re.search(r"(?:FAIL|ERROR|Traceback|AssertionError|^E$)", line)
        ]
        return {
            "type": "failure_report",
            "run_id": run_id,
            "passed": record.returncode == 0 and not record.timed_out,
            "timed_out": record.timed_out,
            "summary_lines": failing_lines[:100],
            "stdout": record.stdout,
            "stderr": record.stderr,
        }

    def intervene(self, event_id: int, mode: str = "mask_output") -> dict[str, Any]:
        """Return a deterministic counterfactual view of one read event.

        This hook does not mutate the repository. It is intentionally explicit:
        the evaluator can mask a named intermediate read and replay the agent,
        while retaining the original trace and state hashes.
        """
        if event_id < 0 or event_id >= len(self.events):
            raise ValueError("unknown trace event")
        event = self.events[event_id]
        op = event.action.get("op") if isinstance(event.action, dict) else None
        if op not in {"find_symbol", "open_file", "read_region"}:
            raise ValueError("only read events can be intervened on")
        if mode != "mask_output":
            raise ValueError("unknown intervention mode")
        output = dict(event.output)
        for field in ("content", "source", "matches"):
            if field in output:
                output[field] = "" if field != "matches" else []
        return {
            "event_id": event_id,
            "mode": mode,
            "original_output_hash": _sha256_text(json.dumps(event.output, sort_keys=True)),
            "counterfactual_output": output,
            "state_after": event.state_after,
        }

    def trace_jsonl(self) -> str:
        return "".join(json.dumps(asdict(event), sort_keys=True) + "\n" for event in self.events)

