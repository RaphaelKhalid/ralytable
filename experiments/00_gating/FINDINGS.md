# Gating checks — results

Model sweep over OpenRouter. Total spend: **< $0.01**.

## G1 — is raw reasoning text visible?

Yes, on the open-weight families. `reasoning: {"effort": ...}` returns plaintext at
`message.reasoning`. Anthropic returns a *summary*, not the trace, and OpenAI o-series
returns nothing — both unusable here, since a summary is a description of the
computation rather than the computation.

## G2 — can we prefill a partial reasoning trace? **This was the project-killer risk.**

String-matching a returned prefix is weak evidence, so the test used a *poisoned*
prefix that commits to an arithmetic error (net rate `7+3=10` instead of `7-3=4`).
If prefill genuinely conditions the continuation, the model inherits the error and
answers 6. If it re-derives, it answers 15.

| model | `<think>` prefill | plain assistant-content prefill |
|---|---|---|
| qwen/qwen3-14b | ignored | ignored |
| qwen/qwen3-32b | ignored | ignored |
| deepseek/deepseek-r1-0528 | ignored | ignored |
| **deepseek/deepseek-r1-distill-llama-70b** | ignored | **works** |

Replication on the one positive, n=5 per condition:

- poisoned prefix → answered `6` in **4/5** runs (error propagated)
- neutral prefix → answered `15` in **5/5** runs (control behaves)

**Conclusion: sentence resampling is possible over the API, but only on
`deepseek/deepseek-r1-distill-llama-70b`, and only via plain assistant-content
prefill.** Everything else re-derives from scratch and would have silently produced
garbage importance scores. This constrains model choice for the whole project.

Convenient: this is the same family as the paper's main model (R1-Distill-Qwen-14B).

Note the 1/5 that recovered from the poisoned premise. That is spontaneous error
correction, which is item 4 on the paper's own future-work list, and it is now
measurable here for free.

## G3 — will the model emit dependency annotations?

Yes, essentially perfectly, on the first try. Clean numbered steps with citations:

```
[1] The filling pipe adds 7 liters per minute.
[2] The draining pipe removes 3 liters per minute.
[3] from [1],[2]: The net inflow rate is 7 - 3 = 4 liters per minute.
[4] The tank capacity is 60 liters.
[5] from [3],[4]: Time to fill = 60 / 4 = 15 minutes.
```

Accuracy was unaffected (6/6 correct across all annotated runs).

**Caveat, and it is the useful lesson from this run:** the first parser reported
0 citations on several runs that plainly had them. The model alternates between
`from [1],[2]:` and `From [1] and [2],` and the regex only matched the first.
The measurement instrument was broken before the experiment was. Citation-extraction
needs to be written against real samples and validated by hand, not assumed.

## Costs

One full trace on r1-distill-llama-70b runs about **$0.001**. A 20-sentence trace at
100 resamples is therefore ~$2 — most of the $10 budget on a single problem. Resample
counts must be capped well below 100, or the pilot uses one or two problems only.

## What this settles

1. Model is chosen for us: `deepseek/deepseek-r1-distill-llama-70b`.
2. The black-box approach survives; no forced move to Colab weights.
3. Annotated-CoT (rung 2 of the legibility ladder) is viable with no accuracy cost
   at least on a trivial problem — needs retesting on real MATH difficulty.
