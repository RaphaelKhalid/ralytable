# Experiment 31 — proof-carrying typed ledger runtime

Small dependency-free executable prototype of the proposed intermediate state.
It is intentionally separate from the Raly compiler until the semantics are
stable. The runtime accepts only typed, acyclic nodes; every step emits a hash
receipt that can be replayed and checked for tampering.

Run `python ledger_runtime.py`.
