# Loop 39 findings

Status: executed after correcting the surface-sensitive control.

The falsification target was a metamorphic suite that leaves common semantic
shortcuts alive. The 2-test surface suite killed 2/5 mutants, leaving constant,
commutative-only, and semantic reference behavior alive. The 5-test typed-core
suite killed 4/5, eliminating constant, first-argument, commutative-only, and
surface-sensitive shortcuts; only the semantic reference survived. Adding two
structural controls did not improve this matrix (4/5), so extra tests should
be justified by new mutant families rather than volume.

Decision: preregister a mutant family and require preserve/change tests that
kill it; do not equate larger metamorphic suites with stronger evidence. This
is a test-design probe, not evidence of learned coder-model capability.
