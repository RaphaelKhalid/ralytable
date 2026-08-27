# 10_auditing_baseline

How well do simple methods recover a secret held inside a model? This is the
floor for a possible auditing benchmark. Verdict and numbers: `FINDINGS.md`.

## Organisms

Taboo models: a chat model fine-tuned to know one secret English word, hint at
it, and never say it. All are LoRA adapters over an ungated base, so one base
download serves every organism.

- `qwen3-8b` — Qwen/Qwen3-8B + `adamkarvonen/Qwen3-8B-taboo-{word}_50_mix`, 20 words, 4-bit NF4.
- `qwen3-1.7b` — Qwen/Qwen3-1.7B + `bcywinski/qwen3-1.7b-taboo-{word}`, 3 words, bf16.

## Run

```
python organisms.py                      # prefetch base + adapters
python gen_attacks.py                    # regenerate the adversarial bank (cached in git)
python run_blackbox.py --family qwen3-8b
python run_blackbox.py --family qwen3-8b --control
python run_whitebox.py --family qwen3-8b
python analyze.py                        # writes results/tables.md
```

`--control` runs every attack against the base model, which holds no secret.
That is the null: whatever it "recovers" it recovers by accident.

## Files

| file | what |
|---|---|
| `organisms.py` | model loading, the candidate set, the file allowlist that keeps training data out of the cache |
| `attacks.py` | the four prompt banks, with an assertion that none of them contains a candidate word |
| `gen_attacks.py` | one secret-blind LLM call that produced the adversarial bank |
| `scoring.py` | the recovery criterion and the Wilson interval, stated once |
| `run_blackbox.py` | naive, adversarial, prefill, hint elicitation |
| `run_whitebox.py` | logit lens on the hint tokens; caches activations for the probe |
| `analyze.py` | recovery rates, controls, chance baselines, dev/test layer selection |

Model weights, caches and raw results are gitignored.
