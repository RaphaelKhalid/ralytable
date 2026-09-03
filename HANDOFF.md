# Handoff

Written at the end of a long session so the next one starts cold without losing
anything. Read `CLAUDE.md` (or `AGENTS.md`, same content) first: it holds the
methodology rules, each written after a result here turned out wrong in that
exact way.

## 2026-09-03 typed-ledger runtime and learned-parser gate

Raly now has its first executable vertical slice. The new `raly-ledger` crate
materializes a checked program as a content-addressed semantic sidecar. Node
identity includes operation, semantic parameters, inputs, and inferred type;
source spans and bound-name spellings remain provenance. Pure top-level
constants execute through `raly run`, emit per-node replay receipts internally,
and replay verification identifies the first divergent node. Unsupported
runtime operations fail explicitly instead of being approximated.

Experiment 66 ran the preregistered matched learned-parser smoke on three seeds.
Both arms fit the training graphs, but neither generalized compositionally.
The structured arm improved exact held-out graph recovery from 0.0% to 11.5%,
while replay equivalence fell from 29.3% to 25.5% and relevant-intervention
change fell from 17.2% to 12.2%. This fails the causal gate by a wide margin.
The under-40M training run is therefore blocked; environment and parameter-count
checks may continue, but no benchmark-guided training should start until a
revised parser passes the preregistered thresholds.

The initial Experiment 66 instrument was discarded before reporting because
its placebo pair changed semantic wording and its evaluation required wholly
unseen synonyms. The committed result is from the corrected paired instrument;
the invalid trial's numbers are not evidence.

## 2026-09-02 full-site and research consolidation

The public Vercel surface now uses one visual system on every shipped route:
`index.html`, `research.html`, `interpretability.html`, `blind-test.html`, and
`playground/index.html`. Each uses the bundled KaTeX/Computer Modern face,
near-black silver-gelatin palette, square archival panels, restrained darkroom
red, and common project navigation. The interactive behavior was preserved.

The substantive local research backlog was also prepared for `main`: updated
research logs and autoresearch code/tests, experiments 21 through 65, the two
preregistrations, the under-40M architecture document, and the flagship brief.
The temporary `.codex/autoresearch.lock` and the obsolete private-preview
`site/.openai/hosting.json` are intentionally excluded.

Validation for this consolidation:

- all five public routes returned HTTP 200 locally;
- every inline page script parsed;
- 15 `autoresearch_next` unit tests passed;
- all 44 standalone probes from experiments 22 through 65 exited successfully;
- all new Python sources compiled; and
- `git diff --check` passed apart from existing line-ending notices.

## 2026-09-02 flagship application artifact handoff

The immediate application-facing deliverable is now one coherent public story,
not another experiment: **Readable is not reliable.** The homepage opens with
the failed discrete TinyStories model, shows the identity-drift failure, then
lets a visitor test whether an explanation is merely readable or actually
load-bearing by erasing it, changing a real reason, or changing an unused note.

### Files deliberately changed in this pass

- `site/index.html` — canonical static homepage.
- `site/.openai/hosting.json` — private Sites project metadata for the live
  application preview.
- `web/index.html` — exact mirror of `site/index.html` for the existing Vercel
  configuration.
- `docs/flagship-research-brief.md` — concise claim/evidence/limitations brief.
- `README.md` — points readers to the flagship story and brief.
- `HANDOFF.md` — this section only.

Do not fold the unrelated dirty research tree into this work. In particular,
the pre-existing edits in `RESEARCH_LOG.md`, `tools/autoresearch_next/`, and the
untracked experiment/preregistration directories were preserved.

### Claim boundary

The strongest supported claim is that the repository contains concrete,
falsification-oriented evidence for design requirements on a future typed causal
ledger. It does **not** contain a trained typed-ledger coding model, a public
coding-benchmark result, or evidence of parity with Qwen or any 27B model. Those
limitations are prominent on both the page and the brief.

### Verification completed

- The two published source trees are byte-identical.
- The visible flagship story was reduced from 1,001 to 444 words (a 55.6%
  reduction), while preserving the interactive causal test and limitations.
- Headings and prose now use the bundled KaTeX/Computer Modern face; compact
  experiment labels remain monospaced.
- The page serves successfully as a dependency-free static site and its inline
  JavaScript parses successfully.
- The seven probes cited by the page were rerun: causal no-bypass, field
  steganography, scoped identity, calibration shift, equivalence-aware splitting,
  typed composition, and the under-40M parameter budget.
- The cited headline values reproduced: `85.4%`, `21/21` versus `0/21`, `25/25`,
  `7.4/12` versus `0/12`, and `38,265,728` learned parameters with zero opaque
  residual bypass.
- `git diff --check` passed; only the repository's existing line-ending warnings
  appeared.
- A private production preview was created at
  `https://ralytable-readable-not-reliable.raphaelbahadurkhan.chatgpt.site`.
  It remains owner-only until the user explicitly approves public access.
- The canonical public reviewer URL is `https://ralytable.vercel.app/`; deploy
  the `web/` tree there from `main` rather than sharing the private preview.

### Next falsifiable research step

Run the preregistered flat/null baseline against a learned structured
typed-ledger variant on grouped held-out compositional tasks, with alpha-renaming,
permutation, relevant-state interventions, raw-prompt and unused-field no-bypass
tests, exact graph/binding recovery, coverage, error, abstention, confidence
intervals, and transparent parameter accounting. Until that exists, keep calling
the current artifact an executable surrogate and causal-audit testbed.

## 2026-08-31 website redesign handoff for Claude Fable

The user approved a **silver-gelatin darkroom** redesign for the whole public
website. Codex stopped before implementing it so Claude Fable can own the visual
pass without overlapping edits.

### Current Git state

- Branch: `codex/moonshot-photography`
- Current pushed commit: `3e6dc48` (`Rewrite public copy in plain language`)
- Remote branch: `origin/codex/moonshot-photography`
- PR creation URL:
  <https://github.com/RaphaelKhalid/ralytable/pull/new/codex/moonshot-photography>
- The plain-language copy pass is finished and pushed. Preserve that copy unless
  a small wording change is required by the new visual treatment.
- No silver-gelatin implementation has been started.

There are unrelated uncommitted research changes in `RESEARCH_LOG.md`,
`tools/autoresearch_next/`, `experiments/16_humaneval_plus_baseline/`,
`experiments/21_under40m_neurosymbolic/`, and
`preregistrations/21_under40m_neurosymbolic.md`, plus
`.codex/autoresearch.lock`. Do not stage, rewrite, or commit them as part of the
website work.

### Approved art direction

Treat the site as a **silver-gelatin research archive**, not a generic retro
theme. The photographs and atmosphere can feel analogue; scientific data,
controls, code, charts, and claims must remain crisp and easy to read.

- Near-black charcoal and warm photographic-paper whites, with a broad grayscale
  range. Suggested dark tokens: background `#090909`, raised surface `#111111`,
  line `#303030`, primary text `#F0EDE6`, secondary text `#B8B4AB`, dim text
  `#77736C`.
- Use one restrained darkroom red, suggested `#A33A32`, for focus, selection,
  active states, and occasional editorial marks. Keep success/error semantics
  independently recognizable; do not turn every accent or chart series red.
- Remove the animated cyan/violet/pink Aurora Foil gradient. Replace it with
  silver highlights, soft exposure blooms, and static tonal contrast.
- Keep the existing seagull hero photograph. It is strong because the left-side
  negative space supports the headline and the bird supplies directional motion.
  Grade it as a high-contrast black-and-white print with controlled grain and a
  slight edge burn or vignette; preserve feather and water detail.
- Add subtle film grain, dust, contact-sheet frame numbers, crop marks, or
  handwritten grease-pencil annotations as sparse editorial details. Keep
  texture away from body copy, code, charts, buttons, and interactive controls.
- Prefer square or nearly square corners, thin keylines, generous margins, and
  photographic caption typography over glossy cards and rounded gradient pills.
- Preserve the current typographic hierarchy and locally available KaTeX faces
  unless a change clearly improves the archive/editorial character. Monospace
  metadata can carry frame numbers, dates, experiment IDs, and exposure-style
  labels.
- Motion should feel mechanical and photographic: a brief exposure fade, contact
  sheet reveal, or focus transition. Avoid looping gradients, fake projector
  jitter, flashing, and continuous film scratches. Respect
  `prefers-reduced-motion`.
- Light mode can read as warm fiber paper with black ink rather than merely an
  inverted dark UI. Maintain usable contrast in both modes.

Suggested motifs, used sparingly:

- `FRAME 03 / EXPERIMENT 21` metadata above research sections.
- A red proofing mark or stamped verdict on failed/null results.
- Contact-sheet borders for photographic separators or key experiment cards.
- Silver highlight lines that resemble reflected light on a developed print.
- Small captions such as `ARCHIVE PRINT · RAPHAEL KHALID`, without inventing
  camera, film-stock, exposure, or date metadata.

Do not bury the site's actual research behind decorative film language. Do not
rewrite measured findings into metaphors, add unsupported scientific claims, or
make negative results look like success.

### Photography

The only reliably available personal photograph in this checkout is
`site/assets/seagull.webp` / `site/assets/seagull.png`, mirrored under
`web/assets/`. The user says there are other strong options in their photography,
but no portfolio URL is recorded here and a previous search could not identify a
definitive portfolio. Ask the user for the exact photography URL before importing
or selecting additional images. Do not substitute stock photography.

### Files and synchronization

The site is static and has no build step. The editable public pages are:

- `site/index.html`
- `site/research.html`
- `site/interpretability.html`
- `site/blind-test.html`
- `playground/index.html` for the local/source playground presentation

The deployable Vercel copy lives under `web/`. Mirror the corresponding page and
asset changes into `web/`, including `web/playground/index.html` where relevant.
The `site/` and `web/` copies of the four main pages should finish identical.
Preserve codebook data, experiment data, WASM, and page behavior.

### Smallest useful implementation sequence

1. Apply the new tokens and silver-gelatin treatment to the landing-page hero,
   navigation, one representative card, and one primary button in both
   `site/index.html` and `web/index.html`.
2. Show that first coherent slice to the user before expanding the treatment.
3. Carry the same tokens and motifs through research, interpretability, blind
   test, and playground pages without forcing identical layouts.
4. Keep the seagull social-preview image unless the final grading makes a new
   preview necessary; if it changes, keep Open Graph and X metadata aligned.
5. Check mobile widths, keyboard focus, reduced motion, light/dark contrast,
   interactive diagrams, the blind-test controls, and playground behavior.
6. Run `git diff --check`, parse every inline `<script>` with JavaScript, compare
   the mirrored `site/` and `web/` pages, and review the final diff before staging
   only website files.

The next smallest action is therefore the landing-page representative slice,
not a full-site blind rewrite.

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
