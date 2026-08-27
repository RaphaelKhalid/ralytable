# Research log

Append-only. Dead ends stay in.

## 2026-08-26 -- repo created

Scoping. Direction chosen: reasoning-model interpretability, building on and then
departing from Thought Anchors.

Framing settled: the interesting cut is at the level of *substrate*, not at the level
of patching the resampling estimator. Thought Anchors probes text from the outside
because natural language has no machine-readable dependency structure. If the model
reasons in a substrate where dependencies are explicit, the causal graph can be read
rather than estimated.

Open, unresolved:
- Which cheap reasoning model on OpenRouter exposes usable CoT.
- What the formal substrate actually is (Prolog/Datalog clauses vs. typed steps vs.
  proof terms). Unknown whether models emit any of these reliably enough to study.
- Whether "read-off graph vs. resampled importance" can be compared on a common scale
  at all. This is the load-bearing methodological risk and is not yet solved.

Not yet done: no code, no API calls, no cost measured.

## 2026-08-27 -- overnight autoresearch integration and correction

Verdict: the overnight run found a narrow efficiency/state result, not a
general coder. In the valid Experiment 13 record, typed legality plus
public-example search moved a learned sketch from 52.1% raw pass to 89.6%
full-system hidden pass on a generated synthetic composition family; the
deterministic null also reached 89.6%. The larger state-only controller is a
candidate mechanism that is causally load-bearing in a synthetic control: state
erasure changed 50.0% of raw decisions while an irrelevant placebo preserved
100%. Raw learned, verified full-system, symbolic, and deterministic-null
scores are distinct and must not be merged.

The integration provenance is the completed overnight worktree at
`ef74feb27fffdeeebfa380f2f8b344bb17a4db7f`, descended from `faaf00d`. The
machine facts are RTX 4060 Laptop, 8.6GB VRAM, torch 2.6.0+cu124, bf16
autocast, fused AdamW, and a <=9M learned-parameter gate; the largest logged
model was 54,516 parameters. Experiment 14 is CPU-only smoke evidence and is
paused: its planned multi-seed run was stopped after file-backed package
imports exceeded the short budget.

Scientific correction: the two-parameter predicate gate is supplied-bit
identity/routing, not semantic inference. The `semantic_rule_gate` and
`repository_bundle_gate` nuisance-placebo controls are tautological because
nuisance is absent from the gate, so their historical causal rates are invalid
for causal promotion. All Experiment 13/14 tasks are synthetic or generated.
The actual Raly compiler/runtime was not in the execution path; call this
Raly-style or Raly-inspired research, not Raly-based.

Measurement correction: historical `latency_ms` starts after inference and
includes old-loop evaluation work, so it is not end-to-end latency. New
`run.py` rows separate inference, selection, hidden scoring, and
inference-through-selection. The valid JSONL has 386 rows. The 12-row
oracle-contaminated smoke remains preserved in
`experiments/13_autoresearch_raly_coder/research_log_invalidated_null_oracle.jsonl`
and is excluded from aggregates. The record audit and reproduction path are
in `experiments/13_autoresearch_raly_coder/measurement_audit.py` and its
README; no replacement confirmation results were manufactured.

Next decision: do not promote this architecture. First remove the supplied
label/state shortcut with independently specified tasks where executable state
is necessary but not sufficient, keeping hidden answers scoring-only. Then
test a richer Python surface or repository-local repair. GitHub publication,
pull request, Vercel preview, and production promotion remain separate review
actions and were not performed here.

Public destination (predeclared, not run here): EvalPlus HumanEval+ is the
benchmark-guided discovery scoreboard; task-level failures may be inspected and
optimized against with contamination disclosed, so its tuned score is not held-out
evidence. EvalPlus MBPP+ is the cleaner cross-benchmark generalization check;
BigCodeBench-Hard Complete is the practical stretch target; and a later,
time-separated LiveCodeBench slice is the freshness audit. Autoresearch uses frozen
local proxy tasks. Public prompts/solutions stay out of training; HumanEval+ is the
deliberate, disclosed exception for iterative diagnostic optimization. Future runs
predeclare <=9M learned parameters, raw-controller/full-system/deterministic-null
scores, search/test-time budget, and separate latency fields. No public benchmark
was run or published in this integration.
