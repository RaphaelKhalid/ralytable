# Ralytable

I think models will eventually need stronger evidence about what they are doing
before deployment. Ralytable is an attempt to make that evidence part of the
model and compiler, not an afterthought.

Ralytable is two things that we are trying to make work together: **Raly**, a
language whose type system understands what a model represents, and
**Ralytable**, a model whose important intermediate state can be inspected and
causally tested.

The name is the pitch; a model you can actually relate to, because you can read what it's doing.

## Why now

The project is motivated by a practical concern: post-hoc explanations can be
wrong, so we want to test whether some useful structure can be specified and
measured during construction. The size of that problem and the value of a
construction-first approach remain empirical questions.

Reasoning models also moved the interesting computation out into text, across thousands of forward passes with a visible scratchpad in between. That's an open invitation to make the scratchpad structured.

An inexpensive capable teacher may make small-student experiments practical.
The exact teacher, price, and licence are run-time facts and must be checked
before any distillation budget is approved.

## What I already measured

Before writing a line of the language, on real data:

Asking a model what its own reasoning depended on doesn't work. The dependency graph an LLM reports carries no causal information once you control for position (`experiments/01_claimed_vs_causal`). Structure has to be built in, not requested.

Importance looks like it decays with depth, and that turns out not to be a measurement artifact; it disappears entirely once you condition on how decided the answer already is (`experiments/03_position_decay`). Models commit early and the rest of the trace is follow through.

VSA capacity at D=1000 is about 31 items, not the 10 a literature summary suggested (`experiments/04_capacity`). I measured it rather than citing it.

Averaging embedded chunks costs real retrieval accuracy, not just recoverability in an artificial task. On BEIR scifact recall drops 0.877 to 0.619 with realistic grouping, and 70 to 76 percent of that loss is the averaging itself rather than coarser granularity (`experiments/07_retrieval_cost`). mpnet has twice MiniLM's nominal dimension, the same effective dimension, and the same cost, so nominal dimension predicts nothing.

A discrete bottleneck costs about 3 points of top-1 accuracy at matched parameters and buys role legibility 3.3 points above what the raw character already predicts, and bigger codebooks got more capable and more legible together (`experiments/06_discrete_core`). One datapoint at toy scale, but it points the opposite way to the tradeoff I feared.

## Potentially open questions

The prior-art review in `docs/prior-art.md` suggests several narrow questions
that may be open, but each needs a fresh literature check before publication:
whether a typed modelling language can make the gradient-carrying structure
itself inspectable, whether legibility can be measured across architecture
families, and whether a small discrete reasoning core can retain capability.

Plenty is already taken. HPVM-HDC is a real VSA compiler. GHRR already swapped transformer attention for VSA binding. And all-logic-gate language models were tried at ETH Zurich and got 4.39 BLEU, which is near the floor; that kills the maximalist version and leaves the version I actually want to test, which is soft perception with a hard reasoning core.

## The phases

Every phase has a gate, and a gate is a number that can fail, not a milestone to walk past.

### Phase 0, foundations

Write down the semantics before the compiler assumes them.

- [x] VSA and discrete op semantics, including which algebraic laws actually hold
- [x] Capacity measured instead of cited
- [x] Prior art surveyed
- [x] Compiler architecture decisions researched before they get expensive to change
- [x] `raly` compiler skeleton: diagnostics, lexer, AST

Gate: no claim in the semantics doc that isn't either measured or cited. Holding so far; one asserted claim already got caught and corrected.

### Phase 1, the language runs

A typed VSA DSL that catches what PyTorch can't see.

- [x] Grammar and parser, with error recovery and a tree total over the input
- [x] Name resolution and typechecker
- [x] Capacity types, so `Vec[Concepts; load 3]` and overstuffing is a compile error
- [x] Role schema types, so the type knows which roles are bound in even though the values are runtime; unbinding a role the vector doesn't carry won't compile
- [x] Static nesting depth checks that force a `cleanup` before retrieval degrades
- [ ] Differentiable end to end (needs the IR and a backend)
- [x] Error messages good enough to be the reason people use it (179 tests, rustc-style UI tests)
- [x] Browser playground (`playground/`), the compiler as wasm

Gate: one VSA experiment that is visibly easier in Raly than in fifty lines of `jax.numpy`. If I can't produce that, the language is a cathedral and I stop.

### Phase 2, the curve

This is the first comparison to run because it tells us whether the proposed
tradeoff is real before we invest in one architecture.

Train the same task across dense, weight sparse, discrete bottleneck, VSA structured and gate based models, and measure both how good each one is and how much of it a person or an auditing model can actually recover.

- [ ] A legibility metric that works across families; this is the hard part, and it has to measure whether the algorithm can be recovered, not whether the weights are discrete
- [ ] Blind versus oracle in the loop as the instrument
- [ ] The curve, with confidence intervals

Gate: none, because this one can't fail, it can only inform. Cheap legibility tax means the direction is live. Expensive tax is a real negative result that saves other people a wall. That's exactly why it comes before I bet on any architecture.

### Phase 3, Ralytable-1

Small, local, legible.

- [ ] A small alphabet the model's whole internal vocabulary can be listed from
- [ ] Soft perception, hard reasoning: neural encoder, discrete readable core
- [ ] Distilled from DeepSeek V4 Flash
- [ ] Trains on one 8GB laptop GPU

Gate: the reasoning core is readable and the model isn't useless. Both, or the thesis is wrong and I'll say so.

The bar got sharper after the first toy model. It emits dependency citations
while producing arithmetic nonsense, so the structure may be decorative. The
real gate is that it must be load-bearing: change step 1 and step 3 has to
change. The resampling method from `experiments/01` can test that on our own
model.

### Phase 4, legible RLHF

This is the most ambitious part of the plan, and it is still a hypothesis.

RLHF rewards outcomes because outcomes are all a reward model can see. The reasoning that produced the answer is opaque so it goes ungraded, and that is exactly how you end up training a model to reach right answers through broken reasoning.

If the reasoning core is legible then the reward model could see inside it. We
could grade process as well as product, but whether that improves training is
an experiment. A dense transformer does not expose the same typed state by
construction; that is a design difference, not proof of an advantage.

If it works, it would be evidence that inspectable process state can improve
training rather than only provide an audit surface. That is a hypothesis, not a
claim about the field.

- [ ] Process level reward over the discrete reasoning trace
- [ ] Preference data on reasoning structure, not just final answers
- [ ] Test whether process reward beats outcome reward at equal compute

Gate: process supervised Ralytable beats outcome supervised Ralytable on held out reasoning. If legibility doesn't buy capability here it probably never will, and that's still worth knowing.

### Phase 5, scale

- [ ] Does the legibility tax shrink with scale or grow
- [ ] Raly as infrastructure other people build on
- [ ] Be the obvious default when interpretability stops being optional

## What's next

In order, cheapest and most decision-relevant first.

1. **Run the structured-memory shootout.** The design, controls, smoke test,
   and kill criteria are in [`docs/codex-audit-2026-08.md`](docs/codex-audit-2026-08.md).
   This tests whether an explicit state can preserve identity and support
   causal intervention better than the current single-vector bottleneck.
2. **Is the existing structure load-bearing?** Resample a step in our own model's output and see whether the steps that cite it actually change.
3. **Look inside the codebook.** I measured that codes carry role information and never once looked at what an individual code responds to. Cheap, and it is the difference between a number and an explanation.
4. **Codebook provenance in the type system.** A learned codebook invalidates every capacity number the checker uses and it currently cannot tell.
5. **Phase 2 properly.** Multiple seeds, real text rather than synthetic problems, a matched continuous bottleneck as a fairer control, and more than one architecture family.
6. **An IR and a backend**, so Raly programs run instead of only type-checking.
7. **Then process-level training**, if the structured state passes the causal gate.

## How I work

Every claim is measured or cited; motivating sentences that sound good and aren't known don't get written. Kill criteria go in before the experiment, not after. Negative results ship, and four of the first findings here are negative, which is the point rather than an embarrassment. And I try hard to break anything exciting before believing it; every headline number in this repo got independently re-derived, and twice that caught something that would have been wrong.

## What could kill this

The legibility tax might just be fundamental, and 4.39 BLEU is not encouraging. Phase 2 exists to find that out before I bet on it.

Learned codebooks might void VSA's capacity guarantees entirely; those guarantees depend on atoms staying near orthogonal and gradient descent has no reason to keep them that way. The prior-art review has not found a training-time guarantee, and this gates the whole learnable VSA premise.

Discrete doesn't mean legible, small means legible. A ten million gate circuit is as opaque as ten million weights, so Phase 2's metric has to measure recovery rather than discreteness.

The compiler still needs an on-ramp beyond diagnostics, which is why Phase 1 has a usability gate rather than only a correctness gate.

I'd rather find out which of these is true in a month than spend a year assuming none of them are.
