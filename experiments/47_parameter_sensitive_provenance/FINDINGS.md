# Loop 28 findings

Status: executed.

The falsification target was provenance that records only source IDs or an
unordered operation bag. Across five seeds, the content-addressed ledger
passed original identity, node-list reordering, literal sensitivity,
non-commutative operand sensitivity, and unreachable-placebo checks 5/5 each.
Source-only and operation-tag variants failed all five because the base source
set stayed `{a.py:1, b.py:2}` and the operation bag stayed unchanged when the
literal or ordered operands changed.

Decision: provenance addresses must include operation parameters and ordered
child addresses, not merely source spans or an unordered bag of operation
types. This is a narrow causal-state contract, not evidence of learned
coder-model capability.
