# Loop 20: typed overload ledger

This bounded CPU probe tests type-directed resolution of overloaded symbols.
It compares name-only and argument-only selection with a typed overload
ledger that uses symbol, argument type, and expected result type, and rejects
ambiguity.

Run:

```text
python experiments/39_typed_overload_ledger/overload_probe.py
```
