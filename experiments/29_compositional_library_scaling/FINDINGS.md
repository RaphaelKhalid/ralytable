# Findings — Experiment 29

**Under the explicit scaling model, a typed primitive library preserves a
large systematic-generalization advantage over flat whole-program storage, but
search becomes the bottleneck: with 32 primitives at depth 8, expected module
success is 92.3% while type-pruned enumeration still reaches about 19.2M
nodes.**

## Evidence

At module accuracy 99%, a depth-8 composition has expected exact success
\(0.99^8 = 92.3\%\), once the primitive coverage assumption is satisfied. With
32 primitives, a flat table has a space of \(32^8 = 1.10\times10^{12}\)
programs; 100 training examples cover an expected 9.1×10⁻¹¹ of that space and
10,000 cover 9.1×10⁻⁹. The compositional library stores 32×512 learned
scalars in the model used by the accounting script, a 99.999%+ reduction
relative to the corresponding flat table at those sample counts.

At type compatibility 25%, estimated search nodes were 4,681 for 32
primitives/depth 4, 299,593 at depth 6, and 19,173,961 at depth 8. The search
estimate assumes a regular branching factor and is not a runtime measurement.

## Decision

Keep typed primitive composition as the generalization mechanism. Add a hard
search budget and require memoized partial graphs, admissible type/invariant
pruning, or retrieval of partial programs before claiming depth beyond six.
Module error compounding and search cost must be measured separately from graph
recovery and benchmark pass rates.

## Limitations

- This is a combinatorial model, not a learned result.
- Primitive independence and module accuracy are assumptions.
- Search cost is a simple branching estimate.
- No coding benchmark or Qwen comparison is run.
