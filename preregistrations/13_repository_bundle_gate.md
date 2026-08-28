# Protocol — multi-file repository bundle gate

Status: written before smoke testing.

Use a fresh three-module Python repository bundle: `__init__.py` imports the
public `solve` function from `api.py`, which imports the repaired function from
`transforms.py`. Candidate edits replace one source hole in `transforms.py`.
Each module is independently parsed and compiled, then imported and executed
on three public and four hidden cases. Compare a zero-parameter typed rule,
the two-parameter learned predicate gate, and bounded public verification on
512 training tasks, 256 held-out tasks, and seeds 11, 23, and 37. Report raw
and full task/hidden pass, syntax/compile, parameters, VRAM, latency,
expansions, and state-erasure causality.

The bundle is executed in isolated in-memory module namespaces to keep the
experiment local and reproducible; hidden expected outputs are scoring-only.
This is repository-shaped rather than a claim of general repository coding.

## Post-run audit note

The two-parameter gate receives a predicate bit computed by the fixed package
executor and routes it through fixed true/false actions. This is supplied-bit
identity/routing, not semantic inference. The nuisance placebo is tautological
because nuisance is absent from the gate, so its causal rate is not valid for
causal promotion. The package remains generated and repository-shaped only.
