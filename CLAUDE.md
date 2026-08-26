# Ralytable

**Raly** is the language and compiler (Rust, `compiler/`). **Ralytable** is the project and the model.
Plan and honest risks: `ROADMAP.md`. Current state: `README.md`.

## Methodology rules

These are not style preferences. Every one of them was written after a result in this
repo turned out to be wrong in exactly that way.

### Before reporting any number, ask what it would be if nothing were happening

Report the baseline alongside the result, always. A finding without its null is not a
finding.

- Finding 06 reported role purity 0.664 as evidence codes carry reasoning structure.
  The majority class alone scores 0.580, and **predicting from the raw character alone
  scores 0.6314** — so 61% of the "excess" was the character, not the code. See
  `experiments/06_discrete_core/leakage.py`.
- The right null is not "could a model carrying no information score this?" It is
  **"could I score this without the model at all?"**

### Check whether a correlation is mechanically forced by the definitions

Two metrics in this repo turned out to be entangled with the thing they were predicting.

- `overdeterminedness` showed the largest effect in an early analysis. It is the
  duplicate rate among the same resamples the importance score is computed from. A
  tautology.
- `resampling_importance_kl` correlated 0.53 with a committor metric. It is a KL over
  the same resampled answer distribution whose correct-answer marginal *is* that
  metric. Definitional, not independent.

### An impossible value is a bug, not an outlier

This has caught more errors than any other technique here.

- A dense model with no codebook reported a **nonzero commitment loss**. It cannot be
  nonzero. The cause: computing it as `total - CE` under bf16 autocast, where rounding
  noise is the same magnitude as the term.
- Ask of every number: what values are impossible here? Then check.

### Never sum loss terms you might want to compare

Cross-entropy and any auxiliary term are reported separately, always. Summing them made
one experiment's discrete configs look simultaneously better and worse than dense.

### Analyse within-unit, aggregate after

Pooling across traces flipped a correlation's sign (+0.203 within-trace, -0.047 pooled).
Simpson's paradox. Each trace, problem or run is its own control; Fisher-z average
across them and report a confidence interval.

### Confidence intervals, not point estimates

Multiple seeds. If the budget will not fit the seeds and the configs, **cut configs
before cutting seeds.**

### Excitement is evidence of a bug

Attack a good-looking result before reporting it. Every headline number in this repo was
independently re-derived before being believed, and twice that caught something wrong.

### Negative results ship

Several findings here are negative. That is the point, not an embarrassment. If an
experiment comes back null, say so in the first sentence of its FINDINGS.md.

### Never write an unsubstantiated motivating sentence

No "this is why X never took off" unless it was actually verified. Say which parts are
measured, which are cited, and which are guesses — then cut the guesses. A fabricated
motivation is worse than none because it hides a real threat to the project.

## Claims we are NOT allowed to make

Checked in `docs/prior-art.md`; each of these was asserted at some point and was wrong.

- **Not** "compile-time dimension checking is unprecedented." Dex has typed index sets,
  Futhark has size types. Our claim is narrower: no ML tool people actually use has it.
- **Not** "interpretable-by-construction is a new field." Concept Bottleneck LLMs,
  weight-sparse transformers and KANs exist. Ours is interpretability in the *type
  system*.
- **Not** "discrete bottlenecks are better." Meta's Large Concept Models also lost to
  their own dense control. The claim is that legibility is **cheap**, not free or better.
- **Not** "nothing tracks superposition load." Unverified.
- The model cannot reason. Do not imply otherwise anywhere, including on the website.

## Experiments

Each lives in `experiments/NN_name/` with a `FINDINGS.md` whose **first sentence is the
verdict**, a limitations section naming what was not tested, and runnable code. No
notebooks. Do not commit data caches, checkpoints or model weights.

## Machine

RTX 4060 Laptop, 8.6GB VRAM, torch 2.6.0+cu124. Use bf16 autocast and fused AdamW.

**`torch.compile` is disabled deliberately** and measured 5x slower on the VQ model
(222 ms/step against 41.6 ms eager) because dead-code revival's data-dependent `topk`
breaks the graph every step. Reasoning is in `experiments/06_discrete_core/core.py`'s
`build()` docstring. Do not re-enable without re-benchmarking.

**Batch 32 is optimal**, measured: 64 is 12% slower and 128 spills past VRAM and is 5x
slower. The GPU is compute-bound, not launch-bound; unused VRAM is not unused compute.

## Rust

Rust 1.98 is installed but not on PATH in a fresh shell:
`export PATH="$HOME/.cargo/bin:$PATH"` (bash) or
`$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"` (PowerShell).

The compiler gate is non-negotiable: `cargo build`, `cargo test --workspace`,
`cargo clippy --workspace --all-targets` and `cargo fmt --all --check` all clean with
**zero warnings**. Do not commit anything that does not pass, and never commit
`compiler/target/`.

## Shell

Heredocs with backticks or `$` have repeatedly broken `gh pr create` — use
`--body-file` with a heredoc instead. A long-running job in the repo root may hold the
working tree; work in your own `git worktree` when running agents in parallel.
