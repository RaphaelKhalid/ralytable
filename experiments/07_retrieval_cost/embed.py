"""Embed a BEIR corpus + queries with several encoders; cache to .npy.

Usage: python embed.py [dataset]   (dataset in {scifact, nfcorpus})

Everything lands in experiments/07_retrieval_cost/cache/ (gitignored).
Pooling per model follows each model's own card: CLS for bge-*, mean otherwise.
Query prefixes: bge-* wants an instruction prefix for retrieval; e5-style
models would too.  Applied only where the card asks for it.
"""
import os, sys, json
import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

MODELS = {
    "minilm":  dict(hf="sentence-transformers/all-MiniLM-L6-v2", pool="mean", qprefix=""),
    "mpnet":   dict(hf="sentence-transformers/all-mpnet-base-v2", pool="mean", qprefix=""),
    "bge":     dict(hf="BAAI/bge-small-en-v1.5", pool="cls",
                    qprefix="Represent this sentence for searching relevant passages: "),
    "gte":     dict(hf="thenlper/gte-small", pool="mean", qprefix=""),
}

DATASETS = {
    "scifact":  dict(hf="BeIR/scifact",  qrels="BeIR/scifact-qrels",  split="test"),
    "nfcorpus": dict(hf="BeIR/nfcorpus", qrels="BeIR/nfcorpus-qrels", split="test"),
}


def load_beir(name):
    from datasets import load_dataset
    cfg = DATASETS[name]
    corpus = load_dataset(cfg["hf"], "corpus", split="corpus")
    queries = load_dataset(cfg["hf"], "queries", split="queries")
    qrels = load_dataset(cfg["qrels"], split=cfg["split"])

    cids = [str(x) for x in corpus["_id"]]
    ctexts = [(t + ". " + b).strip() if t else b
              for t, b in zip(corpus["title"], corpus["text"])]
    qid2text = {str(i): t for i, t in zip(queries["_id"], queries["text"])}

    # keep only positives (score > 0) whose query text we have
    pos = {}
    cset = set(cids)
    for qid, did, s in zip(qrels["query-id"], qrels["corpus-id"], qrels["score"]):
        if s <= 0:
            continue
        qid, did = str(qid), str(did)
        if qid in qid2text and did in cset:
            pos.setdefault(qid, []).append(did)
    qids = sorted(pos)
    return cids, ctexts, qids, [qid2text[q] for q in qids], pos


@torch.no_grad()
def encode(texts, spec, device, bs=32, maxlen=256):
    tok = AutoTokenizer.from_pretrained(spec["hf"])
    mdl = AutoModel.from_pretrained(spec["hf"]).to(device).eval()
    out = []
    for i in range(0, len(texts), bs):
        b = tok(texts[i:i + bs], padding=True, truncation=True,
                max_length=maxlen, return_tensors="pt").to(device)
        h = mdl(**b).last_hidden_state
        if spec["pool"] == "cls":
            v = h[:, 0]
        else:
            m = b["attention_mask"].unsqueeze(-1).float()
            v = (h * m).sum(1) / m.sum(1).clamp(min=1e-9)
        out.append(v.float().cpu().numpy())
        if i % (bs * 40) == 0:
            print(f"    {i}/{len(texts)}", flush=True)
    del mdl
    if device == "cuda":
        torch.cuda.empty_cache()
    return np.concatenate(out, 0)


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else "scifact"
    device = "cuda" if (torch.cuda.is_available() and
                        os.environ.get("FORCE_CPU") != "1") else "cpu"
    os.makedirs(CACHE, exist_ok=True)
    print(f"[{ds}] device={device}")
    cids, ctexts, qids, qtexts, pos = load_beir(ds)
    print(f"  corpus={len(cids)} queries={len(qids)} "
          f"positives={sum(len(v) for v in pos.values())}")
    with open(os.path.join(CACHE, f"{ds}_meta.json"), "w") as f:
        json.dump(dict(cids=cids, qids=qids, pos=pos), f)

    for key, spec in MODELS.items():
        cp = os.path.join(CACHE, f"{ds}_{key}_corpus.npy")
        qp = os.path.join(CACHE, f"{ds}_{key}_queries.npy")
        if os.path.exists(cp) and os.path.exists(qp):
            print(f"  {key}: cached"); continue
        print(f"  {key}: encoding corpus")
        C = encode(ctexts, spec, device)
        print(f"  {key}: encoding queries")
        Q = encode([spec["qprefix"] + t for t in qtexts], spec, device)
        np.save(cp, C); np.save(qp, Q)
        print(f"  {key}: done {C.shape} {Q.shape}")


if __name__ == "__main__":
    main()
