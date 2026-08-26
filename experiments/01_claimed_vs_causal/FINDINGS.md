# A claimed dependency graph adds nothing to position

Null result, on the Thought Anchors released data. Cost: $0.

## Setup

`chunks_labeled.json` in the released rollout dataset carries, per reasoning step:

| field | what it is |
|---|---|
| `depends_on` | an LLM judge's **claim** about which earlier steps this one uses |
| `counterfactual_importance_kl` | **measured** by resampling ~100 continuations |
| `chunk_idx` | position in the trace, the paper's admitted confound |

`analyze_rollouts.py` writes `depends_on` and never reads it again. It is never
checked against the causal measures sitting beside it, even though the prompt that
generates it says the annotation is "for causal analysis".

If the claimed graph is causally real, a step that many later steps transitively
depend on should matter more when resampled.

n = 6,955 steps, 40 traces, 20 problems, 2 models (R1-Distill-Qwen-14B,
R1-Distill-Llama-8B).

## Result

Within-trace Spearman against `counterfactual_importance_kl`, Fisher-z averaged
across traces, 95% CI:

| predictor | raw | position controlled |
|---|---|---|
| `n_descendants` | **+0.203** [+0.12, +0.28] p=7e-06 | **+0.015** [-0.04, +0.07] p=0.59 |
| `frac_descendants` | +0.203 [+0.12, +0.28] | +0.015 [-0.04, +0.07] |
| `out_degree` | -0.042 [-0.08, -0.01] | -0.024 [-0.07, +0.02] |
| `in_degree` | -0.071 [-0.10, -0.04] | +0.020 [-0.01, +0.05] |

Position by itself:

```
position -> importance:  rho = -0.551,  p = 7e-17,  negative in 40/40 traces
```

The claimed graph looks predictive until you control for where the step sits, then
it is indistinguishable from zero. Consistent across both models separately (+0.007
and +0.022, both n.s.) and against the alternative importance measure
(`resampling_importance_kl`: +0.015, n.s.).

## The caveat that bounds the claim

`counterfactual_importance_kl` is itself position-confounded, and heavily so
(rho = -0.55, every trace). Partialling out position therefore removes variance the
two measures legitimately share. This design cannot separate "the graph is empty"
from "position is the mechanism and the graph merely tracks it".

The defensible claim is the narrow one: **the annotated dependency graph carries no
information about causal importance beyond position.**

See `experiments/03_position_decay` for the follow-up, which found that the position
effect is itself a proxy for how decided the answer already is.

## Two traps this run walked into

**Simpson's paradox.** Pooling all 6,955 steps gives rho = **-0.047**, and -0.133
with position controlled, the *opposite sign* to the within-trace result. Traces
differ in length and difficulty, so pooling mixes between-trace variation into a
within-trace question. The first version of this analysis pooled, and would have
reported a confident negative correlation. Each trace is its own control.

**A tautology that looked like the strongest finding.** `overdeterminedness` showed
rho = -0.36 with importance, the largest effect in the pooled run. It is defined as
the duplicate rate among resampled strings, so it is near-mechanically
anti-correlated with an importance score computed from the spread of those same
resamples. Dropped. It also does not mean what the paper's Section 8 means by
overdetermination (several sufficient causal paths); it means the model is locally
deterministic at that point.

## Why this matters for the direction

The cheapest way to get reasoning structure is to ask a model what depends on what.
That produces a graph with no measurable causal content beyond position. It is the
empirical case for making dependencies **structural** rather than self-reported.

Reproduce with `analyse.py` then `within_problem.py`, after `download.py`.
