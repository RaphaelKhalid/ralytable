# Protocol — executable-prefix typed-state gate

Status: written before smoke testing.

Use a fresh ordinary-Python repair family in which the function executes one
of four frozen prefixes (identity, sorting, absolute-value normalization, or
zero filtering) before a single repair hole. The request names a conditional
rule in prose; the predicate is evaluated on the actual prefix output. Candidate
lines are parsed, compiled, and executed as ordinary Python. Compare the
zero-parameter typed rule, the two-parameter learned predicate gate, and the
public-verifier arm on 512 training tasks, 256 held-out tasks, and seeds 11,
23, and 37. Report raw/full pass, syntax/compile, parameters, VRAM, latency,
expansions, and state-erasure/placebo causality.

This tests whether the previous source-repair result survives variation in the
executed state-producing code rather than depending on an identity prefix.
It remains a generated local Python repair proxy, not a repository benchmark.
