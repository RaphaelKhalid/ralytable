# Ralytable

I think that within a few years you won't be allowed to deploy a model you can't explain, and almost nobody is building for that yet. So that's what this is.

Ralytable is two things that only make sense together: **Raly**, a language whose type system understands what a model represents, and **Ralytable**, a model built in that language whose reasoning you can read instead of reverse engineer.

The name is the pitch; a model you can actually relate to, because you can read what it's doing.

## Why now

Reverse engineering trained networks is stalling out; the people furthest along with it are the ones saying so. Models have a bit of legible structure and then a very long tail of junk heuristics, and every year that stays true, building models legible from the start gets more valuable.

Reasoning models also moved the interesting computation out into text, across thousands of forward passes with a visible scratchpad in between. That's an open invitation to make the scratchpad structured.

And teachers got cheap. DeepSeek V4 Flash is $0.03 per million input tokens, so distilling a small student is no longer something only a lab can afford; $10 buys around 130 million output tokens.

## What I already measured

Before writing a line of the language, on real data:

Asking a model what its own reasoning depended on doesn't work. The dependency graph an LLM reports carries no causal information once you control for position (`experiments/01_claimed_vs_causal`). Structure has to be built in, not requested.

Importance looks like it decays with depth, and that turns out not to be a measurement artifact; it disappears entirely once you condition on how decided the answer already is (`experiments/03_position_decay`). Models commit early and the rest of the trace is follow through.

VSA capacity at D=1000 is about 31 items, not the 10 a literature summary suggested (`experiments/04_capacity`). I measured it rather than citing it.

Averaging embedded chunks costs real retrieval accuracy, not just recoverability in an artificial task. On BEIR scifact recall drops 0.877 to 0.619 with realistic grouping, and 70 to 76 percent of that loss is the averaging itself rather than coarser granularity (`experiments/07_retrieval_cost`). mpnet has twice MiniLM's nominal dimension, the same effective dimension, and the same cost, so nominal dimension predicts nothing.

A discrete bottleneck costs about 3 points of top-1 accuracy at matched parameters and buys role legibility 3.3 points above what the raw character already predicts, and bigger codebooks got more capable and more legible together (`experiments/06_discrete_core`). One datapoint at toy scale, but it points the opposite way to the tradeoff I feared.

## What nobody has done

Checked properly in `docs/prior-art.md`, and the honest answer is narrower than I hoped. A typed language where the gradient carrying model is the symbolic program is open. A legibility versus capability curve that spans architecture families is open; one lab has published a curve inside a single family, nobody has done it across families. A small alphabet discrete reasoning core built from scratch is open.

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

This is the contribution nobody has claimed and it goes first.

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

The bar got sharper after the first toy model. It emits perfect dependency citations (`[3] from [1],[2]`) while producing arithmetic nonsense, which is finding 01 reproduced inside our own architecture: structure that is present but decorative. So the real gate is that the structure must be LOAD-BEARING. Change step 1 and step 3 has to change. The resampling method from `experiments/01` is how you test that, pointed at our own model, and nobody has run it on an architecture built to pass it.

### Phase 4, legible RLHF

This is the part I'm most excited about.

RLHF rewards outcomes because outcomes are all a reward model can see. The reasoning that produced the answer is opaque so it goes ungraded, and that is exactly how you end up training a model to reach right answers through broken reasoning.

If the reasoning core is legible then the reward model can see inside it. You grade the process instead of just the product; you penalise a right answer that came out of a derivation that doesn't hold, and you reward a sound step that happened to land wrong. A dense transformer can't do this because there's no readable process to grade. Ralytable can, because of the architecture.

That would make it the first case I know of where being interpretable makes a model better rather than just safer, which flips interpretability from a tax into an advantage.

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

1. **Is the structure load-bearing?** Resample a step in our own model's output and see whether the steps that cite it actually change. This is the sharpest open question in the project and it is about a day's work on data we already have.
2. **Look inside the codebook.** I measured that codes carry role information and never once looked at what an individual code responds to. Cheap, and it is the difference between a number and an explanation.
3. **Codebook provenance in the type system.** A learned codebook invalidates every capacity number the checker uses and it currently cannot tell. That is risk 2 below, and it is now a concrete missing feature rather than a worry.
4. **Phase 2 properly.** Multiple seeds, real text rather than synthetic problems, a matched continuous bottleneck as a fairer control, and more than one architecture family. Last night was one family with one knob turned.
5. **An IR and a backend**, so Raly programs run instead of only type-checking.
6. **Then Phase 4**, which is the one worth being excited about.

## How I work

Every claim is measured or cited; motivating sentences that sound good and aren't known don't get written. Kill criteria go in before the experiment, not after. Negative results ship, and four of the first findings here are negative, which is the point rather than an embarrassment. And I try hard to break anything exciting before believing it; every headline number in this repo got independently re-derived, and twice that caught something that would have been wrong.

## What could kill this

The legibility tax might just be fundamental, and 4.39 BLEU is not encouraging. Phase 2 exists to find that out before I bet on it.

Learned codebooks might void VSA's capacity guarantees entirely; those guarantees depend on atoms staying near orthogonal and gradient descent has no reason to keep them that way. Nobody has published a training time guarantee, and this gates the whole learnable VSA premise.

Discrete doesn't mean legible, small means legible. A ten million gate circuit is as opaque as ten million weights, so Phase 2's metric has to measure recovery rather than discreteness.

And DSLs mostly die from missing on ramps rather than bad design, which is why Phase 1 has the gate it has.

I'd rather find out which of these is true in a month than spend a year assuming none of them are.
