# Findings — Experiment 27

**Field-level interventions rejected the hidden metadata, provenance, and
confidence channels: only the semantic renderer passed all invariance checks
(100%), while the metadata and confidence routers failed the combined gate and
the provenance router preserved its nominally unused field only 24.6% of the
time.**

## Evidence

Five seeds evaluated 320 synthetic ledgers per renderer. Aggregate results:

| renderer | semantic change | metadata invariant | provenance invariant | confidence invariant | field gate |
|---|---:|---:|---:|---:|---:|
| semantic renderer | 100% | 100% | 100% | 100% | 100% |
| metadata router | 0% | 26.4% | 100% | 100% | 0% |
| provenance router | 100% | 100% | 24.6% | 100% | 0% |
| confidence router | 76.1% | 100% | 100% | 64.2% | 58.3% |

## Decision

Add field-level invariance to the promotion contract. A state-level causal
intervention is not sufficient: each unused metadata, confidence, and
provenance field must be randomized or erased while the declared semantics are
held fixed. Any output sensitivity is a steganographic bypass.

## Limitations

- Renderers and interventions are hand-written controls.
- The field taxonomy is synthetic and incomplete.
- No learned model, code benchmark, or Qwen comparison is run.
