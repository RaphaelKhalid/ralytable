# Handoff

Written at the end of a long session so the next one starts cold without losing
anything. Read `CLAUDE.md` (or `AGENTS.md`, same content) first: it holds the
methodology rules, each written after a result here turned out wrong in that
exact way.

## What this is

**Raly** is a programming language and compiler. **Ralytable** is the model and
research project around it; the overnight Python harnesses are Raly-style, not
executed by the compiler. Bet: within a few years you will not be allowed to deploy a model you
cannot explain, and everyone will be retrofitting explanations onto models that
were never built to have one.

Live: https://ralytable.vercel.app (landing, playground, blind test, codebook)
Repo: https://github.com/RaphaelKhalid/ralytable

## 2026-08-27 AR2 and next-run checkpoint

AR2 is complete. The corrected valid run `ar2-20260827T234349Z-4c250f`
performed 1,218 trials and produced 623,831 validated receipts. Fixed
MAP-Elites remains the incumbent at R=29.33. Adaptive QD-UCB's +0.82 paired
delta (95% CI -0.95 to 2.68) and the stagnation-aware controller's +0.41 delta
(95% CI -0.27 to 1.09) do not support promotion. All receipt integrity and
reproduction gates passed. This was CPU-only simulation; no GPU model was
trained.

The clean integration branch is `codex/autoresearch-ar2-roadmap`, stacked on
`codex/raly-coder-foundation`. The next run is specified, but not authorized to
execute, in `docs/plan-under-40m-humaneval-plus.md`. It compares the fixed
MAP-Elites incumbent with Karpathy greedy keep/revert on a real, matched-compute
under-40M Python training task; uses a 37-39M dense control and typed-state
candidate; reports greedy HumanEval+ separately from causal reasoning gates; and
keeps publication/submission outside present authorization.

The product route now assumes commodity silicon. A future compact companion
appliance may package existing ARM/Linux or NPU hardware, but custom silicon and
a replacement phone are not current work. The model path should preserve
standard operations and measure quantization, RAM, latency, and energy.

## 2026-08-27 integration checkpoint

The clean integration was sourced from the completed overnight worktree at
commit `ef74feb27fffdeeebfa380f2f8b344bb17a4db7f` (descendant of `faaf00d`).
It includes the committed Experiment 13 lineage, paused Experiment 14,
Experiment 15 dashboard, Experiment 11 lineage, preregistrations, generator
audits, and append-only JSONL logs. Caches, weights, checkpoints, generated
datasets, `.env`, W&B material, and `__pycache__` are intentionally excluded.

### Corrected verdict

Experiment 13 supports two narrow statements. First, typed legality plus
public-example search can improve the selected program on a generated synthetic
repair family: 52.1% raw learned pass versus 89.6% full-system hidden pass,
while the deterministic null also reaches 89.6%. Second, the larger state-only
controller is a candidate mechanism that is causally load-bearing in a
synthetic control: state erasure changes 50.0% of raw decisions and an
irrelevant placebo preserves 100%. Raw learned, verified full-system,
symbolic, and deterministic-null scores stay separate.

The two-parameter predicate gates are supplied-bit identity/routing controls,
not semantic inference. In `semantic_rule_gate` and `repository_bundle_gate`,
the nuisance-placebo controls are tautological because nuisance is absent from
the gate; those causal rates are historical and invalid for causal promotion.
Every Experiment 13/14 task is synthetic or generated, even where the surface
looks like Python or a repository. The actual Raly compiler/runtime is not in
the execution path, so describe this work as Raly-style or Raly-inspired, not
Raly-based.

### Measurement and reproduction

The old `latency_ms` field begins after model inference and includes old-loop
evaluation work; it is not end-to-end latency. New `run.py` rows separate
inference, selection, hidden scoring, and inference-through-selection. The
invalidated oracle-null file remains at
`experiments/13_autoresearch_raly_coder/research_log_invalidated_null_oracle.jsonl`;
the valid log has 386 rows and the preserved invalid file has 12. Run the
dependency-free record audit with:

    C:\Users\rapha\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe experiments/13_autoresearch_raly_coder/measurement_audit.py --expected-valid 386

The learned parameter gate is <=9M; the overnight maximum was 54,516. Machine
facts remain RTX 4060 Laptop, 8.6GB VRAM, torch 2.6.0+cu124, bf16 autocast and
fused AdamW. Experiment 14 is CPU-only smoke evidence, paused before its
planned multi-seed run because file-backed imports exceeded the short budget.

### Next decision

Do not promote the architecture. The next smallest useful experiment removes
the supplied label/state shortcut with independently specified tasks where
executable state is necessary but not sufficient, while keeping hidden answers
scoring-only. Then test richer Python or repository-local repair. Public GitHub
and Vercel actions remain separate review steps; this integration is local only.

The explicit public destination is a benchmark ladder. EvalPlus HumanEval+ is the
benchmark-guided discovery scoreboard: task-level failures may be inspected and
optimized against, with contamination disclosed, so its tuned score is not
held-out evidence. EvalPlus MBPP+ is the cleaner cross-benchmark generalization
check; BigCodeBench-Hard Complete is the practical stretch target; and a later,
time-separated LiveCodeBench slice is the freshness audit. Autoresearch uses
separate frozen local proxy tasks. Public prompts/solutions stay out of training;
HumanEval+ is the deliberate, disclosed exception for iterative diagnosis. Future
runs preregister <=9M parameters, raw/full/null scores, search budget, and separate
latency fields. No public benchmark was run here.

### HumanEval+ baseline attempt

The official EvalPlus 0.3.1 loader smoke passed and reported 164 HumanEval+ tasks.
The complete `deterministic_pass_baseline` attempt was started locally but did not
produce a score: EvalPlus's official evaluator imports POSIX `resource` and uses
`signal.setitimer`/`SIGALRM`, which native Windows cannot provide. The run was
stopped without weakening the evaluator, and no pass@1 number is reported. The
smallest honest adapter is committed at
`experiments/16_humaneval_plus_baseline/zero_baseline.py`; it emits `pass` for
runtime-loaded task keys only and is a null baseline, not a model.

The same directory contains `result_record.schema.json`, an append-only record
runner, and a loopback-only dashboard. Launch it with a record path outside the
repository; use a POSIX environment (WSL or Linux) for the official evaluator.
The shortest valid route is to install EvalPlus 0.3.1 there, run the adapter with
`--evaluate --output <temp-samples> --record <temp-record>`, and open
`http://127.0.0.1:8766/` via `dashboard_server.py`. A future candidate runner must
freeze EvalPlus 0.3.1 and the HumanEval+ release, keep mutable model/search code
separate, and label any optimized result HumanEval+-tuned. Never rank candidates
with evaluation tests or answers, and never hardcode task IDs, prompts, expected
outputs, or solutions. MBPP+ and LiveCodeBench remain untouched.

Do not start that loop from this task. The next phase should begin in a fresh
isolated worktree using the Luna-high setting, with the evaluator and benchmark
release frozen before any task-level failure inspection. Keep the mutable model,
adapter, and search code separate from the frozen baseline record, and label every
optimized result HumanEval+-tuned.

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

Nine experiments in `experiments/`, each with a `FINDINGS.md` whose first
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
