# Loop 42 findings

Status: executed.

The falsification target was a typed signature treated as sufficient trust.
Name-only and type-only retrieval accepted poisoned and counterfeit modules;
the signed content-addressed policy rejected both 5/5 across five seeds. All
policies were correct on the trusted library and invariant to module-list
reordering. The trusted target implementations were
`parse_int_lines_v1` and `sum_checked_v1`.

Decision: bind module retrieval to content digests, publisher identity, and a
trusted manifest; type compatibility is not supply-chain integrity. This is a
narrow contract, not evidence of learned coder-model capability.
