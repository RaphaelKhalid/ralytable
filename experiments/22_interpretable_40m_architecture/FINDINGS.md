# Findings — Experiment 22

**The typed program graph and the proposed typed program ledger both recovered
100% of 600 supplied-fact synthetic programs, but the ledger did not beat the
simpler graph; the result supports explicit typed edges as a viable substrate,
not a unique ledger advantage.**

## Evidence

Five seeds (11, 23, 37, 41, 53) evaluated 120 tasks each. The task family
alternated linear chains with branch/merge graphs and shuffled the surface fact
order.

| architecture | learned-parameter budget | exact recovery | branch/merge | relevant change | placebo preserved |
|---|---:|---:|---:|---:|---:|
| flat sketch | 39.6M | 13.2% | 7.7% | 13.2% | 0.0% |
| entity slots | 12.7M | 37.5% | 0.0% | 37.5% | 37.5% |
| typed program graph | 18.4M | 100.0% | 100.0% | 100.0% | 100.0% |
| typed program ledger | 23.6M | 100.0% | 100.0% | 100.0% | 100.0% |

All scores are aggregate means over the five seed-specific task sets. The
within-architecture seed variation was zero for the graph and ledger and was
small for the flat sketch (exact-recovery mean 13.2%, 95% normal-approximation
CI ±3.3 percentage points). The graph and ledger tie because this experiment
does not include ledger-specific operations such as reversible edits,
provenance queries, or deduplicated repeated subgraphs.

## Decision

Keep explicit typed dataflow edges as the baseline substrate for the next
design. Keep content addressing and provenance as an implementation hypothesis,
not as a capability claim. The next useful test is a learned parser with
independently generated paraphrases and adversarial distractors; it must infer
the graph rather than receive exact facts.

## Limitations

- The task generator is synthetic.
- The encoder receives exact typed facts; no natural-language or code model is
  trained.
- The parameter counts are architecture-budget estimates, not trained
  checkpoints.
- No result here can establish parity with Qwen2.5-Coder-27B or any public
  benchmark.
- The probe tests representation sufficiency, not optimization, data quality,
  retrieval, decoding, or runtime cost.
