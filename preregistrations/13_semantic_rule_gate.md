# Protocol — learned predicate gate with fixed rule multiplexer

Status: written before smoke testing.

Reuse the frozen semantic conditional-repair tasks, parser, public/hidden
execution, and three-seed evaluation. The learned component receives only the
typed truth value of the parsed predicate and learns a single scalar gate. The
parsed rule then deterministically selects its true-action or false-action
description. Compare the zero-parameter symbolic rule, the two-parameter
learned gate, and the same gate with public verification. Measure raw and full
functional pass, compile, parameters, VRAM, latency, expansions, and causal
predicate erasure versus nuisance-noise placebo.

The hypothesis is that the generic MLP failure is a conditional-multiplexer
failure, not a missing-data failure. This is deliberately a small architectural
ablation and remains a synthetic Python proxy rather than a general coding
benchmark.

## Post-run audit note

The two-parameter gate is a supplied predicate-bit identity/routing control,
not semantic inference. The nuisance bit is absent from the gate and fixed
multiplexer, so its placebo preservation is tautological; the reported causal
rate is historical and invalid for causal promotion. Scores and the original
protocol are retained in Experiment 13's JSONL and findings.
