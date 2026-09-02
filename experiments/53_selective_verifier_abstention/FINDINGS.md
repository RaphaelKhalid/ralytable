# Loop 34 findings

Status: executed.

The falsification target was confidence-only emission with high-confidence
invalid candidates. On the base batch, confidence-only emission covered 6/8
with risk 0.50 and emitted two high-confidence invalid candidates. Proof-gated
emission covered 4/8 with risk 0.25. Proof-plus-verifier selection covered 3/8
with zero errors and zero high-confidence invalid emissions. Across five seeds
and three variants, average risk was 0.4444, 0.1667, and 0.0 respectively;
average coverage was 0.75, 0.50, and 0.4167.

Decision: make selective abstention a first-class output and require proof plus
verifier approval for the high-confidence path. This is a distributional
safety contract, not evidence of learned coder-model parity.
