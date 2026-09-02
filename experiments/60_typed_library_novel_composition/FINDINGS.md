# Loop 41 findings

Status: executed after expanding the primitive vocabulary and depth.

The falsification target was whole-program memorization versus typed primitive
composition. After expanding to ten primitives and depth-4 pipelines, the
space contained 42 valid compositions: 21 training and 21 genuinely novel
evaluation combinations with no exact overlap. Whole-program retrieval solved
0/21, typed-library composition solved 21/21, and the untyped control solved
10/21 (47.62%).

Decision: spend the small model's learned capacity on semantic parsing/routing
and compose an explicit typed module library; do not treat whole-program
retrieval as systematic generalization. This is synthetic evidence, not
learned coder-model parity.
