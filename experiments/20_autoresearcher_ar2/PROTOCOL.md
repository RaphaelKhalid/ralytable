# Autoresearcher AR2 preregistration

## Scope and freeze

AR2 evaluates the autoresearcher, not a Python coder. It will not run
HumanEval+, MBPP+, LiveCodeBench, the typed-state coder search, or any final
model evaluation. The trust kernel, evaluator contracts, protected paths,
GPU-owner lock, and append-only ledger are frozen from AR1. Generated AR2
data, checkpoints, receipts, and reports are written outside Git under
`/home/rapha/ralytable-autoresearch-next/ar2`.

The AR1 incumbent remains frozen:

1. `map_elites_fixed`: 60% mutation, 25% crossover, 10% simplification, and
   5% radical proposals with MAP-Elites archive replacement.
2. `adaptive_qd_ucb`: AR1's cost-normalized UCB reward using the mean of
   normalized global-best improvement and normalized archive-QD improvement.

The primary AR2 challenger is `stagnation_aware_map_elites`. It begins with
the exact fixed MAP-Elites schedule and can change only proposal/operator and
parent-emission choices using signals available from completed receipts in the
current trial. It may not inspect the family label, declared optimum, hidden
scores, exhaustive ideal QD, future receipts, or any other oracle material.
Kernel/controller self-editing remains disabled.

No result, blind-family score, or ablation outcome may be used to alter this
protocol, its weights, thresholds, seeds, budgets, or promotion rule.

## Fresh landscapes, instances, and paired budget

The visible set contains six fresh procedural families. Their generator
instances use only the seeds below, which were not used by AR0 or AR1:

| family | purpose | visible instance seeds |
|---|---|---|
| `deceptive_trap_v2` | deeper deceptive blocks and local optima | 1103, 1109, 1117, 1123 |
| `sparse_portals_v2` | sparse reward with two necessary portal events | 1201, 1207, 1213, 1223 |
| `neutral_plateau_v2` | wide neutral plateaus with narrow exits | 1301, 1307, 1319, 1327 |
| `epistatic_bridge_v2` | crossover-helpful block composition | 1403, 1409, 1423, 1429 |
| `constraint_ridge_v2` | feasibility constraints plus deceptive score | 1501, 1511, 1523, 1531 |
| `mixed_pressure_v2` | composition of constraint, neutrality, and sparse rewards | 1601, 1607, 1613, 1621 |

Visible dimensions are 18 bits for the first five families and 20 bits for
`mixed_pressure_v2`. Every visible instance is exhaustively enumerated before
execution to certify its optimum and ideal archive QD. The blind family is
`blind_rotated_composition_v2`, a separate structural composition with
dimension 20 and generator seeds 1709 and 1721. Its generator is frozen in
the implementation before the blind run and is not used for policy choices;
its optimum and ideal QD are exhaustively enumerated by the harness before
scoring. The blind family is never used for policy selection or threshold
choice.

All primary policies use paired researcher seeds
`(17, 29, 43, 59, 71, 83, 97)`, more than AR1. Each visible policy/seed/
instance receives 512 proposal evaluations. Each blind policy/seed/instance
receives the same 512-evaluation budget. The CPU is the primary execution
device. A CUDA typed-state transfer diagnostic, if run, is explicitly
non-scoring and cannot affect selection, promotion, or R.

## Exact cost and curve metric

Proposal evaluation costs are fixed before execution and independent of score:

| operator | cost units |
|---|---:|
| mutation | 1.00 |
| crossover | 1.20 |
| simplification | 0.90 |
| radical | 1.50 |

For instance `i` in family `f`, let `b_fi` be the finite score of the initial
all-zero point, or zero when that point is infeasible, and let `o_fi` be the
exhaustively verified optimum. At each normalized cumulative evaluation-cost
fraction `t`, `q_fi(t)` is the best-so-far score linearly interpolated at `t`,
normalized and clipped:

`q_fi(t) = clip((best_fi(t) - b_fi) / (o_fi - b_fi), 0, 1)`.

The denominator must be positive. An instance that fails this check is a
protocol error and is not silently scored. `A_fi` is trapezoidal area under
`q_fi(t)` against normalized cumulative evaluation cost, and `F_fi=q_fi(1)`.
Family values are arithmetic means across instances: `A_f=mean_i(A_fi)` and
`F_f=mean_i(F_fi)`. Proposal count, raw wall time, CPU time, and cost units
remain separately reported diagnostics; AUC is never computed against mere
proposal count.

## Exact archive-QD metric and unchanged Researcher Score

For each instance, the harness enumerates all feasible points, groups them by
the declared archive niche, and sums the best normalized score in each niche.
That sum is the exhaustive ideal QD, `QD*_fi`. The observed archive QD is
normalized as `Q_fi=min(observed_QD_fi/QD*_fi,1)`, then averaged over instances
to `Q_f`.

The AR1 aggregation and score are unchanged:

`D = 0.70*mean_f(A_f) + 0.30*min_f(A_f)`

`T = 0.70*mean_f(F_f) + 0.30*min_f(F_f)`

`Q = 0.70*mean_f(Q_f) + 0.30*min_f(Q_f)`

`V = 0.50*mean(valid-proposal-rate) + 0.50*mean(1-duplicate-rate)`

`G=1` iff there are zero trust/protected-path violations, exact same-seed
reproducibility, exact checkpoint/resume replay, and no compute-budget
violation; otherwise `G=0`.

`R = 100*G*(0.60*D + 0.20*T + 0.15*Q + 0.05*V)`

Every report and dashboard API must expose the complete receipt-to-score
chain: proposal receipt, operator, parent IDs, lineage depth, validity,
duplicate/novelty, cumulative cost, best-so-far curve, archive coverage/QD,
then every `A_fi`, `F_fi`, `Q_fi`, family aggregate, `D`, `T`, `Q`, `V`, `G`,
and `R`. Novelty, operator-specific yield, lineage depth, archive coverage,
wall/GPU time, and failure categories are mandatory diagnostics only.

## Frozen stagnation-aware policy

The challenger starts every trial with fixed weights
`(mutation=.60, crossover=.25, simplification=.10, radical=.05)`.
Signals are calculated only from the current trial's completed receipts:

* `stall_best`: cumulative cost since the last strict global-best increase;
* `stall_qd`: cumulative cost since the last strict normalized archive-QD increase;
* `duplicate16`: duplicate fraction in the most recent 16 proposals;
* `valid16`: valid fraction in the most recent 16 proposals;
* `growth16`: new archive-niche fraction in the most recent 16 proposals.

When at least 16 proposals have completed, a burst starts if
`(stall_best >= 18.0 OR stall_qd >= 24.0)` AND `duplicate16 >= 0.50` AND
`valid16 >= 0.75`. A burst lasts at most 20 proposals. During a burst, operator
weights are `(mutation=.35, crossover=.15, simplification=.05, radical=.45)`.
Parent emission chooses a least-occupied archive niche with probability 0.65
and a uniform archive member with probability 0.35; ties are resolved by the
trial RNG. Least-occupied and archive membership are current observable
state, not ideal-QD information. If the archive is empty, uniform population
selection is used.

The burst ends early after a strict best or QD improvement followed by four
completed proposals, and it cannot restart until 24 additional cost units
have elapsed. If it reaches 20 proposals without useful progress it ends and
the same cooldown applies. Outside a burst, weights and parent emission are
exactly fixed MAP-Elites. `growth16` is recorded and displayed but is not used
as an unregistered trigger. All thresholds, weights, durations, tie breaks,
and cooldowns are frozen here.

## Preregistered ablations and falsification checks

The following diagnostics use the same seeds, instances, budgets, and score;
they are not eligible for promotion and cannot tune the primary challenger:

* `no_stagnation_trigger`: challenger with its trigger disabled, leaving fixed
  operator weights and ordinary archive parent emission;
* `no_radical_restart`: challenger trigger and cooldown intact, but burst
  weights `(mutation=.55, crossover=.20, simplification=.15, radical=.10)`;
* `no_novelty_targeting`: challenger burst operator weights intact, but parent
  emission is uniform over the current archive;
* `overreactive_trigger`: trigger thresholds `stall_best>=4.0 OR stall_qd>=6.0`,
  `duplicate16>=.25`, `valid16>=.50`, burst length 40, cooldown 8 cost units,
  and burst weights `(mutation=.15, crossover=.10, simplification=.05,
  radical=.70)`.

The harness must also repeat at least one fixed and one challenger block with
perturbed execution seed, verify exact same-seed replay, and deliberately
replay a corrupted credit/receipt stream to prove that the hard gate rejects
it. Ablation results are reported as mechanism/falsification diagnostics,
never as alternate promotion candidates.

## Statistical decision rule

The primary comparison is paired mean `R` over seed-family-instance blocks.
Use a paired percentile bootstrap with 10,000 resamples of those blocks and
the same resampled blocks for challenger-minus-fixed delta R. Promotion of
`stagnation_aware_map_elites` requires all of:

* lower 95% CI for visible delta R versus fixed MAP-Elites greater than 0;
* point-estimate visible delta R at least +2.0 points, the unchanged AR1
  minimum meaningful effect;
* lower 95% CI of blind-family delta R at least -1.0 point;
* `G=1` for fixed, AR1 challenger, and primary challenger, with no integrity
  or budget violation.

The AR1 `adaptive_qd_ucb` arm is a transfer context and is not promoted under
AR2. If any condition fails, fixed MAP-Elites remains incumbent. No score
weights, thresholds, seeds, or decision criteria may be revised after results
are seen.

## Recovery, provenance, and commands

Each proposal writes an append-only receipt containing policy, seed, family,
instance, operator, parent IDs, candidate hash, score, validity, duplicate,
novelty, cost, lineage, and cumulative resource data. Checkpoints serialize
the RNG, population, archive, policy state, trigger/cooldown state, credit
state, and cost state. A checkpoint replay must be byte-equivalent. A paired
repeat with the same policy, seed, and instance must produce byte-equivalent
curves and component metrics. Any mismatch, protected-path change, trust
violation, or budget overrun sets `G=0` and blocks promotion.

After this protocol commit, implementation and execution use:

```text
wsl.exe -d Ubuntu -- env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/mnt/c/Users/rapha/.codex/worktrees/8bdb/mechinterp /home/rapha/ralytable-autoresearch-next/.venv/bin/python -m tools.autoresearch_next ar2 --root /home/rapha/ralytable-autoresearch-next --environment local
```

The AR2 dashboard is loopback-only on port 8792 unless occupied. No public
actions are permitted.
