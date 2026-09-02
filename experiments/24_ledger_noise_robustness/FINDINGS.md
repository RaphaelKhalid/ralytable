# Findings — Experiment 24

**Content-addressed deduplication earned a narrow robustness win: the typed
ledger recovered 100% of duplicated-fact cases while the typed graph recovered
0%; all architectures failed dropped or mutated facts, so the ledger is not an
error-correcting parser.**

## Evidence

Across five seeds and 120 tasks per seed, mean exact recovery was:

| architecture | reorder | duplicate | drop | mutate |
|---|---:|---:|---:|---:|
| flat sketch | 13.2% | 13.2% | 0.0% | 0.0% |
| entity slots | 37.5% | 0.0% | 0.0% | 0.0% |
| typed program graph | 100.0% | 0.0% | 0.0% | 0.0% |
| typed program ledger | 100.0% | 100.0% | 0.0% | 0.0% |

Seed variation was zero for every architecture/mode except the flat sketch,
whose duplicate and reorder means had a seed standard deviation of 3.7 points.

## Decision

Keep content-addressed deduplication as a small ledger primitive. Do not call
it parser error correction: missing and altered facts remain unrecoverable.
The next parser experiment must model uncertainty explicitly, for example as
multiple typed hypotheses with a verifier selecting only legal graphs.

## Limitations

- Synthetic exact facts are supplied to the representations.
- The duplicate channel is not a model of all parser errors.
- No learned parser, code generation, benchmark, or Qwen comparison is run.
