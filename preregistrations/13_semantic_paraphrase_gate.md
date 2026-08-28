# Protocol — held-out request paraphrase gate

Status: written before smoke testing.

Train the two-parameter typed predicate gate on canonical requests from the
frozen semantic repair family. Evaluate on the same executable tasks with a
held-out paraphrase variant for every predicate and action description. Use the
same three public and four hidden tests, 512 training tasks, 256 evaluation
tasks, and seeds 11, 23, and 37. Compare a deterministic alias parser plus
typed rule, the learned predicate gate, and the learned gate with public
verification. Report raw/full pass, compile, parameters, VRAM, latency,
expansions, and predicate erasure causality.

This isolates request-language robustness from the prior state-interface and
multiplexer failures. The alias lexicon is fixed before evaluation; this is a
local synthetic Python proxy, not a public benchmark.
