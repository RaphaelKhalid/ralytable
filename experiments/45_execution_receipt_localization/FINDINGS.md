# Loop 26 findings

Status: executed after correcting the digest-link control.

The falsification target was a receipt that validates only a final digest or
hash links. Across five seeds, all three variants accepted the valid trace.
Final-only receipts detected none of the altered-output or dropped-receipt
cases and reported no location; hash chains detected those tamper cases but
did not detect a changed operation argument whose old chain remained linked.
The replay ledger detected all three fault classes and localized the altered
output to step 1 in 5/5 cases. Overall detection counts were 10/15 for each
tamper class and 5/15 for exact first-step localization because only replay
has semantic access.

Decision: retain per-step input/output digests plus deterministic operation
replay; a final digest or hash chain is useful integrity metadata but is not a
semantic receipt. This is a narrow observability contract, not evidence of
learned coder-model capability.
