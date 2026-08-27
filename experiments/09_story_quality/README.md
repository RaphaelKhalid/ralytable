# 09 — Is the discrete model GOOD ENOUGH?

Experiment 08 established that the 512-code discrete bottleneck costs about
+0.59 validation cross-entropy against a parameter-matched dense control on
TinyStories. That is a *proxy* measurement. This experiment asks the question
the proxy stands in for, using the protocol TinyStories was published with:
does a reader — here an LLM judge — notice?

This is deliberately **not** the same question as experiment 08's. 08 asked
"does discrete match dense?" (no, on perplexity). 09 asks "is discrete good
enough?", which has its own preregistered bar.

## The preregistered threshold

Fixed before any generation was looked at, and applied mechanically in
`analyze.py`:

> **Good enough = the discrete model's grammar and consistency scores are
> within noise of the dense model's, even though its perplexity is worse.**

"Within noise" = the 95% CI on the within-prompt dense-minus-discrete
difference contains zero.

## Files

| file | what it is |
|---|---|
| `generate.py` | loads experiment 08's checkpoints, generates matched completions of held-out validation prompts, plus a real-human-text arm |
| `judge.py` | blind LLM judging: absolute 1-10 scores, pairwise A/B/tie, position-bias and human-ceiling controls |
| `analyze.py` | aggregation, confidence intervals, and the ruling on the threshold |
| `samples.py` | writes `samples.md` — blind side-by-side for a human to judge |
| `generations.json` | every generation, committed, so the judging is reproducible and the raw output inspectable |
| `judgements.jsonl` | every judge call and its reply, committed |
| `results.md` | generated tables |
| `samples.md` | blind side-by-side, key at the bottom |
| `FINDINGS.md` | the verdict |

## Running it

```
python generate.py --exp08 <path to experiments/08_tinystories>
python judge.py --show-prompt      # the exact prompts, no model name in them
python judge.py                    # cached and resumable; hard spend cap
python analyze.py
python samples.py
```

`generate.py` needs experiment 08's `ckpt/` and its `cache/` (tokenizer and
memmaps); neither is committed, so its path is a flag. Judging needs
`OPENROUTER_API_KEY` in the repo-root `.env`.

## Controls

- **Human ceiling.** Real held-out TinyStories continuations are judged as if
  they were model completions. If the judge does not rank them top, the judge
  is broken and every other number here is void. This is the most important
  control in the experiment.
- **Position bias.** Which arm appears first in a pairwise comparison is
  randomised by a seeded RNG and recorded, so the judge's preference for the
  first slot is measured, not assumed absent.
- **Same-quality null.** Two dense seeds are compared against each other. They
  are draws from the same distribution, so the truth is 50/50; whatever the
  judge reports there is its noise floor and its bias, and the dense-vs-discrete
  result is read against it.
