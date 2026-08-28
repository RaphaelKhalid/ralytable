# Preregistration — larger executable Python repair suite

Status: written before implementation and smoke testing.

## Question

Does a very small state-only controller remain accurate and causally legible
when scaled from two choices and one test to a larger executable-Python repair
suite with four choices, three public tests, and four hidden tests per task?

## Frozen suite

Each task contains a typed list-transform request and a corrupted Python
sketch. The missing repair is one of `sort_asc`, `unique`, `reverse`, or
`filter_gt`; its identity is not disclosed in the request. The controller sees
only an abstract runtime state after the prefix has executed on the first
public input. The target class is a fixed function of that state, and task
construction rejects public cases where candidate outputs collide. Public
tests are used for candidate verification; hidden tests are scoring-only.

The held-out suite has 256 tasks, three prefix families, three public tests,
four hidden tests, and fixed evaluation RNG 290000. Training uses 512 tasks
and seed-specific RNG offsets; confirmation uses seeds 11, 23, and 37. Every
candidate is rendered as Python and passed through `ast.parse`, `compile`, and
`exec`. Compare a fixed-order public-search null with state-only raw and
public-search directions. Report per-test functional pass, task pass,
compile rate, expansions, latency, VRAM, parameter count, and raw versus
verified causal interventions.

## Promotion and kill criteria

The model must remain below 9M learned parameters. Retain as an exploratory
lead if state-only raw task pass exceeds 75% and relevant raw state change is
above 25% with at least 95% placebo preservation across seeds. Full-system
promotion requires a separately generated natural-language/code-repair suite
and repository-level tests; this suite alone cannot establish general Python
coding ability.
