# The discrete model is not good enough: the preregistered threshold was NOT met

**Negative result.** The 512-code discrete bottleneck loses to the parameter-matched
dense control on grammar and consistency by about 2.5 points on a 10-point scale --
nowhere near "within noise" -- and a blind judge picks the dense completion in **85.4%**
of head-to-head comparisons. Experiment 08's perplexity gap is not a proxy artefact; it
shows up in the stories. `samples.md` has 12 unlabelled pairs to judge yourself: the
discrete model drifts referentially -- given a kite it yields a balloon, then a drum,
then a trumpet in one paragraph -- while the dense model stays on the kite and repeats.

## The preregistered threshold

Committed (`cb36255`) before any generation existed, applied mechanically in
`analyze.py`:

> Good enough = the discrete model's grammar and consistency scores are within noise of
> the dense model's, even though its perplexity is worse.

Operationalised as: the 95% CI on the within-prompt dense-minus-discrete difference
contains zero. It does not, for either criterion. **Threshold not met.**

## Setup

60 held-out validation prompts, each the opening 40 tokens of a real story found at EOS
boundaries, drawn by a seeded RNG and used in the order produced -- nothing filtered or
cherry-picked. All six experiment-08 checkpoints completed all 60 under identical
sampling: **temperature 0.8, top-k 50, 200 new tokens**. Judge: DeepSeek V4 Flash,
temperature 0, reasoning disabled. **Total API spend $0.0259.** The 420 generations are
in `generations.json`, the 720 judge calls in `judgements.jsonl`.

## Absolute protocol (1-10, mean [95% CI], pooled over 3 seeds)

| criterion | dense | discrete | human | dense - discrete | within noise? |
|---|---|---|---|---|---|
| grammar | 7.00 [6.78, 7.22] | 4.54 [4.27, 4.82] | 9.47 [9.30, 9.63] | **2.44 [2.08, 2.79]** | NO |
| consistency | 5.83 [5.58, 6.08] | 3.08 [2.86, 3.30] | 9.47 [9.26, 9.67] | **2.72 [2.38, 3.06]** | NO |
| creativity | 4.83 [4.65, 5.02] | 3.61 [3.44, 3.77] | 6.88 [6.71, 7.06] | 1.22 [0.97, 1.46] | NO |

Differences are within-prompt -- every model saw the same prompt, so each is its own
control -- aggregated after. The gap dwarfs the seed spread: the worst dense seed (6.68
grammar) beats the best discrete seed (4.88).

## Pairwise protocol

| comparison | n | first-named wins | other | ties | win rate [95% CI] |
|---|---|---|---|---|---|
| **dense vs discrete (3 seed pairs, pooled)** | 179 | 152 | 26 | 1 | **0.854 [0.795, 0.898]** |
| null control: dense_s0 vs dense_s1 | 60 | 31 | 29 | 0 | 0.517 [0.393, 0.638] |
| ceiling control: human vs dense_s0 | 60 | 56 | 4 | 0 | 0.933 [0.841, 0.974] |

## Did the instrument behave?

**Sanity control: PASS.** Real human text, judged blind in the same shape as a model
completion, scores highest on every criterion and beats dense 93% of the time. Had it
not, nothing above would mean anything.

**Null control.** Two dense seeds are draws from the same distribution, so the truth is
50/50; the judge returns 0.517 [0.393, 0.638]. It does not invent a winner between
equivalent arms. That is the reference for indistinguishable, and 0.854 is nowhere near
it.

**Position bias: present, cannot explain the result.** The judge picks the first slot
41.6% [36.2, 47.3] of the time -- but equally in every comparison type (main 0.427, null
0.433, ceiling 0.367), and sides were randomised, so an equal offset cannot manufacture
a win-rate gap.

**The judge will not tie.** 1 tie in 300, including zero in the 60 dense-vs-dense
comparisons where "indistinguishable" is truthful, so the main test's low tie rate is
*not* independent evidence of a difference. **Malformed replies:** 3 of 720, rejected by
a range check, not coerced.

## The exact judge prompt

No model name, config or hint of one; the templates have no slot for one. Reproduce with
`python judge.py --show-prompt`; the pairwise template sits beside it.

```
The following exercise: the student is given the beginning of a story. The student needs
to complete it into a full story. The exercise tests the student's language abilities and
creativity.

The beginning of the story is:
---
{prompt}
---

The student's completion is:
---
{completion}
---

Grade the student's completion on three separate criteria, each on an integer scale from
1 to 10, where 1 is very poor and 10 is excellent:

- GRAMMAR: is the writing grammatically correct and fluent English?
- CONSISTENCY: does the completion follow coherently from the given beginning, and does
  it stay internally consistent about characters, objects and events?
- CREATIVITY: is the story interesting and imaginative rather than bland or repetitive?

Judge only what is written. Reply with exactly one line of JSON and nothing else:
{"grammar": <int>, "consistency": <int>, "creativity": <int>}
```

## Limitations

- **One judge model**, uncalibrated against a second judge or humans. It passed its
  controls and the effect is large; a marginal result would need more.
- **One bottleneck**: 512 codes, one code dimension, one insertion point. Experiment 06
  found the cost varies with codebook size.
- **One scale and budget** (29.5M parameters, 87M tokens); whether the gap narrows with
  compute is untested.
- **One decoding setting**, matched across arms for fairness but not tuned per model.
- **200-token hard truncation**: every completion ends mid-sentence, human control
  included -- equal across arms, but may depress grammar scores.
- **Creativity was not in the threshold** and is the least trustworthy criterion: the
  judge gives real human text only 6.88.

This licenses only that *at this scale, codebook and budget, a 512-code bottleneck costs
enough story quality that a blind judge notices 85% of the time* -- not that discrete
bottlenecks do not work. Legibility is cheap, not free; here, not cheap.
