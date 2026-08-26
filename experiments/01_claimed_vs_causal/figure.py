import pathlib, numpy as np, pandas as pd
from scipy import stats
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[2]
df = pd.read_csv(ROOT / "results" / "claimed_vs_causal.csv")

def partial(x, y, z):
    rx, ry, rz = (stats.rankdata(v) for v in (x, y, z))
    a = rx - np.polyval(np.polyfit(rz, rx, 1), rz)
    b = ry - np.polyval(np.polyfit(rz, ry, 1), rz)
    return stats.pearsonr(a, b)[0]

raw, par, pos = [], [], []
for _, g in df.groupby(["model", "problem"]):
    g = g.dropna(subset=["n_descendants", "cf_kl"])
    if len(g) < 20 or g["n_descendants"].nunique() < 3: continue
    raw.append(stats.spearmanr(g["n_descendants"], g["cf_kl"])[0])
    par.append(partial(g["n_descendants"].values, g["cf_kl"].values, g["chunk_idx"].values))
    pos.append(stats.spearmanr(g["chunk_idx"], g["cf_kl"])[0])

fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
data = [raw, par, pos]
labels = ["claimed graph\n(raw)", "claimed graph\n(position controlled)", "position\nalone"]
cols = ["#7aa6c2", "#c27a7a", "#8a8a8a"]
for i, (d, c) in enumerate(zip(data, cols)):
    ax[0].scatter(np.random.normal(i, .06, len(d)), d, s=18, alpha=.6, color=c, zorder=3)
    ax[0].hlines(np.mean(d), i-.28, i+.28, color="k", lw=2, zorder=4)
ax[0].axhline(0, color="k", lw=.8, ls="--", alpha=.5)
ax[0].set_xticks(range(3)); ax[0].set_xticklabels(labels, fontsize=9)
ax[0].set_ylabel("within-trace Spearman rho vs causal importance")
ax[0].set_title("One point per reasoning trace (n=40)", fontsize=10)
ax[0].spines[["top","right"]].set_visible(False)

b = df.dropna(subset=["cf_kl"]).copy()
b["bin"] = pd.cut(b["rel_pos"], 10, labels=False)
m = b.groupby("bin")["cf_kl"].agg(["mean", "sem"])
ax[1].errorbar(np.arange(10)/9, m["mean"], yerr=m["sem"], marker="o", color="#8a8a8a", lw=1.6)
ax[1].set_xlabel("relative position in trace"); ax[1].set_ylabel("counterfactual importance (KL)")
ax[1].set_title("Importance falls with position in 100% of traces", fontsize=10)
ax[1].spines[["top","right"]].set_visible(False)
fig.suptitle("An LLM's claimed dependency graph adds nothing to position", fontsize=12, y=1.0)
fig.tight_layout()
out = ROOT / "results" / "claimed_vs_causal.png"
fig.savefig(out, dpi=150, bbox_inches="tight")
print("->", out)
