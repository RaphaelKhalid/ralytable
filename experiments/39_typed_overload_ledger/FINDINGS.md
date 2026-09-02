# Loop 20 findings

Status: executed.

The falsification target was silent overload selection. Across five seeds, the
typed overload ledger passed the original calls, family renaming, overload
table permutation, an argument edit, ambiguity rejection, and an unreachable
scope placebo 5/5 for each case. Name-only and argument-only selectors failed
all six cases. The typed target selected binders `(0, 1, 3, 2)`; removing the
expected result from the `parse(Text)` call correctly produced an ambiguous
`None` result.

Decision: overload entries must carry argument and result types, and the
resolver must reject non-unique matches. This is a narrow IR contract, not
evidence of learned code generation or parity with a larger coder model.
