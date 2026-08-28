# Protocol — text/state recombination repair

Status: exploratory protocol record. The initial mean-pooled representation
was run before this file was added; the intent-first correction is recorded
separately and does not erase that negative result.

## Question

Can a tiny controller combine an independent natural-language intent with an
executable abstract state to choose a Python repair, when either input alone
is insufficient?

## Frozen task and evaluation design

Use 512 training tasks and 256 held-out tasks from three generated prefix
families, three public cases, and four hidden cases per task. The missing
repair is one of `sort_asc`, `unique`, `reverse`, or `filter_gt`. The label is
generated from the intent and prefix-state facts, but is not disclosed in the
request. All candidate programs cross `ast.parse`, `compile`, and `exec`.
Compare a fixed-order public-search null, state-only, text-only, hybrid raw,
and hybrid plus public verification. Confirmation seeds are 11, 23, and 37;
the evaluation RNG is fixed independently from training.

## Promotion gate

The hybrid must remain below 9M learned parameters, beat both one-factor
controls by at least 20 percentage points in raw held-out task pass, and show
at least 25% relevant state intervention with at least 95% irrelevant-placebo
preservation across seeds before promotion beyond exploratory status. Full
system promotion additionally requires a natural-language/code-repair suite.

## Representation correction

The first attempt mean-pooled all request tokens and failed to optimize. The
bounded correction reserves request position 1 for the intent token and reads
that embedding directly; the task distribution, labels, held-out cases, and
execution boundary remain unchanged. This correction is marked in the durable
log with `representation=intent-first-token`.

## Follow-up architecture

After the hybrid correction, an explicitly inspectable cross-product controller
was run as a follow-up. It separately encodes the intent token and typed state,
forms their outer product, and feeds only that interaction tensor to the repair
head. This follow-up uses the same frozen tasks and seeds; its results are
exploratory evidence for the architecture, not a retroactive change to the
promotion gate above.
