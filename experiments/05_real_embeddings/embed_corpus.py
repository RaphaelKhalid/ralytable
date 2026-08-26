"""Embed a real corpus two ways and cache to disk.

Workflow 1: mean-pooled all-MiniLM-L6-v2 sentence embeddings (D=384).
            This is what every sentence-transformers / RAG pipeline produces.
Workflow 2: bag-of-embeddings -- average of the model's INPUT token embeddings
            for the same sentences (D=384). Classic averaged-word-vector doc rep.

Both are cached as .npy under experiments/05_real_embeddings/cache/ (gitignored).
"""
import os
import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
V = 7600  # ag_news test split, deduped below


def load_corpus():
    from datasets import load_dataset
    ds = load_dataset("fancyzhx/ag_news", split="test")
    seen, texts = set(), []
    for t in ds["text"]:
        t = " ".join(t.split())
        if t and t not in seen:      # exact-dupe removal: a dupe makes a "miss"
            seen.add(t)              # that is not really a miss
            texts.append(t)
    return texts[:V]


def embed(texts, batch=256):
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModel.from_pretrained(MODEL).to(dev).eval()
    tok_emb = model.get_input_embeddings().weight.detach()

    sent, bag = [], []
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            enc = tok(texts[i:i + batch], padding=True, truncation=True,
                      max_length=128, return_tensors="pt").to(dev)
            out = model(**enc).last_hidden_state
            m = enc["attention_mask"].unsqueeze(-1).float()
            sent.append(((out * m).sum(1) / m.sum(1)).float().cpu().numpy())
            # bag-of-embeddings over the same (non-special) tokens
            ids = enc["input_ids"]
            special = (ids == tok.cls_token_id) | (ids == tok.sep_token_id)
            m2 = (m.squeeze(-1) * (~special).float()).unsqueeze(-1)
            te = tok_emb[ids]
            bag.append(((te * m2).sum(1) / m2.sum(1).clamp(min=1)).float().cpu().numpy())
    return np.concatenate(sent), np.concatenate(bag)


def main():
    os.makedirs(CACHE, exist_ok=True)
    texts = load_corpus()
    print(f"corpus: {len(texts)} unique sentences")
    sent, bag = embed(texts)
    np.save(os.path.join(CACHE, "sent.npy"), sent)
    np.save(os.path.join(CACHE, "bag.npy"), bag)
    with open(os.path.join(CACHE, "texts.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(texts))
    print("saved", sent.shape, bag.shape)


if __name__ == "__main__":
    main()
