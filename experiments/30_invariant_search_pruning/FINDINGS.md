# Findings — Experiment 30

**Conservative abstract invariants reduced synthetic search nodes by 65.5% at
depth 8 and 75.6% at depth 10 with 100% target completeness across 2,500
generated depth-8 programs; plain type legality produced no reduction on this
homogeneous list domain.**

## Evidence

| depth | unrestricted/typed nodes | invariant nodes | reduction |
|---:|---:|---:|---:|
| 4 | 426 | 291 | 31.7% |
| 6 | 6,826 | 3,321 | 51.3% |
| 8 | 109,226 | 37,641 | 65.5% |
| 10 | 1,747,626 | 426,313 | 75.6% |

The invariant rules removed only provable no-ops such as `sort` after an
already-sorted abstract state and `unique` after an already-unique state. All
five seeds achieved 1.0 target survival for 500 generated depth-8 programs.

## Decision

Keep invariant-guided search in the design and make completeness a required
test for every new invariant. Do not treat type checks alone as meaningful
search pruning; the next runtime prototype should carry explicit abstract
properties alongside each ledger node.

## Limitations

- The state domain is intentionally tiny and hand-designed.
- Search counts are node counts, not wall-clock measurements.
- No learned model, code benchmark, or Qwen comparison is run.
