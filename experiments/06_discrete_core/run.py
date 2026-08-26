"""Overnight run: what does a discrete bottleneck cost, and does it stay legible?

This is Phase 2 in miniature. Same task, same parameter count, same compute; the
only thing that varies is whether the reasoning state is forced through a discrete
codebook and how big that codebook is.

  dense              no bottleneck at all -- the control
  codes=64/256/1024  discrete bottleneck of increasing alphabet size

Two axes are recorded per config:
  CAPABILITY  held-out loss and next-token accuracy
  LEGIBILITY  how many codes are actually live, code entropy, and how well a
              code predicts the reasoning-step ROLE it sits in (premise / derived
              / answer). A code that maps onto a role is a code you can name;
              that is the difference between "discrete" and "legible".

Everything is resumable: the corpus is cached, and each config writes its result
to results.jsonl as it finishes, so an interrupted run loses at most one config.

  python experiments/06_discrete_core/run.py --smoke     # ~2 min, proves it works
  python experiments/06_discrete_core/run.py             # the overnight run
"""
import argparse, json, math, os, pathlib, re, sys, time
import concurrent.futures as cf
import urllib.request, urllib.error

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

MODEL = "~deepseek/deepseek-v4-flash-latest"
API = "https://openrouter.ai/api/v1/chat/completions"
CORPUS = HERE / "corpus.jsonl"
RESULTS = HERE / "results.jsonl"

TOPICS = [
    "rate and work", "percentage change", "linear equations", "areas and perimeters",
    "probability with counting", "sequences and series", "ratios and proportion",
    "speed distance time", "compound interest", "systems of two equations",
    "unit conversion", "averages and weighted averages",
]

GEN_PROMPT = """Write {k} distinct short word problems about {topic}, each with a
full worked solution. Each problem must have a single numeric answer.

Format each one EXACTLY like this, with no other text:

PROBLEM: <the problem>
[1] <a premise taken directly from the problem>
[2] <another premise>
[3] from [1],[2]: <a derived step>
[4] from [3]: <another derived step>
ANSWER: <number>

Rules: premises cite nothing. Every derived step cites the steps it uses. Keep
each step to one short sentence."""


def key():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip()
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k:
        sys.exit("no OPENROUTER_API_KEY in .env or environment")
    return k


def call(topic, k, api_key):
    # reasoning OFF: this model thinks by default and will spend the entire
    # token budget on reasoning, returning empty content. We want output, not
    # deliberation, and turning it off is faster and cheaper too.
    body = {"model": MODEL, "temperature": 0.9, "max_tokens": 4000,
            "reasoning": {"enabled": False},
            "messages": [{"role": "user",
                          "content": GEN_PROMPT.format(k=k, topic=topic)}]}
    req = urllib.request.Request(
        API, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.load(r)
        m = d["choices"][0]["message"]
        # fall back to the reasoning channel if content came back empty
        return (m.get("content") or m.get("reasoning") or "",
                float((d.get("usage") or {}).get("cost") or 0))
    except Exception as e:
        return "", 0.0


BLOCK = re.compile(r"PROBLEM:(.*?)ANSWER:\s*([-\d.,/]+)", re.S)
STEP = re.compile(r"^\[(\d+)\]\s*(?:from\s*((?:\[\d+\][,\s and]*)+):)?\s*(.*)$", re.M)


def parse(text):
    out = []
    for m in BLOCK.finditer(text):
        body, answer = m.group(1), m.group(2).strip()
        steps = []
        for s in STEP.finditer(body):
            deps = [int(x) for x in re.findall(r"\[(\d+)\]", s.group(2) or "")]
            content = s.group(3).strip()
            if content:
                steps.append({"id": int(s.group(1)), "deps": deps, "text": content})
        if len(steps) >= 3 and any(s["deps"] for s in steps):
            out.append({"steps": steps, "answer": answer})
    return out


def build_corpus(target, api_key, workers=12):
    have = []
    if CORPUS.exists():
        have = [json.loads(l) for l in CORPUS.open(encoding="utf-8")]
    if len(have) >= target:
        print(f"  corpus: {len(have)} examples cached")
        return have
    print(f"  corpus: {len(have)} cached, generating up to {target}")
    spend, t0 = 0.0, time.time()
    with CORPUS.open("a", encoding="utf-8") as f:
        while len(have) < target:
            jobs = [(TOPICS[i % len(TOPICS)], 8, api_key) for i in range(workers)]
            with cf.ThreadPoolExecutor(workers) as ex:
                for text, cost in ex.map(lambda a: call(*a), jobs):
                    spend += cost
                    for ex_ in parse(text):
                        have.append(ex_)
                        f.write(json.dumps(ex_) + "\n")
            f.flush()
            print(f"    {len(have)}/{target}  ${spend:.4f}  {time.time()-t0:.0f}s", flush=True)
            if spend > 3.0:
                print("    stopping: $3 generation cap reached")
                break
    return have


# ---------------------------------------------------------------- training

def render(ex):
    """Flatten one example to text, and tag each character with its step role."""
    ROLES = {"premise": 0, "derived": 1, "answer": 2}
    parts, roles = [], []
    for s in ex["steps"]:
        line = f"[{s['id']}] " + (f"from {','.join(f'[{d}]' for d in s['deps'])}: "
                                  if s["deps"] else "") + s["text"] + "\n"
        parts.append(line)
        roles += [ROLES["derived"] if s["deps"] else ROLES["premise"]] * len(line)
    tail = f"ANSWER: {ex['answer']}\n\n"
    parts.append(tail)
    roles += [ROLES["answer"]] * len(tail)
    return "".join(parts), roles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="tiny run to prove it works")
    a = ap.parse_args()

    import torch
    import torch.nn.functional as F
    from core import build, optimizer, cosine_lr

    api_key = key()
    n_corpus = 60 if a.smoke else 4000
    steps = 150 if a.smoke else 6000
    configs = ([("dense", False, 0), ("codes=64", True, 64)] if a.smoke else
               [("dense", False, 0), ("codes=64", True, 64),
                ("codes=256", True, 256), ("codes=1024", True, 1024)])
    dim, depth, ctx, bs = (128, 2, 128, 16) if a.smoke else (256, 6, 256, 32)

    print("=" * 66)
    print(f"{'SMOKE' if a.smoke else 'OVERNIGHT'} RUN   "
          f"{len(configs)} configs x {steps} steps")
    print("=" * 66)

    data = build_corpus(n_corpus, api_key)
    if len(data) < 10:
        sys.exit("FAIL: corpus too small; check the API")

    text_all, role_all = "", []
    for ex in data:
        t, r = render(ex)
        text_all += t
        role_all += r
    vocab = sorted(set(text_all))
    stoi = {c: i for i, c in enumerate(vocab)}
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    ids = torch.tensor([stoi[c] for c in text_all], dtype=torch.long, device=dev)
    roles = torch.tensor(role_all, dtype=torch.long, device=dev)
    split = int(len(ids) * 0.9)
    print(f"  {len(data)} examples | {len(ids):,} chars | alphabet {len(vocab)} | {dev}")

    def batch(lo, hi):
        i = torch.randint(lo, max(lo + 1, hi - ctx - 1), (bs,), device=dev)
        x = torch.stack([ids[j:j + ctx] for j in i])
        y = torch.stack([ids[j + 1:j + ctx + 1] for j in i])
        r = torch.stack([roles[j:j + ctx] for j in i])
        return x, y, r

    for name, use_vq, n_codes in configs:
        t0 = time.time()
        torch.manual_seed(0)
        model = build(len(vocab), device=dev, compile_model=not a.smoke,
                      dim=dim, depth=depth, heads=4, ctx=ctx,
                      n_codes=max(n_codes, 8), bottleneck=use_vq)
        opt = optimizer(model, lr=3e-3 if a.smoke else 1e-3)
        nparam = sum(p.numel() for p in model.parameters())
        print(f"\n  [{name}] {nparam/1e6:.2f}M params")

        for st in range(steps):
            for g in opt.param_groups:
                g["lr"] = cosine_lr(st, steps, steps // 20 + 1,
                                    3e-3 if a.smoke else 1e-3)
            x, y, _ = batch(0, split)
            with torch.autocast("cuda", torch.bfloat16, enabled=(dev == "cuda")):
                _, loss, _ = model(x, y)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            if st % max(1, steps // 6) == 0:
                print(f"    step {st:>5}  loss {loss.item():.3f}", flush=True)

        # ---- evaluate: capability, and whether codes mean anything
        model.eval()
        vl, acc, nb = 0.0, 0.0, 20
        codes_seen, code_role = [], []
        with torch.no_grad():
            for _ in range(nb):
                x, y, r = batch(split, len(ids))
                with torch.autocast("cuda", torch.bfloat16, enabled=(dev == "cuda")):
                    logits, loss, idx = model(x, y)
                vl += loss.item()
                acc += (logits.argmax(-1) == y).float().mean().item()
                if idx is not None:
                    codes_seen.append(idx.flatten())
                    code_role.append(r.flatten())
        vl, acc = vl / nb, acc / nb

        live = ent = purity = float("nan")
        if codes_seen:
            c = torch.cat(codes_seen)
            rr = torch.cat(code_role)
            counts = torch.bincount(c, minlength=max(n_codes, 8)).float()
            p = counts / counts.sum()
            nz = p[p > 0]
            live = int((counts > 0).sum())
            ent = float(-(nz * nz.log2()).sum())
            # legibility proxy: can a code be named? majority role per code.
            hits = tot = 0
            for k in c.unique():
                m = c == k
                hits += int(torch.bincount(rr[m], minlength=3).max())
                tot += int(m.sum())
            purity = hits / max(tot, 1)

        rec = {"config": name, "params": nparam, "val_loss": round(vl, 4),
               "val_acc": round(acc, 4), "live_codes": live,
               "code_entropy_bits": None if math.isnan(ent) else round(ent, 3),
               "role_purity": None if math.isnan(purity) else round(purity, 4),
               "n_codes": n_codes, "steps": steps, "seconds": round(time.time() - t0, 1),
               "smoke": a.smoke}
        with RESULTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"    -> val_loss {vl:.3f} | acc {acc:.3f} | live {live}/{n_codes} "
              f"| entropy {ent:.2f} bits | role purity {purity:.3f} "
              f"| {time.time()-t0:.0f}s", flush=True)

    print("\n" + "=" * 66)
    print(f"done. results appended to {RESULTS}")
    print("=" * 66)


if __name__ == "__main__":
    main()
