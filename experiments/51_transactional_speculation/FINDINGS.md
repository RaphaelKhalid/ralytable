# Loop 32 findings

Status: executed.

The falsification target was speculative execution that exposes effects before
proof validation. Across five seeds, the transactional ledger passed original
selection, candidate reordering, late-failure isolation, all-invalid
isolation, and an invalid high-score placebo 5/5 each. The eager executor
leaked both invalid and valid effects. The undo-log variant removed invalid
memory writes but leaked the irreversible `email_bad` effect, failing every
case. The ledger committed only candidate 1's `answer` and `write_good`
effects.

Decision: speculative search needs an effect-isolated transaction and a
proof-gated commit boundary; compensating logs are not sufficient for external
effects. This is a narrow runtime contract, not evidence of learned
coder-model capability.
