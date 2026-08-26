"""Within-trace test, with position controlled inside each trace.

The pooled analysis in analyse.py gives the OPPOSITE sign to the within-trace
analysis. That is Simpson's paradox: traces differ in length and difficulty, and
pooling chunks across them mixes between-trace variation into a within-trace
question. Each trace is its own control; that is the correct unit.

overdeterminedness is excluded: it is the duplicate-rate of resampled strings, so
it is near-mechanically anti-correlated with an importance score computed from the
spread of those same resamples. Not a finding.
"""
import json, pathlib
import numpy as np, pandas as pd
from scipy import stats

ROOT = pathlib.Path(__file__).resolve().parents[2]
df = pd.read_csv(ROOT / "results" / "claimed_vs_causal.csv")


def partial_spearman(x, y, z):
    rx, ry, rz = (stats.rankdata(v) for v in (x, y, z))
    out = []
    for r in (rx, ry):
        out.append(r - np.polyval(np.polyfit(rz, r, 1), rz))
    return stats.pearsonr(out[0], out[1])[0]


def summarise(name, pred, target):
    raw, par, keep = [], [], 0
    for (m, p), g in df.groupby(["model", "problem"]):
        g = g.dropna(subset=[pred, target])
        if len(g) < 20 or g[pred].nunique() < 3:
            continue
        keep += 1
        r = stats.spearmanr(g[pred], g[target])[0]
        pr = partial_spearman(g[pred].values, g[target].values, g["chunk_idx"].values)
        if not np.isnan(r):
            raw.append(np.arctanh(np.clip(r, -.999, .999)))
        if not np.isnan(pr):
            par.append(np.arctanh(np.clip(pr, -.999, .999)))
    def agg(z):
        z = np.array(z)
        t, p = stats.ttest_1samp(z, 0)
        lo, hi = stats.t.interval(.95, len(z)-1, z.mean(), stats.sem(z))
        return np.tanh(z.mean()), np.tanh(lo), np.tanh(hi), p
    r_m, r_lo, r_hi, r_p = agg(raw)
    p_m, p_lo, p_hi, p_p = agg(par)
    print(f"{name:34} n={keep:3}  raw {r_m:+.3f} [{r_lo:+.2f},{r_hi:+.2f}] p={r_p:.1e}"
          f"   |pos {p_m:+.3f} [{p_lo:+.2f},{p_hi:+.2f}] p={p_p:.1e}")
    return p_m


print("Fisher-z averaged within-trace Spearman, 95% CI, vs counterfactual_importance_kl\n")
for pred in ["n_descendants", "frac_descendants", "out_degree", "in_degree"]:
    summarise(pred, pred, "cf_kl")

print("\nrobustness -- same test against the other importance measure:")
for pred in ["n_descendants", "out_degree"]:
    summarise(pred + " -> resamp_kl", pred, "resamp_kl")

print("\nsplit by model:")
full = df.copy()
for m in sorted(df.model.unique()):
    df = full[full.model == m]
    summarise(f"  {m[:30]}", "n_descendants", "cf_kl")
df = full

print("\nhow strong is position on its own, within trace?")
z = []
for _, g in df.groupby(["model", "problem"]):
    g = g.dropna(subset=["cf_kl"])
    if len(g) < 20: continue
    r = stats.spearmanr(g["chunk_idx"], g["cf_kl"])[0]
    if not np.isnan(r): z.append(np.arctanh(np.clip(r, -.999, .999)))
z = np.array(z)
print(f"  position -> cf_kl: rho={np.tanh(z.mean()):+.3f}  p={stats.ttest_1samp(z,0)[1]:.1e}"
      f"  ({(np.array(z)<0).mean()*100:.0f}% of traces negative)")

print("\nannotated graph shape:")
print(f"  chunks claiming no dependencies: {(df.in_degree==0).mean()*100:.1f}%")
print(f"  chunks nothing claims to use:    {(df.out_degree==0).mean()*100:.1f}%")
print(f"  median in_degree {df.in_degree.median():.0f}, out_degree {df.out_degree.median():.0f}")
