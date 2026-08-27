# Search is useful; the state result is synthetic and the two-parameter gates are routing controls, not semantic inference

Experiment 13 found a useful but limited architectural crack: on generated,
synthetic repair tasks, a 50,378-parameter sketch policy plus typed legality and
public-example search reached 89.6% hidden functional pass versus 52.1% for the
same policy decoded greedily, while the deterministic null reached the same
89.6%. The learned sketch did not add correctness, and its end-to-end causal
dependence was 0%. The state-only result is a candidate mechanism that is
causally load-bearing in a synthetic control; the two-parameter predicate gates
are supplied-bit identity/routing tasks, not semantic inference. Nothing here
establishes general Python coding or parameter-level interpretability.

## Overnight record correction

The historical JSONL, dashboards, and checkpoint prose are retained. This
section corrects how they may be interpreted; it does not manufacture
replacement confirmation results.

- The two-parameter predicate gate receives a predicate truth bit computed by a
  fixed parser/executor and routes it through a fixed true-action/false-action
  multiplexer. Its perfect scores demonstrate supplied-bit routing on a small
  generated task, not semantic parsing or inference.
- The `semantic_rule_gate` and `repository_bundle_gate` nuisance-placebo
  controls are tautological: nuisance is not in the gate's computation, so
  preservation is guaranteed by construction. Their reported causal rates are
  retained as historical measurements but are invalid for causal promotion.
- Historical `latency_ms` values start after model inference and include
  evaluation work in the old loop. They are post-inference timings, not
  end-to-end latency. New runs of `run.py` emit explicit inference, selection,
  hidden-scoring, and end-to-end-through-selection fields.
- Raw learned output, typed/full-system output, symbolic control, and the
  deterministic null are separate quantities. A verifier can improve the
  selected program while hiding a weak raw controller; the deterministic null
  is the correctness baseline for that system boundary.
- Every task family here is synthetic or generated, including the Python and
  repository-shaped surfaces. The actual Raly compiler/runtime is not in the
  execution path, so this is Raly-style or Raly-inspired research, not
  Raly-based execution.

## Recurrent typed-state branch

The preregistered recurrent branch was rerun after correcting its public
verifier to use the same restricted-Python parse/compile/execute path as the
hidden scorer. It uses 53,418 learned parameters, a GRU request encoder, a
GRUCell transition conditioned on typed state, and a width-4 beam with a
120-expansion budget. Training uses six two-operation templates; evaluation
uses the fixed four-operation compositions `take_filter_sort_unique` and
`reverse_filter_take_unique`, with 48 held-out tasks shared across seeds.

| direction | hidden pass | compile | raw pass | search expansions | latency | learned params |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| state-raw | 27.1% ± 15.8 | 100% | 27.1% ± 15.8 | 0 | 3.2 ms | 53,418 |
| state-typed-greedy | 27.1% ± 15.8 | 100% | 27.1% ± 15.8 | 0 | 5.3 ms | 53,418 |
| state-typed-beam | 45.8% ± 1.7 | 79.2% | 27.1% ± 15.8 | 52.0 | 12.6 ms | 53,418 |
| state-null | 4.2% | 29.2% | 100%* | 90.5 | 1.8 ms | 0 |

The learned beam therefore beats the target-independent null on this harder
synthetic composition family, while the raw learned model remains much less
reliable. However, the result is still exploratory: the beam's compile rate is
only 79.2%. The original greedy audit had 0% relevant change and 100% placebo
preservation. The post-hoc full-system beam audit changed 1 of 144 selected
programs across the three seeds (0.7% relevant change), preserved the placebo
in all 144 cases, and therefore had a 0.7% conjunction rate. This is an
effective causal null at the present sample size. The controller is using
learned ordering and broad search, but the exposed typed state is not yet
load-bearing.

The recurrent result is a capability lead over the null, not a general Python
coding result. Its task family is deliberately small and synthetic, and the
full-system score includes typed legality, public-example verification, and
beam search. The raw learned-model score is reported separately above.

* As in the earlier table, the null raw-pass field is a comparator artifact,
  not a learned-model score.

## State-gated margin branch

The next cheap intervention added a 1,098-parameter state-to-action gate and a
counterfactual training margin requiring the correct typed state to outrank an
erased-type state on applicable teacher-forced steps. It stayed far below the
9M gate at 54,516 learned parameters.

| direction | hidden pass | compile | raw pass | search expansions | latency | learned params |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| state-gated-raw | 41.7% | 100% | 41.7% | 0 | 3.4 ms | 54,516 |
| state-gated-greedy | 43.1% | 100% | 41.7% | 0 | 6.0 ms | 54,516 |
| state-gated-beam | 45.1% | 73.6% | 41.7% | 50.4 | 13.8 ms | 54,516 |

The gate improved raw generation relative to the ungated recurrent controller
(27.1% mean raw pass), and the smoke showed the intended state sensitivity.
The frozen three-seed beam confirmation did not preserve the prior operating
point, however: 45.1% versus 45.8% hidden pass, lower compile rate, and only
3/144 relevant beam changes (2.1%) with 100% placebo preservation. It is
therefore rejected as a promoted operating point, while retaining the clue
that explicit state pressure can help the raw policy even when broad search
still dominates the final system.

## State-dependent one-gap repair

The fresh-task repair branch changes the unit of work: instead of emitting a
whole program, the controller ranks one missing operation in a corrupted
executable sketch. The corruption gap is frozen and target-independent at
evaluation time; public examples select candidates and hidden execution is
reserved for scoring. The policy has 25,614 learned parameters.

| direction | hidden pass | compile | raw pass | repair expansions | latency | learned params |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| repair-raw | 44.4% | 100% | 44.4% | 0 | 1.5 ms | 25,614 |
| repair-typed | 47.2% | 100% | 44.4% | 1.0 | 2.6 ms | 25,614 |
| repair-public | 97.2% | 100% | 44.4% | 1.92 | 3.0 ms | 25,614 |
| repair-null | 93.8% | 100% | 27.1%* | 2.73 | 0.6 ms | 0 |

This is the strongest efficiency lead so far: public-verified learned repair
beats the deterministic null by 3.5 percentage points while trying fewer
candidates. It remains a synthetic restricted-Python result, and the raw
learned repair is not competitive by itself. The state intervention changed
5/144 public-selected final repairs (3.5%), preserved the placebo in 144/144,
and therefore missed the preregistered 10% causal threshold. The learned
repair ranker is useful, but the typed state is still not demonstrated as a
load-bearing reasoning variable.

* The null raw-pass field is the fixed first candidate, not a learned-model
  score; its public-verified full-system result is the relevant comparison.

## Abstract value state and the state-only bottleneck

The second fresh family deliberately hides the missing operation from the
request and exposes only a compact public-runtime summary. The
text-conditioned model and the public-search null both reached 100% on the
three-seed held-out draw, so the text-conditioned result alone is not
informative. Removing the text pathway creates a sharper test:

| direction | hidden pass | compile | raw pass | expansions | latency | learned params |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| value-state-only | 100% | 100% | 100% | 0 | 1.0 ms | 1,058 |
| value-state-only-public | 100% | 100% | 100% | 1.0 | 1.6 ms | 1,058 |
| value-null | 100% | 100% | 56.3%* | 1.46 | 0.5 ms | 0 |

With no request-text route, erasing the abstract value facts changed 22/48
raw decisions for every seed (45.8% relevant change), while the unused-noise
placebo preserved 144/144 raw decisions. This is the first direct evidence
that a tiny declared state bottleneck can be causally load-bearing. The
public-verified final program remained unchanged under ablation because the
verifier repaired the alternate candidate; raw and full-system causality must
therefore remain separate metrics.

This is not yet an effective coding system: the state summary is deliberately
matched to a tiny synthetic rule, and the deterministic null reaches the same
full-system accuracy. The result is a candidate architectural primitive—a
small state-only controller over executable abstract facts—not a promotion to
general Python coding.

* The null raw-pass field is its fixed first candidate, not a learned-model
  score.

## Executable-Python state-only port

The state-only controller was then moved across the actual restricted Python
surface. Each candidate was rendered as a Python function, parsed with
`ast.parse`, compiled, executed on public inputs, and finally run on hidden
inputs. Two prefix families (`filter_then_normalize` and
`reverse_then_normalize`) were used, with the selected operation still hidden
from the request.

| direction | hidden pass | Python compile | raw pass | expansions | latency | learned params |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| py-state-only | 100% | 100% | 100% | 0 | 0.9 ms | 1,058 |
| py-state-only-public | 100% | 100% | 100% | 1.0 | 1.3 ms | 1,058 |
| py-state-null | 100% | 100% | 60.4%* | 1.5 | 0.7 ms | 0 |

Across all three seeds, erasing the abstract runtime facts changed 72/144 raw
decisions (50.0%) and the unused-noise placebo preserved 144/144 decisions.
The result survives the Python execution boundary and demonstrates a tiny,
causally legible state-only controller. Public verification again masks the
effect at final-program level, so the raw and full-system rows are not merged.
This remains a generated microtask benchmark, not repository-level Python
coding or a public benchmark claim.

* The null raw-pass field is its fixed first candidate, not a learned-model
  score.

## What was built

The system emits a short operation sketch over a small typed IR. The compiler
owns legality: list transforms cannot run on integers, reductions produce
Int, and a return must match the requested result type. The full system uses
bounded beam search and verifies candidates against two public examples, then
executes the selected program on a hidden input. The hidden expected value is
never passed to the model, verifier, search scorer, or null ordering.

The three logged directions are:

- raw-controller: greedy learned sketch, no type mask or search.
- typed-greedy: same sketch with type masks but no public-example search.
- typed-local-repair: public-example repair restricted to edit distance two from
  the raw sketch.
- typed-sketch: same weights, typed legality plus public-example search.
- deterministic-null: no learned model, target-independent typed enumeration.

The dashboard is local-only and live-refreshes from research_log.jsonl:
experiments/13_autoresearch_raly_coder/dashboard.html, served by
dashboard_server.py on loopback.

## Corrected smoke result

Fixed protocol: six training compositions, two held-out compositions
(sort_unique_count and reverse_filter_sum), 48 held-out tasks, three
independent training seeds (11, 23, 37), 181 updates, beam 24, search budget
400. The evaluation task draw is fixed across seeds.

| direction | hidden pass | compile | raw pass | search expansions | latency | learned params |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| raw-controller | 52.1% | 100% | 52.1% | 0 | 0.016 ms | 50,378 |
| typed-greedy | 52.1% | 100% | 52.1% | 0 | 0.026 ms | 50,378 |
| typed-sketch | 89.6% | 100% | 52.1% | 76.6 | 0.063 ms | 50,378 |
| deterministic-null | 89.6% | 100% | 100%* | 114.5 | 0.1 ms | 0 |

The three seeds gave the same task-level rates because the learned controller
converged to the same held-out sketch policy on this small benchmark. Peak
model VRAM was 0.024 GB as reported by PyTorch allocator statistics; this
excludes the desktop's pre-existing allocation. All learned-model rows are
well below the 9M gate.

* The null's raw_pass column is not a learned-model measure: it records the
known typed enumerator candidate used as its raw comparator. The null's actual
role is the full-system baseline, and its 89.6% hidden pass is the comparison
that matters.

## Causal legibility

The intervention first swaps the logits for a request-dependent non-commuting
operation pair, then separately perturbs only EOS by 0.0001. The learned raw
sketch changed in 0%, 100%, and 50% of typed trials for seeds 11, 23, and 37.
The compiler/search-selected verified program changed in 0% for all seeds,
while the irrelevant perturbation preserved it in 100% of trials.

The cheap typed-greedy falsification arm also stayed at 52.1%, so type masks
alone did not recover the held-out composition. The 89.6% result requires the
broader verifier/search step.

The local-repair branch made the causal requirement pass but failed capability:
all three seeds reached 50.0% hidden pass and 50.0% compile rate, with 100.0%
relevant-intervention change and 100.0% irrelevant preservation. It is rejected
as the current operating point, but it isolates a promising design knob:
causal load-bearingness and broad repair are in tension here.

## Python executable-surface replication

The same fixed three-seed protocol was lowered to restricted generated Python
and validated with ast.parse, compile, and execution. Python typed search reached
89.6% hidden pass and 100% compile with 76.6 mean expansions; Python raw
generation reached 52.1% pass; the Python deterministic null reached 89.6% with
114.5 expansions. The result therefore survives the language boundary but not
the null comparison: it is a search-efficiency result, not a competitive Python
coding benchmark result.

That is a clean negative result for the stronger claim. The intermediate
sketch is readable and sometimes causally affects the pre-repair proposal, but
the verifier repairs around it. The full system therefore depends on typed
search and public examples, not on the learned sketch as a load-bearing
reasoning state. This is not parameter-level understanding.

## Larger executable-Python repair suite

To test whether the state-only result was an artifact of the 48-task pilot, I
added a frozen, independently generated suite with 512 training tasks and 256
held-out tasks, three public cases per task, four hidden cases per task, and
three prefix families. Every candidate is lowered through `ast.parse`,
`compile`, and execution. Public cases were constructed to distinguish all
four candidate repairs; hidden cases were never shown to selection. The
controller receives only 19 typed/abstract state features and has 1,732
learned parameters.

Across seeds 11, 23, and 37, the confirmation was identical:

| direction | raw task pass | raw hidden tests | full task pass | compile | mean expansions | latency | causal state change / placebo preserve |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| suite-state-only | 100% | 100% | 100% | 100% | 0 | 1.46 ms | 39.1% / 100% |
| suite-state-only-public | 100% | 100% | 100% | 100% | 1.0 | 2.90 ms | 0% / 100% |
| suite-null | 42.2% | 48.1% | 100% | 100% | 1.73 | 1.18 ms | n/a |

The raw result is a meaningful causal-state checkpoint: erasing the eight
abstract value facts changes the selected repair on 39.1% of held-out tasks,
while toggling an unrelated noise bit preserves it on 100%. The public
verifier is unnecessary for this controller on this suite and adds latency;
the deterministic null still reaches the same full accuracy, so the learned
state is not needed for correctness. The result is therefore a strong,
inspectable primitive for state-conditioned repair, not evidence of general
repository-level Python coding. The construction also makes the current
limitation explicit: the label is a small deterministic function of the
exposed abstract state, so the controller demonstrates causal use of a typed
state interface rather than discovering arbitrary program semantics.

## Text/state recombination falsification

The larger-suite state-only win still allowed a direct exposed-state-to-label
shortcut. A new recombination family made the target depend on two independent
factors: an intent token in the request and the executable prefix state. The
state-only and text-only controls each lack one factor; the hybrid receives
both. All candidates still crossed the restricted Python parse/compile/exec
boundary, with 512 training and 256 held-out tasks.

The first mean-pooled text representation failed: the hybrid reached only
30.9--39.5% raw task pass across seeds. A bounded correction reserved the
second token position for the intent and used that embedding directly. The
three-seed confirmation then produced:

| direction | raw task pass | raw hidden tests | full task pass | compile | mean expansions | params |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| state-only | 25.4% | 32.1% | 25.4% | 100% | 0 | 1,636 |
| text-only | 34.4% | 38.8% | 34.4% | 100% | 0 | 1,156 |
| hybrid | 77.3% | 77.9% | 77.3% | 100% | 0 | 2,148 |
| hybrid + public verifier | 77.3% | 77.9% | 100% | 100% | 1.22 | 2,148 |
| deterministic null | 21.9% | 28.6% | 100% | 100% | 2.62 | 0 |

The hybrid beats both one-factor controls by more than 40 percentage points in
raw task pass and remains far below the 9M gate. This supports a compact
multimodal controller over intent plus executable state. It does not pass the
causal promotion gate: relevant state intervention averaged 19.8%, placebo
preservation averaged 91.4%, and the causal conjunction averaged 15.0%
(per-seed hybrid causal rates were 16.4%, 12.5%, and 16.0%). The model uses
both channels for useful prediction, but the current representation is not
causally legible enough to claim that the exposed state is reliably
load-bearing. Public verification again masks raw errors and reaches 100%,
matching the null.

## Explicit cross-product controller

The next architectural crack was to replace the generic hybrid head with an
explicit cross-product: the intent embedding is separated from a 16-dimensional
state encoding, and their outer product is the only input to the repair head.
This keeps the interaction inspectable while allowing multiplicative use of
independent factors. Across the same three seeds and 256 held-out tasks, the
cross controller reached 100% raw task pass and 100% raw hidden-test pass,
100% compile, zero search expansions, 9,348 learned parameters, and 2.56 ms
mean latency. The public-verifier arm also reached 100% with 1.0 mean
expansion and 3.67 ms latency.

The causal audit passed the synthetic promotion gate: relevant state erasure
changed 38.3%, 34.0%, and 34.0% of selected repairs for seeds 11, 23, and 37
(35.4% mean), while the irrelevant noise placebo preserved the baseline in
100% of all three seeds. This is the strongest Raly-style primitive so far:
small, inspectable, and causally state-dependent. It is still only a generated
Python repair proxy; the next test must use independently specified
natural-language/code-repair tasks or repository-local tests before any claim
of competitive coding ability.

## Held-out factor-combination stress test

The cross-product controller was then trained with every task containing the
factor pair `intent=delta` and negative prefix state removed. Evaluation used
256 fixed held-out tasks containing only that pair, with the same three public
and four hidden executable-Python tests per task. The deterministic null still
reached 100% after public verification, but all learned directions failed the
raw composition test across seeds: state-only task pass was 0%, generic hybrid
task pass was 0%, and explicit cross-product task pass was 0%; each learned
model reached only 2.1% hidden-test pass. The cross model's training loss still
fell below 0.01, so this is not an under-training diagnosis.

This is an important boundary result. The explicit interaction tensor is
causally legible and solves seen combinations, but it memorizes the observed
factor table rather than composing an unseen intent/state pair. The correct
next architectural move is to impose a shared symbolic or arithmetic factor
rule, or to train on a task family where the semantic relation is specified
independently of the label generator. No general coding claim is warranted.

The held-out-combination run is therefore a discard for capability promotion,
but a keep for diagnosis: the cross-product architecture changes the problem
from generic sequence modeling to factorized state/action control, yet its
learned factors are not compositional by default.

An even smaller additive controller was tested as the obvious shared-rule
alternative: four-dimensional intent logits plus four-dimensional state logits,
with no interaction table and only 248 learned parameters. It also reached 0%
task pass on the held-out factor pair across all seeds, with 6.5% mean hidden
test pass. Its training loss remained around 1.34--1.42, so this follow-up is
consistent with a representational mismatch rather than a successful rule
induction. The current evidence favors explicit symbolic factorization or
supervised state slots over another generic neural head.

The cyclic-factor follow-up encoded intent and state as additive phases on a
four-cycle and decoded by fixed class angles, using only 62 learned parameters.
It showed the desired behavior for one seed (100% held-out task pass, 100%
placebo preservation, 33.6% relevant intervention), but seeds 11 and 23 had
0% task pass and 11.3% and 2.1% hidden-test pass. The three-seed mean was only
33.3% task pass and 37.8% hidden-test pass. This is a causal and highly
inspectable mechanism, but not a stable composition solver; phase optimization
is currently too seed-sensitive to promote.

## Natural-language conditional repair proxy

The first move toward coding-like tasks replaced the arbitrary factor label
with a semantic rule: the request states, in ordinary prose, what to do when
the inspected list has duplicates, contains a negative value, or is long, and
what to do otherwise. The correct repair is determined by that rule and the
executed prefix state. Action names are described in prose rather than exposed
as candidate labels. The restricted Python boundary, three public tests, four
hidden tests, 512 training tasks, 256 held-out tasks, and three seeds were
unchanged in scale.

The raw confirmation averaged 24.3% task pass for state-only, 50.4% for
text-only, 48.7% for the generic hybrid, and 50.1% for the cross-product
controller. Every learned direction compiled at 100%; public verification
lifted the hybrid and cross directions to 100% full-system task pass, matching
the deterministic null. The hybrid's state intervention averaged 21.0% with
91.4% placebo preservation; the cross controller changed only 6.5% of repairs
under relevant intervention. Neither passes the causal promotion gate, and
neither shows a raw gain over the text-only language control.

This is the clearest current transfer boundary: the controllers can exploit a
structured intent token and typed state, but they do not robustly parse a
natural-language conditional and bind it to runtime state. The next route is a
small inspectable semantic parser or typed rule compiler whose output is then
controlled by the learned state policy. This remains a synthetic Python proxy,
not an external coding benchmark.

## Typed semantic parser/controller audit

The parser/controller split was preregistered as a direct test of that next
route. The parser correctly recovered one predicate and the two prose action
descriptions on every held-out task. Its deterministic rule executor reached
100% held-out task pass and 100% compile on all three seeds. The learned
1,508-parameter controller, however, averaged only 51.3% raw held-out task
pass across seeds (55.1%, 46.1%, and 52.7%), despite 100% compile. The public
verifier lifted every learned run to 100% full-system pass, but that is not a
raw learned-model win; it averaged 1.49 candidate expansions and 2.75 ms
latency compared with 1.54 ms for the raw controller.

The causal audit also failed the promotion gate: relevant state erasure
changed 13.7% of learned decisions on average, while the irrelevant-noise
placebo preserved 79.8%. The failure has a concrete interface diagnosis, not
an ambiguous optimization explanation. The generic typed runtime vector
contains a negative-value bit, but it does not expose the semantic predicates
`duplicates` or `long`; therefore a parsed rule can be perfectly recovered
while the learned controller lacks the typed facts needed to evaluate two of
the three allowed conditions. The next experiment will expose predicate
truths as explicit typed state slots and test whether this fixes raw accuracy
and causal dependence without adding a larger sequence model.

## Learned predicate gate with fixed rule multiplexer

The explicit-slot MLP was still spending its capacity learning the conditional
multiplexer that the parser had already specified. The next ablation therefore
learned only a shared scalar predicate gate and used a fixed typed rule
multiplexer to select the parsed true-action or false-action. This has just two
learned parameters; the nuisance noise bit is absent from the computation and
the predicate erasure intervention is applied before the gate.

Across all three seeds, the learned gate reached 100% raw held-out task pass,
100% hidden-test pass, and 100% compile, matching the zero-parameter symbolic
rule. It used no search expansions and averaged 1.62 ms latency. The public
verifier also reached 100%, with one expansion and 2.60 ms latency. Erasing the
typed predicate changed 56.6% of learned decisions on every seed, while the
nuisance-noise placebo preserved 100%; the causal conjunction therefore also
averaged 56.6%. This is a supplied-bit identity/routing control, not semantic
inference. The fixed multiplexer and absent nuisance input make its placebo
preservation tautological, so the reported causal rate is historical and
invalid for causal promotion. It remains a tiny typed-rule primitive, not
evidence of general coding ability.

## Held-out request paraphrase audit

The two-parameter gate was then trained on canonical requests and evaluated on
the same executable tasks after replacing every predicate and action phrase
with a preregistered held-out paraphrase. The alias parser recovered the typed
rule, and the learned gate reached 100% raw task pass, 100% hidden-test pass,
and 100% compile on all three seeds. It retained 50.0% relevant predicate
erasure change and 100% placebo preservation, with 2.27 ms raw latency and no
search expansions. Public verification again remained perfect but added one
expansion and 2.94 ms latency.

This supports only a narrow decomposition: a fixed inspectable lexicon can
absorb the authored paraphrase variation while a supplied predicate bit is
routed to the matching action. It does not test open-ended language
understanding; the paraphrase inventory was authored in advance and the state
predicate remains explicitly supplied. The next capability test must therefore
move the typed rule boundary closer to ordinary Python code rather than adding
more synthetic aliases.

## Ordinary Python source-repair boundary

The typed gate was next evaluated on a fresh task family whose candidates are
actual lines inserted into a Python function containing a `# REPAIR` hole. Each
candidate was independently passed through `ast.parse`, `compile`, and
execution; public examples selected verifier candidates and hidden examples
scored the final function. A generator audit found and fixed three classes of
candidate collision before the confirmation; the repaired generator produced
1,000 collision-free, predicate-consistent tasks.

On the preregistered 512-train/256-held-out, three-seed run, the learned
two-parameter gate reached 100% raw task pass, 100% hidden-test pass, and 100%
syntax/compile. It averaged 1.91 ms with no search expansions. Predicate
erasure changed 52.0% of decisions and the placebo preserved 100%; the public
verifier remained perfect at one expansion and 2.67 ms. The zero-parameter
symbolic control also reached 100%, so this is not a learned-capability lead,
but it is evidence that the tiny causal typed-rule primitive survives the
transition from restricted operation tokens to executable Python source edits.
The surface is still generated and single-hole; repository-level generality
has not been established.

## Executable-prefix state observation

The source-repair gate was stressed with four executable prefixes before the
repair hole: identity, sorting, absolute-value normalization, and zero
filtering. The predicate was computed from the prefix's actual Python return
value, not from the task metadata. A 1,000-task generator audit passed after
restricting one collision-prone sorted-prefix condition to duplicate-bearing
states.

On the frozen three-seed confirmation, the two-parameter learned gate reached
100% raw task pass, 100% hidden-test pass, and 100% syntax/compile across all
prefix families. It averaged 2.56 ms, no search expansions, 65.6% relevant
state-erasure change, and 100% nuisance preservation. The public verifier tied
on correctness at one expansion and 2.84 ms. This is a stronger executable-state
routing check than the identity-prefix result, while still not establishing
repository-level or open-ended coding performance.

## Two-hole ordinary Python composition

The next stress test placed two independent repair holes in the same Python
function and gave each hole its own prose conditional. The shared two-parameter
gate had to make two typed predicate decisions and compose them into one
executable source patch. A bounded 16-combination verifier searched public
examples; hidden examples remained scoring-only. One initial generator attempt
was discarded because some action pairs were not distinguishable on public
cases; after resampling action pairs, a 1,000-task audit found no ambiguity.

Across seeds 11, 23, and 37, the learned controller reached 100% raw task pass,
100% hidden-test pass, and 100% syntax/compile, averaging 3.99 ms with no
search. Pair-level predicate erasure changed 55.5% of decisions and the
placebo preserved 100%. The verifier also reached 100% full-system pass with
one mean expansion and 4.96 ms latency. This demonstrates stable composition
of two supplied-state routing decisions through the typed rule interface, but
it remains a generated two-hole family with fixed candidate operations, not a
repository coding benchmark.

## Multi-file repository-bundle boundary

The typed gate was then placed behind a repository-shaped module graph:
`__init__.py` imported `solve` from `api.py`, which imported the repaired
function from `transforms.py`. Each candidate changed only the transform
module, while every module was independently parsed and compiled before the
public API was imported and executed on hidden cases. The bundle ran in
isolated in-memory module namespaces to keep the loop local and reproducible.

Across the three preregistered seeds, the two-parameter learned gate reached
100% raw task pass, 100% hidden-test pass, and 100% syntax/compile. It averaged
3.95 ms with no public search; predicate erasure changed 47.3% of decisions and
the placebo preserved 100%. The verifier tied at 100% full-system pass with one
expansion and 4.34 ms. This shows that the fixed routing harness can cross a
file-backed import boundary, but it is still a generated single-hole package
and should not be reported as repository-level coding performance. The
predicate-placebo result is tautological because nuisance is absent from the
gate; it is invalid for causal promotion.

## Autoresearch correction

The first 10-update smoke used a null score that accidentally ranked candidates
using the generated target program. That log is preserved as
research_log_invalidated_null_oracle.jsonl and is excluded from the finding.
The corrected null uses a fixed action ordering independent of target and hidden
values. This correction was made before the corrected three-seed run.

The invalidated file is not part of any aggregate: the valid log has 386 rows
and the preserved oracle-contaminated file has 12 rows. The audit script checks
both counts and checks that the selection functions do not reference hidden
answers.

## Verdict and next action

Keep typed legality/search as a possible efficiency primitive, and retain the
larger-suite state-only controller as the strongest candidate for a mechanism
that is causally load-bearing in a synthetic control. Do not promote either as
a general Raly-style coding architecture: full-system accuracy is often matched
by the deterministic null, the predicate-gate placebos are tautological, and
all suites remain synthetic or generated repairs. The next move should break
the label/state shortcut with independently specified tasks whose executable
state is necessary but not sufficient, then test a richer Python surface or
repository-local repair setting without inspecting hidden answers.

## Limitations

- This is a synthetic integer-list DSL, not Python, repositories, tests, or
  natural-language coding.
- Public examples make verification possible; no claim is made that this
  transfers to hidden tests without such examples.
- The larger suite has three generated prefix families, but its repair label is
  deliberately a simple function of exposed abstract facts.
- The three-seed rates are identical here and do not establish robust
  uncertainty across task distributions.
- The compile metric measures restricted generated Python, not a full Raly
  compiler backend or general repository execution.
- The actual Raly compiler/runtime is not called by these Python harnesses; the
  relationship is Raly-style/Raly-inspired, not Raly-based.
- Historical latency values are post-inference evaluation timings. They are not
  end-to-end measurements, and no corrected timing rerun is claimed here.

## Reproduce

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/run.py --device cuda --updates 181 --train-count 96 --eval-count 48 --seeds 11,23,37

The script enforces the learned-parameter gate, writes raw and full-system
metrics separately, and on new runs writes explicit timing fields to
`research_log.jsonl`. For the record audit, run:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/measurement_audit.py --expected-valid 386
