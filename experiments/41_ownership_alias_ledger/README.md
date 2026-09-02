# Loop 22: ownership and alias ledger

This bounded CPU probe tests resource identity, borrow intervals, mutation
exclusivity, and use-after-move. It compares value-only state, an interval
borrow checker without move/lifetime semantics, and an ownership ledger.

Run:

```text
python experiments/41_ownership_alias_ledger/ownership_probe.py
```
