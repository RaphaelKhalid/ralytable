# Loop 37 findings

Status: executed.

The falsification target was the assumption that unanimous standard verifiers
are independent. Standard unanimity emitted 5/8 with risk 0.40 and accepted
both correlated blind-spot candidates. Adding an independent challenge emitted
3/8 with zero errors and removed both blind-spot errors. Five shuffled seeds
left the metrics unchanged.

Decision: unanimity is not a correctness proof when checks share a blind spot;
the architecture needs structurally different challenge tests and must expose
the coverage cost. This is a distributional verification probe, not evidence
of learned coder-model parity.
