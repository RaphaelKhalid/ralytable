"""What does a discrete bottleneck cost on a REAL corpus, with error bars?

Experiment 06 found that a VQ bottleneck cost ~3 points of top-1 accuracy at
matched parameters -- on a synthetic corpus we generated ourselves, with one
seed per config and no confidence interval. That is weak evidence twice over.
This is the same question asked properly:

  CORPUS      TinyStories (Eldan & Li 2023, arXiv:2305.07759), a published
              benchmark designed for exactly this parameter scale.
  TOKENIZER   subword BPE, not characters (see data.py for why 8k and not GPT-2).
  SEEDS       3 per config, reported as mean with a 95% interval, never a
              single number.
  LOSSES      cross-entropy and the VQ commitment term are recorded and
              reported SEPARATELY. Summing them is what let 06's discrete
              configs look better and worse at the same time. The optimiser
              still descends the sum -- that is what training a VQ means -- but
              nothing is ever *reported* as a sum.
  CONTROL     dense, at parameters matched to within 1%, verified and printed.

Usage:
  python run.py --smoke          # whole pipeline end to end, <3 min
  python run.py                  # the real thing
  python run.py --resume         # pick up after a crash
  touch STOP                     # stop cleanly at the next checkpoint

A live dashboard is served at http://localhost:7777 (see dashboard.py), and
train.log gets a newline-delimited progress line every 30 s so `tail -f` and
`Get-Content -Wait` both show something.
"""
import argparse, json, math, os, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "experiments" / "06_discrete_core"))

import numpy as np
import torch
import torch.nn.functional as F

import data as D
from dashboard import Dashboard
from wb import WandB
from core import DiscreteCore, optimizer, cosine_lr   # exp 06's architecture, imported

CKPT = HERE / "ckpt"
GEN = HERE / "generations"
RESULTS = HERE / "results.jsonl"
METRICS = HERE / "metrics.jsonl"
TRAINLOG = HERE / "train.log"
STOP = HERE / "STOP"


# ------------------------------------------------------------------ utilities

def hms(s):
    s = int(max(s, 0))
    return f"{s//3600}h{(s%3600)//60:02d}m{s%60:02d}s"


def bar(done, total, width=28):
    f = int(width * done / max(total, 1))
    return "[" + "#" * f + "-" * (width - f) + "]"


def logline(msg):
    """Newline-delimited, tailable. The console gets a \\r bar; the FILE never does."""
    stamp = time.strftime("%H:%M:%S")
    with TRAINLOG.open("a", encoding="utf-8") as f:
        f.write(f"{stamp}  {msg}\n")


def jsonl(path, rec):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def mean_ci(xs, conf=0.95):
    """Mean and half-width of a 95% interval, Student-t, tiny-n honest.

    With n=3 the t multiplier is 4.303, not 1.96. Using the normal quantile at
    n=3 understates the interval by more than a factor of two, which is exactly
    the sort of quiet overclaim this repo keeps having to walk back.
    """
    xs = [float(x) for x in xs]
    n = len(xs)
    m = sum(xs) / n
    if n < 2:
        return m, float("nan")
    sd = (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5
    t = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571,
         7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}.get(n, 1.96)
    return m, t * sd / (n ** 0.5)


# ------------------------------------------------------------------ the model

def make_model(cfg, vocab, device):
    m = DiscreteCore(vocab, dim=cfg["dim"], depth=cfg["depth"], heads=cfg["heads"],
                     ctx=cfg["ctx"], n_codes=max(cfg["n_codes"], 8),
                     code_dim=cfg["code_dim"], bottleneck=cfg["n_codes"] > 0).to(device)
    return m


def n_params(m):
    return sum(p.numel() for p in m.parameters())


class CommitProbe:
    """Read the VQ commitment term straight off the module, never by subtraction.

    core.py folds cross_entropy + commit into one returned scalar. The obvious
    move is commit = total - ce. It does not work: `total` is computed under
    bf16 autocast and our `ce` is recomputed in fp32, so the difference carries
    ~1e-3 of rounding noise -- the SAME order as the real commitment term, and
    it made the dense control report a nonzero "commit loss" in the smoke run,
    which is impossible (dense has no codebook). A forward hook on the VQ
    module returns the exact tensor instead, and dense reports exactly 0.0.
    """

    def __init__(self, model):
        self.v = 0.0
        self.on = bool(getattr(model, "bottleneck", False))
        if self.on:
            model.vq.register_forward_hook(self._hook)

    def _hook(self, mod, inp, out):
        self.v = float(out[1].detach())

    def read(self):
        return self.v if self.on else 0.0


# ------------------------------------------------------------------ evaluation

@torch.no_grad()
def evaluate(model, sampler, n_batches, device, n_codes, probe=None):
    model.eval()
    ce_s = acc_s = commit_s = 0.0
    counts = torch.zeros(max(n_codes, 8), device=device)
    for _ in range(n_batches):
        x, y = sampler()
        with torch.autocast("cuda", torch.bfloat16, enabled=(device == "cuda")):
            logits, total, idx = model(x, y)
        ce = F.cross_entropy(logits.reshape(-1, logits.size(-1)).float(), y.reshape(-1))
        ce_s += ce.item()
        commit_s += (probe.read() if probe is not None else 0.0)
        acc_s += (logits.argmax(-1) == y).float().mean().item()
        if idx is not None:
            counts += torch.bincount(idx.flatten(), minlength=counts.numel()).float()
    model.train()
    ce, acc, commit = ce_s / n_batches, acc_s / n_batches, commit_s / n_batches
    live = ent = None
    if n_codes > 0:
        p = counts / counts.sum().clamp(min=1)
        nz = p[p > 0]
        live = int((counts > 0).sum())
        ent = float(-(nz * nz.log2()).sum())
    return {"val_ce": ce, "val_acc": acc, "val_commit": commit,
            "val_ppl": math.exp(min(ce, 20)), "live_codes": live,
            "code_entropy_bits": ent}


@torch.no_grad()
def generate(model, prompts, ctx, max_new=120, temp=0.8, top_k=50, device="cuda"):
    """Greedy-ish sampling, one prompt at a time. Only used at the end of a run."""
    model.eval()
    outs = []
    for p in prompts:
        seq = torch.tensor(p, dtype=torch.long, device=device)[None]
        for _ in range(max_new):
            with torch.autocast("cuda", torch.bfloat16, enabled=(device == "cuda")):
                logits, _, _ = model(seq[:, -ctx:])
            lg = logits[0, -1].float() / temp
            k = min(top_k, lg.numel())
            v, i = lg.topk(k)
            probs = F.softmax(v, -1)
            nxt = i[torch.multinomial(probs, 1)]
            seq = torch.cat([seq, nxt[None]], 1)
        outs.append(seq[0].tolist())
    model.train()
    return outs


WORD = __import__("re").compile(r"[a-z']+")


def surface_stats(texts):
    """Cheap, local, judge-free statistics of generated text.

    Every one of these is also computed on REAL held-out TinyStories in the same
    call site, because none of them means anything without knowing what the
    corpus itself scores. A model that scored 0.0 on repetition would be
    suspicious, not good -- real text repeats.
    """
    toks = []
    for t in texts:
        toks.append(WORD.findall(t.lower()))
    flat = [w for t in toks for w in t]
    if len(flat) < 10:
        return {"distinct_2": 0.0, "type_token": 0.0, "mean_word_len": 0.0}
    bg = set()
    nbg = 0
    for t in toks:
        for a, b in zip(t, t[1:]):
            bg.add((a, b))
            nbg += 1
    return {"distinct_2": len(bg) / max(nbg, 1),
            "type_token": len(set(flat)) / len(flat),
            "mean_word_len": sum(len(w) for w in flat) / len(flat)}


def oov_rate(texts, vocab_words):
    flat = [w for t in texts for w in WORD.findall(t.lower())]
    if not flat:
        return 0.0
    return sum(w not in vocab_words for w in flat) / len(flat)


# ------------------------------------------------------------------ one run

def train_one(cfg, seed, args, tok, meta, dash, wb, budget, run_idx, n_runs, gstart):
    """Train one (config, seed) to completion. Returns the result record."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    rid = f"{cfg['name']}_s{seed}"
    torch.manual_seed(seed)
    np.random.seed(seed)

    model = make_model(cfg, meta["vocab_size"], device)
    probe = CommitProbe(model)
    opt = optimizer(model, lr=args.lr, wd=0.1)
    nparam = n_params(model)
    steps = budget["steps"]
    micro, accum = budget["batch"], 1
    start_step = 0

    ck = CKPT / f"{rid}.pt"
    if args.resume and ck.exists():
        st = torch.load(ck, map_location=device, weights_only=False)
        model.load_state_dict(st["model"])
        opt.load_state_dict(st["opt"])
        start_step = st["step"]
        micro, accum = st.get("micro", micro), st.get("accum", accum)
        print(f"  resumed {rid} at step {start_step}", flush=True)
        logline(f"RESUME {rid} step={start_step}")

    train = D.Sampler("train", cfg["ctx"], micro, device, seed=seed,
                      limit=budget.get("data_limit"))
    val = D.Sampler("val", cfg["ctx"], budget["batch"], device, seed=1234)

    dash.set_run(name=cfg["name"], seed=seed, total=steps, step=start_step,
                 params=nparam, batch=micro, accum=accum, ce=None, commit=None,
                 val_ce=None, live_codes=None, tps=None, gpu_gb=None)
    dash.set(phase=f"training {rid}", run_index=run_idx, n_runs=n_runs)
    wb.start(name=f"{cfg['name'].replace('=','')}-s{seed}", group=cfg["name"],
             config={"params": nparam, "dim": cfg["dim"], "depth": cfg["depth"],
                     "heads": cfg["heads"], "vocab_size": meta["vocab_size"],
                     "n_codes": cfg["n_codes"], "code_dim": cfg["code_dim"],
                     "batch": micro, "accum": accum, "ctx": cfg["ctx"],
                     "steps": steps, "lr": args.lr, "seed": seed,
                     "tokens_planned": steps * micro * accum * cfg["ctx"],
                     "smoke": args.smoke})
    if wb.url():
        print(f"  wandb: {wb.url()}", flush=True)
        logline(f"WANDB {rid} {wb.url()}")

    t0 = time.time()
    last_ck = last_log = time.time()
    ce_hist, first_ce, bad = [], None, 0
    status, note = "ok", ""
    tokens_done = 0
    model.train()

    st = start_step
    while st < steps:
        if STOP.exists():
            status, note = "stopped", "STOP file present"
            break
        for g in opt.param_groups:
            g["lr"] = cosine_lr(st, steps, max(steps // 50, 1), args.lr)

        try:
            opt.zero_grad(set_to_none=True)
            ce_acc = com_acc = 0.0
            for _ in range(accum):
                x, y = train(micro)
                with torch.autocast("cuda", torch.bfloat16, enabled=(device == "cuda")):
                    logits, total, idx = model(x, y)
                with torch.no_grad():
                    ce = F.cross_entropy(logits.detach().reshape(-1, logits.size(-1)).float(),
                                         y.reshape(-1))
                (total / accum).backward()
                ce_acc += ce.item() / accum
                com_acc += probe.read() / accum
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        except torch.cuda.OutOfMemoryError:
            # Halve the micro-batch and double accumulation: the effective batch,
            # and therefore the experiment, is unchanged. An OOM costs one step.
            torch.cuda.empty_cache()
            if micro <= 1:
                status, note = "oom", "OOM at micro-batch 1"
                break
            micro, accum = micro // 2, accum * 2
            train = D.Sampler("train", cfg["ctx"], micro, device, seed=seed,
                              limit=budget.get("data_limit"))
            msg = f"OOM at step {st}: micro-batch -> {micro}, accum -> {accum}"
            print(f"\n  !! {msg}", flush=True)
            logline(f"OOM {rid} {msg}")
            dash.set_run(batch=micro, accum=accum)
            continue

        tokens_done += micro * accum * cfg["ctx"]
        st += 1

        # --- divergence guard -------------------------------------------------
        if not math.isfinite(ce_acc):
            status, note = "diverged", f"non-finite loss at step {st}"
            break
        if first_ce is None:
            first_ce = ce_acc
        ce_hist.append(ce_acc)
        if st > steps * 0.05 and ce_acc > first_ce:
            bad += 1
            if bad > 200:
                status, note = "diverged", (f"CE above its initial value "
                                            f"({first_ce:.3f}) for 200 steps")
                break
        else:
            bad = 0

        # --- telemetry --------------------------------------------------------
        now = time.time()
        el = now - t0
        if st % 20 == 0 or st == steps:
            tps = tokens_done / max(el, 1e-9)
            gpu = (torch.cuda.max_memory_allocated() / 1e9) if device == "cuda" else 0.0
            eta = el / max(st - start_step, 1) * (steps - st)
            dash.set_run(step=st, ce=ce_acc, commit=com_acc, tps=tps, gpu_gb=gpu,
                         elapsed=el, eta=eta,
                         live_codes=(model.vq.live_codes() if model.bottleneck else None))
            dash.set(eta_total=eta + (n_runs - run_idx) * (el / max(st - start_step, 1) * steps))
            dash.point(rid, st, ce_acc)
            sys.stdout.write(
                f"\r  {rid:<16}{bar(st, steps)} {st:>6}/{steps}  ce {ce_acc:6.3f}  "
                f"commit {com_acc:8.2e}  {tps/1e3:5.1f}k tok/s  {hms(el)}  "
                f"eta {hms(eta)}  run {run_idx}/{n_runs}   ")
            sys.stdout.flush()
        if now - last_log > 30 or st == steps:
            last_log = now
            logline(f"{rid} step={st}/{steps} ce={ce_acc:.4f} commit={com_acc:.3e} "
                    f"tok/s={tokens_done/max(el,1e-9):.0f} elapsed={hms(el)} "
                    f"eta={hms(el/max(st-start_step,1)*(steps-st))}")
        if st % args.eval_every == 0:
            ev = evaluate(model, val, 10, device, cfg["n_codes"], probe)
            dash.set_run(val_ce=ev["val_ce"])
            m = {"run": rid, "step": st, "train_ce": ce_acc,
                 "train_commit": com_acc, **ev, "t": time.time()}
            jsonl(METRICS, m)
            # train CE, val CE and the commitment term go in as three separate
            # series. They are never added together, here or anywhere else.
            wb.log({"train/ce": ce_acc, "train/commit": com_acc,
                    "val/ce": ev["val_ce"], "val/commit": ev["val_commit"],
                    "val/acc": ev["val_acc"], "val/ppl": ev["val_ppl"],
                    "codes/live": ev["live_codes"],
                    "codes/entropy_bits": ev["code_entropy_bits"],
                    "lr": opt.param_groups[0]["lr"],
                    "perf/tokens_per_sec": tokens_done / max(time.time() - t0, 1e-9),
                    "perf/gpu_gb": (torch.cuda.max_memory_allocated() / 1e9
                                    if device == "cuda" else 0.0)}, step=st)
        # --- checkpoint on step count OR a 5-minute timer ---------------------
        if st % args.ckpt_every == 0 or now - last_ck > 300:
            last_ck = now
            CKPT.mkdir(exist_ok=True)
            tmp = ck.with_suffix(".tmp")
            torch.save({"model": model.state_dict(), "opt": opt.state_dict(),
                        "step": st, "micro": micro, "accum": accum,
                        "cfg": cfg, "seed": seed}, tmp)
            tmp.replace(ck)

    # --- final checkpoint + evaluation ---------------------------------------
    CKPT.mkdir(exist_ok=True)
    tmp = ck.with_suffix(".tmp")
    torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "step": st,
                "micro": micro, "accum": accum, "cfg": cfg, "seed": seed}, tmp)
    tmp.replace(ck)

    ev = evaluate(model, val, budget["eval_batches"], device, cfg["n_codes"], probe)
    rec = {"config": cfg["name"], "seed": seed, "params": nparam,
           "n_codes": cfg["n_codes"], "dim": cfg["dim"], "depth": cfg["depth"],
           "heads": cfg["heads"], "ctx": cfg["ctx"], "steps_done": st,
           "steps_planned": steps, "tokens": tokens_done,
           "val_ce": round(ev["val_ce"], 5), "val_acc": round(ev["val_acc"], 5),
           "val_ppl": round(ev["val_ppl"], 4),
           "commit": None if cfg["n_codes"] == 0 else round(ev["val_commit"], 8),
           "live_codes": ev["live_codes"], "code_entropy_bits": ev["code_entropy_bits"],
           "train_ce_final": round(ce_hist[-1], 5) if ce_hist else None,
           "seconds": round(time.time() - t0, 1), "status": status, "note": note,
           "batch": micro, "accum": accum, "smoke": args.smoke}

    # --- generations, saved for a separate judge -----------------------------
    if status in ("ok", "stopped"):
        GEN.mkdir(exist_ok=True)
        vm = D.memmap("val")
        rng = np.random.default_rng(7)
        starts = rng.integers(0, len(vm) - cfg["ctx"] - 200, size=budget["n_gen"])
        prompts = [[int(t) for t in vm[s:s + 32]] for s in starts]
        outs = generate(model, prompts, cfg["ctx"], max_new=budget["gen_tokens"],
                        device=device)
        texts = [tok.decode(o[32:]) for o in outs]
        refs = [tok.decode([int(t) for t in vm[s + 32:s + 32 + budget["gen_tokens"]]])
                for s in starts]
        vocab_words = set()
        tm = D.memmap("train")
        vocab_words.update(WORD.findall(tok.decode([int(t) for t in tm[:400_000]]).lower()))
        gs, rs = surface_stats(texts), surface_stats(refs)
        rec["gen"] = {"model": {**gs, "oov": oov_rate(texts, vocab_words)},
                      "real_heldout_baseline": {**rs, "oov": oov_rate(refs, vocab_words)}}
        out = GEN / f"{rid}.txt"
        with out.open("w", encoding="utf-8") as f:
            f.write(f"# {rid}  val_ce={rec['val_ce']}  params={nparam}\n")
            f.write("# prompt = 32 tokens of held-out TinyStories; "
                    "continuation = model, temp 0.8, top-k 50\n")
            f.write("# no LLM judge was run; this file exists so one can be, later\n\n")
            for p, t, r in zip(prompts, texts, refs):
                f.write("=" * 70 + "\nPROMPT: " + tok.decode(p).replace("\n", " ") + "\n")
                f.write("-" * 70 + "\nMODEL:  " + t.strip() + "\n")
                f.write("-" * 70 + "\nREAL:   " + r.strip() + "\n\n")
        rec["generations_file"] = str(out.relative_to(HERE))

    jsonl(RESULTS, rec)
    wb.log({"final/val_ce": rec["val_ce"], "final/val_acc": rec["val_acc"],
            "final/val_ppl": rec["val_ppl"],
            "final/commit": rec["commit"] if rec["commit"] is not None else 0.0,
            "final/live_codes": rec["live_codes"] or 0}, step=st)
    wb.finish()
    dash.result({k: rec[k] for k in ("config", "seed", "val_ce", "val_acc", "val_ppl",
                                     "commit", "live_codes", "params", "tokens",
                                     "seconds", "status")})
    print(f"\n    -> {rid}: val CE {ev['val_ce']:.4f}  ppl {ev['val_ppl']:.2f}  "
          f"acc {ev['val_acc']:.4f}  commit "
          f"{'n/a' if cfg['n_codes']==0 else format(ev['val_commit'],'.2e')}  "
          f"live {ev['live_codes']}  [{status}]  {hms(time.time()-t0)}", flush=True)
    logline(f"DONE {rid} val_ce={ev['val_ce']:.4f} val_acc={ev['val_acc']:.4f} "
            f"status={status} {note}")
    del model, opt
    torch.cuda.empty_cache()
    return rec


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="whole pipeline end to end on a tiny model, <3 min")
    ap.add_argument("--resume", action="store_true",
                    help="skip finished (config,seed) pairs, resume the partial one")
    ap.add_argument("--no-dashboard", action="store_true")
    ap.add_argument("--no-wandb", action="store_true",
                    help="disable the Weights and Biases mirror. It is ON by "
                         "default and needs `wandb login` (or WANDB_API_KEY) "
                         "once; missing auth is a printed warning, never an error")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--steps", type=int, default=0, help="override the step budget")
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--eval-every", type=int, default=500)
    ap.add_argument("--ckpt-every", type=int, default=1000)
    ap.add_argument("--max-hours", type=float, default=4.0)
    ap.add_argument("--serve-forever", action="store_true",
                    help="keep the dashboard up until Ctrl-C instead of exiting "
                         "after a 60 s grace period")
    ap.add_argument("--sec-per-step", type=float, default=0.0,
                    help="measured step time; 0 = benchmark it")
    a = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("=" * 78)
    print(f"  TinyStories: dense vs discrete bottleneck at matched parameters"
          f"{'   [SMOKE]' if a.smoke else ''}")
    print("=" * 78, flush=True)

    tok, meta = D.prepare()
    D.verify(tok, meta)

    # ---- geometry. vocab 8192 tied embedding = 4.19M; each block is 16*dim^2
    #      (4*dim^2 attention + 12*dim^2 SwiGLU MLP). dim 512, depth 6 gives
    #      6*16*512^2 = 25.2M in blocks, +4.19M embedding +0.13M positions
    #      = 29.5M. That is the "~28M" scale, stated exactly.
    if a.smoke:
        geom = dict(dim=128, depth=2, heads=4, ctx=128, code_dim=32)
        seeds = [0, 1]
        cfgs = [dict(name="dense", n_codes=0), dict(name="codes=512", n_codes=512)]
        budget = dict(steps=60, batch=8, eval_batches=4, n_gen=3, gen_tokens=40,
                      data_limit=4_000_000)
        a.eval_every, a.ckpt_every = 30, 30
    else:
        geom = dict(dim=512, depth=6, heads=8, ctx=256, code_dim=64)
        seeds = list(range(a.seeds))
        cfgs = [dict(name="dense", n_codes=0),
                dict(name="codes=512", n_codes=512)]
        budget = dict(steps=0, batch=32, eval_batches=60, n_gen=24, gen_tokens=160,
                      data_limit=None)
    for c in cfgs:
        c.update(geom)

    # ---- parameter matching, verified before a single step is taken ---------
    print("\n  PARAMETER MATCH (must be within 1%)")
    counts = {}
    for c in cfgs:
        m = make_model(c, meta["vocab_size"], "cpu")
        counts[c["name"]] = n_params(m)
        del m
    ref = counts["dense"]
    ok = True
    for k, v in counts.items():
        d = (v - ref) / ref
        ok &= abs(d) <= 0.01
        print(f"    {k:<14}{v:>12,} params   {d:+.3%} vs dense")
    print(f"    -> matched within 1%: {'YES' if ok else 'NO'}")
    if not ok:
        sys.exit("FAIL: configs are not parameter-matched; fix the geometry first")

    # ---- compute budget ----------------------------------------------------
    n_runs = len(cfgs) * len(seeds)
    if a.smoke:
        sec_step = 0.05
    elif a.sec_per_step > 0:
        sec_step = a.sec_per_step
    else:
        sec_step = benchmark(cfgs[-1], meta, budget["batch"], device)
        print(f"  measured step time: {sec_step*1000:.0f} ms "
              f"({budget['batch']*geom['ctx']/sec_step/1e3:.0f}k tokens/s)")
    if a.steps:
        budget["steps"] = a.steps
    elif not a.smoke:
        # Spend the wall-clock budget, not an arbitrary step count. Reserve 12%
        # for eval and generation.
        budget["steps"] = int(a.max_hours * 3600 * 0.88 / n_runs / sec_step)
        budget["steps"] = min(budget["steps"], 30_000)
    toks = budget["steps"] * budget["batch"] * geom["ctx"]
    chinch = 20 * ref
    print(f"\n  COMPUTE BUDGET")
    print(f"    {len(cfgs)} configs x {len(seeds)} seeds = {n_runs} runs")
    print(f"    {budget['steps']:,} steps x batch {budget['batch']} x ctx {geom['ctx']}"
          f" = {toks/1e6:.0f}M tokens per run")
    print(f"    {toks/ref:.1f} tokens/param; Chinchilla-optimal is 20 "
          f"({toks/chinch:.2f}x of it)")
    print(f"    estimated wall clock: {hms(n_runs * budget['steps'] * sec_step / 0.88)}")
    if n_runs * budget["steps"] * sec_step / 0.88 > a.max_hours * 3600 * 1.05:
        budget["steps"] = int(a.max_hours * 3600 * 0.88 / n_runs / sec_step)
        print(f"    OVER {a.max_hours}h: step budget auto-reduced to "
              f"{budget['steps']:,}")
    print(f"\n  to stop cleanly, keeping everything already written:")
    print(f"      create the file {STOP}")
    print(f"  tailable log: {TRAINLOG}")
    print(f"  per-eval json: {METRICS.name}   final results: {RESULTS.name}")

    wb = WandB(enabled=not a.no_wandb)
    dash = Dashboard(enabled=not a.no_dashboard)
    if dash.url:
        print(f"\n  live dashboard: {dash.url}\n", flush=True)
    dash.set(n_runs=n_runs, phase="starting")

    done = set()
    if a.resume and RESULTS.exists():
        for line in RESULTS.open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("smoke") == a.smoke and r.get("status") == "ok":
                done.add((r["config"], r["seed"]))
        print(f"  resume: {len(done)} run(s) already complete, skipping them")

    logline(f"START {'smoke' if a.smoke else 'full'} n_runs={n_runs} "
            f"steps={budget['steps']} params={ref}")
    gstart = time.time()
    i = 0
    for c in cfgs:
        for s in seeds:
            i += 1
            if (c["name"], s) in done:
                print(f"  [{i}/{n_runs}] {c['name']} seed {s}: already done")
                continue
            if STOP.exists():
                print("\n  STOP file present; stopping before the next run.")
                break
            print(f"\n  [{i}/{n_runs}] {c['name']}  seed {s}", flush=True)
            train_one(c, s, a, tok, meta, dash, wb, budget, i, n_runs, gstart)
        else:
            continue
        break

    dash.set(phase="finished", done_frac=1.0)
    summarize(a.smoke)
    print(f"\n  total wall clock: {hms(time.time()-gstart)}")
    # The dashboard stays up briefly so a human who wanders back can read the
    # final table, then the process EXITS. Blocking forever by default meant a
    # scripted `run.py --smoke` never returned and had to be killed.
    if dash.url:
        grace = 1e9 if a.serve_forever else 60
        print(f"  dashboard still serving final results at {dash.url}")
        print(f"  exiting in {'never (--serve-forever)' if a.serve_forever else '60s'};"
              f" Ctrl-C to exit now.")
        try:
            time.sleep(grace)
        except KeyboardInterrupt:
            pass
    print("  done.")


def benchmark(cfg, meta, batch, device, n=12):
    """Measure real step time so the budget is chosen from data, not from hope."""
    m = make_model(cfg, meta["vocab_size"], device)
    o = optimizer(m, lr=1e-4)
    smp = D.Sampler("train", cfg["ctx"], batch, device, seed=0)
    for i in range(n):
        if i == 4 and device == "cuda":
            torch.cuda.synchronize()
            t0 = time.time()
        x, y = smp()
        with torch.autocast("cuda", torch.bfloat16, enabled=(device == "cuda")):
            _, loss, _ = m(x, y)
        o.zero_grad(set_to_none=True)
        loss.backward()
        o.step()
    if device == "cuda":
        torch.cuda.synchronize()
    dt = (time.time() - t0) / (n - 4)
    del m, o
    torch.cuda.empty_cache()
    return dt


def summarize(smoke):
    if not RESULTS.exists():
        return
    rows = [json.loads(l) for l in RESULTS.open(encoding="utf-8")
            if json.loads(l).get("smoke") == smoke and json.loads(l).get("status") == "ok"]
    if not rows:
        return
    by = {}
    for r in rows:
        by.setdefault(r["config"], []).append(r)
    print("\n" + "=" * 78)
    print(f"  {'config':<14}{'n':>3}{'val CE (mean +/- 95% CI)':>30}"
          f"{'val acc':>26}{'params':>12}")
    base = None
    for k, v in by.items():
        ce, ce_ci = mean_ci([r["val_ce"] for r in v])
        ac, ac_ci = mean_ci([r["val_acc"] for r in v])
        if k == "dense":
            base = (ce, ac)
        print(f"  {k:<14}{len(v):>3}{ce:>21.4f} +/- {ce_ci:<7.4f}"
              f"{ac:>17.4f} +/- {ac_ci:<7.4f}{v[0]['params']:>12,}")
    if base:
        print("\n  gap vs dense (positive = discrete is worse):")
        for k, v in by.items():
            if k == "dense":
                continue
            dce, dci = mean_ci([r["val_ce"] - base[0] for r in v])
            dac, dai = mean_ci([base[1] - r["val_acc"] for r in v])
            print(f"    {k:<14} CE  {dce:+.4f} +/- {dci:.4f}    "
                  f"top-1 acc  {dac*100:+.2f} +/- {dai*100:.2f} points")
    print("=" * 78)


if __name__ == "__main__":
    main()
