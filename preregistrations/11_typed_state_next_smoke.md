# Experiment 11 next smoke preregistration

## Purpose

Check whether the corrected typed-state controller transfers beyond the first
task template before we spend time on a longer run.

## Design

- Base model: the locally cached `Qwen/Qwen2.5-0.5B-Instruct`.
- Arms: transcript controller and hard-mediated controller.
- Training templates: `filter_sort_unique`, `sort_filter_unique`, and
  `filter_unique_count`.
- Evaluation template held out from training:
  `sort_unique_count`.
- Three seeds: 11, 23, and 37.
- Sixteen fresh evaluation tasks per seed.
- One hundred updates per arm and seed.
- The compiler-constrained decoder and the unconstrained decoder are both
  evaluated and logged separately.

## Endpoints

Primary descriptive endpoint: hidden-task pass rate under compiler-constrained
decoding on the held-out template, reported per seed and as the mean across
seeds. The same generated task is used for both arms within a seed.

Secondary endpoints: raw hidden-task pass rate, constrained and raw parse rate,
number of executor errors, loss change, GPU memory, and checkpoint round-trip.

## Hypotheses

The scientific hypothesis is that hard mediation can retain useful task
execution when the transcript is removed. The null hypothesis for a future
confirmatory run is that hard mediation is at least 20 percentage points worse
than the transcript controller on held-out tasks. The alternative is that it is
within that margin or better. This smoke is too small for a valid superiority or
non-inferiority claim, so it reports the predefined descriptive endpoints only.

For the future confirmatory run, alpha will be 0.05, the unit will be the task
within seed, and the analysis will be paired within seed before aggregation.
That run will be separately preregistered before looking at its results.

## Stopping and exclusions

Do not stop, add seeds, change templates, or change decoding settings based on
intermediate results. Exclude a run only for a recorded infrastructure failure
such as out-of-memory or corrupted checkpoint, and report the exclusion.
Malformed unconstrained outputs are outcomes, not exclusions.

## Interpretation rule

Passing this smoke only clears the engineering gate. It does not establish
general coding ability, reasoning, causal interpretability, or superiority over
ordinary language models.
