# Findings — Experiment 25

**On 800 synthetic tasks, beam-8 typed hypotheses plus public execution
verification reached 79.0% hidden pass versus 31.1% for top-1 selection; type
checking alone reached 36.9%, confirming that legality is not semantic
verification.**

## Evidence

Five seeds evaluated 160 tasks each. Hidden pass and exact graph recovery were:

| selector | beam | hidden pass | exact graph |
|---|---:|---:|---:|
| top-1 | 1 | 31.1% | 11.8% |
| type-only | 4 or 8 | 36.9% | 14.3% |
| public execution | 1 | 28.5% | not improved |
| public execution | 4 | 66.4% | 31.4% |
| public execution | 8 | 79.0% | 41.6% |

The type-only selector accepted many valid-but-wrong programs. Beam-1 public
verification was worse than top-1 because it could reject a candidate without
searching alternatives. The beam-8 gain is therefore a test-time compute gain,
not evidence that the parser became more accurate.

## Decision

Keep a bounded typed-hypothesis beam and deterministic execution verifier in
the proposed architecture. Report raw, type-filtered, and verifier-assisted
scores separately; freeze public examples and keep hidden cases scoring-only.
The next experiment should add a no-bypass intervention and measure how much
of the verifier gain survives when the parser is forced to emit the ledger
before seeing execution feedback.

## Limitations

- Candidate graphs and public/hidden examples are synthetic.
- The parser uncertainty is simulated, not learned.
- Public execution verification is a test-time compute assumption and can
  overfit if examples are not frozen.
- No coding benchmark or Qwen comparison is run.
