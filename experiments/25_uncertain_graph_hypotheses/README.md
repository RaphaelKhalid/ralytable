# Experiment 25 — uncertain typed-graph hypotheses

This dependency-free probe asks whether a typed intermediate representation
still helps when a parser is uncertain. A synthetic parser emits ranked
candidate operation graphs. We compare top-1 selection, type-only filtering,
and deterministic execution verification on public examples, then score the
selected graph on held-out hidden examples.

This is a methodology experiment, not a learned model or benchmark run. The
candidate generator is intentionally explicit so it tests the search/verifier
architecture rather than hiding an oracle in a model.

Run `python hypotheses_probe.py`.
