# Experiment 16 local handoff

Run date: 2026-08-27. Base checkout: `fb3d4037111ade47b9ca7d70ab04785e65bd8715`.
The committed adapter needed one experiment-owned correction after audit:
completed events now set `completed_tasks` to the runtime task count. That fix
is present in the working tree but could not be committed because this linked
worktree's shared OneDrive Git object database is not writable.

## Valid baseline

- Benchmark: official EvalPlus HumanEval+, EvalPlus `0.3.1`, 164 runtime-loaded tasks.
- Arm: `deterministic_pass_baseline`; emits the literal completion `pass` for each runtime task key. It is a null, not a model or Raly runtime.
- Learned parameters: 0 (within the <=9M boundary); generation budget: 1 sample, temperature 0.0; search budget: 0 expansions, 0 seconds.
- Official result: base HumanEval `pass@1 = 0.000`; HumanEval+ `pass@1 = 0.000`. The right null is this deterministic baseline; no raw-controller/full-system split is claimed, and compile rate is not applicable.
- Official evaluator return code: 0. Wall time: 242.544 seconds. Latency convention: no model; inference/search are null and total would be end-to-end.
- Failures: none. The dashboard's final event reports `completed 164/164`.

Environment: WSL2 Ubuntu, kernel `6.18.33.2-microsoft-standard-WSL2`, Python
`3.14.4`, EvalPlus `0.3.1`, disposable venv at
`/home/rapha/.venvs/ralytable-evalplus-0.3.1`. The live dashboard is
loopback-only at `http://127.0.0.1:8766/` and reads the append-only record at
`/home/rapha/ralytable-human-eval-plus/records/humaneval_zero_baseline.record.jsonl`.
Samples and logs are under `/home/rapha/ralytable-human-eval-plus/`, outside
the repository. The dashboard API exposes only run metadata and no hidden
tests, expected outputs, or solutions.

## Reproduction

```text
wsl.exe -d Ubuntu -- bash -lc 'cd /home/rapha; PYTHONDONTWRITEBYTECODE=1 /home/rapha/.venvs/ralytable-evalplus-0.3.1/bin/python /mnt/c/Users/rapha/.codex/worktrees/94d2/mechinterp/experiments/16_humaneval_plus_baseline/zero_baseline.py --evaluate --output /home/rapha/ralytable-human-eval-plus/artifacts/humaneval_zero_baseline_rerun.samples.jsonl --record /home/rapha/ralytable-human-eval-plus/records/humaneval_zero_baseline.record.jsonl'
wsl.exe -d Ubuntu -- bash -lc 'PYTHONDONTWRITEBYTECODE=1 /home/rapha/.venvs/ralytable-evalplus-0.3.1/bin/python /mnt/c/Users/rapha/.codex/worktrees/94d2/mechinterp/experiments/16_humaneval_plus_baseline/dashboard_server.py --record /home/rapha/ralytable-human-eval-plus/records/humaneval_zero_baseline.record.jsonl --port 8766'
```

The first completed attempt was preserved in the same append-only record; it
was rerun after the `0/164` bookkeeping bug was found. Do not start the
HumanEval+-tuned autoresearch loop in this task.
