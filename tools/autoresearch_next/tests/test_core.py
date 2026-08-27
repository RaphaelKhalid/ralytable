from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.autoresearch_next.archive import ArchiveEntry, MapElitesArchive
from tools.autoresearch_next.evaluator_contract import EvaluatorContract
from tools.autoresearch_next.ledger import AppendOnlyLedger
from tools.autoresearch_next.policy import PolicyManager
from tools.autoresearch_next.schema import CandidateContract
from tools.autoresearch_next.runner import gpu_owner
from tools.autoresearch_next.trust_kernel import ProtectedPathError, TrustKernel


class TrustKernelTests(unittest.TestCase):
    def test_partition_is_deterministic_and_outside_repo(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); artifact = root / "artifacts"; kernel = TrustKernel(Path.cwd(), artifact)
            a = kernel.freeze_partitions(["b", "a", "c", "d", "e"], artifact / "p.json", "run")
            b = kernel.freeze_partitions(["e", "d", "c", "b", "a"], artifact / "q.json", "run")
            self.assertEqual(a["development"], b["development"])
            self.assertEqual(a["task_key_hash"], b["task_key_hash"])

    def test_protected_paths_and_oracle_material_rejected(self):
        kernel = TrustKernel(Path.cwd(), Path(tempfile.mkdtemp()))
        with self.assertRaises(ProtectedPathError):
            kernel.validate_candidate_paths(["tools/autoresearch_next/ledger.py"])
        with self.assertRaises(ValueError):
            CandidateContract("bad", config={"expected_output": "secret"}).validate()

    def test_ledger_is_append_only_and_resume_is_visible(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = AppendOnlyLedger(Path(d) / "ledger.sqlite3")
            ledger.create_run("r", "test", "v1", d)
            c = CandidateContract("c").to_dict()
            ledger.experiment("e", "r", "greedy", c, "RUNNING")
            self.assertEqual(len(ledger.pending_experiments("r")), 1)
            ledger.experiment("e", "r", "greedy", c, "FAILED", {"failure": "timeout"}, "timeout")
            self.assertEqual(len(ledger.pending_experiments("r")), 0)
            with self.assertRaises(Exception):
                ledger.db.execute("DELETE FROM experiments")
            self.assertEqual(len(ledger.snapshot("r")["experiments"]), 2)
            ledger.close()

    def test_gpu_owner_serializes(self):
        with tempfile.TemporaryDirectory() as d:
            lock = Path(d) / "gpu.lock"
            with gpu_owner(lock, timeout=1):
                self.assertTrue(lock.exists())

    def test_policy_cannot_target_kernel_and_can_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = AppendOnlyLedger(Path(d) / "ledger.sqlite3")
            ledger.create_run("r", "test", "v1", d)
            policy = PolicyManager(ledger, "r")
            with self.assertRaises(ValueError):
                policy.activate({"ledger": "rewrite"})
            policy.rollback("gate_failed")
            self.assertGreaterEqual(len(ledger.snapshot("r")["policies"]), 2)
            ledger.close()

    def test_evaluator_contract_is_frozen_and_labeled(self):
        contract = EvaluatorContract()
        self.assertEqual(contract.task_count, 164)
        self.assertEqual(len(contract.digest()), 64)
        self.assertIn("tuned", contract.to_dict()["benchmark_tuning_label"])


class ArchiveTests(unittest.TestCase):
    def test_hard_rejection_and_niche_frontier(self):
        archive = MapElitesArchive()
        self.assertFalse(archive.propose(ArchiveEntry("bad", {"full_system_score": 0}, 2, "x", accepted=False)))
        self.assertTrue(archive.propose(ArchiveEntry("good", {"full_system_score": .5, "learned_parameters": 9}, 2, "x")))
        self.assertEqual(archive.leaders()[0].candidate_id, "good")


class CandidateTests(unittest.TestCase):
    def test_candidate_is_trainable_and_small(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "result.json"
            script = Path(__file__).resolve().parents[3] / "experiments/17_interpretable_humaneval/train_candidate.py"
            command = [sys.executable, str(script), "--config-json", json.dumps({"epochs": 8, "learning_rate": .1}), "--seed", "3", "--seconds", "1", "--output", str(output)]
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertGreater(payload["throughput"], 0)
            self.assertLessEqual(payload["learned_parameters"], 9_000_000)
            self.assertEqual(payload["exact_trace_replay"], 1.0)


if __name__ == "__main__":
    unittest.main()
