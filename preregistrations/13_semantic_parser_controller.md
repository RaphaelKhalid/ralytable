# Protocol — typed semantic parser plus state controller

Status: written before smoke testing.

Use the frozen semantic conditional-repair task family with 512 training tasks,
256 held-out tasks, three public cases, four hidden cases, and seeds 11, 23,
and 37. Add an inspectable lexicon parser that converts the prose rule into a
typed predicate and two candidate actions. Compare a deterministic typed-rule
executor, a learned controller over the parsed rule plus executable state, and
the learned controller with public verification. Report raw and full-system
functional pass, compile rate, parameters, VRAM, latency, expansions, and
causal state interventions. The parser may only read the request; hidden cases
remain scoring-only.

This tests whether separating language parsing from typed state control fixes
the failure of the end-to-end neural semantic controller. It is still a local
synthetic Python proxy, not an external coding benchmark.
