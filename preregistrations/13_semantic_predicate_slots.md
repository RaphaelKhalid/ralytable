# Protocol — explicit typed predicate slots

Status: written before smoke testing.

Reuse the frozen natural-language conditional repair family with 512 training
tasks, 256 held-out tasks, three public cases, four hidden cases, and seeds 11,
23, and 37. Reuse the exact parser from the preceding checkpoint, but replace
the incomplete generic runtime vector with three explicit Boolean typed state
slots: duplicates, negative, and long. Add one nuisance noise slot randomized
during training so the placebo intervention is not a constant out-of-support
feature. Compare a deterministic typed-slot rule executor, a learned MLP over
parsed rule features plus slots, and the learned controller with public
verification. Report raw and full-system functional pass, compile rate,
parameters, VRAM, latency, search expansions, and interventions that erase all
predicate slots versus toggle only nuisance noise.

The hypothesis is that the previous parser/controller failure was an interface
failure: the parser recovered the rule, but generic state omitted duplicates and
long. This remains a local synthetic Python proxy; it is not an external
benchmark or a general coding claim.
