# Loop 22 findings

Status: executed.

The falsification target was typed state without resource identity and alias
intervals. Across five seeds, all three variants passed the legal original,
resource renaming, and lease-order permutation checks 5/5. The interval
checker and ownership ledger rejected overlapping mutation 5/5, while the
value-only variant accepted it. Only the ownership ledger rejected
use-after-move 5/5; the interval checker intentionally lacked move semantics.
All variants passed the unreachable-placebo control because the probe exposes
reachability explicitly.

Decision: retain resource IDs, borrow intervals, alias kind, and move/lifetime
rules in the runtime contract. Effect labels alone do not capture alias
safety. This is a narrow execution-safety contract, not evidence of learned
coder-model capability.
