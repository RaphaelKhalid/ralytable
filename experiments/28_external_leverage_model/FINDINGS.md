# Findings — Experiment 28

**Under the explicit optimistic model, a 0.80 success target requires about
31% exact-module coverage with 16-way search and strong parser/retrieval, but
about 67.8% coverage with weaker parser/retrieval; a 0.90 target still needs
69% coverage in the strongest setting, so the feasible claim is narrow-domain
parity rather than open-world parity.**

## Evidence

The model uses assumed module accuracy 99%, execution accuracy 98%, novel-task
accuracy 18%, and per-hypothesis recall 38%. With parser accuracy 95% and
retrieval hit 95%, minimum exact-module coverage for a target score of 0.80 was
72.4% at beam 1, 49.1% at beam 4, 34.4% at beam 8, and 31.0% at beam 16. At
parser accuracy 70%, retrieval hit 60%, and beam 8, the requirement rose to
67.8%. For the strongest parser/retrieval setting, a 0.90 target still needed
69.0% module coverage at beam 8.

These are sensitivity results, not measurements. The beam model assumes
independent hypotheses and is optimistic; real candidates will be correlated.

## Decision

Make exact-module/retrieval coverage the primary feasibility gate for a compact
coder. Prioritize a frozen repository/API task distribution where coverage can
be measured, and report search/verifier resources separately. Do not pursue an
unqualified “40M rivals Qwen-27B” claim.

## Limitations

- All probabilities are assumptions, not measurements.
- The beam formula assumes independent hypotheses and is optimistic.
- No larger-model score is observed or re-created.
- Module coverage, retrieval quality, and parser accuracy must be measured on a
  frozen task distribution before making any parity claim.
