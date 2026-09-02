# Loop 31 findings

Status: executed.

All schedulers produced valid topological schedules and honored the explicit
write-order constraint 15/15. Only semantic-key scheduling was invariant to
task-list permutation 5/5 and repeatable across ten runs per seed 5/5. FIFO
was repeatable but order-sensitive; randomized ready-queue scheduling varied
across runs. Aggregate reorder-invariance was 6/15 and repeatability 10/15,
with the extra passes coming from chance schedule agreement.

Decision: deterministic parallel execution needs a canonical semantic tie-break
for ready tasks, plus explicit effect-order edges; input order and randomized
ready queues are not replayable. This is a narrow runtime contract, not
evidence of learned coder-model capability.
