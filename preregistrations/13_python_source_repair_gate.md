# Protocol — ordinary Python source repair gate

Status: written before smoke testing.

Use a fresh generated task family in which each candidate is an actual line
inserted into a Python function containing a `# REPAIR` hole. Parse with
`ast.parse`, compile, and execute the function on three public and four hidden
inputs. The request describes a conditional rule in prose; the target branch
depends on a predicate of the executed pre-repair list state. Compare a
zero-parameter typed rule executor, the two-parameter learned predicate gate
with a fixed rule multiplexer, and the learned gate with public verification.
Use 512 training tasks, 256 held-out tasks, and seeds 11, 23, and 37. Report
raw/full functional pass, syntax and compile rates, parameters, VRAM, latency,
expansions, and predicate erasure causality.

This is the first Experiment 13 checkpoint whose candidates are ordinary Python
source edits rather than restricted operation tokens. It remains a generated
local repair proxy, not a repository benchmark; hidden expected outputs are
used only for scoring and public selection.
