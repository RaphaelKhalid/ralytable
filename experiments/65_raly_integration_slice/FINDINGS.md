# Loop 46 findings

Status: executed.

The audit found three reusable boundaries: arena/index AST nodes with origin
and canonical operands, pure resolver `DefId` mappings with hoisted items, and
the existing dimension/family/load/row type solvers. Six required contracts are
absent: effects/capabilities, alias/move safety, proof DAGs, ordered semantic
addresses, replay receipts, and code generation/execution. The smallest slice
is a pure sidecar ledger keyed by existing IDs/spans, with alpha-normalized
binders, typed ordered addresses, one effect-free primitive interpreter, and
per-step receipts. Training and compiler behavior remain untouched.

Decision: prototype the sidecar against current Raly before any salsa, MLIR,
SMT, opaque residual, or real external effects.
