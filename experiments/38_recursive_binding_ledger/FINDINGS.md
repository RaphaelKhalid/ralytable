# Loop 19 findings

Status: executed.

The key falsification target was a scoped name map that resolves every
same-scope name but has no explicit recursive-group legality. Across five
seeds, the recursive-group ledger passed the original program, alpha-renaming,
recursive-group reordering, non-recursive self-reference rejection, and an
unreachable recursive placebo group: 25/25 checks. The scoped name map passed
the four invariance/legal cases 20/20 but accepted the illegal self-reference
5/5. A prior-declaration sequence failed legal self/mutual recursion and
reordering.

Decision: add an explicit recursive-group identifier and legality rule to the
typed IR. Scope resolution alone is insufficient. This is only a
compiler-front-end contract, not evidence of learned code generation or
large-model parity.
