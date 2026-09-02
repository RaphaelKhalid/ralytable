# Loop 18 findings

Status: executed after correcting two controls.

This probe falsified both a position-only sequence and a flat global name map
for repeated names. Across five seeds, the scoped name map and scoped typed
ledger were exact on the original program, alpha-renaming, declaration
reordering, the intentional outer-binding edit, and an unreachable placebo
scope: 25/25 checks each. Position and flat maps were 0/5 on original,
reordering, and placebo checks, while alpha-renaming happened to pass after
all binders received fresh names. The binding-edit check passed for all
architectures because the surface edit made the altered binding explicit; it
is therefore not evidence of scope correctness.

Decision: require lexical scope plus explicit binder identity in the ledger;
names and declaration positions are renderer/parser conveniences only. A
scoped name map ties the typed ledger on this contract, so the extra ledger
fields still need independent causal and type-level justification.

This is a deterministic front-end probe, not evidence of model capability,
code correctness, or parity with a large coder model.
