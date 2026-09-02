# Experiment 24 — ledger noise robustness

Dependency-free follow-up to Experiment 22. It tests whether content-addressed
typed entries provide a concrete benefit when the parser emits reordered,
duplicated, dropped, or mutated facts. This remains a representational probe:
the facts are synthetic and no neural parser is trained.

Run `python noise_probe.py`.
