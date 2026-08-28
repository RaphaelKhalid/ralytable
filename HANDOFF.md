# Handoff

Written at the end of a long session so the next one starts cold without losing
anything. Read `PROJECT_GUIDE.md` first. `CLAUDE.md` and `AGENTS.md` point to it;
it holds the shared methodology and collaboration rules.

## What this is

**Raly** is a programming language and compiler. **Ralytable** is the model we
are trying to build with it. The bet is that some useful model structure can be
specified and tested during construction instead of explained only after the
fact.

Live: https://ralytable.vercel.app (landing, playground, blind test, codebook)
Repo: https://github.com/RaphaelKhalid/ralytable

## What exists and works

**The compiler.** 8 crates, 198 tests, zero clippy warnings, fmt clean. Lexer,
diagnostics, parser with error recovery, name resolution, and a type system
tracking four things a tensor library cannot see: dimension (abelian-group
unification), VSA family, superposition load against measured capacity, and role
schema (row polymorphism). Plus `raly explain`, which prints in plain English what
a program represents, derived only from types. Runs in the browser as WebAssembly.

There is no IR, no codegen, no backend. **Raly type-checks but cannot execute.**

**The model.** 29.5M parameters, TinyStories, dense and 512-code discrete
variants, three seeds each. It cannot reason and is not meant to.

**Infrastructure.** Memmap data pipeline, checkpointing with resume, multi-seed
with confidence intervals, live dashboards (`tools/watch.py`, localhost:7900),
W&B mirroring, blind LLM judging, OOM and divergence recovery.

## What was found

Ten experiments in `experiments/`, each with a `FINDINGS.md` whose first
sentence is the verdict. The load-bearing ones:

**01 — asking a model about its own reasoning does not work.** An LLM's stated
dependency graph carries no causal information beyond position (rho +0.203 raw,
+0.015 controlled). Structure has to be built in, not requested.

**03 — importance decaying with trace depth is real, not an artifact.** It
vanishes once you condition on how decided the answer already is. Models commit
early; the rest is follow-through.

**07 — averaging embedded chunks costs real retrieval accuracy.** BEIR scifact
recall 0.877 to 0.619 with realistic grouping; 70-76% of the loss is the
averaging itself, isolated with a max-pooling control. Nominal dimension predicts
nothing (mpnet has twice MiniLM's nominal dimension, the same effective
dimension, the same cost). **This is the most immediately useful finding here and
the one most likely to be a product.**

**08 — the discrete bottleneck costs 0.63 cross-entropy and 9.9 accuracy points**
on real text, three seeds each, non-overlapping intervals, all 512 codes live. It
overturns experiment 06, which measured a third of that on a synthetic corpus and
concluded legibility was cheap. Formulaic text compresses into a small alphabet;
real text does not.

**09 — and the stories are worse to read.** Blind judging against a threshold
committed to git before any text existed: dense wins 85.4% of 179 pairwise
comparisons. The failure is not grammar, it is losing track of what is being
discussed. A kite becomes a balloon becomes a drum inside one paragraph. Syntax
survives a nine-bit channel; identity does not.

**10 — the taboo organism has no game in it.** All 23 models cracked, 100%
recovery, for under a cent each, using ten benign questions plus one LLM call.
They defend against *saying* the secret and not at all against *meaning* it. The
logit lens looked like a white-box win at 9/10 until a text control (base model
reading the same hints) scored 0.50.

## What was tried and did not work

Do not redo these.

- **torch.compile**: 222 ms/step against 41.6 ms eager. The VQ's dead-code
  revival does a data-dependent `topk` that breaks the graph every step. Disabled
  deliberately; reasoning is in `experiments/06_discrete_core/core.py`.
- **Bigger batches**: batch 32 is optimal, measured. 64 is 12% slower, 128 spills
  past VRAM and is 5x slower. The GPU is compute-bound, not launch-bound.
- **The committor idea** (experiment 02): reasoning trajectories are not
  step-like and the metric inherited the same position confound it was meant to
  remove.
- **Role purity as a legibility metric**: 61% of the apparent signal was the raw
  character. See `experiments/06_discrete_core/leakage.py`.

## Open directions, ranked

**1. Extend Cywinski, Rajamanoharan, Nanda, Conmy and Marks, arXiv:2510.01070.**
Their stated limitation is that behavioural probing might make elicitation
methods unnecessary. They did not quantify it. Experiment 10 did, accidentally,
on one organism family: every elicitation method lost to plain semantic
inference. Doing this properly across all three of their released families is a
real paper, it uses their own models, and it lands on measurement validity.
Note their prefill result is ~5% on taboo and >90% on the other two, so the
answer probably differs by organism type, which is the interesting part.

**2. The auditing arena.** No public competitive interpretability arena exists
(`docs/arena-prior-art.md`). Trojan competitions died from having no leaderboard
gradient: top TrojAI entries scored recall around 0.16, indistinguishable from
random. Experiment 10 shows the taboo organism has the opposite problem, a
ceiling. A viable benchmark needs a property that is not inferable from outputs,
no enumerable answer key, and organisms trained to resist elicitation. Anthropic
named this as future work 17 months ago and has not built it.

**3. Automated auditing agents.** Named future work in the same paper: agents
that form hypotheses, select tools and synthesise findings rather than handing
raw tool output to a human. This is also what an arena needs as a baseline
entrant.

**4. The embedding diagnostic.** Finding 07 is a product: point it at an
embedding pipeline, report the effective dimension and what averaging is costing.
Ships in a week, does not need Raly at all, and is the only thing here that could
have a user this month.

**5. The controlled-language pilot.** Full plan in
`docs/plan-controlled-language.md`, written to be picked up cold. API-only, costs
cents, opens with a kill-switch.

**6. An IR and a backend for Raly**, so programs run rather than only
type-check. This is what turns a very good linter into a tool people install.

**7. The split architecture** (continuous path for identity, discrete for
structure). Not novel on its own; Concept Embedding Models and residual VQ do
versions of it, and the known failure is leakage through the continuous path.
Only worth running with a leakage probe as the pass condition. The genuinely
unoccupied version is training for causal necessity: intervene on a discrete code
during training and require the output to change, so load-bearingness is an
objective rather than a hope.

## Practical notes

- **Rust is installed but not on PATH** in a fresh shell:
  `export PATH="$HOME/.cargo/bin:$PATH"` (bash) or
  `$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"` (PowerShell).
- **Compiler gate is non-negotiable**: build, `cargo test --workspace`, clippy
  `--workspace --all-targets`, `cargo fmt --all --check`, all with zero warnings.
- **GPU**: RTX 4060 Laptop, 8.6GB, torch 2.6.0+cu124. bf16 and fused AdamW are
  good. Corpora do not fit in VRAM as int64; use a uint16 memmap.
- **Keys**: `OPENROUTER_API_KEY` in `.env`. W&B authenticated via `~/_netrc`
  (underscore, Windows). HF authenticated but **has no token for gated repos**,
  which blocked the gemma-2-9b taboo family in experiment 10.
- **`gh pr create` breaks on heredocs containing backticks or dollar signs.** Use
  `--body-file`.
- Agents running in parallel should each take their own `git worktree`; the repo
  root gets held by long jobs.
- `~deepseek/deepseek-v4-flash-latest` with `reasoning: {"enabled": false}` is the
  cheap workhorse. It is a reasoning model and will spend the whole token budget
  thinking and return empty content if you leave reasoning on.

## The rule that has earned its place

Before reporting a number, ask what it would be if nothing were happening. Four
findings here were overturned by their own control: role purity by the character
baseline, overdeterminedness by its definition, the committor by position, and
the logit lens by a base model reading text. An impossible value is a bug, not an
outlier; a dense model reporting a nonzero commitment loss is what caught a bf16
precision bug.

## Latest handoff: corrected Experiment 11 smoke (2026-08-27)

The corrected smoke was run from an isolated copy of the three Experiment 11
scripts with seeds 11, 23, and 37; 24 training tasks, 16 held-out
`sort_unique_count` tasks, and 100 updates per arm. The transcript controller
solved 6/48 typed constrained tasks and hard mediation solved 0/48; untyped
constrained results were 5/48 and 0/48, respectively. Raw unconstrained
generation solved 0/48 in both arms. All constrained outputs parsed without
executor errors, all six adapters round-tripped, and three 16-task oracle checks
passed 16/16.

Artifacts, raw outputs, validation, and run metadata are preserved under
`experiments/11_typed_state_mediation/corrected_smoke_20260827_01/`. The result
is exploratory plumbing evidence only. Keep IR/backend work paused; do not
start confirmatory training before the preregistration gate.
