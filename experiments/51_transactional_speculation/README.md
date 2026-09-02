# Loop 32: transactional speculative execution

This bounded CPU probe tests speculative candidate execution with proof-gated
commit. It distinguishes eager execution, an undo log that cannot retract
external effects, and a transactional ledger that delays all external effects
until a candidate is validated.

Run:

```text
python experiments/51_transactional_speculation/speculation_probe.py
```
