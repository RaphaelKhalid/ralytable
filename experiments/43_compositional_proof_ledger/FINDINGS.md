# Loop 24 findings

Status: executed.

The falsification target was a proof channel that checks only claimed
conclusions. Across five seeds, all variants passed the original proof,
node-reordering, placebo, and chain-extension cases. The compositional ledger
rejected forged axioms, missing premises, and cyclic proofs 5/5 each. Conclusion
presence and shallow rule checking rejected the first two but accepted the
cycle 5/5. The proof grew from four to five nodes for the chain extension,
while each node retained a local rule and explicit premise IDs.

Decision: use a recursively checked proof DAG with explicit axiom/rule
semantics and cycle detection; do not treat a list of claimed conclusions as
evidence. This is a narrow certificate contract, not evidence of learned
coder-model capability.
