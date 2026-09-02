# Findings — Experiment 36

**The explicit typed copy table retained 100% identity recall through length 32
and passed all causal/no-bypass checks; the opaque residual recalled 100% but
had 0% state dependence and raw-path invariance, while 8-slot hashing fell to
26.1% identity at length 32.**

## Evidence

Aggregate identity recall for hashed slots was 83.5%, 67.9%, 46.6%, and 26.1%
at lengths 4, 8, 16, and 32. The typed copy table was 100% at every length,
with 100% relevant-state change, raw-path invariance, and placebo preservation.
The opaque residual was 100% accurate but failed both the state-dependence and
raw-path-invariance checks at every length.

## Decision

Keep a narrow explicit copy table for identifiers and literals. Reject compact
hash slots as the primary identity channel at long context lengths unless they
gain collision detection and fallback. Reject any residual raw channel unless
it is removed from the renderer and independently audited.

## Limitations

- Entity names and queries are synthetic.
- The copy table is an explicit idealized channel, not a trained mechanism.
- No coding benchmark or Qwen comparison is run.
