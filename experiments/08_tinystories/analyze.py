"""Aggregate results.jsonl into the table and the figure that go in FINDINGS.md.

Two rules this repo learned the hard way and this script enforces:

  1. Nothing is reported as a single number. Every cell is a mean over seeds
     with a 95% Student-t interval, and the gap is computed as a per-seed
     PAIRED difference where seeds line up, which removes the shared
     seed-to-seed variance instead of pretending it is not there.
  2. Cross-entropy and the VQ commitment term are printed in separate columns.
     They are never added.

  python analyze.py            # table + figure from results.jsonl
"""
import json, math, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run import mean_ci   # one definition of the interval, not two

RESULTS = HERE / "results.jsonl"
FIG = HERE / "gap.png"


def load(smoke=False):
    rows = []
    for line in RESULTS.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("smoke") == smoke and r.get("status") == "ok":
            rows.append(r)
    # a rerun of the same (config,seed) supersedes the earlier one
    keep = {}
    for r in rows:
        keep[(r["config"], r["seed"])] = r
    return list(keep.values())


def table(rows):
    by = {}
    for r in rows:
        by.setdefault(r["config"], []).append(r)
    order = ["dense"] + sorted(k for k in by if k != "dense")
    out = []
    out.append("| config | seeds | params | val CE | val ppl | top-1 acc | "
               "commit loss | live codes |")
    out.append("|---|---|---|---|---|---|---|---|")
    for k in order:
        v = by.get(k)
        if not v:
            continue
        ce, cci = mean_ci([r["val_ce"] for r in v])
        pp, pci = mean_ci([r["val_ppl"] for r in v])
        ac, aci = mean_ci([r["val_acc"] for r in v])
        com = [r["commit"] for r in v if r["commit"] is not None]
        cs = f"{mean_ci(com)[0]:.2e}" if com else "n/a (no bottleneck)"
        lc = [r["live_codes"] for r in v if r["live_codes"] is not None]
        ls = (f"{sum(lc)/len(lc):.0f} / {v[0]['n_codes']}" if lc else "n/a")
        out.append(f"| {k} | {len(v)} | {v[0]['params']:,} | {ce:.4f} ± {cci:.4f} | "
                   f"{pp:.2f} ± {pci:.2f} | {ac*100:.2f}% ± {aci*100:.2f} | {cs} | {ls} |")
    return "\n".join(out), by


def gaps(by):
    if "dense" not in by:
        return ""
    d = {r["seed"]: r for r in by["dense"]}
    out = ["| config | ΔCE vs dense | Δtop-1 acc (points) | paired seeds |",
           "|---|---|---|---|"]
    for k, v in by.items():
        if k == "dense":
            continue
        pairs = [(r, d[r["seed"]]) for r in v if r["seed"] in d]
        if not pairs:
            continue
        dce, dci = mean_ci([a["val_ce"] - b["val_ce"] for a, b in pairs])
        dac, dai = mean_ci([(b["val_acc"] - a["val_acc"]) * 100 for a, b in pairs])
        out.append(f"| {k} | {dce:+.4f} ± {dci:.4f} | {dac:+.2f} ± {dai:.2f} | "
                   f"{len(pairs)} |")
    return "\n".join(out)


def gen_table(rows):
    """Generated-text statistics next to the same statistics on REAL held-out text.

    Reporting distinct-2 or OOV alone would be meaningless: they are properties
    of the surface form, and the corpus itself has a value for each. The real
    column IS the baseline. A model far from it in either direction is wrong.
    """
    by = {}
    for r in rows:
        if r.get("gen"):
            by.setdefault(r["config"], []).append(r["gen"])
    if not by:
        return ""
    out = ["| config | distinct-2 | type/token | OOV word rate | mean word len |",
           "|---|---|---|---|---|"]
    keys = ["distinct_2", "type_token", "oov", "mean_word_len"]
    for k, v in by.items():
        m = [f"{mean_ci([g['model'][x] for g in v])[0]:.4f}" for x in keys]
        out.append(f"| {k} | " + " | ".join(m) + " |")
    ref = [f"{mean_ci([g['real_heldout_baseline'][x] for v in by.values() for g in v])[0]:.4f}"
           for x in keys]
    out.append("| **real held-out text (baseline)** | " + " | ".join(ref) + " |")
    return "\n".join(out)


def figure(rows):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"  (no figure: {type(e).__name__})")
        return
    by = {}
    for r in rows:
        by.setdefault(r["config"], []).append(r)
    order = ["dense"] + sorted(k for k in by if k != "dense")
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    for ax, key, lab, scale in ((axes[0], "val_ce", "held-out cross-entropy (nats/token)", 1),
                                (axes[1], "val_acc", "held-out top-1 accuracy (%)", 100)):
        xs, ms, es = [], [], []
        for i, k in enumerate(order):
            vals = [r[key] * scale for r in by[k]]
            m, ci = mean_ci(vals)
            xs.append(i)
            ms.append(m)
            es.append(0 if math.isnan(ci) else ci)
            ax.scatter([i] * len(vals), vals, s=16, color="#8b93a7", zorder=3)
        ax.errorbar(xs, ms, yerr=es, fmt="o", color="#1f4e9c", capsize=5,
                    markersize=7, zorder=4, linestyle="none")
        ax.set_xticks(xs)
        ax.set_xticklabels(order)
        ax.set_xlim(-0.5, len(order) - 0.5)
        ax.set_ylabel(lab, fontsize=9)
        ax.grid(axis="y", alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("TinyStories, ~29.5M parameters matched to 0.22%: "
                 "dots are seeds, bars are 95% CI", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG, dpi=150)
    print(f"  figure -> {FIG.name}")


if __name__ == "__main__":
    smoke = "--smoke" in sys.argv
    rows = load(smoke)
    if not rows:
        sys.exit("no completed runs in results.jsonl")
    t, by = table(rows)
    print("\n" + t)
    print("\n" + gaps(by))
    g = gen_table(rows)
    if g:
        print("\n" + g)
    figure(rows)
