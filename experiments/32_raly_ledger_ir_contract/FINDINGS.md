# Findings — Experiment 32

**The Raly-aligned Python IR contract round-tripped all five valid graphs,
changed every graph digest under mutation, and rejected all four malformed
controls; it is a viable schema candidate but is not yet wired into Rust.**

## Evidence

The contract represented dimension, VSA family, load interval/capacity, role
schema, node provenance, and ordered dataflow references. Five seeded valid
graphs all passed canonical round-trip and mutation-digest checks. Four invalid
controls were rejected: a forward reference, load above capacity, an empty
dimension, and a non-terminal `return` replacement.

## Decision

Keep these fields for a first Raly IR/backend slice. Preserve ordered node
references and type/load validation, and carry provenance as an auditable field
subject to the field-level invariance tests from Experiment 27. Do not claim
compiler integration until the same properties pass in Rust.

## Limitations

- The validator is a Python prototype and is not wired into the Rust compiler.
- The operation/type rules are a minimal subset.
- No learned model, code benchmark, or Qwen comparison is run.
