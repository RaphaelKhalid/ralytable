"""results.json -> results/real_embedding_capacity.png"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
d = json.load(open(os.path.join(HERE, "results.json")))

SERIES = [  # key, label, colour (palette validated with dataviz validator)
    ("gauss", "random Gaussian (D=384)", "#3b6fd6"),
    ("bipolar", "random bipolar (the toy result)", "#2f8f5b"),
    ("minilm_ctr", "MiniLM, corpus mean removed", "#a34bbf"),
    ("minilm", "MiniLM sentence embeddings", "#b03a48"),
    ("bagemb", "averaged token embeddings", "#d4732a"),
]
SURF, INK, MUT = "#fcfcfb", "#22252a", "#7a7f88"

fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True, facecolor=SURF)
for ax, V in zip(axes, d["pools"]):
    rows = [r for r in d["rows"] if r["V"] == V]
    ns = [r["N"] for r in rows]
    ax.set_facecolor(SURF)
    for k, lab, c in SERIES:
        y = [r[k]["acc"] for r in rows]
        ax.fill_between(ns, [r[k]["lo"] for r in rows],
                        [r[k]["hi"] for r in rows], color=c, alpha=0.18, lw=0)
        ax.plot(ns, y, color=c, lw=2, label=lab, solid_capstyle="round")
    ax.plot(ns, [r["chance"] for r in rows], color=MUT, lw=1.5, ls=":",
            label="chance (N/V)")
    ax.set_xscale("log")
    ax.set_xticks(ns)
    ax.set_xticklabels([str(n) for n in ns], fontsize=8)
    ax.minorticks_off()
    ax.set_xlabel("N items bundled into one vector", color=INK, fontsize=9)
    ax.set_title(f"retrieval pool = {V} items", color=INK, fontsize=10, pad=8)
    ax.grid(True, color="#e6e6e4", lw=0.8)
    ax.set_axisbelow(True)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=MUT, length=0, labelsize=8)

axes[0].set_ylabel("fraction of bundled items in top-N", color=INK, fontsize=9)
axes[0].set_ylim(0, 1.02)
axes[1].legend(frameon=False, fontsize=8, labelcolor=INK, loc="upper right")
fig.suptitle("Averaging real embeddings loses items far faster than the toy "
             "random-vector result", color=INK, fontsize=12, y=0.99, x=0.02,
             ha="left", fontweight="bold")
fig.text(0.02, 0.90, "all-MiniLM-L6-v2 over 7600 AG News headlines, D=384 "
         "throughout; 200 trials, bands are 95% CI", color=MUT, fontsize=8.5)
fig.tight_layout(rect=[0, 0, 1, 0.88])
out = os.path.join(ROOT, "results", "real_embedding_capacity.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
fig.savefig(out, dpi=170, facecolor=SURF)
print("wrote", out)
