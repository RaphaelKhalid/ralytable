"""60-second smoke test for the whole overnight pipeline.

Exercises every moving part end to end, small enough to watch:

  1. DeepSeek V4 Flash generates reasoning with EXPLICIT step dependencies
     ("[3] from [1],[2]: ..."), so the training signal carries structure and
     not just prose.
  2. Those traces are tokenised into a tiny fixed alphabet.
  3. A discrete-bottleneck model trains on them: soft encoder -> VQ codebook
     -> decoder. This is the "soft perception, hard reasoning" thesis in
     miniature; the codebook is the enumerable internal alphabet.
  4. Loss and CODEBOOK USAGE are reported. Usage is the one that matters:
     codebook collapse (most codes dead) is the known failure mode of
     discrete bottlenecks and it is silent otherwise.

Run:  python experiments/06_discrete_core/smoke.py
Pass condition is printed at the end. If it fails, the overnight run would
have failed too, eight hours later.
"""
import json, os, pathlib, re, sys, time, urllib.request, urllib.error
import concurrent.futures as cf

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODEL = "~deepseek/deepseek-v4-flash-latest"
API = "https://openrouter.ai/api/v1/chat/completions"
N_SAMPLES = 8
STEPS = 200

PROBLEMS = [
    "A tank fills at 7 L/min and drains at 3 L/min. It holds 60 L. How long to fill?",
    "A train travels 240 km in 3 hours. How far in 5 hours at the same speed?",
    "A shirt costs $40 after a 20% discount. What was the original price?",
    "Three consecutive integers sum to 72. What is the largest?",
    "A rectangle has perimeter 34 and width 6. What is its area?",
    "If 5 machines make 5 widgets in 5 minutes, how long for 100 machines to make 100?",
    "A jar has 3 red and 5 blue marbles. Two are drawn without replacement. P(both red)?",
    "A car depreciates 15% per year from $20000. What is it worth after 2 years?",
]

SUFFIX = """

Reason in numbered steps. Every step that uses earlier steps must cite them.
Use exactly this format, one step per line, nothing else:

[1] <statement>
[2] <statement>
[3] from [1],[2]: <statement>

End with a final line: ANSWER: <number>"""


def key():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip()
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k:
        sys.exit("FAIL: no OPENROUTER_API_KEY in .env or environment")
    return k


KEY = key()


def generate(problem):
    body = {"model": MODEL, "temperature": 0.7,
            "messages": [{"role": "user", "content": problem + SUFFIX}]}
    req = urllib.request.Request(
        API, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"error": repr(e)[:200]}
    m = d["choices"][0]["message"]
    return {"text": m.get("content") or "", "cost": (d.get("usage") or {}).get("cost")}


STEP_RE = re.compile(r"^\[(\d+)\]\s*(?:from\s*((?:\[\d+\][,\s]*)+):)?\s*(.*)$", re.M)


def parse_steps(text):
    """Return [(step_id, [dep_ids], content)]. Tolerant of 'from [1] and [2],'."""
    out = []
    for m in STEP_RE.finditer(text):
        deps = [int(x) for x in re.findall(r"\[(\d+)\]", m.group(2) or "")]
        out.append((int(m.group(1)), deps, m.group(3).strip()))
    return out


def main():
    t0 = time.time()
    print("=" * 62)
    print("STAGE 1  generate structured reasoning from DeepSeek V4 Flash")
    print("=" * 62)
    with cf.ThreadPoolExecutor(N_SAMPLES) as ex:
        results = list(ex.map(generate, PROBLEMS[:N_SAMPLES]))

    errs = [r for r in results if "error" in r]
    if errs:
        print(f"  FAIL: {len(errs)}/{len(results)} API calls failed")
        print("  first error:", errs[0]["error"])
        sys.exit(1)

    traces, n_steps, n_cited = [], 0, 0
    for r in results:
        steps = parse_steps(r["text"])
        if steps:
            traces.append(steps)
            n_steps += len(steps)
            n_cited += sum(1 for _, d, _ in steps if d)
    cost = sum(float(r.get("cost") or 0) for r in results)
    print(f"  {len(traces)}/{N_SAMPLES} traces parsed | {n_steps} steps | "
          f"{n_cited} carry citations | ${cost:.5f} | {time.time()-t0:.1f}s")
    if len(traces) < N_SAMPLES // 2:
        sys.exit("  FAIL: fewer than half the traces parsed; format is not holding")
    if n_cited == 0:
        sys.exit("  FAIL: no dependency citations at all; the structure signal is absent")
    print("  sample:", " / ".join(c[:34] for _, _, c in traces[0][:2]))

    print()
    print("=" * 62)
    print("STAGE 2  train a discrete-bottleneck model on those traces")
    print("=" * 62)
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  device: {dev}"
          f"{' (' + torch.cuda.get_device_name(0) + ')' if dev == 'cuda' else ''}")
    if dev == "cpu":
        print("  WARN: no GPU; the overnight run needs one")

    # tiny character alphabet -- the enumerable-alphabet premise, in miniature
    text = "\n\n".join("\n".join(f"[{i}] {c}" for i, _, c in t) for t in traces)
    vocab = sorted(set(text))
    stoi = {c: i for i, c in enumerate(vocab)}
    data = torch.tensor([stoi[c] for c in text], dtype=torch.long, device=dev)
    print(f"  alphabet: {len(vocab)} symbols | corpus: {len(data)} tokens")

    D, CODES, CTX = 128, 64, 64

    class DiscreteCore(nn.Module):
        """Soft encoder -> discrete code -> decoder. Straight-through VQ."""

        def __init__(self):
            super().__init__()
            self.emb = nn.Embedding(len(vocab), D)
            self.pos = nn.Embedding(CTX, D)
            self.enc = nn.GRU(D, D, batch_first=True)
            self.codebook = nn.Embedding(CODES, D)
            self.dec = nn.Linear(D, len(vocab))

        def forward(self, x):
            h, _ = self.enc(self.emb(x) + self.pos(torch.arange(x.size(1), device=x.device)))
            # nearest codebook entry
            d = (h.pow(2).sum(-1, keepdim=True)
                 - 2 * h @ self.codebook.weight.T
                 + self.codebook.weight.pow(2).sum(-1))
            idx = d.argmin(-1)
            q = self.codebook(idx)
            vq = F.mse_loss(q, h.detach()) + 0.25 * F.mse_loss(h, q.detach())
            q = h + (q - h).detach()          # straight-through
            return self.dec(q), vq, idx

    torch.manual_seed(0)
    model = DiscreteCore().to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3)
    print(f"  params: {sum(p.numel() for p in model.parameters()):,} | "
          f"codebook: {CODES} codes")

    losses, first = [], None
    for step in range(STEPS):
        i = torch.randint(0, max(1, len(data) - CTX - 1), (32,), device=dev)
        x = torch.stack([data[j:j + CTX] for j in i])
        y = torch.stack([data[j + 1:j + CTX + 1] for j in i])
        logits, vq, idx = model(x)
        loss = F.cross_entropy(logits.reshape(-1, len(vocab)), y.reshape(-1)) + vq
        opt.zero_grad(); loss.backward(); opt.step()
        losses.append(loss.item())
        if first is None:
            first = loss.item()
        if step % 50 == 0 or step == STEPS - 1:
            used = idx.unique().numel()
            print(f"  step {step:>4}  loss {loss.item():.3f}  "
                  f"codes used {used:>3}/{CODES}")

    final = sum(losses[-20:]) / 20
    used = idx.unique().numel()

    print()
    print("=" * 62)
    print(f"VERDICT   ({time.time()-t0:.1f}s total, ${cost:.5f} spent)")
    print("=" * 62)
    checks = [
        ("API returns parseable structured reasoning", len(traces) >= N_SAMPLES // 2),
        ("dependency citations present in the signal", n_cited > 0),
        ("GPU available", dev == "cuda"),
        ("loss decreased", final < first * 0.9),
        ("codebook not collapsed (>25% codes live)", used > CODES * 0.25),
    ]
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n  loss {first:.3f} -> {final:.3f} | codes live {used}/{CODES}")
    ok = all(c[1] for c in checks)
    print(f"\n  {'READY for the overnight run.' if ok else 'NOT READY: fix the FAILs above.'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
