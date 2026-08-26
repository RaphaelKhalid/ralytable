"""Extract everything the interpretability page shows, from the trained checkpoint.

The codebook is the only interpretable object this architecture has: 1024 discrete
codes, and every character position in the corpus is assigned to exactly one of
them. This script runs the real corpus through the real checkpoint and records,
per code, what it actually fires on -- contexts, characters, reasoning-step roles
-- plus a 2D PCA layout of the code vectors so the codebook can be drawn.

Nothing here is estimated or illustrative. Every number in the output JSON comes
from a forward pass of `codes1024.pt` over `corpus.jsonl`.

  python experiments/06_discrete_core/export_viz.py

Writes site/codebook.json and web/codebook.json (byte-identical).

WHY THE STRIDED WINDOWS. The model is causal with ctx=256, so the code assigned
to a position depends on the prefix inside its window. A position at offset 3 of
a window has almost no context and gets a code that reflects that, not the text.
So windows overlap by half and only the second half of each window is kept: every
scored position has at least 128 characters of real left-context, exactly as it
would during training on the middle of a sequence.
"""
import collections
import json
import math
import pathlib
import random
import sys

import torch
import torch.nn.functional as F

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import run as R                       # noqa: E402  (render() lives there)
from core import DiscreteCore         # noqa: E402

CKPT = HERE / "codes1024.pt"
CORPUS = HERE / "corpus.jsonl"
OUTS = [ROOT / "site" / "codebook.json", ROOT / "web" / "codebook.json"]

CTX = 256
STRIDE = 128
N_CODES = 1024
CODE_DIM = 32
ROLE_NAMES = ["premise", "derived", "answer"]

CTX_BEFORE = 16                       # characters of left context in an example
CTX_AFTER = 7                         # characters of right context
MAX_EXAMPLES = 20                     # per code, reservoir-sampled not cherry-picked
TOP_CHARS = 8                         # per code, in the character distribution

SEED = 0


# ------------------------------------------------------------------ load

def load():
    if not CKPT.exists():
        sys.exit(f"missing {CKPT}\n  regenerate with: python {HERE/'sample.py'}")
    if not CORPUS.exists():
        sys.exit(f"missing {CORPUS} (it is gitignored; run.py regenerates it)")

    data = [json.loads(l) for l in CORPUS.open(encoding="utf-8")]

    # Reproduce sample.py's text and vocab EXACTLY, or the code indices are
    # meaningless. render() also hands back the per-character role tags.
    parts, roles, bounds = [], [], []
    for ex in data:
        t, r = R.render(ex)
        bounds.append((sum(len(p) for p in parts), len(t)))
        parts.append(t)
        roles += r
    text = "".join(parts)

    blob = torch.load(CKPT, map_location="cpu", weights_only=False)
    vocab = blob["vocab"]
    assert vocab == sorted(set(text)), "vocab mismatch: corpus differs from training"
    assert len(roles) == len(text), "role tags misaligned with text"

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = DiscreteCore(len(vocab), dim=256, depth=6, heads=4, ctx=CTX,
                         n_codes=N_CODES, bottleneck=True).to(dev)
    model.load_state_dict(blob["model"])
    model.eval()
    return data, text, roles, bounds, vocab, model, dev


# ------------------------------------------------------- forward the corpus

@torch.no_grad()
def assign_codes(text, vocab, model, dev):
    """Return a numpy-free list: code index for every character of the corpus.

    -1 marks a position that was never scored (the very tail, and the first
    half of nothing since window 0 is kept whole).
    """
    stoi = {c: i for i, c in enumerate(vocab)}
    ids = torch.tensor([stoi[c] for c in text], dtype=torch.long, device=dev)
    n = len(ids)
    out = torch.full((n,), -1, dtype=torch.long, device=dev)

    starts = list(range(0, max(1, n - CTX + 1), STRIDE))
    if starts[-1] + CTX < n:
        starts.append(n - CTX)

    BATCH = 64
    for b0 in range(0, len(starts), BATCH):
        chunk = starts[b0:b0 + BATCH]
        x = torch.stack([ids[s:s + CTX] for s in chunk])
        with torch.autocast("cuda", torch.bfloat16, enabled=(dev == "cuda")):
            _, _, idx = model(x)
        for row, s in enumerate(chunk):
            keep = 0 if s == 0 else STRIDE     # only well-conditioned positions
            out[s + keep:s + CTX] = idx[row, keep:]
        if b0 % (BATCH * 40) == 0:
            print(f"  windows {b0}/{len(starts)}", flush=True)
    return out.cpu().tolist()


# --------------------------------------------------------------- statistics

def purity_from(pairs_counts):
    """pairs_counts: {code: [n_premise, n_derived, n_answer]} -> majority purity."""
    hits = tot = 0
    for rc in pairs_counts.values():
        hits += max(rc)
        tot += sum(rc)
    return hits / max(tot, 1)


def shuffle_null(codes, roles_at, rng):
    """Purity when code identities are permuted across positions at random.

    This is the number a codebook carrying no role information at all would
    score, and it is what the reported purity must be compared against.
    """
    shuffled = codes[:]
    rng.shuffle(shuffled)
    tab = collections.defaultdict(lambda: [0, 0, 0])
    for c, r in zip(shuffled, roles_at):
        tab[c][r] += 1
    return purity_from(tab)


def pca2(mat):
    """Plain PCA to 2D. No sklearn, no UMAP, no dependency risk."""
    x = mat - mat.mean(0, keepdim=True)
    # torch.pca_lowrank is fine here but SVD on 1024x32 is instant and exact.
    u, s, v = torch.linalg.svd(x, full_matrices=False)
    proj = x @ v[:2].T
    var = (s ** 2) / (s ** 2).sum()
    return proj, float(var[0]), float(var[1])


# -------------------------------------------------------------- generation

@torch.no_grad()
def generate(model, vocab, dev, prompt, n=300, temp=0.7, seed=0):
    torch.manual_seed(seed)
    stoi = {c: i for i, c in enumerate(vocab)}
    idx = torch.tensor([[stoi.get(c, 0) for c in prompt]], device=dev)
    for _ in range(n):
        logits, _, _ = model(idx[:, -CTX:])
        p = F.softmax(logits[0, -1].float() / temp, -1)
        idx = torch.cat([idx, torch.multinomial(p, 1).view(1, 1)], 1)
    return "".join(vocab[int(i)] for i in idx[0])


# --------------------------------------------------------------------- main

def main():
    rng = random.Random(SEED)
    print("loading checkpoint and corpus ...", flush=True)
    data, text, roles, bounds, vocab, model, dev = load()
    print(f"  {len(data)} examples | {len(text):,} chars | alphabet {len(vocab)} | {dev}")

    print("forwarding the corpus through the model ...", flush=True)
    codes = assign_codes(text, vocab, model, dev)

    scored = [i for i, c in enumerate(codes) if c >= 0]
    print(f"  {len(scored):,} scored positions of {len(text):,}")

    # ---- per-code accumulators, single pass
    freq = [0] * N_CODES
    role_tab = [[0, 0, 0] for _ in range(N_CODES)]
    char_tab = [collections.Counter() for _ in range(N_CODES)]
    reservoir = [[] for _ in range(N_CODES)]      # reservoir sampling, not top-k

    for pos in scored:
        c = codes[pos]
        freq[c] += 1
        role_tab[c][roles[pos]] += 1
        char_tab[c][text[pos]] += 1
        res = reservoir[c]
        if len(res) < MAX_EXAMPLES:
            res.append(pos)
        else:
            j = rng.randint(0, freq[c] - 1)       # classic Algorithm R
            if j < MAX_EXAMPLES:
                res[j] = pos

    # ---- corpus-wide role base rates over the SCORED positions
    base = [0, 0, 0]
    for pos in scored:
        base[roles[pos]] += 1
    total = sum(base)
    base_rate = [b / total for b in base]

    # ---- purity, and the null it has to beat
    tab = {c: role_tab[c] for c in range(N_CODES) if freq[c]}
    purity = purity_from(tab)
    codes_scored = [codes[p] for p in scored]
    roles_scored = [roles[p] for p in scored]
    nulls = [shuffle_null(codes_scored, roles_scored, rng) for _ in range(3)]
    null = sum(nulls) / len(nulls)
    print(f"  role purity {purity:.4f} | shuffle null {null:.4f} "
          f"| excess {purity-null:+.4f}")

    # ---- code entropy and live count
    live = sum(1 for f in freq if f)
    p = [f / total for f in freq if f]
    entropy = -sum(q * math.log2(q) for q in p)
    print(f"  live codes {live}/{N_CODES} | entropy {entropy:.2f} bits")

    # ---- 2D layout of the codebook
    cb = model.vq.codes.detach().float().cpu()
    proj, v1, v2 = pca2(cb)
    print(f"  PCA variance explained: PC1 {v1:.3f}, PC2 {v2:.3f}")

    # ---- assemble per-code records
    def ctx_example(pos):
        lo = max(0, pos - CTX_BEFORE)
        hi = min(len(text), pos + CTX_AFTER + 1)
        return {"t": text[lo:hi], "i": pos - lo}     # window, and trigger offset

    codes_out = []
    for c in range(N_CODES):
        f = freq[c]
        rc = role_tab[c]
        codes_out.append({
            "id": c,
            "n": f,
            "x": round(float(proj[c, 0]), 4),
            "y": round(float(proj[c, 1]), 4),
            "roles": rc,
            "chars": [[ch, k] for ch, k in char_tab[c].most_common(TOP_CHARS)],
            "nchars": len(char_tab[c]),
            "ex": [ctx_example(p) for p in sorted(reservoir[c])],
        })

    # ---- one real trace, coloured character by character
    #      pick a fully-scored example of a readable length
    trace = None
    for gi, (start, length) in enumerate(bounds):
        if start >= STRIDE and 260 <= length <= 420 and \
                all(codes[start + k] >= 0 for k in range(length)):
            trace = {
                "example": gi,
                "text": text[start:start + length],
                "codes": codes[start:start + length],
                "roles": roles[start:start + length],
            }
            break
    if trace is None:
        sys.exit("no fully-scored example of a usable length; widen the filter")
    print(f"  trace: example {trace['example']}, {len(trace['text'])} chars, "
          f"{len(set(trace['codes']))} distinct codes")

    # ---- a real generated sample, from this same checkpoint
    print("generating a sample from the checkpoint ...", flush=True)
    sample = generate(model, vocab, dev, "[1] A train travels")

    out = {
        "meta": {
            "generated_by": "experiments/06_discrete_core/export_viz.py",
            "checkpoint": "codes1024.pt",
            "params": sum(p.numel() for p in model.parameters()),
            "n_codes": N_CODES,
            "code_dim": CODE_DIM,
            "dim": 256, "depth": 6, "ctx": CTX, "stride": STRIDE,
            "examples_in_corpus": len(data),
            "chars_in_corpus": len(text),
            "scored_positions": total,
            "alphabet": len(vocab),
            "role_names": ROLE_NAMES,
        },
        "stats": {
            "live_codes": live,
            "entropy_bits": round(entropy, 3),
            "role_purity": round(purity, 4),
            "shuffle_null": round(null, 4),
            "excess": round(purity - null, 4),
            "role_base_rate": [round(b, 4) for b in base_rate],
            "pca_var": [round(v1, 4), round(v2, 4)],
        },
        "codes": codes_out,
        "trace": trace,
        "sample": sample,
    }

    blob = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(blob, encoding="utf-8")
    print(f"\nwrote {len(blob)/1e6:.2f} MB to:")
    for path in OUTS:
        print(f"  {path}")


if __name__ == "__main__":
    main()
