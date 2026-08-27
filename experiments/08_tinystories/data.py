"""TinyStories data pipeline: BPE -> uint16 memmap on disk -> batches.

WHY NOT EXPERIMENT 06's PIPELINE. run.py in 06 put the entire corpus in a GPU
int64 tensor. TinyStories is ~470M tokens; as int64 that is 3.8 GB, which does
not fit next to a 28M model, its Adam state and activations in 8.6 GB of VRAM.
Here the corpus lives on disk as uint16 (~0.9 GB), is opened with np.memmap so
the OS page cache does the work, and only the sampled batch (a few MB) is ever
moved to the GPU.

WHY A CUSTOM 8k BPE RATHER THAN GPT-2. Both were measured on 4,000 held-out
TinyStories (`python data.py --compare` reproduces it):

    tokenizer            vocab   bytes/token   embedding params @ dim 512
    GPT-2 (tiktoken)     50257       4.09              25.7 M
    ours (BPE, 8192)      8192       4.16               4.2 M

Ours compresses *better* -- 4.16 bytes per token against GPT-2's 4.09, so 1.7%
FEWER tokens -- with one sixth of the vocabulary. That is not a fluke: GPT-2's
merges were fit to web text and spend most of their table on tokens TinyStories
never uses, while 8k merges fit to TinyStories cover its deliberately small
child-level vocabulary almost completely. And the parameter consequence is
decisive: with tied embeddings, GPT-2's vocabulary would be 25.7M of a 28M
budget -- a lookup table with a transformer stapled on, with almost nothing
left in the layers whose bottleneck this experiment exists to measure.
So: custom 8k BPE, on both compression and parameter grounds.

Everything is cached. A rerun of prepare() with the caches present is instant.
"""
import argparse, json, pathlib, sys, time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
CACHE = HERE / "cache"
VOCAB_SIZE = 8192
EOS = "<|endoftext|>"

TOK_JSON = CACHE / f"bpe_{VOCAB_SIZE}.json"
META = CACHE / "meta.json"


def _bin(split):
    return CACHE / f"{split}_{VOCAB_SIZE}.bin"


def load_raw():
    from datasets import load_dataset
    return load_dataset("roneneldan/TinyStories")


def train_tokenizer(ds, n_sample=200_000, seed=0):
    """Byte-level BPE on a sample of the training stories.

    200k stories (~10% of the corpus) is well past the point where the merge
    table stops moving, and training on all 2.1M takes many times longer.
    """
    if TOK_JSON.exists():
        from tokenizers import Tokenizer
        return Tokenizer.from_file(str(TOK_JSON))
    from tokenizers import Tokenizer, models, trainers, pre_tokenizers, decoders
    CACHE.mkdir(parents=True, exist_ok=True)
    print(f"  training BPE (vocab {VOCAB_SIZE}) on {n_sample:,} stories ...", flush=True)
    t0 = time.time()
    tok = Tokenizer(models.BPE(unk_token=None))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=VOCAB_SIZE, special_tokens=[EOS], show_progress=True,
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet())
    rng = np.random.default_rng(seed)
    n = min(n_sample, ds["train"].num_rows)
    idx = rng.choice(ds["train"].num_rows, size=n, replace=False)
    texts = ds["train"].select(idx)["text"]
    tok.train_from_iterator(texts, trainer=trainer, length=n)
    tok.save(str(TOK_JSON))
    print(f"  BPE trained in {time.time()-t0:.0f}s -> {TOK_JSON.name}", flush=True)
    return tok


def tokenize_split(ds, tok, split, eos_id):
    """Encode one split to a flat uint16 file, stories joined by EOS.

    Streamed: encode a batch, append its raw uint16 bytes, drop it. Peak RAM is
    one batch of encodings, not the 470M-token corpus. Written to a .part file
    and renamed at the end, so an interrupted run never leaves a truncated
    cache that a later run would happily train on.
    """
    path = _bin(split)
    if path.exists():
        n = path.stat().st_size // 2
        print(f"  {split}: {n:,} tokens cached")
        return n
    texts = ds[split]["text"]
    print(f"  tokenising {split}: {len(texts):,} stories ...", flush=True)
    t0, B, total = time.time(), 20_000, 0
    tmp = path.with_suffix(".part")
    with tmp.open("wb") as f:
        for i in range(0, len(texts), B):
            enc = tok.encode_batch_fast(texts[i:i + B])
            ids = []
            for e in enc:
                ids.extend(e.ids)
                ids.append(eos_id)
            a = np.asarray(ids, dtype=np.uint16)
            f.write(a.tobytes())
            total += len(a)
            done = min(i + B, len(texts))
            el = time.time() - t0
            msg = (f"    {done:,}/{len(texts):,} stories  {total:,} tokens  "
                   f"{el:.0f}s  eta {el/max(done,1)*(len(texts)-done):.0f}s   ")
            sys.stdout.write(chr(13) + msg)
            sys.stdout.flush()
    tmp.replace(path)
    print(f"\n  {split}: {total:,} tokens -> {path.name} "
          f"({path.stat().st_size/1e9:.2f} GB)", flush=True)
    return total


def prepare():
    """Returns (tokenizer, meta dict). Idempotent and cached."""
    CACHE.mkdir(parents=True, exist_ok=True)
    if META.exists() and TOK_JSON.exists() and _bin("train").exists() and _bin("val").exists():
        from tokenizers import Tokenizer
        meta = json.loads(META.read_text())
        print(f"  cache hit: {meta['train_tokens']:,} train / "
              f"{meta['val_tokens']:,} val tokens, vocab {meta['vocab_size']}")
        return Tokenizer.from_file(str(TOK_JSON)), meta
    ds = load_raw()
    tok = train_tokenizer(ds)
    eos_id = tok.token_to_id(EOS)
    ntr = tokenize_split(ds, tok, "train", eos_id)
    ds2 = {"train": ds["train"], "val": ds["validation"]}   # HF names it "validation"
    nva = tokenize_split(ds2, tok, "val", eos_id)
    meta = {"vocab_size": tok.get_vocab_size(), "eos_id": eos_id,
            "train_tokens": ntr, "val_tokens": nva}
    META.write_text(json.dumps(meta, indent=2))
    return tok, meta


def memmap(split):
    return np.memmap(_bin(split), dtype=np.uint16, mode="r")


def verify(tok, meta, n_preview=200):
    """Fail loudly, before training, if the data is not what we think it is.

    Silent data corruption is the most expensive failure mode there is: the run
    completes, the numbers look plausible, and they mean nothing. Three checks:
    the memmaps are the length the metadata claims, the tokenizer round-trips a
    real story exactly, and a human can read the first 200 decoded characters.
    """
    for split, key in (("train", "train_tokens"), ("val", "val_tokens")):
        p = _bin(split)
        assert p.exists(), f"missing memmap {p}"
        on_disk = p.stat().st_size // 2
        assert on_disk == meta[key], (
            f"{split} memmap has {on_disk:,} tokens, metadata says {meta[key]:,}")
    arr = memmap("train")
    assert int(arr[:100000].max()) < meta["vocab_size"], "token id out of vocab range"
    probe = ('One day, a little girl named Lily found a needle in her room. '
             'She said, "Mom, can you help me?"')
    rt = tok.decode(tok.encode(probe).ids)
    assert rt == probe, f"tokenizer does not round-trip:\n  in  {probe!r}\n  out {rt!r}"
    head = tok.decode([int(t) for t in arr[:120]])
    print(f"  data check OK: {meta['train_tokens']:,} train / {meta['val_tokens']:,} "
          f"val tokens, vocab {meta['vocab_size']}, round-trip exact")
    print(f"  first {n_preview} chars of the training memmap, decoded:")
    print("    | " + head[:n_preview].replace("\n", " / "))
    return head


class Sampler:
    """Random-offset batch sampler over a uint16 memmap.

    Reads uint16 slices, widens to int64 on the CPU, one H2D copy per step.
    At batch 32 x ctx 512 that is 16k tokens, ~130 KB on the wire -- negligible
    against a ~100 ms step.
    """

    def __init__(self, split, ctx, batch, device="cuda", seed=0, limit=None):
        self.data = memmap(split)
        if limit:
            self.data = self.data[:limit]
        self.ctx, self.batch, self.device = ctx, batch, device
        self.rng = np.random.default_rng(seed)
        import torch
        self.torch = torch

    def __call__(self, batch=None):
        torch = self.torch
        b = batch or self.batch
        hi = len(self.data) - self.ctx - 1
        i = self.rng.integers(0, hi, size=b)
        x = np.stack([self.data[j:j + self.ctx] for j in i]).astype(np.int64)
        y = np.stack([self.data[j + 1:j + self.ctx + 1] for j in i]).astype(np.int64)
        return (torch.from_numpy(x).to(self.device, non_blocking=True),
                torch.from_numpy(y).to(self.device, non_blocking=True))


def compare_tokenizers(n=4000):
    """bytes/token for GPT-2 BPE vs ours, on held-out TinyStories."""
    ds = load_raw()
    texts = ds["validation"]["text"][:n]
    nbytes = sum(len(t.encode("utf-8")) for t in texts)
    rows = []
    try:
        import tiktoken
        g = tiktoken.get_encoding("gpt2")
        ng = sum(len(x) for x in g.encode_ordinary_batch(texts))
        rows.append(("GPT-2 (tiktoken)", 50257, nbytes / ng))
    except Exception as e:
        rows.append((f"GPT-2 unavailable ({type(e).__name__})", 0, float("nan")))
    tok = train_tokenizer(ds)
    no = sum(len(e.ids) for e in tok.encode_batch_fast(texts))
    rows.append((f"ours (BPE, {VOCAB_SIZE})", tok.get_vocab_size(), nbytes / no))
    print(f"\n  held-out sample: {n:,} stories, {nbytes:,} bytes\n")
    print(f"  {'tokenizer':<24}{'vocab':>8}{'bytes/token':>14}{'emb par @dim512':>18}")
    for name, v, bpt in rows:
        print(f"  {name:<24}{v:>8}{bpt:>14.2f}{v*512/1e6:>17.1f}M")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", action="store_true",
                    help="bytes/token: GPT-2 vs our BPE, then exit")
    a = ap.parse_args()
    if a.compare:
        compare_tokenizers()
    else:
        tok, meta = prepare()
        verify(tok, meta)
