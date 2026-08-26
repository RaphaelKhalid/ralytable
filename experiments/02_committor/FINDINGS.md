# Committor jumps: mostly noise, a thin real tail, and the position confound survives

**Verdict.** The strong version of the hypothesis is dead: committor trajectories q(t) are
not step-like. They are a slow drift to the q=1 ceiling buried in binomial sampling noise,
and ~99% of consecutive-step changes are fully explained by that noise. A weak version
survives - there is a statistically real excess of large jumps (|dq| > 0.20 occurs 5.4x more
often than a smooth-curve + binomial null, ~49 excess events in 6915 steps, paired t=3.63) -
but it is rare (~1.2 jumps per trace, present in only 21/40 traces), half of those jumps are
one-chunk spikes that revert rather than level shifts, and, fatally for the main motivation,
|dq| carries the *same* position confound as the existing metric
(rho = -0.565 vs -0.551 for `counterfactual_importance_kl`).

Data: 40 traces (20 problems x 2 models), 6955 chunks, all local.
Code: `experiments/02_committor/analyse.py`. Figure: `results/committor.png`.

## 1. Shape

Traces are long (median 152 chunks, range 60-521). q starts at 0.649 +/- 0.231 and ends at
0.994 +/- 0.018; 39/40 traces end above 0.9. Only 37.4% of individual steps are increases -
i.e. the per-step series looks like *downward*-biased noise around an upward drift, which is
what you get when a bounded quantity approaches its ceiling from below with symmetric noise.
Total variation is huge relative to net movement: median TV = 4.95 against a net change of
about 0.35, a ratio of 16.7. Almost all of the motion in q(t) is jitter, not signal.

Visually (panel A): a noisy band that fans up into the ceiling near the end of the trace.
Nothing resembling clean plateaus separated by risers.

## 2. Jumps vs noise - the crux

q is k/n with n recovered per chunk (see Limitations); median n = 99, only 1.4% of chunks
below n = 50. The null: smooth each trace with a local-linear smoother (Gaussian kernel,
bandwidth 0.25 * len), treat that as the true q, resample Binomial(n, q_hat)/n, 200 reps.

| threshold t | observed P(dq>t) | smooth null | ratio | excess events / 6915 |
|---|---|---|---|---|
| 0.10 | 0.0703 | 0.0601 | 1.17 | 71 |
| 0.15 | 0.0226 | 0.0109 | 2.07 | 81 |
| 0.20 | 0.0087 | 0.0016 | 5.38 | 49 |
| 0.30 | 0.0026 | 0.0000 | ~67 | 18 |
| 0.40 | 0.0006 | ~0 | - | 4 |

Per-trace paired test at threshold 0.20: observed rate 0.0104 vs null 0.0011, paired
difference **+0.0093, 95% CI [+0.0043, +0.0143]**, t = 3.63, and 21/40 traces show any
excess at all. A second, assumption-light null (adjacent chunks have identical true q) gives
|z|>3 at 1.19% against an expected 0.27% - a 4.4x tail excess, with sd(z) = 1.07, i.e. the
bulk of the distribution is exactly binomial and only the tail is not.

Read plainly: **the distribution of |dq| is indistinguishable from sampling noise everywhere
except a tail containing roughly 50 events across 6955 chunks.** That is a real effect, but
it is a fringe phenomenon, not the structure of reasoning.

### 2b. Are the surviving jumps level shifts or spikes?

For the 60 jumps with |dq| > 0.20, compare mean q over the 5 chunks before vs the 5 after.
Only **31/60 retain more than half of the jump**; the other 29 revert. Median retained
fraction 0.59 (IQR 0.22-0.93). So even among the real jumps, roughly half are transient
excursions rather than the plateau-to-plateau transition the hypothesis predicts. This is the
clearest single piece of evidence against "discrete decision moments".

## 3. Location and the position confound

This was the entire selling point of the committor route, and it fails.

| within-trace Spearman vs chunk index | rho (Fisher-z avg) | 95% CI | traces negative |
|---|---|---|---|
| abs(dq) | **-0.565** | [-0.631, -0.491] | 39/40 |
| `counterfactual_importance_kl` | -0.551 | [-0.608, -0.488] | 40/40 |
| `resampling_importance_kl` | -0.652 | [-0.709, -0.587] | 40/40 |
| abs(z) (noise-normalised) | -0.390 | [-0.472, -0.301] | 39/40 |

|dq| is *just as* position-confounded as the metric it was supposed to improve on. The
confound is at least partly mechanical: q climbs to the ceiling, and near q=1 both the room
to move and the binomial sd shrink to zero, so late chunks cannot produce large |dq|.
Normalising by the local binomial sd reduces the correlation to -0.39 but does not remove it,
so a genuine "early steps matter more" effect and a ceiling artefact are entangled here and
this design cannot separate them. Large jumps sit at relative position mean 0.42 (quartiles
0.19 / 0.42 / 0.63) - broadly mid-trace, not concentrated at a specific stage.

## 4. Transition states

Over all steps the mean midpoint q is 0.796 and only 1.4% of steps cross q = 0.5 - 54% of all
chunks already sit above q = 0.9. Conditioning on size: for |dq| > 0.20 the mean midpoint
falls to 0.648, 28% land in [0.35, 0.65] and 30% cross 0.5; for |dq| > 0.30, 44% land in
[0.35, 0.65] and 56% cross 0.5. So big jumps *are* pulled toward q ~ 0.5 relative to base
rate - consistent with transition-state theory, but **this is at least partly forced**:
binomial sd is maximal at q = 0.5, and arithmetic forbids a 0.3 jump starting from q = 0.85.
The pooled rho = +0.74 between |dq| and min(q, 1-q) should be read as mostly mechanical. I do
not count section 4 as independent evidence.

## 5. What are the jump sentences?

Top jumps are dominated by concrete arithmetic and algebraic assertions ("So, the entire
expression is 3 times the result of Layer 9", "Thus, the total number of distributions is
5 * 2^7"), plus a few backtracking cues ("Wait, but the left side is..."). Tag distribution at
the 60 jump chunks vs base rate:

| tag | base | at jumps | 95% CI | n |
|---|---|---|---|---|
| active_computation | 0.317 | 0.383 | [0.261, 0.518] | 23 |
| fact_retrieval | 0.262 | 0.283 | [0.175, 0.414] | 17 |
| uncertainty_management | 0.124 | 0.183 | [0.095, 0.304] | 11 |
| plan_generation | 0.109 | 0.083 | [0.028, 0.184] | 5 |
| result_consolidation | 0.102 | 0.000 | [0.000, 0.060] | 0 |
| self_checking | 0.056 | 0.033 | [0.004, 0.115] | 2 |
| problem_setup | 0.019 | 0.033 | [0.004, 0.115] | 2 |
| final_answer_emission | 0.011 | 0.000 | [0.000, 0.060] | 0 |

chi2 = 9.1, df = 4, p = 0.058 - not significant, and every individual CI overlaps its base
rate. **This method does not reproduce the paper claim that planning is where the action
is**: `plan_generation` is if anything *under*-represented at jumps (0.083 vs 0.109 base), and
`uncertainty_management` is only nominally up (0.183 vs 0.124, CI [0.095, 0.304] contains the
base rate). The only suggestive result is that `result_consolidation` and
`final_answer_emission` account for 0/60 jumps against an 11.3% combined base rate - which is
more plausibly the ceiling artefact again (those tags occur late, when q is already ~1) than a
fact about reasoning. With n = 60 there is not enough here to claim anything.

## 6. Agreement with the existing method

Within-trace Spearman, Fisher-z averaged over 40 traces:

- |dq| vs `resampling_importance_kl`: **+0.533** [+0.444, +0.612]
- |dq| vs `counterfactual_importance_kl`: **+0.483** [+0.401, +0.558]
- |dq| vs `counterfactual_importance_accuracy`: -0.029 [-0.053, -0.005]
- |dq| vs `overdeterminedness`: -0.035 [-0.087, +0.017]

The first two look like independent corroboration and are not. `resampling_importance` is
defined as a divergence between the distribution over *final answers* obtained by resampling
from chunk i and from chunk i+1. q(t) is P(correct answer) under exactly that resampling
distribution, so |dq| is a one-dimensional projection of the same object the KL is computed
from. A rho of +0.53 between a KL and its own binary marginal is close to the floor of what
mechanical overlap would produce, not evidence of two methods converging. This is the same
trap as `overdeterminedness` in experiment 01 and should be treated as such: **|dq| is not an
independent measurement, it is a coarsening of `resampling_importance_kl`.** The near-zero
correlations with `counterfactual_importance_accuracy` and `overdeterminedness` are the only
genuinely non-overlapping comparisons, and they show nothing.

## Limitations

- **n per chunk is inferred, not given.** `accuracy` is stored as a reduced float, so the
  smallest consistent denominator is only a lower bound. 96% of values are consistent with n
  in [90,100] (we assume 99); the remaining 4% have denominators in 17-89 and we take those at
  face value. If some n~99 chunks actually had far fewer rollouts, the null is
  under-dispersed and the jump excess in section 2 is overstated. Using the naive n=100 for
  every chunk inflates the excess (ratio 14x rather than 5.4x at threshold 0.20), so this
  correction matters and it cuts against the surviving finding.
- **The smoother is fit to the observed data**, so it partially absorbs genuine jumps into the
  true curve. That inflates the null tail and makes section 2 conservative - but it also
  means the null is not independent of the data, and the bandwidth (0.25 * len) is arbitrary.
  A different bandwidth would move the excess counts.
- **The ceiling dominates everything.** 54% of chunks have q > 0.9, and all traces are
  `correct_base_solution`. Sections 3 and 4 are both contaminated by the fact that q cannot
  move much once it is near 1. Running this on incorrect-base traces, where q stays low, is
  the obvious control and has not been done.
- **n = 40 traces, 60 jump events.** Section 5 in particular is underpowered; the tag analysis
  is descriptive only.
- **Only two models, one temperature, one dataset** (MATH-style problems). No claim about
  reasoning in general.
- Jump detection uses a single fixed threshold (0.20, ~4 sigma of binomial noise at q=0.5).
  Thresholds were chosen after looking at the |dq| distribution but before the tag analysis.

## What would change the verdict

A committor-based anchor detector would be worth pursuing if (a) the jump excess survived on
incorrect-base traces where there is no ceiling, (b) the position correlation dropped
substantially below the -0.55 of the existing metric after a principled ceiling correction,
and (c) jumps were persistent level shifts at a rate well above the current 31/60. As it
stands none of the three holds, and the method apparent agreement with the existing metric
is definitional rather than empirical.
