"""Generate matched story completions from every experiment-08 checkpoint.

WHY THIS FILE EXISTS. Experiment 08 measured that the 512-code discrete
bottleneck costs +0.59 val cross-entropy against a parameter-matched dense
control. Perplexity is a proxy. TinyStories exists to measure the thing the
proxy stands in for: whether the generated stories are any good. This script
produces the raw material for that judgement and nothing else -- it does no
scoring, so the generations can be inspected before anyone knows the scores.

EVERY MODEL SEES THE SAME PROMPTS, in the same order, with identical sampling
settings (temperature 0.8, top-k 50, 200 new tokens). The prompts are drawn
from the TinyStories *validation* split -- held out from training -- at story
boundaries found by scanning for the EOS token, so a prompt is the opening of
a real story rather than a fragment cut mid-sentence. They are taken in the
order the RNG produces them; nothing is filtered, inspected or cherry-picked.

A REAL-TEXT CONTROL is emitted alongside, under the name `human`: the genuine
TinyStories continuation of the same prompts. It is written into the same JSON
in the same shape as a model, so the judge cannot tell it apart by structure.
If the judge does not rank it top, the judge is broken and every other number
in this experiment is meaningless.
"""
import argparse, json, pathlib, sys

import numpy as np
import torch
import torch.nn.functional as F

HERE = pathlib.Path(__file__).resolve().parent

# Experiment 08 lives in a separate worktree while its sweep runs. Both the
# checkpoints and the tokenizer/memmap cache belong to it, and neither is
# committed, so the path is a flag with a sensible default rather than an
# import-time constant.
DEFAULT_EXP08 = pathlib.Path(
    r"C:\Users\rapha\AppData\Local\Temp\claude\wt-tinystories\experiments\08_tinystories")

TEMP, TOP_K, MAX_NEW = 0.8, 50, 200
PROMPT_TOKENS = 40


def load_deps(exp08):
    """Import experiment 08's data module and experiment 06's model, in place.

    Both are imported rather than copied: a re-implementation of either would
    be a second thing that can silently drift from the thing that was trained.
    """
    sys.path.insert(0, str(exp08))
    sys.path.insert(0, str(exp08.parent / "06_discrete_core"))
    import data as D
    from core import DiscreteCore
    return D, DiscreteCore


def story_starts(vm, eos_id, n, seed, min_len):
    """Offsets of story openings in the validation memmap.

    Scans a window for EOS tokens; the token after each EOS starts a story.
    Requires the next EOS to be at least `min_len` tokens away, so the prompt
    plus the human continuation both exist within one story and the human
    control is never a concatenation of two unrelated stories.
    """
    window = vm[:6_000_000]
    eos = np.flatnonzero(np.asarray(window) == eos_id)
    starts = eos[:-1] + 1
    lens = np.diff(eos)
    ok = starts[lens >= min_len]
    if len(ok) < n:
        raise SystemExit(f"only {len(ok)} usable stories, need {n}")
    rng = np.random.default_rng(seed)
    return sorted(int(s) for s in rng.choice(ok, size=n, replace=False))


@torch.no_grad()
def generate(model, prompts, ctx, device):
    """Same sampler as experiment 08's run.py: temp 0.8, top-k 50, multinomial."""
    model.eval()
    outs = []
    for p in prompts:
        seq = torch.tensor(p, dtype=torch.long, device=device)[None]
        for _ in range(MAX_NEW):
            with torch.autocast("cuda", torch.bfloat16, enabled=(device == "cuda")):
                logits, _, _ = model(seq[:, -ctx:])
            lg = logits[0, -1].float() / TEMP
            k = min(TOP_K, lg.numel())
            v, i = lg.topk(k)
            nxt = i[torch.multinomial(F.softmax(v, -1), 1)]
            seq = torch.cat([seq, nxt[None]], 1)
        outs.append(seq[0].tolist())
    return outs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp08", type=pathlib.Path, default=DEFAULT_EXP08)
    ap.add_argument("--n-prompts", type=int, default=60)
    ap.add_argument("--seed", type=int, default=90901)
    ap.add_argument("--out", type=pathlib.Path, default=HERE / "generations.json")
    a = ap.parse_args()

    exp08 = a.exp08.resolve()
    if not (exp08 / "ckpt").is_dir():
        raise SystemExit(f"no ckpt/ under {exp08}")
    D, DiscreteCore = load_deps(exp08)

    tok, meta = D.prepare()
    eos_id = meta["eos_id"]
    vm = D.memmap("val")
    starts = story_starts(vm, eos_id, a.n_prompts, a.seed,
                          min_len=PROMPT_TOKENS + MAX_NEW + 1)

    prompts = [[int(t) for t in vm[s:s + PROMPT_TOKENS]] for s in starts]
    prompt_text = [tok.decode(p) for p in prompts]
    human = [tok.decode([int(t) for t in vm[s + PROMPT_TOKENS:
                                            s + PROMPT_TOKENS + MAX_NEW]])
             for s in starts]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    ckpts = sorted((exp08 / "ckpt").glob("*.pt"))
    print(f"{len(ckpts)} checkpoints, {a.n_prompts} prompts, device={device}")

    out = {"meta": {"temperature": TEMP, "top_k": TOP_K, "max_new_tokens": MAX_NEW,
                    "prompt_tokens": PROMPT_TOKENS, "prompt_seed": a.seed,
                    "n_prompts": a.n_prompts, "split": "validation",
                    "vocab_size": meta["vocab_size"],
                    "sampling": "multinomial over top-k logits at temperature"},
           "prompts": prompt_text,
           "completions": {"human": human}}

    for ck in ckpts:
        rid = ck.stem
        blob = torch.load(ck, map_location=device, weights_only=False)
        cfg = blob["cfg"]
        m = DiscreteCore(meta["vocab_size"], dim=cfg["dim"], depth=cfg["depth"],
                         heads=cfg["heads"], ctx=cfg["ctx"],
                         n_codes=max(cfg["n_codes"], 8), code_dim=cfg["code_dim"],
                         bottleneck=cfg["n_codes"] > 0).to(device)
        m.load_state_dict(blob["model"])
        outs = generate(m, prompts, cfg["ctx"], device)
        out["completions"][rid] = [tok.decode(o[PROMPT_TOKENS:]) for o in outs]
        print(f"  {rid}: step {blob['step']}, {len(outs)} completions")
        del m, blob
        torch.cuda.empty_cache()

    # An impossible value is a bug: every arm must have exactly n_prompts
    # non-empty completions, or the judging downstream is comparing ragged sets.
    for name, texts in out["completions"].items():
        assert len(texts) == a.n_prompts, f"{name}: {len(texts)} != {a.n_prompts}"
        assert all(t.strip() for t in texts), f"{name}: empty completion"

    a.out.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {a.out}  ({len(out['completions'])} arms)")


if __name__ == "__main__":
    main()
