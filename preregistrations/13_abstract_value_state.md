# Preregistration — abstract runtime-state repair

Status: written before implementation and smoke testing.

## Question

Does a compact abstract runtime state carry useful and causally legible
information when the request does not disclose which repair operation is
missing?

## Frozen task construction

Each task asks for a canonical normalization step from the candidate set
`sort_asc` or `unique`, but the request does not reveal the selected operation.
The corrupted sketch is `input -> filter_gt -> take -> return`; the missing
step is inserted at the fixed gap after `filter_gt`. The selected operation is
determined by the public runtime list state: a filtered list that is already
ordered selects `unique`, otherwise it selects `sort_asc`. Public values are
available to the executable-state summarizer but are not serialized into the
request. Hidden values use the same selected operation and are scored only
after candidate selection.

Training and held-out task generators, seeds 11/23/37, 48 held-out tasks,
public verifier, and Python execution path are frozen in
`abstract_value_state.py`. The target-independent null tries the two edits in
fixed order. Report raw top-1, public-verified full-system pass, compile rate,
search expansions, latency, VRAM, parameters, and relevant/placebo state
interventions.

## Promotion and kill criteria

The state-conditioned controller must remain below 9M learned parameters. It
is retained as an exploratory lead only if it beats the null in raw pass or
search efficiency and exceeds 10% relevant state change with at least 95%
placebo preservation across the three seeds. Otherwise record a negative
causal-state result and keep only any separately demonstrated search benefit.
