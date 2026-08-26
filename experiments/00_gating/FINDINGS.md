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

---

# Correction (same day): G2's conclusion was too narrow

Prompted by the paper's demo site offering five models, including three my test
called impossible. Checked their code instead of guessing.

`generate_rollouts.py` line 247, and the `--provider` default:

```python
api_url = "https://api.novita.ai/v3/openai/completions"
prompt = f"...Problem: {problem['problem']} Solution: \n<think>\n{prefix_without_chunk}"
```

They hit **raw text-completions endpoints at providers directly** — Novita by
default, Together and Fireworks as alternates — passing a `prompt` string rather
than a `messages` array. `--use_openrouter` defaults to False. The response is read
as `result["choices"][0]["text"]`, with no separate `reasoning` field, because no
chat template was applied.

That is the whole trick, and it means **prefill was never a property of the model.
It is a property of the endpoint.** A raw completions endpoint continues whatever
string you hand it, so any model served that way can be prefilled. A chat endpoint
applies a template that opens its own reasoning block, which is what defeated the
first test.

## What I got wrong, and what still stands

Wrong: "only `deepseek/deepseek-r1-distill-llama-70b` supports prefill." That is a
fact about OpenRouter's chat endpoint, not about the models.

Still stands, and re-verified: OpenRouter **also normalises its `/completions`
endpoint** for reasoning models. Sending the same raw `<think>`-prefixed prompt
there still comes back with a populated `reasoning` field and a freshly derived
answer of 15. `reasoning: {"enabled": false}`, `{"max_tokens": 0}` and pinning
`provider: {"order": ["novita"]}` all failed to suppress it. Together and Fireworks
return 404 for this model through OpenRouter. So OpenRouter cannot reproduce the
paper's method on any endpoint, and the chat-endpoint path I found is a workaround,
not the real thing.

## Three routes, in order of preference

1. **Novita directly** (`https://api.novita.ai/v3/openai/completions`). What the
   paper used. Needs a separate key and credit. Unblocks every model on their demo.
2. **OpenRouter chat + `r1-distill-llama-70b` + plain assistant-content prefill.**
   The 4/5 propagation result from the first run is real and needs no new signup,
   but it is undocumented behaviour that could change, and 4/5 is not 5/5.
3. **Don't generate rollouts at all** — see below.

## The rollouts are already public

https://huggingface.co/datasets/uzaymacar/math-rollouts

The full MATH rollout dataset from the paper is released. The baseline replication
therefore costs **$0** and the entire $10 can go to the novel experiment instead.
This should have been the first thing checked, before any API call.
