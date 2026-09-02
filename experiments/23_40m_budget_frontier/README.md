# Experiment 23 — 40M interpretable-coder budget frontier

Dependency-free theoretical accounting for a coder whose learned component
routes into a typed program ledger and a fixed module library. This is not a
training run. It asks whether the proposed components can fit under 40M
learned parameters while leaving enough capacity for a useful parser/router.

Run `python budget_frontier.py`. The output is a parameter ledger, not a model
score. The formulas are deliberately printed in the result so future changes
cannot silently alter the budget.
