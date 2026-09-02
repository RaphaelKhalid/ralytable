# Loop 23 findings

Status: executed.

The falsification target was a value-type checker or unverified predicate
annotation channel. Across five seeds, the proof ledger passed every case,
including missing-proof rejection, wrong-proof rejection, annotation
corruption, step reordering, and a placebo value: 30/30. The base type checker
accepted both missing and wrongly bound proofs. Predicate tags also accepted
those proof failures, but rejected harmless annotation corruption because it
mistook metadata for semantics.

Decision: refinement predicates must be separate proof obligations bound to a
specific value identity; annotations are explanatory metadata and cannot
authorize execution. This is a narrow verification contract, not evidence of
learned coder-model capability.
