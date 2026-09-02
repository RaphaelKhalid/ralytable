# Loop 18: scoped binding ledger

This bounded CPU probe tests whether an explicit identity channel remains
interpretable for repeated names, lexical shadowing, alpha-renaming, and
surface declaration reordering.

It compares a flat name map, a position-sensitive sequence, a scoped name
map, and a scoped typed ledger. The target is a tiny compiler front-end
contract, not evidence of coder-model capability.

Run:

```text
python experiments/37_scoped_binding_ledger/binding_probe.py
```
