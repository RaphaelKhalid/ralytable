# Loop 43 findings

Status: executed.

The falsification target was a wrapper whose declared/direct effects fit the
caller budget while a nested callee exceeds it. All variants passed the safe
base and module-list reordering checks. Shallow checking caught a direct
network wrapper but missed the nested network wrapper and cycles. Only the
transitive capability ledger rejected both nested network exposure and cycles;
it passed each case 5/5 across five seeds.

Decision: compute effect closure recursively through module calls and reject
cycles; wrapper declarations are not trustworthy boundaries. This is a narrow
capability contract, not evidence of learned coder-model capability.
