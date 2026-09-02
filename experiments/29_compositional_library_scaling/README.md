# Experiment 29 — typed compositional library scaling

Dependency-free combinatorial analysis of a primitive-module coder. It
compares a flat whole-program table with a typed compositional library as the
number of primitives and program depth grow.

The calculation is a feasibility model, not a trained-model result. It makes
the central tradeoff visible: compositional modules need far fewer learned
entries and can generalize to unseen combinations, but module errors compound
with depth and typed search consumes computation.

Run `python scaling.py`.
