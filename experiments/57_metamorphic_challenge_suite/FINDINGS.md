# Loop 38 findings

Status: executed.

The falsification target was a suite that tests only surface invariance or
leaks expected answers. The constant and surface-sensitive shortcuts passed
2/2 preserving tests but 0/3 semantic-change tests. The semantic evaluator
passed all 5/5. The clean suite had no forbidden metadata; the contaminated
suite was caught on `alpha_rename` because it carried an `expected_output`
field.

Decision: every challenge suite needs both preserve and change relations, and
its records must pass recursive oracle-leakage scanning. This is a test-design
probe, not evidence of learned coder-model capability.
