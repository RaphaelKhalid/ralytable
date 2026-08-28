# Preregistration: iterative multi-file repository repair

## Question

Can a tiny learned controller over typed executable state choose successive
repairs in a real on-disk Python package, while preserving causal dependence on
the state and staying under nine million learned parameters?

## Frozen design

The generator, candidate patches, package layout, public/hidden split, and
metrics are frozen in
`experiments/14_iterative_repo_repair/iterative_repo_repair.py` before the
full run. Each task contains two holes in separate modules. The API imports
both modules and applies the transform before the summary, so the summary
diagnostic is collected after the selected transform repair. Each package is
written below an experiment-local temporary directory and loaded through
Python's normal import machinery. Temporary packages are removed after each
case.

The learned model is one `nn.Linear(1, 1)` gate shared by both stages: two
learned scalar parameters. It sees only a typed boolean diagnostic state. Text
is used only to identify the two candidate actions for each branch; it is not a
learned input. The raw system selects exactly one action per hole. The verified
system enumerates at most 16 action pairs in a fixed order and accepts the
first pair passing all public tests.

## Controls and metrics

Every frozen seed reports raw learned task pass, hidden pass, syntax/compile
rate, learned parameter count, raw latency, verified latency, and verifier
expansions. It also reports symbolic state control, null-state control, and a
causal state-erasure intervention. A placebo intervention supplies the state
bits from an unrelated task while leaving the request and candidate actions
unchanged. Trace readability is not counted as causal legibility.

## Promotion gate

The direction is exploratory unless all three seeds remain under 9M learned
parameters, raw hidden pass exceeds the null control by at least 10 percentage
points, and state erasure changes the raw selected repair on at least 40% of
held-out tasks while the placebo rate is materially lower than the causal rate.
Even if it passes, the result is only a causal execution-boundary result because
the tasks are procedurally generated.

## Budget

First run a CPU smoke test. The frozen run is short and uses the existing local
GPU only after a read-only process-ownership check; no process may be stopped.
If GPU contention is present, the same fixed run may be executed on CPU without
changing the data or evaluation.
