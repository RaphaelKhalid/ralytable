"""Train the best config and actually sample from it, so we can see what it does.

The overnight run reported metrics but saved no checkpoints, so there was no way
to look at the model's output. This retrains codes=1024 and generates.
"""
import json, sys, pathlib, torch, torch.nn.functional as F

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as R
from core import build, optimizer, cosine_lr

data = [json.loads(l) for l in (HERE / "corpus.jsonl").open(encoding="utf-8")]
text = "".join(R.render(ex)[0] for ex in data)
vocab = sorted(set(text)); stoi = {c: i for i, c in enumerate(vocab)}
itos = {i: c for c, i in stoi.items()}
dev = "cuda"
ids = torch.tensor([stoi[c] for c in text], dtype=torch.long, device=dev)
split = int(len(ids) * 0.9)
ctx, bs, steps = 256, 32, 6000

torch.manual_seed(0)
m = build(len(vocab), device=dev, compile_model=False, dim=256, depth=6,
          heads=4, ctx=ctx, n_codes=1024, bottleneck=True)
opt = optimizer(m, lr=1e-3)
for st in range(steps):
    for g in opt.param_groups:
        g["lr"] = cosine_lr(st, steps, steps // 20 + 1, 1e-3)
    i = torch.randint(0, split - ctx - 1, (bs,), device=dev)
    x = torch.stack([ids[j:j + ctx] for j in i])
    y = torch.stack([ids[j + 1:j + ctx + 1] for j in i])
    with torch.autocast("cuda", torch.bfloat16):
        _, loss, _ = m(x, y)
    opt.zero_grad(set_to_none=True); loss.backward()
    torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0); opt.step()
    if st % 1500 == 0:
        print(f"  step {st} loss {loss.item():.3f}", flush=True)

m.eval()
torch.save({"model": m.state_dict(), "vocab": vocab}, HERE / "codes1024.pt")
print(f"\ncheckpoint saved: {(HERE/'codes1024.pt').stat().st_size/1e6:.1f} MB\n")


@torch.no_grad()
def gen(prompt, n=320, temp=0.7):
    idx = torch.tensor([[stoi.get(c, 0) for c in prompt]], device=dev)
    for _ in range(n):
        logits, _, _ = m(idx[:, -ctx:])
        p = F.softmax(logits[0, -1].float() / temp, -1)
        idx = torch.cat([idx, torch.multinomial(p, 1).view(1, 1)], 1)
    return "".join(itos[int(i)] for i in idx[0])


for prompt in ["[1] ", "[1] A train travels"]:
    print("=" * 70)
    print(f"PROMPT: {prompt!r}")
    print("=" * 70)
    print(gen(prompt))
    print()
