# Loop 28: parameter-sensitive provenance

This bounded CPU probe tests whether provenance must include operation names,
literal parameters, and ordered input edges. Source IDs alone cannot explain
an operator-literal edit or an operand swap for a non-commutative operation.

Run:

```text
python experiments/47_parameter_sensitive_provenance/provenance_probe.py
```
