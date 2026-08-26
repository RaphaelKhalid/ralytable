"""Figure: results/retrieval_cost.png"""
import os
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.abspath(os.path.join(HERE, "..", "..", "results"))
KS = [2, 4, 8, 16]
B = 32
MODELS = ["minilm", "mpnet", "bge", "gte"]
NAMES = {"minilm": "MiniLM-L6 (384)", "mpnet": "mpnet-base (768)",
         "bge": "bge-small (384)", "gte": "gte-small (384)"}


def load(ds, w=False):
    return json.load(open(os.path.join(
        HERE, "results_%s%s.json" % (ds, "_whitened" if w else ""))))


def main():
    os.makedirs(RES, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))

    # -- panel A/B: hit-rate vs k on scifact, per grouping mode
    r = load("scifact")
    for ax, mode, title in ((axes[0], "random", "scifact, arbitrary grouping"),
                            (axes[1], "coherent",
                             "scifact, topically coherent grouping")):
        for m, col in zip(MODELS, ["C0", "C1", "C2", "C3"]):
            c = r["models"][m]["cells"]
            pc = c["%s|k2|B%d|per_chunk" % (mode, B)]["mean"]
            av = [c["%s|k%d|B%d|avg_group" % (mode, k, B)]["mean"] for k in KS]
            lo = [c["%s|k%d|B%d|avg_group" % (mode, k, B)]["lo"] for k in KS]
            hi = [c["%s|k%d|B%d|avg_group" % (mode, k, B)]["hi"] for k in KS]
            mx = [c["%s|k%d|B%d|max_group" % (mode, k, B)]["mean"] for k in KS]
            ax.errorbar(KS, av, yerr=[np.array(av) - lo, np.array(hi) - av],
                        marker="o", color=col, label=NAMES[m])
            ax.plot(KS, mx, marker="^", ls=":", color=col, alpha=.55)
            ax.axhline(pc, color=col, ls="--", lw=.8, alpha=.5)
        ax.set_xscale("log", base=2)
        ax.set_xticks(KS)
        ax.set_xticklabels(KS)
        ax.set_xlabel("passages averaged per group, k")
        ax.set_ylim(0, 1)
        ax.set_title(title, fontsize=10)
        ax.grid(alpha=.25)
    axes[0].set_ylabel("hit-rate @ 32 retrieved passages")
    axes[0].legend(fontsize=7, loc="lower left")
    axes[1].text(2.1, .06, "dashed = per-chunk index\ndotted ^ = same groups,\n"
                 "max-member score\nsolid o = mean-pooled", fontsize=7)

    # -- panel C: averaging-only cost vs D_eff
    ax = axes[2]
    for ds, mk, cc in (("scifact", "o", "C0"), ("nfcorpus", "s", "C3")):
        for w, fc in ((False, "none"), (True, "full")):
            rr = load(ds, w)
            xs, ys = [], []
            for m in MODELS:
                e = rr["models"][m]
                c = e["cells"]
                key = "random|k8|B%d|%s" % (B, "cost_avg_only" if ds == "scifact"
                                            else "rec_cost_avg_only")
                base = c["random|k8|B%d|%s" % (B, "max_group" if ds == "scifact"
                                               else "max_group_rec")]["mean"]
                xs.append(e["D_eff"])
                ys.append(c[key]["mean"] / base)
            ax.scatter(xs, ys, marker=mk,
                       facecolors=cc if w else "none", edgecolors=cc, s=55,
                       label="%s, %s" % (ds, "whitened" if w else "native"))
    ax.set_xscale("log")
    ax.set_xlabel("effective dimension (participation ratio)")
    ax.set_ylabel("fraction of max-member accuracy\nlost to mean-pooling (k=8)")
    ax.set_title("cost of averaging vs D_eff", fontsize=10)
    ax.legend(fontsize=7)
    ax.grid(alpha=.25)

    fig.tight_layout()
    p = os.path.join(RES, "retrieval_cost.png")
    fig.savefig(p, dpi=150)
    print("wrote", p)


if __name__ == "__main__":
    main()
