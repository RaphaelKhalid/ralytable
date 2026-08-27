# Findings

AR1 did not promote the cost-normalized QD-credit challenger: fixed MAP-Elites scored higher on the preregistered visible Researcher Score, and the challenger’s visible confidence interval crossed zero.

The corrected final run is `ar1-20260827T230402Z-22acd9`, with 5 paired
researcher seeds, 5 visible families, 4 instances per visible family, 256
proposals per policy/instance/seed, and a 2-instance untouched blind family.
All visible and blind optima and ideal archive QD values were exhaustively
verified. The visible score breakdown was:

| policy | G | D | T | Q | V | R |
|---|---:|---:|---:|---:|---:|---:|
| fixed MAP-Elites | 1 | 0.2321 | 0.3088 | 0.2101 | 0.8158 | 27.33 |
| current UCB | 1 | 0.2018 | 0.2849 | 0.1697 | 0.8668 | 24.69 |
| cost-normalized QD UCB | 1 | 0.2084 | 0.2788 | 0.1710 | 0.8521 | 24.90 |

Against fixed MAP-Elites, current UCB had delta R `-2.64` with paired
bootstrap 95% CI `[-6.08, 0.67]`; cost-normalized QD UCB had delta R `-2.43`
with CI `[-6.00, 1.34]`. The challenger therefore missed both the required
positive lower bound and the minimum meaningful effect of `+2.0` points.

On the untouched `composed_constraint_epistasis` family, the challenger had
R `8.20` versus fixed `3.98`, delta `+4.22`, but the paired bootstrap CI was
`[-0.07, 12.65]`; this passed the point non-inferiority margin but does not
override the visible failure.

Per-family visible A/F/Q values are in the external report and summary. The
sparse-reward family remained the hardest visible case, with all three primary
policies at zero A/F/Q under this budget. Recovery replay matched exactly for
all three policies, same-seed reproducibility matched for all three, and the
eligibility gate was `G=1`.

The QD-removed, inverted-credit, collapsed-niche, and perturbed-seed ablations
are recorded in the raw results. They are diagnostics only and were not used to
tune the challenger. No GPU proxy rerun was needed, and no HumanEval+ or final
coder search was run.

## Limitations

AR1 is still a finite synthetic researcher benchmark with two blind instances;
its R score is not a claim about Python coding, HumanEval+, or interpretability.
The next study should expand family generators and paired seeds before any
researcher policy is applied to the eventual under-9M coder search.
