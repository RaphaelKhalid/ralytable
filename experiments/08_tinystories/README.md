# 08 — TinyStories: what a discrete bottleneck costs, with error bars

Experiment 06 asked this on a synthetic corpus we wrote ourselves, at character
level, with one seed per config. This asks it on a published benchmark, with
subword tokens, three seeds and confidence intervals.

## Files

| file | what it is |
|---|---|
| `data.py` | downloads TinyStories, trains an 8k BPE, writes uint16 memmaps, samples batches, verifies the data |
| `run.py` | the sweep: parameter-match check, compute budget, training, checkpointing, eval, generation |
| `dashboard.py` | dependency-free live dashboard on `http://localhost:7777` |
| `wb.py` | optional Weights & Biases mirror (on by default, `--no-wandb` to disable) |
| `analyze.py` | aggregates `results.jsonl` into the tables and figure in FINDINGS.md |
| `results.jsonl` | one JSON object per finished run — committed |
| `generations/` | model continuations of held-out prompts, for a judge to be run later — committed |

Caches, checkpoints, `metrics.jsonl`, `train.log` and `wandb/` are gitignored.

## Running it

```
python data.py                 # one-time: ~5 min, 0.93 GB of memmap. Cached after.
python data.py --compare       # bytes/token: GPT-2 vs our 8k BPE
python run.py --smoke          # whole pipeline end to end, under 3 minutes
python run.py                  # the real sweep
python run.py --resume         # skip finished (config, seed) pairs, resume the partial one
python analyze.py              # tables + gap.png
```

Watching it:

- **Local dashboard** at `http://localhost:7777` — no account, no dependency.
  Loss curves per run, step/ETA, tokens/s, GPU memory, finished-run table.
  `--no-dashboard` turns it off. After the sweep it serves the final table for
  60 s and then the process exits (`--serve-forever` to keep it up).
- **Weights & Biases** is ON by default, project `ralytable`, one run per seed
  grouped by config. It needs `wandb login` (or `WANDB_API_KEY`) once. Missing
  auth prints one line and training continues; `--no-wandb` disables it. Every
  W&B call is wrapped — a network drop degrades to local-only, silently.
- **`train.log`** gets a newline-delimited line every 30 s, so `tail -f` and
  `Get-Content -Wait` both show something. The `\r` progress bar is
  console-only and never reaches the file.
- **`metrics.jsonl`** gets one JSON object per evaluation, analysable mid-run.

Creating a file named `STOP` in this directory ends the run cleanly at the next
checkpoint, keeping everything already written.

## Hardening

- **OOM** halves the micro-batch and doubles gradient accumulation, so the
  effective batch — and therefore the experiment — is unchanged. Logged, then
  training continues.
- **Divergence** (non-finite loss, or CE above its initial value for 200
  consecutive steps after the warmup) aborts that config only, records the
  reason in `results.jsonl`, and moves to the next.
- **Checkpoints** every 1000 steps *or* every 5 minutes, whichever comes first,
  plus one at the end of every run, written to a `.tmp` and renamed so a crash
  mid-write cannot leave a corrupt file.
- **Data verification** before the first step: memmap lengths must match the
  metadata, token ids must be in range, the tokenizer must round-trip a real
  story exactly, and the first 200 decoded characters are printed for a human
  to eyeball.
