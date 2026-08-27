# Findings

The smoke tournament is an exploratory pipeline check and does not establish a HumanEval+ capability or full interpretability result.

## What is measured

The run records a deterministic synthetic code-validation proxy, raw learned
candidate score, full proxy-system score, deterministic-null score, named-state
causal intervention, placebo preservation, trace replay, resources, failures,
and complete append-only lineage. Official EvalPlus HumanEval+ remains a
separate scoring-only integration and is labeled HumanEval+-tuned when used.

## Limitations

The candidate does not generate Python programs, the current sandbox could not
access WSL or PyTorch, and the proxy task family is not a substitute for
HumanEval+. One seed per smoke candidate is exploratory. The causal controls
are internal proxy controls, not evidence about a deployed model.

## Reproduction

See `experiments/17_interpretable_humaneval/README.md` and the report emitted by
`python -m tools.autoresearch_next report --root <artifact-root>`.

