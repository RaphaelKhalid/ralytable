# Readable is not reliable

## A falsification-first route toward AI reasoning that is harder to fake

**Raphael Khalid · Ralytable research brief · September 2026**

Ralytable began with a simple question: can a small model expose an internal
representation that a person can inspect without losing too much capability?

The first serious answer was negative. A 29.5M-parameter model forced through a
512-entry discrete bottleneck performed materially worse than a matched dense
control on held-out TinyStories text. In 179 blind pairwise comparisons, the
dense control was preferred 85.4% of the time (95% CI [79.5, 89.8]). The visible
failure was often identity drift: an object introduced as a kite became a
balloon, flag, drum, and trumpet within one completion.

That failure sharpened the research question. A representation is not useful
merely because a person can read it. The output must actually depend on the
declared representation, harmless surface changes must preserve meaning, and
unused fields must not provide a hidden route from prompt to answer.

The project therefore pivoted from **readable latent symbols** to a **typed,
causally audited program ledger**. This is an architecture hypothesis, not a
completed model result.

## The proposed contract

A compact learned parser would propose a typed graph of facts, bindings, and
operations. A deterministic legality layer would reject malformed graphs. A
small library of typed primitives would operate only on named ledger entries.
Execution would produce replayable receipts. If proof or verification fails,
the system would abstain.

The core requirement is causal:

1. Changing a relevant ledger entry should change every dependent output.
2. Changing irrelevant metadata should not change the output.
3. Removing the raw prompt after parsing should not preserve a hidden bypass.
4. Rendering should be a deterministic function of accepted ledger state and a
   disclosed execution trace.

This is closer to a compact semantic parser plus compiler than a miniature
general-purpose language model.

## Evidence selected from the research record

| Question | Credible null or failure control | Measured result | What it supports |
|---|---|---|---|
| Does a readable discrete bottleneck preserve capability? | Matched dense model | Dense preferred in 85.4% of 179 blind comparisons; discrete model also lost 0.63 cross-entropy and 9.9 accuracy points | Readability can impose a substantial capability cost |
| Can a displayed trace be decorative? | Raw-shortcut and decorative-trace renderers | Both scored 0% on the combined causal gate; a ledger-only synthetic control scored 100% across five seeds | The audit detects known bypasses; it does not prove a learned model is bypass-free |
| Can unused fields hide the answer? | Renderers routing through metadata, provenance, or confidence | Metadata shortcut scored 0% on the field-level gate; semantic renderer scored 100% | Every nominally unused field needs its own intervention |
| Can explicit identity survive repeated names? | Position sequence and flat name map | Scoped name map and scoped typed ledger passed 25/25 checks; flat controls failed original, reorder, and placebo checks | Lexical scope and binder identity are required; extra ledger fields still need justification |
| Does typed composition generalize beyond memorized programs? | Whole-program and untyped retrieval | Typed primitive composition solved 21/21 novel combinations; whole-program retrieval solved 0/21; untyped composition solved 10/21 | Systematic composition is possible in the bounded symbolic task |
| Does ordinary train/eval splitting leak meaning-equivalent examples? | Random example split | Random splits leaked 7.4 of 12 semantic families on average; grouped splits leaked 0 | Future learned results must split by semantic equivalence class |
| Is confidence safe under distribution shift? | Fixed and source-calibrated confidence thresholds | Source-calibrated risk rose from 0% to 100% under the handcrafted shift; the separate verifier gate emitted nothing | Confidence is not a guarantee; safe abstention may reduce coverage to zero |
| Does the design fit below 40M learned parameters? | Explicit component accounting with no opaque residual bypass | Balanced configuration totals 38,265,728 learned parameters | Arithmetic feasibility only—not capability |

## The strongest claim available today

The repository supports a methodology claim: **interpretability should be
tested as a security property rather than inferred from a readable trace.** The
project contains synthetic controls showing that state dependence, raw-path
invariance, unused-field invariance, scoped identity, capability closure,
replay, and contamination-aware evaluation can each expose a specific shortcut
or failure mode.

The repository does not yet establish that a trained typed-ledger model improves
coding capability, systematic generalization, or safety.

## What exists

- Raly, an experimental language front end with a lexer, parser, resolver, type
  checker, diagnostics, and a browser/WebAssembly playground.
- 198 compiler tests covering the checked-in compiler state described by the
  project handoff.
- Matched dense and discrete TinyStories models across three seeds, with blind
  human-readable samples and committed judge records.
- Dependency-free synthetic probes for causal bypasses, identity, effects,
  ownership, proof obligations, provenance, replay, verifier failure,
  contamination, and typed composition.
- An explicit 38,265,728-parameter architecture budget with zero allocated
  opaque residual bypass.

## What this does not establish

- No trained typed-ledger coder exists.
- No public coding benchmark result has been completed.
- The Raly compiler type-checks but does not yet generate or execute code.
- Synthetic audits validate the tests against known mutants; they cannot prove
  that a future learned system has no unknown bypass.
- The parameter budget is accounting, not a capability measurement.
- No Qwen or other 27B-model comparison has been run. Parity is unmeasured and
  not claimed.

## Next falsifiable step

Train the smallest parser that can map paraphrased requirements into ledger
graphs, and compare it with a matched flat structured-state baseline. Freeze
semantic-family splits before the full run. Evaluate exact graph and binding
recovery, held-out operation composition, identifier renaming, declaration
permutation, relevant-state interventions, unused-field interventions,
raw-prompt erasure, coverage, error rate, and abstention. Report all learned
parameters and all external retrieval, verifier, and search work separately.

Downgrade the architecture if the explicit ledger is not causally necessary or
if the matched flat baseline wins on the frozen suite.

## Reproduction

The recent architecture probes are dependency-free and write their summaries
beside the source files:

```text
python experiments/26_no_bypass_causal_audit/causal_audit.py
python experiments/27_ledger_field_steganography/field_audit.py
python experiments/37_scoped_binding_ledger/binding_probe.py
python experiments/54_calibration_shift_probe/calibration_probe.py
python experiments/59_equivalence_aware_split/split_probe.py
python experiments/60_typed_library_novel_composition/library_probe.py
python experiments/63_40m_architecture_budget/architecture_budget.py
```

The blind story comparison, committed generations, judge calls, controls, and
limitations are in `experiments/09_story_quality/`. Regenerating model outputs
requires the uncommitted checkpoints and dataset cache described in that
experiment's README; the committed analysis artifacts remain inspectable
without them.

The interactive public explanation is implemented in `site/index.html` and
mirrored to `web/index.html`. The full blind test is in
`site/blind-test.html`.
