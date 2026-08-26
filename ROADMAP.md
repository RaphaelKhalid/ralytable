# Raly — Roadmap

**Thesis: within a few years, the models people are permitted to deploy will have to be interpretable. Nobody is building for that. We are.**

Raly is two things that only make sense together: a **language** whose type system understands what a model represents, and a **model** built in it whose reasoning can be read rather than reverse-engineered.

---

## Why this is possible now and wasn't before

Three things changed.

**Interpretation-after-the-fact is stalling.** The field's own leading voices now say full reverse engineering of a trained network looks doomed — models carry a little legible structure and an enormous tail of niche heuristics. Every year that conclusion holds makes build-it-legible more valuable, not less.

**Reasoning models moved the computation into text.** The important part of a modern model's work now happens across thousands of forward passes with a visible scratchpad between them. That is an architectural invitation to make the scratchpad structured.

**Teacher models became almost free.** A strong teacher now costs $0.03 per million input tokens. Distilling a small student is no longer a lab-scale privilege.

## What we already know (measured, not assumed)

Established in this repo, on real data, before writing a line of the language:

- An LLM's **stated** dependency structure carries no causal information beyond position (`experiments/01_claimed_vs_causal`). Asking a model to explain its own reasoning does not work. Structure has to be *built in*, not requested.
- The apparent "importance decays with depth" effect is **not** a measurement artifact — it vanishes entirely once you condition on how decided the answer already is (`experiments/03_position_decay`). Models commit early; most of a reasoning trace is follow-through.
- VSA bundling capacity at D=1000 is about 31 items, not the ~10 a literature summary implied (`experiments/04_capacity`). Measured, not cited.

## What nobody has done (verified in `docs/prior-art.md`)

- A **typed** language where the gradient-carrying model *is* the symbolic program.
- A **legibility-vs-capability curve that spans architecture families.** One lab has published a Pareto curve within a single family. Cross-family is unoccupied.
- A small-alphabet discrete reasoning core built from scratch.

Where prior art *does* exist we say so. All-logic-gate language models were tried (RDDLGN, ETH Zürich) and reached 4.39 BLEU — near the floor. That result kills the maximalist version and leaves ours untested: **soft perception, hard reasoning.**

---

# Phases

Each phase has a gate. A gate is a number that decides whether we continue, not a milestone we narrate past. Phases are ordered by information gained per unit cost.

## Phase 0 — Foundations

The language's semantics, written down before the compiler assumes them.

- [x] VSA and discrete-op formal semantics — which algebraic laws actually hold
- [x] Capacity measured empirically rather than cited
- [x] Prior art surveyed; the unoccupied ground identified
- [x] Compiler architecture decisions researched before they get expensive
- [ ] `raly` compiler skeleton: diagnostics, lexer, AST

**Gate:** the semantics document contains no claim we have not either measured or cited. *(Held so far: one asserted claim was caught and corrected.)*

## Phase 1 — The language runs

A typed VSA DSL that catches what PyTorch cannot see.

- [ ] Grammar, parser, typechecker
- [ ] **Capacity types** — `Vec<D=1024, load=3/31>`; overstuffing is a compile error
- [ ] **Role-schema types** — the type knows *which roles* are bound in, not which values. Unbinding a role the vector does not carry is a compile error.
- [ ] Static nesting-depth checks that force a `cleanup` before retrieval degrades
- [ ] Differentiable end-to-end
- [ ] Error messages good enough to be the reason people use it

**Gate:** a VSA experiment that is *visibly easier* in Raly than in fifty lines of `jax.numpy`. If we cannot produce one, the language is a cathedral and we stop.

## Phase 2 — The curve

The contribution nobody has claimed, and the one that makes everything else credible.

Train the same task across architecture families — dense, weight-sparse, discrete bottleneck, VSA-structured, gate-based — and measure **both** capability and how much of the model a person or auditing model can actually recover.

- [ ] A legibility metric portable across families (the hard part — not "is it discrete" but "can the algorithm be recovered")
- [ ] Blind / oracle-in-the-loop ablation as the instrument
- [ ] The curve, with confidence intervals, published

**Gate:** publishable either way. A cheap legibility tax means the direction is live. An expensive one is a real negative result that saves the field a wall. **This phase cannot fail, only inform** — which is why it comes before we bet on an architecture.

## Phase 3 — Raly-1

The first model. Small, local, legible.

- [ ] Small enumerable alphabet — the model's internal vocabulary is *listable*
- [ ] Soft perception, hard reasoning: neural encoder, discrete readable core
- [ ] Distilled from a frontier teacher (DeepSeek V4 Flash: ~130M output tokens for $10)
- [ ] Trains on one 8GB laptop GPU

**Gate:** the reasoning core is readable *and* the model is not useless. Both, or the thesis is wrong and we say so.

## Phase 4 — Legible RLHF

**The idea that makes this more than a small model.**

RLHF today rewards outcomes, because outcomes are all the reward model can see. The reasoning that produced them is opaque, so it goes ungraded — and that is precisely how you train a model to reach good answers by bad reasoning.

If the reasoning core is legible, **the reward model can see inside.** Reward the *process*, not just the product. Penalise a correct answer reached through a structurally broken derivation. Reward a sound step that happened to end wrong.

This is not possible in a dense transformer, because there is no readable process to reward. It is possible here *because of the architecture*. Interpretability stops being a safety tax and becomes a training advantage — the first case where being legible makes a model **better**, not merely safer.

- [ ] Process-level reward over the discrete reasoning trace
- [ ] Preference data on reasoning structure, not just final answers
- [ ] Test: does process-reward beat outcome-reward at equal compute?

**Gate:** process-supervised Raly beats outcome-supervised Raly on held-out reasoning. If legibility does not buy capability here, it never will — and we will have found the most interesting negative result available.

## Phase 5 — Scale, and the bet

- [ ] Does the legibility tax shrink with scale, or grow?
- [ ] Raly as infrastructure others build on
- [ ] The regulatory thesis: be the default when interpretability stops being optional

---

## How we work

- **Every claim is measured or cited.** Motivating sentences that sound good and are not known do not get written.
- **Kill criteria before experiments.** Preregister what would change our minds.
- **Negative results ship.** Four of this repo's first findings are negative. That is the point, not an embarrassment.
- **Excitement is evidence of a bug.** Every headline number here has been independently re-derived before being believed. Twice that caught something.

## The honest risks

1. **The legibility tax may be fundamental.** Best current evidence (4.39 BLEU) is discouraging. Phase 2 exists to find out before we bet on it.
2. **Learned codebooks may void VSA's capacity guarantees.** No published method gives a training-time guarantee. This gates learnable VSA entirely.
3. **Discrete does not mean legible — small means legible.** A ten-million-gate circuit is as opaque as ten million weights. Phase 2's metric must measure recovery, not discreteness.
4. **DSLs die from missing on-ramps, not from bad design.** Hence Phase 1's gate.

We would rather find out which of these is true in a month than believe all four are false for a year.
