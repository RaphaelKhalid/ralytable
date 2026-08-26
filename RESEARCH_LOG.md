# Research log

Append-only. Dead ends stay in.

## 2026-08-26 -- repo created

Scoping. Direction chosen: reasoning-model interpretability, building on and then
departing from Thought Anchors.

Framing settled: the interesting cut is at the level of *substrate*, not at the level
of patching the resampling estimator. Thought Anchors probes text from the outside
because natural language has no machine-readable dependency structure. If the model
reasons in a substrate where dependencies are explicit, the causal graph can be read
rather than estimated.

Open, unresolved:
- Which cheap reasoning model on OpenRouter exposes usable CoT.
- What the formal substrate actually is (Prolog/Datalog clauses vs. typed steps vs.
  proof terms). Unknown whether models emit any of these reliably enough to study.
- Whether "read-off graph vs. resampled importance" can be compared on a common scale
  at all. This is the load-bearing methodological risk and is not yet solved.

Not yet done: no code, no API calls, no cost measured.
