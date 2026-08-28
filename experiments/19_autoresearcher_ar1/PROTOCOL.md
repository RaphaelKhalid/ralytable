# Autoresearcher AR1 preregistration

## Scope and freeze

AR1 evaluates the autoresearcher, not a Python coder. It will not run
HumanEval+, MBPP+, LiveCodeBench, or any final-model search. The existing trust
kernel, candidate contracts, evaluator contracts, protected paths, GPU owner
lock, and append-only ledger are frozen. All generated AR1 data, checkpoints,
and reports are written outside Git under
`/home/rapha/ralytable-autoresearch-next/ar1`.

The AR0 incumbent policies are frozen before AR1 execution:

1. `map_elites_fixed`: the existing 60% mutation, 25% crossover, 10%
   simplification, 5% radical schedule with archive niches.
2. `adaptive_ucb`: the existing UCB operator credit using global-best
   improvement plus a new-niche bonus.
3. `adaptive_qd_ucb`: the single challenger implemented after this protocol:
   UCB credit using cost-normalized archive-quality change, defined below.

No policy weight, score weight, seed, instance, or blind-family decision may be
changed after this commit. Kernel/controller self-editing remains disabled.

## Landscapes and paired budget

The visible set contains five deterministic families: deceptive/local-optimum,
sparse-reward, neutral-plateau, epistatic/crossover-helpful, and
constraint-heavy. Each visible family has four deterministic instances with
dimensions 16 or 20, instance seeds 101, 202, 303, and 404, and a fixed budget
of 256 proposal evaluations per policy/seed/instance. Every visible instance
is exhaustively enumerated before execution to verify its optimum and its ideal
archive QD.

The blind set is the separate `composed_constraint_epistasis` generator family,
with dimension 20 and generator seeds 991 and 997. It is held out from policy
selection and is evaluated only after the visible protocol and challenger are
frozen. Its optimum and ideal QD are exhaustively verified by the harness before
scoring, but no policy may inspect its scores during selection.

All policies use paired researcher seeds `(11, 23, 37, 41, 53)`. The primary
paired unit is one seed across all instances in a family. CPU is the primary
execution device. The existing CUDA typed-state proxy is run only as a
separate, non-scoring orchestration check with one paired seed if the WSL
environment is healthy; it cannot affect policy selection.

## Exact cost and curve metric

Each proposal has a deterministic evaluation-cost unit, declared before the
run and independent of its score:

| operator | cost units |
|---|---:|
| mutation | 1.00 |
| crossover | 1.20 |
| simplification | 0.90 |
| radical | 1.50 |

For instance `i` in family `f`, let `b_fi` be the finite score of the initial
all-zero point, or 0 when that point is infeasible; let `o_fi` be the
exhaustively verified optimum. At each normalized cumulative evaluation-cost
fraction `t`, `q_fi(t)` is the best-so-far score linearly interpolated at `t`,
then normalized and clipped as

`q_fi(t) = clip((best_fi(t) - b_fi) / (o_fi - b_fi), 0, 1)`.

The denominator must be positive; an instance failing that check is a protocol
error, not silently scored. `A_fi` is the trapezoidal area under `q_fi(t)`
against normalized cumulative evaluation cost from 0 to 1. `F_fi` is `q_fi(1)`.
Family values are the arithmetic means across that family's instances:

`A_f = mean_i(A_fi)` and `F_f = mean_i(F_fi)`.

This is an evaluation-cost curve, not a proposal-count curve. Raw wall time,
CPU time, and proposal count remain diagnostics.

## Researcher Score

For each instance, the harness exhaustively enumerates every feasible point,
groups points by the declared archive niche, and sums the best normalized score
per niche. That sum is the ideal QD, `QD*_fi`. The observed archive QD is
normalized as `Q_fi = min(observed_QD_fi / QD*_fi, 1)`, then averaged over
instances to `Q_f`.

The aggregate components are fixed as:

`D = 0.70 * mean_f(A_f) + 0.30 * min_f(A_f)`

`T = 0.70 * mean_f(F_f) + 0.30 * min_f(F_f)`

`Q = 0.70 * mean_f(Q_f) + 0.30 * min_f(Q_f)`

`V = 0.50 * mean(valid-proposal-rate) + 0.50 * mean(1 - duplicate-rate)`.

The hard eligibility gate is

`G = 1` iff there are zero trust/protected-path violations, exact same-seed
reproducibility, exact checkpoint/resume replay, and no compute-budget
violation; otherwise `G = 0`.

The preregistered Researcher Score is:

`R = 100 * G * (0.60*D + 0.20*T + 0.15*Q + 0.05*V)`.

Every report must include `G`, `D`, `T`, `Q`, `V`, every per-family `A_f` and
`F_f`, every per-family `Q_f`, and the raw curves. Novelty, operator yield,
lineage depth, archive coverage, raw wall/GPU time, and failure categories are
mandatory diagnostics but are not separately rewarded.

## Policies and ablations

The challenger `adaptive_qd_ucb` assigns each used operator the reward

`r = (0.50 * delta_best + 0.50 * delta_QD) / evaluation_cost_units`,

where both deltas are normalized to `[0,1]` using the instance optimum and
exhaustive ideal QD. It selects operators with the existing UCB exploration
term. This is the only improved reward tested in the primary comparison.

The following falsification/ablation runs are preregistered and cannot be used
to tune the primary challenger: `adaptive_qd_ucb` with the QD term removed,
deliberately inverted reward credit, collapsed niches, and perturbed researcher
seed pairing. They must be reported with the same score components and gate.

## Statistical decision rule

The primary comparison is paired mean `R` over seed-family-instance blocks.
Confidence intervals use a paired percentile bootstrap with 10,000 resamples of
those blocks, with the same resampled blocks used for challenger-minus-incumbent
delta R. Promotion requires, simultaneously:

* challenger lower 95% CI for delta R versus `map_elites_fixed` greater than 0;
* point-estimate delta R at least 2.0 points, the minimum meaningful effect
  fixed before execution (2% of the 0–100 score range, large enough to exceed
  ordinary paired-run noise but still modest);
* challenger non-inferiority on the untouched blind family: lower 95% CI of
  blind delta R at least -1.0 point;
* `G=1` for both policies and no hard-gate or integrity failure.

If any condition fails, the challenger is not promoted. No score weights or
thresholds may be revised after results are seen.

## Recovery and reproducibility

The harness writes append-only trial receipts and checkpoints outside Git. It
must replay each selected checkpoint exactly from serialized RNG, population,
archive, credit, and cost state. A paired repeat with the same policy, seed, and
instance must produce byte-equivalent curve and component metrics. Any mismatch
sets `G=0` and blocks promotion.

## Commands

After this protocol commit, implementation and execution use:

```text
wsl.exe -d Ubuntu -- env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/mnt/c/Users/rapha/.codex/worktrees/8bdb/mechinterp /home/rapha/ralytable-autoresearch-next/.venv/bin/python -m tools.autoresearch_next ar1 --root /home/rapha/ralytable-autoresearch-next --environment wsl
```

The AR1 dashboard is loopback-only and will use port 8791 unless occupied.
