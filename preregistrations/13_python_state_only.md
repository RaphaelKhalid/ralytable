# Preregistration — executable Python state-only microtasks

Status: written before implementation and smoke testing.

## Question

Does the causally legible state-only controller survive a real Python
parse/compile/execute boundary when the request hides the missing operation?

## Protocol

Each task constructs an executable Python function from a fixed restricted
source generator. The corrupted sketch is either
`input -> filter_gt -> take -> return` or
`input -> reverse -> take -> return`; the missing normalizer is `sort_asc` or
`unique`, selected by the public runtime list state. The request names the
candidate set and prefix family but not the selected operation or public
values. The controller receives only abstract state facts computed after
executing the public prefix. Candidate source is parsed, compiled, and
executed for public verification and hidden scoring by `python_surface.py`.

Use fixed evaluation RNG 270000, 48 held-out tasks, training RNG offset by
seed, seeds 11/23/37, and the 9M parameter gate. Compare a fixed-order null,
state-only raw selection, and state-only public verification. Report raw and
full-system functional pass separately, Python compile rate, expansions,
latency, VRAM, parameter count, and state relevant-change/placebo rates.

## Promotion and kill criteria

Retain as an exploratory architectural lead only if raw state-only Python pass
beats the null's raw comparator and relevant state change exceeds 25% with at
least 95% placebo preservation across seeds. Do not call it general Python
coding capability; promotion requires a larger independently generated task
suite and repository-level tests.
