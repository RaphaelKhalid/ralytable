# A discrete bottleneck costs about 3 points of accuracy and buys a little legibility

First real datapoint on the legibility-versus-capability question, at toy scale.
Cost: about $0.05 of teacher generation and 25 minutes on one laptop GPU.

## Setup

DeepSeek V4 Flash generated 4,042 word problems with **explicit step dependencies**
(`[3] from [1],[2]: ...`), so the training signal carries reasoning structure and not
just prose. Four models, identical task, identical compute, matched parameters. The
only thing that varies is whether the state between encoder and decoder is forced
through a discrete codebook, and how large that codebook is.

Character-level, 6.4M parameters, 6 layers, 6000 steps each.

## Result

Cross-entropy and the VQ commitment term measured separately, because `run.py`
reports their sum and that made the discrete configs look better and worse at the
same time:

| config | cross-entropy | commit | top-1 accuracy | live codes | entropy | role purity |
|---|---|---|---|---|---|---|
| dense | 1.0220 | 0.0000 | **0.8383** | - | - | - |
| codes=64 | 0.8347 | 0.1617 | 0.7736 | 64/64 | 5.72 bits | 0.609 |
| codes=256 | 0.8381 | 0.0819 | 0.8005 | 256/256 | 7.53 bits | 0.634 |
| codes=1024 | **0.8311** | 0.0523 | 0.8065 | 1023/1024 | 8.99 bits | 0.664 |

Parameters match within 0.25% (6,396,160 dense vs 6,412,544 discrete), so none of
this is a capacity difference.

**The two capability metrics disagree, and both are real.** The discrete models have
*lower* cross-entropy and *lower* top-1 accuracy. The bottleneck behaves as a
regulariser: the dense model is right more often but wronger when it misses, which
costs it in cross-entropy. So "what does legibility cost" has no single answer here.
On accuracy it costs about 3 points; on cross-entropy it costs nothing.

## Is the legibility real?

Role purity is the legibility proxy: for each code, how well does it predict whether
the token sits in a premise, a derived step, or the answer. A code that maps onto a
role is a code you could name.

The majority class (`derived`) is 58.0% of the corpus, so **0.580 is what a codebook
carrying no role information at all would score.** A shuffle null, assigning codes at
random, confirms this and stays flat at 0.580-0.581 regardless of codebook size, so
the numbers are not inflated by having more codes.

| codes | purity | null | excess |
|---|---|---|---|
| 64 | 0.609 | 0.580 | **+0.029** |
| 256 | 0.634 | 0.580 | **+0.054** |
| 1024 | 0.664 | 0.581 | **+0.083** |

Small, but real, and monotone in codebook size. Larger alphabets carry more role
structure rather than less.

### Correction: most of that excess is format leakage

The shuffle null was the wrong control. It asks "could a codebook carrying no
information score this?", when the question is "could you score this WITHOUT the
codebook?" You can, largely, because the corpus format gives the role away: `A`
appears only in `ANSWER:`, `]` only inside `from [1],[2]:`. A code firing on `]`
scores 100% on `derived` while understanding nothing.

Predicting the role from the raw CHARACTER alone, no model involved:

| predictor | role purity | over chance |
|---|---|---|
| majority class | 0.5801 | - |
| the character alone (140 of them) | 0.6314 | +0.051 |
| the 1024 codes | 0.6640 | +0.084 |

**So 61% of the reported excess was the character, not the code.** The codes beat
the character by **+0.033**, which is the honest number, and it is real: codes see
context, so they can separate the same character in a premise from one in a derived
step. But it is a third of what this file first claimed.

Inspecting the codebook directly (see `site/interpretability.html`) says the same
thing from the other side: the median code puts 63% of its firings on one character,
and 326 of 1015 live codes are a single character outright.

**The methodological lesson matters more than the number.** Role purity is a leaky
metric because surface form predicts the label. Phase 2's cross-family legibility
metric has to control for what is recoverable from the surface, or it will measure
format recognition and call it interpretability.

## Codebook collapse, and how it was fixed

The first two attempts collapsed to 11 of 64 and then 1 of 64 live codes, entropy
0.00. The bug was in the EMA update: unused codes have a running sum decaying towards
zero, and normalising a near-zero vector produces noise, so dead codes were
re-randomised every step and could never win an assignment.

Four fixes, all standard: cluster-size EMA with unclaimed codes left alone, codebook
initialised from real encoder outputs rather than a random sphere, dead-code revival
onto the worst-reconstructed inputs, and low-dimensional codes. Result: essentially
full utilisation at every size.

## Limitations, and they are substantial

- Character-level, 6.4M parameters, one corpus, one teacher, one seed per config. No
  error bars across seeds.
- The corpus is synthetic and formulaic, which almost certainly makes the reasoning
  structure easier to encode than real text would.
- Role purity is a weak proxy for legibility. Three classes, and "a code predicts a
  role" is much less than "a human can name what a code means".
- No comparison against other architecture families, so this is not yet the
  cross-family curve Phase 2 wants; it is one family with the bottleneck varied.
- The dense baseline gets no bottleneck at all rather than a matched continuous one,
  so some of the gap may be the bottleneck's regularisation rather than discreteness.

## What it says about the direction

The tax is small at this scale and points the right way: a bigger alphabet gets both
more capable and more legible, which is the opposite of the tradeoff we feared. The
ETH result (4.39 BLEU for an all-logic-gate translation model) said the maximalist
version fails. This says the hybrid version, soft perception with a discrete
reasoning core, does not obviously fail.

That is one datapoint at toy scale, not a curve, and it is nowhere near enough to
claim the tax is small in general. It is enough to justify running the real Phase 2.

Reproduce: `python experiments/06_discrete_core/run.py` (corpus is cached), then
`verify.py` to separate cross-entropy from the commitment term.


## What the model actually generates

The overnight run reported metrics and saved no checkpoints, so nothing had been
looked at. `sample.py` retrains codes=1024 and generates. Unedited:

```
PROMPT: "[1] A train travels"

[1] A train travels 300 miles.
[2] The train's pool holds 15,000 gallons.
[3] from [1],[2]: 15,000 / 15,000 = 5,000 quarts.
[4] from [3]: The pool holds 60,000 liters.
ANSWER: 5000
```

It cannot reason. A train acquires a pool, 15,000/15,000 becomes 5,000, gallons
become quarts become litres. Another sample writes "4 feet x 12 = 72 inches" and
answers 92. That is the right outcome for 6.4M parameters and six minutes.

**But the citation structure is flawless.** Every derived step cites earlier steps,
never a step that does not exist, never a premise pretending to cite. Form is learned
long before content.

**And that means the model reproduces the exact pathology this project exists to
fix.** It emits `from [1],[2]` without steps 1 and 2 constraining the result. The
dependency is decorative, which is finding 01 all over again, this time inside our
own architecture.

So the bar for Phase 3 is sharper than "the tax looks small". The structure has to be
LOAD-BEARING: changing step 1 must change step 3. That is testable with the
resampling method from `experiments/01`, pointed at our own model. It is the next
experiment worth running, and nobody has run it on an architecture built to pass it.
