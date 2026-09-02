# Findings — Experiment 31

**The minimal typed ledger accepted its valid control, rejected both malformed
program controls, replayed all five valid synthetic ledgers exactly, and
detected every receipt mutation; this earns a runtime baseline, not a model or
coding-capability claim.**

## Evidence

Five seeded valid programs (4–7 nodes each) all passed exact replay and receipt
tamper detection. The malformed controls—wrong input arity and wrong declared
output type—were both rejected; a valid input node was accepted as a positive
control.

## Decision

Keep deterministic typed append, replay, and receipt hashing as the minimum
runtime contract for the ledger architecture. The next implementation step is
to port the semantics into a small Raly IR/backend slice and test compiler
round-trips, while preserving the same rejection and replay gates.

## Limitations

- The operation set is tiny and synthetic.
- Receipts are local hashes, not a security protocol or formal proof.
- No Raly integration, learned parser, coding benchmark, or Qwen comparison is
  included.
