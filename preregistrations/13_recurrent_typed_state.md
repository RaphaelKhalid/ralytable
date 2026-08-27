# Preregistration — recurrent typed-state controller

Status: exploratory preregistration written before the state-policy smoke.
This is a new branch after Experiment 13 found that position-wise sketches
were repaired around by broad search.

## Question

Does conditioning a small recurrent controller on the current typed executable
state improve held-out composition of non-commuting operations while making the
state causally load-bearing?

## Null and alternative

Null: a target-independent typed beam enumerator at 120 expansions is at least
as accurate as the learned state controller. Any apparent gain from the model
is search ordering only.

Alternative: the recurrent typed-state controller improves hidden functional
pass rate or search efficiency, and erasing the typed state changes its
selected action while an unused noise feature does not.

## Frozen protocol

The benchmark uses integer-list programs lowered to restricted Python. Training
templates are the six two-operation compositions in state_policy.py.
Evaluation uses the fixed held-out four-operation compositions
take_filter_sort_unique and reverse_filter_take_unique, one public example per
task, and a separate hidden input. The evaluation RNG is fixed at 130000 and is
shared across seeds 11, 23, and 37. The controller never sees the hidden input
or expected output. The null ordering is independent of target_program and
hidden values.

The primary endpoint is hidden functional pass rate. Secondary endpoints are
Python compile rate, raw greedy pass rate, mean beam expansions, latency, peak
VRAM, learned parameter count, and state-intervention rates. Beam width is 4;
the search budget is 120 expansions. The learned-parameter gate is 9 million.

## Causal test

At the second controller transition, erase the typed current-type bits and
compare the greedy typed action sequence with the unmodified sequence. In a
separate placebo, set only a reserved unused noise feature to one. The planned
state-causal indicator is relevant-change AND irrelevant-preservation. This is
causal dependence on the exposed state representation, not parameter-level
understanding.

## Kill and promotion criteria

Kill the branch if the typed-state controller cannot run, violates the
parameter gate, or shows no relevant-vs-placebo separation after three seeds.
Keep it exploratory if the deterministic null matches its pass rate. Do not
promote without a fresh task draw, a second task family, and a confirmatory
multiple-comparison plan.
