# Findings — Experiment 35

**Alpha-normalized typed graph state passed rename invariance, declaration-order
invariance, relevant binding sensitivity, and unused-binding preservation at
100% across five seeds; surface and name-normalized controls failed harmless
renaming or placebo tests.**

## Evidence

The alpha graph ignored lexical spelling and declaration order while retaining
source/target roles and type structure. It passed all four checks in every
seed. Surface-position state failed all invariance/placebo checks; the
name-normalized control remained sensitive to lexical renaming and to the
unused declaration.

## Decision

Make alpha-normalized binding structure a required ledger property. Variable
names should be preserved only as renderer metadata/copy-table entries, never
as the semantic identity used by the reasoning graph. The next test should
cover cross-family composition and repeated bindings.

## Limitations

- Programs and bindings are synthetic.
- The graph signature is an abstract equivalence test, not code execution.
- No learned model, coding benchmark, or Qwen comparison is run.
