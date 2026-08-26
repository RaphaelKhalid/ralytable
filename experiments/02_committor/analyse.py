"""Committor jump analysis: are there discrete "decision moments" in q(t)?

q(t) = chunk['accuracy'] = fraction of ~100 resampled rollouts from step t that
end correct. This is a committor. The hypothesis under test: q(t) shows
step-like jumps (forks) rather than smooth drift + sampling noise.

Runs entirely on local data. No API calls.
Usage: python experiments/02_committor/analyse.py
Writes results/committor.png and prints every number used in FINDINGS.md.
"""
import json
import glob
import os
import math
import collections
import numpy as np
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAT = os.path.join(ROOT, "data", "math-rollouts", "*", "temperature_0.6_top_p_0.95",
                   "correct_base_solution", "problem_*", "chunks_labeled.json")
N_ROLL = 100    # ~100 resampled rollouts per chunk (dataset spec)
NSIM = 200      # null replicates per trace
THR = 0.20      # "jump" threshold, ~4 sigma of binomial noise at q=0.5
RNG = np.random.default_rng(0)


def n_eff(a):
    """Recover the number of resampled rollouts behind an accuracy value.

    accuracy is k/n with n ~= 100, but the stored float is the reduced
    fraction, so the smallest consistent denominator is only a lower bound.
    If that lower bound divides some n in [90,100] we assume n=99 (96% of
    chunks); otherwise the lower bound IS the true n (a minority of chunks
    were resampled fewer times, down to n~17).
    """
    d = 100
    for k in range(1, 101):
        if abs(a * k - round(a * k)) < 1e-9:
            d = k
            break
    if any(m % d == 0 for m in range(90, 101)):
        return 99
    return d


def load():
    traces = []
    for f in sorted(glob.glob(PAT)):
        chunks = [c for c in json.load(open(f, encoding="utf-8"))
                  if c.get("accuracy") is not None]
        chunks.sort(key=lambda c: c["chunk_idx"])
        if len(chunks) < 10:
            continue
        parts = f.replace("\\", "/").split("/")
        traces.append(dict(model=parts[-5], prob=parts[-2], chunks=chunks,
                           q=np.array([c["accuracy"] for c in chunks], float),
                           n=np.array([n_eff(c["accuracy"]) for c in chunks], float)))
    return traces


def smooth(q, frac=0.25):
    """Local-linear smoother -> the 'smooth underlying curve' for the null."""
    n = len(q)
    h = max(3.0, frac * n)
    x = np.arange(n, dtype=float)
    out = np.empty(n)
    for i in range(n):
        w = np.exp(-0.5 * ((x - i) / h) ** 2)
        X = np.vstack([np.ones(n), x - i]).T
        A = X.T @ (w[:, None] * X)
        b = X.T @ (w * q)
        out[i] = np.linalg.lstsq(A, b, rcond=None)[0][0]
    return np.clip(out, 0.005, 0.995)


def fisher_z_mean(rhos):
    r = np.clip(np.array([x for x in rhos if np.isfinite(x)]), -0.999, 0.999)
    z = np.arctanh(r)
    m = z.mean()
    se = z.std(ddof=1) / math.sqrt(len(z))
    return np.tanh(m), np.tanh(m - 1.96 * se), np.tanh(m + 1.96 * se), len(r)


def main():
    traces = load()
    print("traces=%d chunks=%d" % (len(traces), sum(len(t["chunks"]) for t in traces)))

    # ------------------------------------------------ 1. SHAPE
    print("\n=== 1. SHAPE ===")
    L, q0, qT, mono, tv, ratio = [], [], [], [], [], []
    for t in traces:
        q = t["q"]
        d = np.diff(q)
        L.append(len(q)); q0.append(q[0]); qT.append(q[-1])
        mono.append((d > 0).mean()); tv.append(np.abs(d).sum())
        ratio.append(np.abs(d).sum() / max(1e-9, abs(q[-1] - q[0])))
    L, q0, qT, mono, tv = map(np.array, (L, q0, qT, mono, tv))
    print("len: median %.0f [%d, %d]" % (np.median(L), L.min(), L.max()))
    print("q_start mean %.3f sd %.3f | q_end mean %.3f sd %.3f"
          % (q0.mean(), q0.std(), qT.mean(), qT.std()))
    print("frac of steps increasing: mean %.3f sd %.3f (0.5 = driftless)"
          % (mono.mean(), mono.std()))
    print("total variation median %.2f ; TV / |net change| median %.1f"
          % (np.median(tv), np.median(ratio)))
    print("traces ending q>0.9: %d/%d ; starting q>0.9: %d"
          % ((qT > 0.9).sum(), len(qT), (q0 > 0.9).sum()))

    # ------------------------------------------------ 2. JUMPS VS NOISE
    print("\n=== 2. JUMPS VS BINOMIAL NOISE (the crux) ===")
    obs_all, z_all, sim_pool = [], [], []
    obs_frac, null_smooth, null_flat = [], [], []
    for t in traces:
        q = t["q"]
        n = len(q)
        d = np.abs(np.diff(q))
        obs_all.append(d)
        nn = t["n"]
        se = np.sqrt(np.clip(q * (1 - q), 1e-4, None) / nn)
        z_all.append(np.diff(q) / np.sqrt(se[:-1] ** 2 + se[1:] ** 2))
        s = smooth(q)
        obs_frac.append((d > THR).mean())
        ff, fs = [], []
        for _ in range(NSIM):
            qf = RNG.binomial(nn.astype(int), np.full(n, q.mean())) / nn
            qs = RNG.binomial(nn.astype(int), s) / nn
            ff.append((np.abs(np.diff(qf)) > THR).mean())
            fs.append((np.abs(np.diff(qs)) > THR).mean())
            sim_pool.append(np.abs(np.diff(qs)))
        null_flat.append(np.mean(ff))
        null_smooth.append(np.mean(fs))
    obs = np.concatenate(obs_all)
    zc = np.concatenate(z_all)
    sim = np.concatenate(sim_pool)
    print("|dq| observed : mean %.4f median %.4f p90 %.3f p99 %.3f max %.3f"
          % (obs.mean(), np.median(obs), np.percentile(obs, 90),
             np.percentile(obs, 99), obs.max()))
    print("|dq| null(sim): mean %.4f median %.4f p90 %.3f p99 %.3f max %.3f"
          % (sim.mean(), np.median(sim), np.percentile(sim, 90),
             np.percentile(sim, 99), sim.max()))
    for thr in (0.10, 0.15, 0.20, 0.30, 0.40, 0.50):
        po, ps = (obs > thr).mean(), (sim > thr).mean()
        print("  P(|dq|>%.2f): obs %.4f  smooth-null %.4f  ratio %5.2f  excess %6.0f / %d"
              % (thr, po, ps, po / max(ps, 1e-9), (obs > thr).sum() - ps * len(obs), len(obs)))
    of, nf, sf = map(np.array, (obs_frac, null_smooth, null_flat))
    diff = of - nf
    se = diff.std(ddof=1) / math.sqrt(len(diff))
    print("per-trace frac(|dq|>%.2f): obs %.4f  smooth-null %.4f  flat-null %.4f"
          % (THR, of.mean(), nf.mean(), sf.mean()))
    print("  paired diff = %+.4f +/- %.4f (95%% CI), t=%.2f, traces with excess %d/%d"
          % (diff.mean(), 1.96 * se, diff.mean() / se, (diff > 0).sum(), len(diff)))
    print("n_eff: median %.0f, frac<50 %.3f, min %.0f"
          % (np.median(np.concatenate([t["n"] for t in traces])),
             np.mean(np.concatenate([t["n"] for t in traces]) < 50),
             np.concatenate([t["n"] for t in traces]).min()))
    print("adjacent-equal-q null z: |z|>2 %.4f (exp .0455), |z|>3 %.4f (exp .0027), sd(z)=%.2f"
          % ((np.abs(zc) > 2).mean(), (np.abs(zc) > 3).mean(), zc.std()))

    # ------------------------------------------------ 3. LOCATION / CONFOUND
    print("\n=== 3. LOCATION & POSITION CONFOUND ===")
    r_pos, r_cf, r_rs = [], [], []
    for t in traces:
        d = np.abs(np.diff(t["q"]))
        r_pos.append(stats.spearmanr(d, np.arange(len(d))).statistic)
        for key, acc in (("counterfactual_importance_kl", r_cf),
                         ("resampling_importance_kl", r_rs)):
            v = np.array([c.get(key, np.nan) for c in t["chunks"]], float)
            ok = np.isfinite(v)
            acc.append(stats.spearmanr(v[ok], np.arange(len(v))[ok]).statistic)
    for name, rr in (("|dq| vs position", r_pos),
                     ("counterfactual_importance_kl vs position", r_cf),
                     ("resampling_importance_kl vs position", r_rs)):
        m, lo, hi, k = fisher_z_mean(rr)
        neg = sum(1 for x in rr if x < 0)
        print("  %-42s rho=%+.3f 95%%CI [%+.3f,%+.3f]  (%d/%d negative)"
              % (name, m, lo, hi, neg, k))
    rz = []
    for t in traces:
        q, nn = t["q"], t["n"]
        se = np.sqrt(np.clip(q * (1 - q), 1e-4, None) / nn)
        z = np.abs(np.diff(q)) / np.sqrt(se[:-1] ** 2 + se[1:] ** 2)
        rz.append(stats.spearmanr(z, np.arange(len(z))).statistic)
    m, lo, hi, k = fisher_z_mean(rz)
    print("  %-42s rho=%+.3f 95%%CI [%+.3f,%+.3f]  (%d/%d negative)"
          % ("|z| (noise-normalised |dq|) vs position", m, lo, hi,
             sum(1 for x in rz if x < 0), k))

    rel = []
    for t in traces:
        d = np.abs(np.diff(t["q"]))
        n = len(d)
        rel += [i / max(1, n - 1) for i in range(n) if d[i] > THR]
    rel = np.array(rel)
    print("  relative position of |dq|>%.2f jumps: n=%d mean %.3f quartiles %s"
          % (THR, len(rel), rel.mean(), np.percentile(rel, [25, 50, 75]).round(3)))

    # ------------------------------------------------ 4. TRANSITION STATES
    print("\n=== 4. TRANSITION STATES: is q ~ 0.5 special? ===")
    qa = np.concatenate([t["q"][:-1] for t in traces])
    qb = np.concatenate([t["q"][1:] for t in traces])
    mid = (qa + qb) / 2
    for thr in (0.0, 0.20, 0.30):
        sel = obs > thr if thr > 0 else np.ones_like(obs, bool)
        cross = ((qa[sel] - 0.5) * (qb[sel] - 0.5) < 0).mean()
        print("  |dq|>%.2f n=%4d  mean midpoint q %.3f  frac in [.35,.65] %.3f  frac crossing .5 %.3f"
              % (thr, sel.sum(), mid[sel].mean(),
                 ((mid[sel] > 0.35) & (mid[sel] < 0.65)).mean(), cross))
    allq = np.concatenate([t["q"] for t in traces])
    print("  frac of all chunks with q>0.9: %.3f ; q<0.1: %.3f"
          % ((allq > 0.9).mean(), (allq < 0.1).mean()))
    print("  pooled spearman |dq| vs min(q,1-q): %+.3f  "
          "(NOTE partly mechanical: binomial sd peaks at q=0.5)"
          % stats.spearmanr(obs, np.minimum(mid, 1 - mid)).statistic)

    # --------------------------- 4b. PERSISTENCE: step or spike?
    print("\n=== 4b. ARE BIG JUMPS PERSISTENT LEVEL SHIFTS OR ONE-CHUNK SPIKES? ===")
    W = 5
    pers, spike, ratios = 0, 0, []
    for t in traces:
        q = t["q"]
        d = np.diff(q)
        for i, dv in enumerate(d):
            if abs(dv) <= THR:
                continue
            a = q[max(0, i + 1 - W):i + 1].mean()
            b = q[i + 1:i + 1 + W].mean()
            shift = b - a
            ratios.append(shift / dv)
            if shift / dv > 0.5:
                pers += 1
            else:
                spike += 1
    ratios = np.array(ratios)
    print("  of %d jumps |dq|>%.2f: %d retain >50%% of the shift over the next %d chunks, "
          "%d do not (spikes/reversions)" % (len(ratios), THR, pers, W, spike))
    print("  retained fraction of the jump: median %.2f  quartiles %s"
          % (np.median(ratios), np.percentile(ratios, [25, 75]).round(2)))

    # ------------------------------------------------ 5. JUMP SENTENCES
    print("\n=== 5. TOP 20 JUMPS: TEXT AND TAGS ===")
    allj = []
    for t in traces:
        d = np.diff(t["q"])
        for i, dv in enumerate(d):
            allj.append((abs(dv), dv, t, i + 1))
    allj.sort(key=lambda x: -x[0])
    for a, dv, t, i in allj[:20]:
        c = t["chunks"][i]
        txt = " ".join(c["chunk"].split())[:110].encode("ascii", "replace").decode()
        print("  d=%+.2f  q %.2f->%.2f  rel=%.2f  %s/%s  tags=%s\n      %s"
              % (dv, t["q"][i - 1], t["q"][i], i / (len(t["q"]) - 1),
                 t["model"][-8:], t["prob"], c["function_tags"], txt))
    base, jump = collections.Counter(), collections.Counter()
    for t in traces:
        d = np.abs(np.diff(t["q"]))
        for i, c in enumerate(t["chunks"]):
            for tag in c["function_tags"]:
                base[tag] += 1
                if i >= 1 and d[i - 1] > THR:
                    jump[tag] += 1
    nb, nj = sum(base.values()), sum(jump.values())
    print("\n  function_tag base rate vs rate at jump chunks (tags at jumps n=%d, all n=%d)"
          % (nj, nb))
    for tag, b in base.most_common():
        j = jump.get(tag, 0)
        lo, hi = stats.binomtest(j, nj).proportion_ci(0.95)
        print("    %-34s base %.3f  jump %.3f [%.3f,%.3f]  n=%d"
              % (tag, b / nb, j / nj, lo, hi, j))
    keys = list(base)
    o = np.array([jump.get(k, 0) for k in keys], float)
    e = np.array([base[k] for k in keys], float) / nb * nj
    keep = e > 5
    chi = ((o[keep] - e[keep]) ** 2 / e[keep]).sum()
    df = keep.sum() - 1
    print("  chi2=%.1f df=%d p=%.4f" % (chi, df, 1 - stats.chi2.cdf(chi, df)))

    # ------------------------------------------------ 6. AGREEMENT
    print("\n=== 6. AGREEMENT WITH EXISTING IMPORTANCE METRICS (within-trace) ===")
    for metric in ("resampling_importance_kl", "counterfactual_importance_kl",
                   "counterfactual_importance_accuracy", "overdeterminedness"):
        rr = []
        for t in traces:
            d = np.abs(np.diff(t["q"]))
            v = np.array([c.get(metric, np.nan) for c in t["chunks"][1:]], float)
            ok = np.isfinite(v) & np.isfinite(d)
            if ok.sum() > 8:
                rr.append(stats.spearmanr(d[ok], v[ok]).statistic)
        m, lo, hi, k = fisher_z_mean(rr)
        print("  |dq| vs %-38s rho=%+.3f 95%%CI [%+.3f,%+.3f] n=%d"
              % (metric, m, lo, hi, k))

    # ------------------------------------------------ FIGURE
    fig = plt.figure(figsize=(13, 9))
    ax = fig.add_subplot(2, 2, 1)
    for t in traces:
        ax.plot(np.arange(len(t["q"])) / (len(t["q"]) - 1), t["q"], lw=0.8, alpha=0.5)
    ax.set_xlabel("relative position in trace")
    ax.set_ylabel("q(t) = P(correct)")
    ax.set_ylim(0, 1.02)
    ax.set_title("A. Committor trajectories, all %d traces" % len(traces))

    ax = fig.add_subplot(2, 2, 2)
    for t in sorted(traces, key=lambda t: -np.abs(np.diff(t["q"])).max())[:4]:
        q = t["q"]
        x = np.arange(len(q))
        ln, = ax.plot(x, q, lw=0.9, alpha=0.45)
        ax.plot(x, smooth(q), lw=2.2, color=ln.get_color(),
                label="%s/%s" % (t["model"][-8:], t["prob"]))
    ax.legend(fontsize=7)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("chunk_idx")
    ax.set_ylabel("q")
    ax.set_title("B. 4 traces with the largest single step (thin=raw, thick=smoothed)")

    ax = fig.add_subplot(2, 2, 3)
    bins = np.linspace(0, 0.6, 40)
    ax.hist(obs, bins=bins, density=True, alpha=0.55, label="observed |dq|")
    ax.hist(sim, bins=bins, density=True, histtype="step", lw=2, color="k",
            label="smooth curve + binomial(per-chunk n) null")
    ax.set_yscale("log")
    ax.legend(fontsize=8)
    ax.set_xlabel("|q(t+1) - q(t)|")
    ax.set_ylabel("density (log)")
    ax.set_title("C. Jumps vs sampling noise")

    ax = fig.add_subplot(2, 2, 4)
    ax.scatter(mid, obs, s=4, alpha=0.15)
    ax.axvline(0.5, color="r", ls="--", lw=1)
    ax.set_xlabel("midpoint q of the step")
    ax.set_ylabel("|dq|")
    ax.set_title("D. Step size vs where in q it occurs")

    fig.tight_layout()
    out = os.path.join(ROOT, "results", "committor.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, dpi=140)
    print("\nwrote %s" % out)


if __name__ == "__main__":
    main()
