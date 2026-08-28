AR2 did not promote the stagnation-aware MAP-Elites challenger; fixed MAP-Elites remains the incumbent under the unchanged preregistered rule.

The valid corrected run is `ar2-20260827T234349Z-4c250f`. It contains all
1,218 scheduled trial rows and 623,831 append-only proposal receipts after
resuming from 1,122 completed rows. The preserved partial overreactive trial
was rerun once; all completed trial keys were skipped. The first run,
`ar2-20260827T232315Z-c58342`, is retained but invalid because its checker
incorrectly treated independent per-trial receipt chains as one global chain.
That forced `G=0`; it is not used as evidence. The correction and rerun did
not change the frozen protocol, landscapes, policies, scores, or promotion
thresholds.

## Valid corrected score

`R = 100 * G * (0.60D + 0.20T + 0.15Q + 0.05V)`.

| policy | G | D | T | Q | V | R |
|---|---:|---:|---:|---:|---:|---:|
| fixed MAP-Elites | 1 | 0.243829 | 0.316279 | 0.311584 | 0.740066 | 29.3294 |
| AR1 adaptive QD-UCB | 1 | 0.246560 | 0.339171 | 0.324558 | 0.802548 | 30.4582 |
| AR2 stagnation-aware MAP-Elites | 1 | 0.247696 | 0.322750 | 0.303395 | 0.773757 | 29.7365 |

The AR2 challenger delta versus fixed was `+0.4071` points with paired
bootstrap 95% CI `[-0.2697, 1.0927]`. It therefore failed both the required
positive lower confidence bound and the preregistered minimum meaningful
effect of `+2.0`. The AR1 transfer-context arm had delta `+0.8163`, CI
`[-0.9461, 2.6765]`; it was not a promotion candidate.

On the untouched blind family, the AR2 challenger delta versus fixed was
`-2.5721`, CI `[-9.2608, 3.4853]`, failing the blind non-inferiority margin of
`-1.0` as well.

Per-family `A_f`, `F_f`, and `Q_f` values, raw cost curves, operator receipts,
lineage, and ablation summaries are in the external `REPORT.md`,
`summary.json`, `results.jsonl`, and `receipts.jsonl` for the valid run.

## Integrity and falsification

The corrected run passed the hard gate: `G=1`; receipt-chain validation was
true; a deliberately corrupted receipt was rejected; all three primary arms
passed exact checkpoint/resume replay; all three passed same-seed
reproducibility; and no compute-budget violation was observed. The four
preregistered ablations (trigger removed, radical restart removed, novelty
targeting removed, and overreactive trigger) are recorded in `summary.json`
and were not used to tune the result.

The initial receipt-checking defect was a serious implementation flaw, but it
was caught by the audit, documented before the corrected rerun, and did not
survive into the valid result. No HumanEval+, final coder search, GPU transfer
diagnostic, or public action was performed.

## Limitations and next recommendation

These are finite synthetic landscapes with exhaustive optima and ideal QD,
not evidence about Python generation or interpretability. The challenger’s
visible point gain is small and its blind score is lower, so the evidence
supports retaining fixed MAP-Elites. Before applying any researcher to a real
coder, preregister a fair equal-budget transfer arena with a genuine small
trainable Python model, identical information and proposer budgets, blind
internal gating, and the existing RTX 4060 WSL constraints. Do not begin that
real-model run until the overnight plan is separately reviewed and approved.
