"""Append-only SQLite lineage ledger.

The ledger is not a cryptographic boundary against an administrator. It is a
durable guard against accidental mutation and ordinary autonomous candidates.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, created_at REAL NOT NULL, status TEXT NOT NULL,
  profile TEXT NOT NULL, policy_version TEXT NOT NULL, root TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiments (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, experiment_id TEXT NOT NULL, run_id TEXT NOT NULL, arm TEXT NOT NULL,
  candidate_id TEXT NOT NULL, parent_ids TEXT NOT NULL, operator TEXT NOT NULL,
  contract_json TEXT NOT NULL, status TEXT NOT NULL, started_at REAL,
  finished_at REAL, metrics_json TEXT, error TEXT,
  FOREIGN KEY(run_id) REFERENCES runs(run_id)
);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
  experiment_id TEXT, event_type TEXT NOT NULL, payload_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, kind TEXT NOT NULL,
  path TEXT NOT NULL, sha256 TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS partitions (
  manifest_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, manifest_json TEXT NOT NULL,
  sha256 TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS archive_entries (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
  candidate_id TEXT NOT NULL, niche TEXT NOT NULL, metrics_json TEXT NOT NULL,
  accepted INTEGER NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS policy_events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
  policy_hash TEXT NOT NULL, action TEXT NOT NULL, policy_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
"""


class AppendOnlyLedger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
        self._lock = threading.RLock()
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.executescript("""
        CREATE TRIGGER IF NOT EXISTS deny_update_experiments BEFORE UPDATE ON experiments BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS deny_delete_experiments BEFORE DELETE ON experiments BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS deny_update_events BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS deny_delete_events BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS deny_update_artifacts BEFORE UPDATE ON artifacts BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS deny_delete_artifacts BEFORE DELETE ON artifacts BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS deny_update_partitions BEFORE UPDATE ON partitions BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS deny_delete_partitions BEFORE DELETE ON partitions BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS deny_update_archive BEFORE UPDATE ON archive_entries BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS deny_delete_archive BEFORE DELETE ON archive_entries BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS deny_update_policy BEFORE UPDATE ON policy_events BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS deny_delete_policy BEFORE DELETE ON policy_events BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        """)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def create_run(self, run_id: str, profile: str, policy_version: str, root: str) -> None:
        self.db.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)", (run_id, time.time(), "RUNNING", profile, policy_version, root))
        self.db.commit()

    def event(self, run_id: str, event_type: str, payload: dict[str, Any], experiment_id: str | None = None) -> None:
        self.db.execute("INSERT INTO events(run_id, experiment_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                        (run_id, experiment_id, event_type, json.dumps(payload, sort_keys=True), time.time()))
        self.db.commit()

    def experiment(self, experiment_id: str, run_id: str, arm: str, contract: dict[str, Any], status: str,
                   metrics: dict[str, Any] | None = None, error: str | None = None,
                   started_at: float | None = None, finished_at: float | None = None) -> None:
        self.db.execute("INSERT INTO experiments(experiment_id,run_id,arm,candidate_id,parent_ids,operator,contract_json,status,started_at,finished_at,metrics_json,error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            experiment_id, run_id, arm, contract["candidate_id"], json.dumps(contract.get("parent_ids", [])),
            contract.get("operator", "unknown"), json.dumps(contract, sort_keys=True), status,
            started_at, finished_at, json.dumps(metrics, sort_keys=True) if metrics else None, error))
        self.db.commit()

    def artifact(self, artifact_id: str, run_id: str, kind: str, path: str, sha256: str) -> None:
        self.db.execute("INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?)", (artifact_id, run_id, kind, path, sha256, time.time()))
        self.db.commit()

    def partition(self, manifest_id: str, run_id: str, manifest: dict[str, Any], sha256: str) -> None:
        self.db.execute("INSERT INTO partitions VALUES (?, ?, ?, ?, ?)", (manifest_id, run_id, json.dumps(manifest, sort_keys=True), sha256, time.time()))
        self.db.commit()

    def archive(self, run_id: str, candidate_id: str, niche: str, metrics: dict[str, Any], accepted: bool) -> None:
        self.db.execute("INSERT INTO archive_entries(run_id,candidate_id,niche,metrics_json,accepted,created_at) VALUES (?,?,?,?,?,?)",
                        (run_id, candidate_id, niche, json.dumps(metrics, sort_keys=True), int(accepted), time.time()))
        self.db.commit()

    def policy(self, run_id: str, policy_hash: str, action: str, policy: dict[str, Any]) -> None:
        self.db.execute("INSERT INTO policy_events(run_id,policy_hash,action,policy_json,created_at) VALUES (?,?,?,?,?)",
                        (run_id, policy_hash, action, json.dumps(policy, sort_keys=True), time.time()))
        self.db.commit()

    def pending_experiments(self, run_id: str) -> list[sqlite3.Row]:
        return list(self.db.execute("SELECT * FROM experiments WHERE run_id=? AND status IN ('RUNNING','INTERRUPTED') ORDER BY seq", (run_id,)))

    def snapshot(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            rows = lambda table: [dict(r) for r in self.db.execute(f"SELECT * FROM {table} WHERE run_id=? ORDER BY rowid", (run_id,))]
            return {"run": dict(self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()),
                    "experiments": rows("experiments"), "events": rows("events"),
                    "artifacts": rows("artifacts"), "partitions": rows("partitions"),
                    "archive": rows("archive_entries"), "policies": rows("policy_events")}
