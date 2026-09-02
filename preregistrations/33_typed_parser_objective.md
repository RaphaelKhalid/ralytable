# Preregistration — typed parser objective and leakage contract

Date: 2026-09-01

Question: can a parser be trained to emit a typed program graph without using
answer bits, hidden tests, or a raw-prompt bypass, while retaining execution
and counterfactual dependence?

Null: a parser trained only on graph-token cross-entropy, with no executable or
causal auxiliary terms.

Alternative: adding deterministic replay loss, counterfactual graph loss, and
unused-field invariance improves held-out graph recovery and causal gates over
the null at matched learned parameters.

Proposed objective:

`L = L_graph + 0.5 L_replay + 0.5 L_counterfactual + 0.25 L_unused`

`L_graph` scores typed node/edge tokens. `L_replay` is zero only when the
decoded graph executes and its receipt matches the target semantics.
`L_counterfactual` requires an edited requirement to change the dependent
node/edge and preserve unrelated nodes. `L_unused` penalizes output changes
under metadata/provenance/confidence interventions with declared semantics
fixed.

Primary endpoint: exact held-out graph recovery. Secondary endpoints: replay
rate, relevant intervention change, unused-field invariance, placebo
preservation, parameter count, and search cost.

Hard invalidation: benchmark answers/tests in training data, answer-bearing
metadata, raw-prompt renderer bypass, non-deterministic replay, or a loss term
derived from hidden evaluation outputs.

This preregistration is a design record; no model is trained in Experiment 33.
