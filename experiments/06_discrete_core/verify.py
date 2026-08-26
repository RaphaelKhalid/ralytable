"""Separate cross-entropy from the VQ commitment term.

run.py reports val_loss = cross_entropy + commit, so the discrete configs are
penalised by a term the dense baseline does not have -- yet they still reported
LOWER loss and LOWER accuracy than dense, which cannot both be right. This
re-evaluates with the terms separated.
"""
import json, sys, pathlib
import torch, torch.nn.functional as F

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as R
from core import build, optimizer, cosine_lr

data = [json.loads(l) for l in (HERE / "corpus.jsonl").open(encoding="utf-8")]
text, roles = "", []
for ex in data:
    t, r = R.render(ex); text += t; roles += r
vocab = sorted(set(text)); stoi = {c: i for i, c in enumerate(vocab)}
dev = "cuda"
ids = torch.tensor([stoi[c] for c in text], dtype=torch.long, device=dev)
split = int(len(ids) * 0.9)
ctx, bs, steps = 256, 32, 6000

def batch(lo, hi):
    i = torch.randint(lo, max(lo + 1, hi - ctx - 1), (bs,), device=dev)
    return (torch.stack([ids[j:j + ctx] for j in i]),
            torch.stack([ids[j + 1:j + ctx + 1] for j in i]))

print(f"{'config':10} {'CE':>8} {'commit':>8} {'acc':>7} {'params':>10}")
for name, use_vq, n_codes in [("dense", False, 0), ("codes=64", True, 64),
                              ("codes=256", True, 256), ("codes=1024", True, 1024)]:
    torch.manual_seed(0)
    m = build(len(vocab), device=dev, compile_model=False, dim=256, depth=6,
              heads=4, ctx=ctx, n_codes=max(n_codes, 8), bottleneck=use_vq)
    opt = optimizer(m, lr=1e-3)
    for st in range(steps):
        for g in opt.param_groups:
            g["lr"] = cosine_lr(st, steps, steps // 20 + 1, 1e-3)
        x, y = batch(0, split)
        with torch.autocast("cuda", torch.bfloat16):
            _, loss, _ = m(x, y)
        opt.zero_grad(set_to_none=True); loss.backward()
        torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0); opt.step()
    m.eval()
    ce = com = acc = 0.0
    with torch.no_grad():
        for _ in range(30):
            x, y = batch(split, len(ids))
            with torch.autocast("cuda", torch.bfloat16):
                logits, _, _ = m(x, y)
                h = m.emb(x) + m.pos(torch.arange(x.size(1), device=dev))
                for b in m.enc: h = b(h)
                c = m.vq(h)[1].item() if m.bottleneck else 0.0
            ce += F.cross_entropy(logits.reshape(-1, len(vocab)).float(),
                                  y.reshape(-1)).item()
            com += c
            acc += (logits.argmax(-1) == y).float().mean().item()
    n = 30
    print(f"{name:10} {ce/n:8.4f} {com/n:8.4f} {acc/n:7.4f} "
          f"{sum(p.numel() for p in m.parameters()):>10,}")
