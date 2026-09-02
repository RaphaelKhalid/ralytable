# Loop 35 findings

Status: executed.

The falsification target was a source-calibrated confidence threshold assumed
to remain safe under shift. The source batch selected threshold 92 for a 10%
risk target. On source data, fixed 80% confidence had coverage 0.60/risk
0.3333, while the calibrated threshold had coverage 0.20/risk 0.0. On the
shifted batch, fixed 80% risk rose to 0.5714 and the calibrated threshold rose
to 1.0 despite its source guarantee. Adding the explicit proof-plus-verifier
gate emitted zero shifted candidates and therefore retained zero observed
risk, at zero coverage.

Decision: confidence is not a guarantee under shift. Report calibration drift
and make verifier-gated abstention explicit, including the possibility of zero
coverage. This is a distributional safety probe, not evidence of learned
coder-model parity.
