# Findings

AR0 did not validate a promotion of the new archive-aging policy: fixed MAP-Elites had the highest visible discovery AUC, so the adaptive variant remains a rejected research branch pending a larger preregistered study.

The final paired run used seeds 11, 23, and 37 with 64 proposals on four visible
landscapes: deceptive/local-optimum, sparse-reward, neutral-plateau, and
epistatic/crossover-helpful. A constraint-heavy landscape was held out until
the policy choice was frozen. Greedy, fixed MAP-Elites, plain adaptive UCB, and
adaptive UCB with archive-aging/curiosity were measured. Visible mean discovery
AUC was 0.188, 0.482, 0.450, and 0.403 respectively; visible mean final
best-so-far was 0.188, 0.573, 0.667, and 0.479 respectively. All policies
reached the holdout optimum in this small budget, so holdout success did not
support promoting the aging variant.

Recovery checkpoints matched uninterrupted replay for all four policies, and
the paired same-seed reproducibility check matched exactly. Falsification
controls showed zero sparse-reward best-so-far/AUC when operator credit was
inverted, novelty was disabled, or niches were collapsed; those controls also
reduced archive coverage as expected.

The CUDA section validated torch 2.13.0+cu130, CUDA, BF16, a real optimizer
step, one GPU owner, and two serialized proxy runs on the RTX 4060. The proxy
has nine learned parameters but does not generate Python and is not HumanEval+
evidence. No official HumanEval+ evaluation or final coder search was run.

## Limitations

This is a small synthetic meta-benchmark with three paired seeds and one blind
family. The result is a go/no-go signal for a larger researcher study, not a
claim about downstream coding quality or interpretability. The current chosen
policy is the existing fixed MAP-Elites baseline; adaptive UCB remains useful
as a candidate improvement to test with more landscapes, larger budgets, and
pre-registered operator-credit variants.
