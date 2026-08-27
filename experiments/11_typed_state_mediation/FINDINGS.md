# Smoke findings

The corrected typed-state controller passes the smoke-learning gate: both the transcript and hard-mediated arms solve 15 of 16 hidden tasks, while the executor and intervention controls pass all 16 oracle tasks.

This is an exploratory plumbing result, not evidence that typed mediation improves language-model capability. The run used 100 updates on 16 evaluation tasks, a cached Qwen2.5-0.5B-Instruct model, parameter-efficient fine-tuning, and constrained decoding. No confirmatory alpha or superiority claim applies to this smoke test.

## What failed first

The first mediated run solved 0/16 tasks. The controller repeatedly emitted `input values -> s0`. The initial state already contained `s0`, `input` did not change the state, and the action generator still offered `input` as a legal candidate. Therefore the mediated prompt was effectively identical after every step. This was an environment/state-machine bug, not evidence against hard mediation.

## Fix

The state now starts with an explicit input buffer. `input values -> s0` consumes that buffer into a typed `List[Int]` slot, and the action is no longer legal after consumption. The transition is visible in the serialized state and is owned by the deterministic interpreter.

## Results

| Arm | Hidden-task pass | Constrained parse rate | Loss | Peak GPU |
| --- | ---: | ---: | ---: | ---: |
| Transcript | 15/16 | 100% | 4.968 → 0.00014 | 2.12 GB |
| Hard mediated | 15/16 | 100% | 6.567 → 0.00023 | 2.12 GB |

Both adapters round-trip successfully. The deterministic executor passes 16/16 oracle tasks, and the relevant, irrelevant, and type-erasure intervention checks behave as expected.

The 100% parse figure is conditional on constrained decoding. It means the decoder selected one legal operation, not that an unconstrained model would naturally produce valid Raly syntax.

## Limitations and next test

- The two arms were trained and evaluated on the same small generated task family, so this is not a general coding or reasoning result.
- There are only 16 hidden tasks and one seed.
- The controller can exploit a narrow operation vocabulary and repeated task template.
- The state representation is still a toy list state, not a repository or coding environment.
- No claim has been made about causal interpretability of the model's internal weights.

Before scaling up, run the preregistered comparison with fresh tasks, held-out templates, multiple seeds, unconstrained-output logging, and the planned oracle, type-erasure, and placebo controls.

## Held-out-template smoke

The held-out smoke finds a generalization failure in the current controller: hard mediation averages 6.25% constrained hidden-task accuracy versus 60.42% for the transcript controller across three seeds.

Training used three templates and evaluation used the unseen `sort_unique_count`
template. The constrained decoder made syntax legal in every case, but that was
not enough. Mediated traces commonly sorted and filtered correctly, then either
returned a list instead of counting it, counted the wrong slot, or stopped before
the count operation. The state type system knows that lists and integers differ,
but the task contract does not currently restrict `return` to the requested
output type.

Unconstrained pass rate was 0/48 for both arms. This is reported separately from
the constrained result because raw generations frequently contained executor
errors. The loss fell in every arm, so loss reduction is not being used as a
capability proxy.

This result does not show that hard mediation is intrinsically worse. It shows
that the present state representation and action policy do not generalize to a
new operation order. The next smoke should preregister an output-type constraint
ablation: give both arms the same declared result type, allow `return` only for a
slot of that type, and compare against the current unconstrained-return control.

## Result-type ablation smoke

The result-type constraint did not produce a reliable improvement in this smoke: it changed which answers were legal, but did not improve total held-out accuracy.

| Controller | Typed return | Untyped return | Difference |
| --- | ---: | ---: | ---: |
| Transcript | 23/48 (47.9%) | 21/48 (43.8%) | +2 tasks |
| Hard mediated | 4/48 (8.3%) | 6/48 (12.5%) | -2 tasks |
| Combined | 27/96 (28.1%) | 27/96 (28.1%) | 0 tasks |

The per-seed transcript differences were +3, +1, and -2 tasks. The mediated
differences were 0, 0, and -2. This is too small and variable for an inferential
claim, and the preregistered alpha is not applied to this smoke.

The compiler constraint did prevent wrong-type returns without introducing
executor errors, but the model still chose the wrong operation sequence or wrong
source slot. That separates two benefits: type safety is working as an
intervention, while planning generalization remains unsolved.

Raw unconstrained pass rate was 0/96 for both controllers. The current system
therefore depends heavily on constrained decoding, which should be treated as a
core part of the architecture rather than hidden in the parse metric.
