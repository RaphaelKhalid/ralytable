# Preregistration — state-only causal controller

Status: written before implementation and smoke testing.

The abstract-value experiment showed balanced labels and perfect raw accuracy,
but the text-conditioned model did not change its discrete output when value
facts were erased. This ablation removes the request encoder from the action
path entirely. The controller receives only the serialized executable-state
features, including abstract ordering/uniqueness facts, and predicts the
missing operation. This tests whether the state representation can be a
minimal causally load-bearing controller rather than merely an auxiliary
feature.

Use the same fixed task generator, public verifier, hidden scorer, seeds,
parameter gate, and metrics as `13_abstract_value_state.md`. Compare raw and
public-verified state-only directions with the existing null. Retain only as an
exploratory causal lead if raw pass remains competitive and relevant state
intervention rises above 80% with at least 95% placebo preservation; otherwise
record the ablation as a negative result.
