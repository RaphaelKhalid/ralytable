# Preregistration — Experiment 13 typed sketch search

Status: committed before the smoke results. The smoke is exploratory; no
confirmatory alpha is applied.

## Question

Can a learned controller with at most 9 million trainable parameters solve a
small held-out typed coding task more effectively when a Raly-like compiler
performs legality checks and bounded public-example verification?

## Null and alternative

Null: deterministic typed enumeration is at least as accurate as the learned
system at the fixed search budget, so learning is not needed for correctness.

Alternative: the typed learned controller has higher held-out functional pass
rate or lower search cost at the same pass rate than both the raw controller
and the deterministic null.

## Frozen protocol

Data generation uses seeded random integer lists and the fixed templates in
experiments/13_autoresearch_raly_coder/run.py. Training uses six templates;
evaluation uses the two held-out compositions sort_unique_count and
reverse_filter_sum, with a fixed evaluation RNG and no hidden values exposed
to the model or public-example verifier. Evaluation tasks are generated once
per invocation and are not tuned after inspection. Search budget is 400
expansions and beam width is 24. Seeds are 11, 23, and 37. The smoke uses 180
updates; a run over 30 minutes would require a new cheaper-alternative record.

Primary endpoint: mean held-out hidden functional pass rate, analysed per task.
Secondary endpoints: raw pass/compile rate, full-system compile rate, learned
parameter count, mean latency, mean search expansions, and peak VRAM.

The dashboard objective is lower-is-better:

    hidden failure rate + 0.05 * min(search expansions / 400, 1)

No public benchmark answers, test cases, or external service are used.

## Causal test

For the typed-sketch arm, swap the logits for the first two declared
non-commuting operations at an intermediate sketch position: reverse and
filter_gt for reverse_filter_sum tasks, otherwise sort_asc and unique.
Separately perturb only the EOS logit by 0.0001.
The preregistered qualitative pass is that the relevant intervention changes
the selected verified program while the irrelevant perturbation preserves it.
This is evidence about causal dependence on the declared sketch, not a claim
of parameter-level mechanistic understanding.

## Kill and promotion criteria

Kill the architectural direction if typed search does not beat raw greedy
generation on held-out functional pass rate in the smoke, or if the result
depends on the hidden expected value. Keep the direction exploratory if the
deterministic null matches it within the fixed budget. Promote only after a
fresh task draw, all three seeds, and a separate confirmatory plan with a
multiple-comparison correction.
