# Loop 19: recursive binding ledger

This bounded CPU probe tests recursive and mutually recursive definitions.
Lexical scope resolves names, but it does not by itself distinguish a legal
recursive group from an illegal forward/self reference in a non-recursive
definition.

Run:

```text
python experiments/38_recursive_binding_ledger/recursive_probe.py
```
