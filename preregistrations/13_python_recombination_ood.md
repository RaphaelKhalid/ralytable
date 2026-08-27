# Protocol — held-out intent/state composition

Status: written before smoke testing.

Train on the same executable-Python recombination family while excluding all
training tasks whose independent factors are `intent=delta` and
negative-prefix-state=1. Evaluate on 256 fixed tasks containing only that
held-out factor pair, with three public and four hidden tests per task. Compare
the deterministic null, state-only, generic hybrid, and explicit cross-product
controllers at 181 updates and seeds 11, 23, and 37. Keep raw learned-model
performance separate from public verification, and record the causal state
intervention and placebo rates. The 9M learned-parameter gate remains hard.

This is a composition/generalization stress test of the synthetic repair
primitive, not a general Python benchmark or a public-test claim.

The additive follow-up uses four-dimensional intent logits plus four-dimensional
state logits with no interaction tensor. It is a post-protocol diagnostic of
whether a shared additive rule is sufficient; it does not revise the original
promotion criteria.

The cyclic follow-up maps each factor to an additive phase on a four-cycle and
decodes with fixed class angles. It is another post-protocol diagnostic of
whether an explicit modular state algebra improves held-out composition; its
results remain exploratory until reproduced across seeds.
