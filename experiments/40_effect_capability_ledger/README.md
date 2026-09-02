# Loop 21: effect and capability ledger

This bounded CPU probe tests whether a typed intermediate representation must
track effects, capabilities, exception obligations, and reachability. Value
types alone cannot explain why two operations may not be reordered or why a
filesystem write should be rejected in a read-only context.

Run:

```text
python experiments/40_effect_capability_ledger/effect_probe.py
```
