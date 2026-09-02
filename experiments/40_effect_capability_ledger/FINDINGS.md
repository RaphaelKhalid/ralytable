# Loop 21 findings

Status: executed after correcting the order-sensitivity control.

The falsification target was a value-only intermediate representation that
accepts unauthorized effects, ignores unhandled exceptions, or canonicalizes
away observable order. Across five seeds, both the effect-tag and capability
ledger variants passed all six checks 5/5 each. The value-only variant failed
the original trace, pure reorder, effect-order sensitivity, capability
rejection, throw rejection, and unreachable-placebo checks 0/5 each. The
correct base effect trace was `(2, 1)`; swapping the operations produced
`(1, 2)`, and only the effect-aware variants exposed that change.

Decision: typed IR nodes need explicit effect sets, capability requirements,
exception obligations, and reachability boundaries; effectful trace order is
semantic state, not a freely sortable token sequence. This is a narrow runtime
contract, not evidence of learned coder-model capability.
