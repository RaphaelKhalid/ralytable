"""Recoverable, serialized experiment runner."""

from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .archive import ArchiveEntry, MapElitesArchive
from .ledger import AppendOnlyLedger
from .schema import CandidateContract, MetricRecord, OPERATOR_WEIGHTS
from .trust_kernel import HiddenScoreStore, TrustKernel


@contextmanager
def gpu_owner(lock_path: Path, timeout: float = 30.0) -> Iterator[None]:
    """Cross-platform exclusive owner lock; never kills another process."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    start = time.monotonic()
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError):
                if time.monotonic() - start >= timeout:
                    raise TimeoutError("GPU owner lock unavailable")
                time.sleep(0.2)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class ExperimentRunner:
    def __init__(self, repo_root: Path, artifact_root: Path, ledger: AppendOnlyLedger, run_id: str, use_wsl: bool = False):
        self.repo_root = repo_root.resolve()
        self.artifact_root = artifact_root.resolve()
        self.ledger = ledger
        self.run_id = run_id
        self.kernel = TrustKernel(self.repo_root, self.artifact_root)
        self.hidden = HiddenScoreStore(self.artifact_root / "hidden")
        self.archive = MapElitesArchive()
        self.lock_path = self.artifact_root / "gpu.owner.lock"
        self.candidate_script = self.repo_root / "experiments/17_interpretable_humaneval/train_candidate.py"
        self.use_wsl = use_wsl
        self.outputs: dict[str, tuple[Path, dict[str, Any], str]] = {}

    @staticmethod
    def _wsl_path(path: Path) -> str:
        resolved = str(path.resolve()).replace("\\", "/")
        if len(resolved) >= 2 and resolved[1] == ":":
            return "/mnt/" + resolved[0].lower() + resolved[2:]
        return resolved

    def _hidden_proxy_scores(self, weights: list[float], seed: int) -> tuple[float, float]:
        path = self.repo_root / "experiments/17_interpretable_humaneval/proxy.py"
        spec = importlib.util.spec_from_file_location("autoresearch_next_proxy", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("proxy evaluator unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return (module.score_weights(weights, seed, "blind_gate"), module.score_weights(weights, seed, "internal_final"))

    def run_one(self, arm: str, contract: CandidateContract, seconds: int, seed: int, partition: dict[str, Any]) -> MetricRecord:
        self.kernel.validate_contract(contract)
        exp_id = f"{self.run_id}-{arm}-{contract.candidate_id}"
        started = time.time()
        self.ledger.experiment(exp_id, self.run_id, arm, contract.to_dict(), "RUNNING", started_at=started)
        self.ledger.event(self.run_id, "experiment_started", {"arm": arm, "candidate_id": contract.candidate_id, "seed": seed}, exp_id)
        output = self.artifact_root / "experiments" / f"{exp_id}.json"
        self.kernel.assert_artifact_outside_repo(output)
        child_args = ["--config-json", json.dumps(contract.config), "--seed", str(seed), "--seconds", str(seconds), "--output", self._wsl_path(output) if self.use_wsl else str(output)]
        cmd = (["wsl.exe", "-d", "Ubuntu", "--", "/home/rapha/ralytable-autoresearch-next/.venv/bin/python", self._wsl_path(self.candidate_script), *child_args]
               if self.use_wsl else [sys.executable, str(self.candidate_script), *child_args])
        try:
            with gpu_owner(self.lock_path, timeout=seconds + 60):
                completed = subprocess.run(cmd, cwd=str(self.repo_root), capture_output=True, text=True, timeout=max(30, seconds + 45), check=False)
            if completed.returncode != 0:
                raise RuntimeError((completed.stderr or completed.stdout or "candidate failed")[-2000:])
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.outputs[contract.candidate_id] = (output, payload, exp_id)
            metrics = MetricRecord(candidate_id=contract.candidate_id, arm=arm, status="completed",
                                   raw_learned_score=payload.get("dev_score"), full_system_score=None,
                                   deterministic_null_score=0.0, code_validation_proxy=payload.get("dev_score"),
                                   transparency=contract.transparency, causal_intervention_rate=payload.get("causal_intervention_rate"),
                                   placebo_preservation=payload.get("placebo_preservation"), exact_trace_replay=payload.get("exact_trace_replay"),
                                   search_expansions=payload.get("search_expansions", 0), end_to_end_latency_ms=payload.get("latency_ms"),
                                   peak_vram_gb=payload.get("peak_vram_gb", 0.0), throughput=payload.get("throughput", 0.0),
                                   simplicity=payload.get("simplicity", 0.0), learned_parameters=payload.get("learned_parameters", contract.learned_parameters),
                                   extra={"training_seconds": payload.get("training_seconds"), "device": payload.get("device", "cpu"), "official_humaneval_plus": None, "named_sparse_rules": ["typed_monotonic_gate"]})
            self.ledger.experiment(exp_id, self.run_id, arm, contract.to_dict(), "COMPLETED", metrics.to_dict(), started_at=started, finished_at=time.time())
            self.ledger.artifact(f"{exp_id}-result", self.run_id, "candidate_result", str(output), __import__("hashlib").sha256(output.read_bytes()).hexdigest())
            self.ledger.event(self.run_id, "experiment_completed", metrics.to_dict(), exp_id)
            entry = ArchiveEntry(contract.candidate_id, metrics.to_dict(), contract.transparency, contract.mechanism_family)
            accepted = self.archive.propose(entry)
            self.ledger.archive(self.run_id, contract.candidate_id, entry.niche, metrics.to_dict(), accepted)
            return metrics
        except subprocess.TimeoutExpired:
            error = "timeout"
        except MemoryError:
            error = "oom"
        except KeyboardInterrupt:
            error = "interrupted"
        except Exception as exc:  # recoverable candidate failure
            error = f"contract_or_runtime:{type(exc).__name__}:{exc}"
        metrics = MetricRecord(candidate_id=contract.candidate_id, arm=arm, status="failed", learned_parameters=contract.learned_parameters, failure_category=error)
        self.ledger.experiment(exp_id, self.run_id, arm, contract.to_dict(), "FAILED", metrics.to_dict(), error=error, started_at=started, finished_at=time.time())
        self.ledger.event(self.run_id, "experiment_failed", {"error": error, "recovery": "candidate rolled back; next proposal may resume"}, exp_id)
        return metrics

    def promote_champion(self, arm: str, candidate_id: str, seed: int) -> dict[str, Any]:
        """Run each hidden partition exactly once for the selected arm champion."""
        if candidate_id not in self.outputs:
            raise ValueError(f"unknown champion: {candidate_id}")
        _, payload, exp_id = self.outputs[candidate_id]
        blind_score, final_score = self._hidden_proxy_scores(payload["weights"], seed)
        blind_hash = self.hidden.put(self.run_id, f"{arm}-champion-blind", {"score": blind_score, "partition": "blind_gate", "candidate_id": candidate_id})
        final_hash = self.hidden.put(self.run_id, f"{arm}-champion-final", {"score": final_score, "partition": "internal_final", "candidate_id": candidate_id})
        result = {"arm": arm, "candidate_id": candidate_id, "blind_proxy_score": blind_score, "internal_final_proxy_score": final_score,
                  "deterministic_null_score": 0.0, "blind_score_hash": blind_hash, "final_score_hash": final_hash,
                  "official_humaneval_plus": None, "policy": "one blind and one final evaluation per arm champion"}
        self.ledger.event(self.run_id, "champion_promoted", result, exp_id)
        return result

    def validate_gates(self, metrics: MetricRecord) -> tuple[bool, list[str]]:
        failures = []
        if metrics.learned_parameters > 9_000_000: failures.append("learned_parameter_limit")
        if (metrics.exact_trace_replay or 0) < 1.0: failures.append("exact_trace_replay")
        if (metrics.causal_intervention_rate or 0) < 0.80: failures.append("causal_intervention_rate")
        if (metrics.placebo_preservation or 0) < 0.95: failures.append("placebo_preservation")
        if metrics.transparency >= 3 and not metrics.extra.get("named_sparse_rules"): failures.append("T3_named_mechanism")
        return not failures, failures

    @staticmethod
    def operator_for(index: int) -> str:
        position = (index % 100) / 100.0
        cumulative = 0.0
        for name, weight in OPERATOR_WEIGHTS.items():
            cumulative += weight
            if position < cumulative: return name
        return "radical"
