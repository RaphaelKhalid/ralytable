# Protocol — two-hole ordinary Python repair gate

Status: written before smoke testing.

Use a fresh two-hole Python function with two conditional prose rules and four
candidate source edits per hole. Parse, compile, and execute the resulting
function on three public and four hidden inputs. Compare a zero-parameter typed
rule executor, a shared two-parameter learned predicate gate with fixed rule
multiplexing, and a bounded 16-combination public verifier. Use 512 training
tasks, 256 held-out tasks, and seeds 11, 23, and 37. Report raw/full task and
hidden-test pass, syntax/compile, parameters, VRAM, latency, expansions, and
pair-level predicate erasure causality.

The target is a harder composition than the single-hole source experiment, not
a claim of repository-level coding ability. Public examples select candidates;
hidden expected outputs remain scoring-only.
