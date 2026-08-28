1. **Retain all six compiler patches.** Each has a local reproducer and focused diagnostic or success consequence, while the full build, test, Clippy, and formatting gates pass. This approval does not imply support for modules, executable IR, or backend semantics.

2. **Pause before implementing an IR or backend.** The Python DSL remains disconnected from executable Raly, and corrected Experiment 11 model-dependent performance is unknown; backend investment therefore lacks demonstrated decision value.

3. **Claims allowed:** the six compiler defects were reproduced and fixed; deterministic DSL controls verify 16 overlapping historical task objects, integer intervention 42→43, provenance omission by default, and explicit provenance inclusion; corrected scripts parse and enforce a disjoint split. **Claims prohibited:** corrected model performance, typed-mediation capability gains, causal interpretability, general coding improvement, private-threshold generalization, a learned codebook, or an implemented DSL/Raly execution path. Historical 15/16, held-out-template, and ablation figures must remain labeled pre-correction.

4. **Smallest next action:** at the first safe idle-GPU window, run the existing corrected model-dependent smoke once, preserving its seed, overlap assertion, outputs, and exit status; use that result solely to decide whether IR/backend work merits reconsideration.

**Continue:** Continue compiler maintenance only where a reproducer produces a regression-test consequence.

**Pause:** Pause IR/backend investment until the corrected smoke supplies the currently missing decision evidence.

**Pivot:** Pivot only if that smoke fails its stated criterion, toward compiler correctness and deterministic tooling rather than model-capability claims.

**Next action:** Execute the corrected smoke once when GPU availability is safe, with no paid review or retry.