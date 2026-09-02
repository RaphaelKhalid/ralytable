# Experiment 30 — invariant-guided typed search

Dependency-free search-cost probe for the compositional typed-ledger coder.
It compares unrestricted enumeration, type legality, and conservative
abstract-invariant pruning. The invariant rules only remove operations that
are provable no-ops on the current abstract state.

Run `python pruning_probe.py`.
