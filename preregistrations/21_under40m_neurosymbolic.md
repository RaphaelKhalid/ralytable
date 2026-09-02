# Preregistration — under-40M neurosymbolic Python synthesis

Date: 2026-08-31

Question: Can a compact learned classifier over an explicit typed state, paired
with a constrained symbolic Python backend, produce working code on a real
HumanEval+ evaluation while preserving measurable dependence on the state?

Null: deterministic `pass` completion, and the symbolic backend with the
learned strategy logits removed. HumanEval+ is a benchmark-guided discovery
score, not held-out evidence.

Alternative: the hybrid learned-state system improves greedy HumanEval+ pass@1
over the null and/or the symbolic-only system, while relevant state erasure
changes selected strategies more often than an irrelevant placebo.

Primary endpoint: official EvalPlus 0.3.1 HumanEval+ plus pass@1 over all 164
tasks, one greedy completion per task. Secondary endpoints: base pass@1,
compile rate, symbolic-only score, state-erasure change rate, placebo
preservation, parameter count, latency, and peak VRAM.

Model family: typed-state transformer with width 512, eight attention layers,
feed-forward width 2048, fixed byte vocabulary, and a linear strategy head.
The learned-parameter gate is strictly below 40,000,000. Training uses only
generated synthetic strategy descriptions, never HumanEval solutions, tests,
or expected outputs. The code backend is a fixed, auditable family of Python
templates.

Search family: five learning-rate/dropout/depth configurations and four lexical
prior weights, one seed per candidate during exploration. A final candidate is
retrained with three seeds before any claim of replication. No candidate is
selected from MBPP+, LiveCodeBench, or hidden test content. The tournament is
HumanEval+-tuned and any result is labeled accordingly.

Stopping rule: eight wall-clock hours, 100 candidates, or an explicit STOP file.
Hard invalidation: parameter overflow, benchmark material in training,
evaluator mutation, malformed samples, non-reproducible generation, or a
nonzero subprocess failure. A zero score is a valid negative result.

Analysis: report the deterministic null beside every score, keep base and plus
separate, report task-level counts and artifact hashes, and do not claim general
coding or interpretability from a single benchmark run.
