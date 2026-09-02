# Loop 36 findings

Status: executed.

The falsification target was reliance on one verifier or majority agreement
under disagreement. On the base batch, the execution-only policy emitted 5/8
with risk 0.40 and included two disagreements. Majority emitted 6/8 but risk
rose to 0.50 and included three disagreements. Unanimous type/effect/execution
agreement emitted 3/8 with zero errors and zero disagreements. Shuffling the
batch across five seeds left these metrics unchanged.

Decision: treat verifier disagreement as a reason to abstain, not a vote to
average away. The unanimous gate is conservative and loses coverage, so expose
the coverage/risk frontier rather than calling it universally superior. This
is a distributional verification probe, not evidence of learned coder-model
parity.
