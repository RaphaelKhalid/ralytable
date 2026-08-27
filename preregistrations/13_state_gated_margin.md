# Preregistration — state-gated controller with counterfactual margin

Status: written before implementation and smoke testing.

## Hypothesis

The recurrent controller currently receives typed state but can ignore it
because the request text already specifies the operation order. Add a small
explicit state-to-action gate and train it with a counterfactual margin: on
steps where the typed state differs from an erased-type state, the correct
state must assign the target action a higher logit. This should make the
exposed state causally load-bearing without materially increasing the model.

## Frozen comparison

Use the existing recurrent typed-state benchmark, data seeds (11, 23, 37),
48 held-out tasks, restricted-Python verifier, beam width 4, and 120-expansion
budget. Compare `state-gated-raw`, `state-gated-greedy`, and
`state-gated-beam` to the already recorded `state-*` rows. No hidden values or
answers enter training, ranking, or public verification.

## Promotion and kill criteria

The learned parameter count must remain below 9M. The branch is retained as an
exploratory lead only if the beam improves or preserves held-out pass and its
state-relevant intervention rate rises above the prior 0.7% beam audit while
the placebo remains above 95%. Otherwise retain the result as a negative
state-use experiment and do not promote it.

Report raw pass, full-system pass, Python compile rate, search expansions,
latency, VRAM, parameter count, and greedy plus beam causal rates separately.
