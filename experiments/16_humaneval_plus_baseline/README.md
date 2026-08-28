# HumanEval+ local baseline

This directory contains the smallest honest benchmark adapter for the current
repository state. Ralytable does not emit Python completions yet, so the adapter
is explicitly a `deterministic_pass_baseline`, not a Raly-style model score. It
loads the official EvalPlus HumanEval+ task map, uses its task keys without a
hardcoded list, and writes `pass` as the completion for every task.

The official `evalplus.evaluate` command evaluates the resulting samples. On
Windows, EvalPlus 0.3.1 imports POSIX `resource`; the runner creates a disposable
no-op compatibility module for this harmless baseline only. It does not weaken
the candidate interface or edit the official harness. Outputs belong in a temp
directory, not this repository.

The benchmark-guided HumanEval+ score is intentionally a discovery baseline. It
is not held-out evidence, and this baseline does not touch MBPP+ or LiveCodeBench.

## Reproduction

Install the official harness in a disposable environment, then run:

```text
python zero_baseline.py --smoke
python zero_baseline.py --evaluate --output C:\path\outside\repo\humaneval_zero_baseline.jsonl --record C:\path\outside\repo\humaneval_zero_baseline.record.jsonl
python dashboard_server.py --record C:\path\outside\repo\humaneval_zero_baseline.record.jsonl --port 8766
```

The evaluation records the EvalPlus version, HumanEval+ task count, output path,
wall time, and official evaluator output. The candidate has zero learned
parameters, zero generation/search budget, and no Raly compiler/runtime in its
path. This adapter does not claim a raw-controller/full-system split; the
deterministic `pass` arm is the only meaningful null here.

`dashboard.html` is a loopback-only live view of the append-only record. It polls
the latest event and recent history, so refresh/restart does not lose completed
events. `result_record.schema.json` defines the machine-readable fields for a
future candidate runner: pass@1, compile rate, parameters, raw/full/null scores,
budgets, expansions, inference/search/total latency, wall time, failures, process
state, and artifact paths. The dashboard must never receive hidden tests,
expected outputs, or solutions.
