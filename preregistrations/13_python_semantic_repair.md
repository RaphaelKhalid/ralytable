# Protocol — natural-language conditional repair proxy

Status: written before the confirmation run.

Use 512 training and 256 held-out executable-Python tasks, three public cases,
four hidden cases, and seeds 11, 23, and 37. Each request describes a
conditional list-repair rule in prose: a predicate over the executed prefix
state selects one of two natural-language action descriptions. Compare a
deterministic public-search null, state-only, text-only, hybrid, and
cross-product learned controllers. Report raw and verified task/test pass,
compile rate, expansions, latency, VRAM, learned parameters, and causal
relevant-state versus irrelevant-placebo interventions.

Promotion requires a raw hybrid/cross gain over both one-factor controls and
at least 25% relevant state intervention with at least 95% placebo preservation
across seeds. This is a controlled Python proxy, not a claim about external
coding benchmarks.
