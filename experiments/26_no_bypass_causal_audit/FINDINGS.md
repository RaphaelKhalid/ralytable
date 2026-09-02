# Findings — Experiment 26

**The causal gate rejected raw and decorative bypass controls and accepted the
ledger-only renderer: relevant-state change, raw-path invariance, and placebo
invariance were all 100% for the ledger-only path, versus 0% state dependence
for raw/decorative controls and about 50% for a mixed path.**

## Evidence

Five seeds evaluated 240 synthetic cases per renderer. Aggregate results:

| renderer | relevant state change | raw-path invariance | placebo invariance | gate pass |
|---|---:|---:|---:|---:|
| raw shortcut | 0% | 0% | 100% | 0% |
| decorative trace | 0% | 0% | 100% | 0% |
| mixed | 50.1% | 50.1% | 100% | 50.1% |
| ledger only | 100% | 100% | 100% | 100% |

## Decision

Keep the three-part causal gate as a mandatory promotion test. It must be
applied to learned models with raw-path erasure and adversarial prompt
interventions; passing this hand-written control is only a validation of the
audit's ability to detect known shortcuts.

## Limitations

- Renderers are hand-written synthetic controls, not learned models.
- The raw intervention is a simple distractor and is not a complete test of
  hidden prompt pathways.
- No coding benchmark, training run, or Qwen comparison is included.
