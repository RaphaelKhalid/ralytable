# Preregistration: Raly Coder first coding experiment

Status: **draft until committed on its own reviewable change**. Do not run the
confirmatory comparison from an uncommitted plan.

Date written: 2026-08-27
Benchmark: `raly-coder-v1`, specified in
`docs/raly-coder-benchmark-2026-08-27.md`

## Question

Does a 9M-parameter model whose coding process is represented as typed,
executable Raly actions pass more private hidden tests than matched dense and
free-text-CoT models?

This is a coding capability and causal-legibility experiment. It does not test
general reasoning, broad software engineering, or public benchmark standing.

## Null and alternative hypotheses

For each planned comparison, the null is that the mean paired task-success
difference is zero: `Raly - matched control = 0`. The alternative is a
two-sided difference. A superiority claim is allowed only when the estimated
difference is positive and its 95% confidence interval excludes zero.

The practical target, written before the run, is at least **5 percentage points**
of hidden-test success over a matched control. This is a decision threshold,
not a substitute for the inferential test.

The causal null is that masking a declared relevant structured state changes
success no more than masking a matched irrelevant state. The alternative is a
larger relevant effect. The causal test is secondary to the capability
comparison but is required for a positive Raly interpretation.

## Models and controls

Three primary arms are trained from the same corpus and tokenizer, with the
same optimizer, update count, context limit, data order, parameter budget,
temperature, action budget, test timeout, and evaluator:

1. **Dense 9M:** ordinary decoder-only model; it emits the common action text
   protocol and has no declared intermediate state.
2. **Free-text-CoT 9M:** matched decoder-only model; it may emit ordinary
   scratch text before an action, but the common scaffold executes only valid
   actions and records the scratch text separately.
3. **Raly 9M:** matched model; it emits only the typed action schema and receives
   the deterministic typed state after each action.

The 28M Raly capacity control is not part of the first confirmatory family. It
is run only after the smoke gate passes, with the same data, prompts, and
evaluator, and is labelled a capacity comparison.

All arms use three independent seeds: **11, 23, and 37**. The same task order
and task IDs are used within a seed across arms. A fresh model is used for each
arm; adapters, checkpoints, prompts, tool outputs, retries, and temperatures
are not shared across arms.

Fixed inference settings: greedy decoding (`temperature=0`, no sampling), at
most 32 actions, at most three `run_tests` calls, and no automatic retry. An
invalid or truncated action consumes its turn and remains in the record. The
model cannot access network, hidden tests, oracle patches, Git metadata, or an
arbitrary shell command.

## Data and split

Training uses only the 1,152-task train split. The 192-task dev split may be used
once to validate that the pipeline runs and to select nothing after the first
locked model configuration. The 384-task private test split is used once for
the primary result. The 384-task private replication split remains sealed until
the first result and all analysis code are frozen.

No public leaderboard is used. LiveCodeBench, if run, is a separate local-only
diagnostic with identical settings and cannot replace the private endpoint.

## Primary endpoint

For each trial, `success = 1` iff all hidden tests pass in a fresh evaluator
process after the agent stops; otherwise `success = 0`. The primary effect is
the mean paired difference in success between Raly and each of the two matched
controls, with task as the within-seed unit and seed-level results reported
separately.

The symbolic oracle, no-op patch, and random-valid-action policies are sanity
baselines. The oracle is a reachable ceiling, not a model comparison. The
matched dense arm remains the principal capability baseline.

## Causal endpoints

For successful or attempted traces containing a structured read, the evaluator
records a declared state identity and its provenance. It then replays the same
deterministic controller with one intervention:

- **relevant:** mask the state that the oracle patch and dependency map mark as
  necessary for the requested behavior;
- **irrelevant:** mask a same-kind read state outside that dependency map;
- **placebo:** apply the intervention machinery to a state not consumed by the
  final patch path;
- **residual-off:** disable any declared continuous residual while preserving
  the structured state.

The causal effect is baseline success minus counterfactual success. The planned
selectivity contrast is relevant effect minus irrelevant effect. A positive
interpretation requires a positive capability result and a positive selectivity
contrast with a 95% interval excluding zero. The 3:1 relevant/irrelevant ratio
is a descriptive gate and is not tested as a ratio because ratios are unstable
near zero.

## Secondary endpoints

Report, without silently excluding failures: success by task family and chain
depth, visible-test success, patch validity, invalid-action rate, truncation
rate, number of actions, test invocations, time to first useful read,
`inspect_failure` usage, failure categories, raw trace length, peak memory,
wall-clock time, and model parameter count. Report constrained and
unconstrained generations separately if either exists.

## Analysis plan

- Alpha is **0.05**, two-sided for the two primary Raly comparisons.
- Apply Holm correction across `Raly-vs-dense` and `Raly-vs-free-text-CoT`.
- Compute task-level paired differences before aggregation; do not pool raw
  successes as if they were independent model runs.
- Report mean effects, per-seed effects, and 95% confidence intervals from a
  fixed-seed, repository-cluster bootstrap with 10,000 resamples. The repository
  is the cluster because its 24 tasks share generated code and bug structure.
- Use a paired randomization test that swaps arm labels within task and seed for
  the primary p-values. The exact randomization seed and number of draws are
  fixed in the analysis script before opening private test outputs.
- Preserve every trial row, including malformed, invalid, truncated, timed-out,
  excluded, and infrastructure-failed rows. Infrastructure exclusions require
  a recorded reason and are reported by arm and seed.
- Do not tune prompts, action budgets, retries, temperatures, model size, or
  exclusions after inspecting private test outcomes. Any plan change creates a
  new preregistration and labels the resulting run exploratory.

## Smoke gate and stopping rule

The one-minute smoke is a pipeline check only. It must demonstrate deterministic
task generation, action validation, safe file boundaries, patch preconditions,
test execution, failure inspection, trace persistence, and a relevant-versus-
irrelevant intervention difference. It cannot tune the confirmatory analysis.

Do not start the primary run unless the smoke passes and this plan is committed.
Stop the first run for an infrastructure reason if checkpoints cannot resume,
the evaluator is nondeterministic on the oracle, hidden-test isolation fails,
or the action trace is not durably recorded. Do not stop for a disappointing
model result. The predeclared kill rule for this variant is: if Raly is more
than five points below dense on in-distribution dev success and shows no
held-out improvement, do not add the 28M control; debug or reject the variant.

## Reproduction and privacy

The benchmark generator, action schema, sandbox, smoke, and analysis code are
local repository artifacts. Private task bundles, hidden tests, oracle patches,
model outputs, checkpoints, and benchmark scores stay in ignored local storage.
No API key, model output, or result may be committed. No benchmark result may be
submitted to a public leaderboard. Paid external services require explicit
approval and are not part of this preregistration.

