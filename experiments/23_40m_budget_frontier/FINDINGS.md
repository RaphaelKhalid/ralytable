# Findings — Experiment 23

**All four transparent low-rank ledger configurations fit far below the 40M
learned-parameter ceiling (1.54M–6.21M), but this is only a feasibility result:
the accounting omitted a full code renderer, retrieval index, and training
quality, so it provides no evidence of parity with a 27B coder.**

## Evidence

| configuration | learned parameters | named-mechanism fraction | ledger nodes | modules |
|---|---:|---:|---:|---:|
| byte_lowrank_ledger | 6.21M | 46.8% | 32 | 128 |
| compact_graph_router | 3.38M | 57.5% | 48 | 192 |
| retrieval_heavy_router | 1.54M | 69.8% | 64 | 256 |
| wide_module_bank | 5.11M | 62.4% | 32 | 256 |

The formulas include byte embeddings, low-rank attention/state updates, slot
queries, a module router, module descriptors, schema heads, and normalisation
terms. Every configuration is strictly below the 40,000,000-parameter limit.
The retrieval-heavy variant maximises named-mechanism fraction but is also the
smallest, so this is not a scalar ranking objective.

## Decision

Keep a low-rank typed-ledger core as a viable budget envelope. Spend the next
experiment on robustness and parser error correction, not on filling the
remaining parameter budget with an opaque residual. A future full model must
replace each accounting term with a measured checkpoint count and report the
external retrieval/search/verifier resources separately.

## Claim boundary

Even if a configuration fits below 40M, a neural byte encoder or router is not
fully interpretable merely because its output state is typed. The strict
interpretability claim requires a no-bypass test showing that output changes
only through named state/module paths, plus causal interventions on those
paths. Until then the architecture is T2 structured-state, not T3 fully
interpretable.

## Limitations

- Parameter formulas are design accounting, not measurements from a trained
  implementation.
- No optimizer, data, retrieval index, verifier, latency, or memory cost is
  included.
- No benchmark or comparison with Qwen2.5-Coder-27B was run.
