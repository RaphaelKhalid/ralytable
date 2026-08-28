"""Immutable trust boundary: partitions, hashes, contracts, and recovery policy."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Iterable

from .schema import POLICY_VERSION, CandidateContract, canonical_json, sha256_file


PROTECTED_RELATIVE_PATHS = {
    "tools/autoresearch_next/trust_kernel.py",
    "tools/autoresearch_next/ledger.py",
    "tools/autoresearch_next/schema.py",
    "experiments/17_interpretable_humaneval/partitions.json",
}


class ProtectedPathError(ValueError):
    pass


class TrustKernel:
    def __init__(self, repo_root: Path, artifact_root: Path):
        self.repo_root = repo_root.resolve()
        self.artifact_root = artifact_root.resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def assert_artifact_outside_repo(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved == self.repo_root or self.repo_root in resolved.parents:
            raise ProtectedPathError(f"artifact must be outside repository: {path}")

    def validate_candidate_paths(self, paths: Iterable[str]) -> None:
        for raw in paths:
            p = Path(raw).as_posix().lstrip("./")
            if p in PROTECTED_RELATIVE_PATHS or p.startswith("tools/autoresearch_next/"):
                raise ProtectedPathError(f"candidate path is protected: {raw}")
            if ".." in Path(p).parts or p.startswith("/"):
                raise ProtectedPathError(f"candidate path escapes workspace: {raw}")

    def validate_contract(self, contract: CandidateContract) -> None:
        self.validate_candidate_paths(contract.files_changed)
        contract.validate(PROTECTED_RELATIVE_PATHS)

    def freeze_partitions(self, task_keys: list[str], manifest_path: Path, run_id: str) -> dict[str, Any]:
        if len(task_keys) < 3:
            raise ValueError("at least three opaque task keys are required")
        if len(set(task_keys)) != len(task_keys):
            raise ValueError("duplicate task keys")
        ordered = sorted(task_keys, key=lambda key: hashlib.sha256(key.encode()).hexdigest())
        n = len(ordered)
        dev_end = max(1, int(n * 0.70))
        blind_end = max(dev_end + 1, int(n * 0.85))
        manifest = {
            "manifest_version": 1, "run_id": run_id, "source": "opaque_runtime_keys",
            "task_count": n, "task_key_hash": hashlib.sha256(canonical_json(ordered)).hexdigest(),
            "development": ordered[:dev_end], "blind_gate": ordered[dev_end:blind_end],
            "internal_final": ordered[blind_end:], "created_at": time.time(),
            "hidden_scores": {"blind_gate": "stored outside candidate context", "internal_final": "stored outside candidate context"},
        }
        self.assert_artifact_outside_repo(manifest_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return manifest

    def receipt(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = canonical_json(payload)
        return {"policy_version": POLICY_VERSION, "receipt_id": secrets.token_hex(16),
                "payload_sha256": hashlib.sha256(data).hexdigest(), "payload": payload,
                "created_at": time.time()}

    def verify_hash(self, path: Path, expected: str) -> bool:
        return path.exists() and sha256_file(path) == expected


class HiddenScoreStore:
    """Stores scores in the artifact root; candidate-facing payloads contain only status."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, run_id: str, partition: str, score: dict[str, Any]) -> str:
        path = self.root / f"{run_id}.{partition}.hidden.json"
        path.write_text(json.dumps(score, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)
        return hashlib.sha256(canonical_json(score)).hexdigest()

    def get(self, run_id: str, partition: str) -> dict[str, Any]:
        path = self.root / f"{run_id}.{partition}.hidden.json"
        return json.loads(path.read_text(encoding="utf-8"))

