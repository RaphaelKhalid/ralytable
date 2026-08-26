"""Attacks on the main result. Each one is a way it could be an artifact.

C1  hubness            do a few "hub" groups get returned for every query, the
                       failure mode found in experiments/05?
C2  pooling variant    is the loss an artefact of normalising members before
                       averaging?  Try raw-mean and sum pooling.
C3  over-fetch rescue  does simply retrieving more (larger B) close the gap?
C4  D_eff vs baseline  is "high D_eff -> low cost" just "good model -> low cost"?
                       Report cost, relative cost, and the rank correlation of
                       D_eff with cost after conditioning on baseline recall.
C5  granularity floor  an ORACLE grouped index (a group is scored by whether it
                       contains a gold passage is not available, so we use the
                       max-member score, already in run.py) -- here we report
                       the k-wise decomposition explicitly.
"""
import os
import json
import itertools
import numpy as np
from run import (CACHE, HERE, MODELS, KS, BUDGETS, SEEDS, l2, d_eff, whiten,
                 group_assign, boot_ci)


def load(ds, m):
    C = np.load(os.path.join(CACHE, ds + "_" + m + "_corpus.npy"))
    Q = np.load(os.path.join(CACHE, ds + "_" + m + "_queries.npy"))
    meta = json.load(open(os.path.join(CACHE, ds + "_meta.json")))
    cidx = {c: i for i, c in enumerate(meta["cids"])}
    gold = [np.array([cidx[d] for d in meta["pos"][q]]) for q in meta["qids"]]
    return C, Q, gold


def c1_hubness(ds, m, k=8, B=32, mode="random", seed=0):
    """Fraction of query pairs whose retrieved group sets overlap, vs the
    per-chunk index's overlap at the same passage budget."""
    C, Q, gold = load(ds, m)
    Zc, Zq = l2(C), l2(Q)
    groups = group_assign(C, k, seed, mode)
    gvec = l2(Zc[groups].mean(1))
    g = B // k
    top_g = np.argpartition(-(Zq @ gvec.T), g, axis=1)[:, :g]
    top_c = np.argpartition(-(Zq @ Zc.T), B, axis=1)[:, :B]

    def ov(top):
        n = top.shape[0]
        sets = [set(r.tolist()) for r in top]
        pairs = [len(sets[i] & sets[j]) / top.shape[1]
                 for i, j in itertools.combinations(range(n), 2)]
        return float(np.mean(pairs))
    ngroup = groups.shape[0]
    return dict(group_overlap=ov(top_g), chunk_overlap=ov(top_c),
                group_chance=g / ngroup, chunk_chance=B / C.shape[0],
                distinct_groups=int(len(set(top_g.ravel().tolist()))),
                n_groups=int(ngroup))


def c2_pooling(ds, m, mode="random", ks=(4, 8, 16), B=32, seeds=(0, 1, 2)):
    """avg_group hit-rate under three pooling rules."""
    C, Q, gold = load(ds, m)
    Zc, Zq = l2(C), l2(Q)
    out = {}
    for k in ks:
        for rule in ("norm_mean", "raw_mean", "sum_raw"):
            hs = []
            for s in seeds:
                groups = group_assign(C, k, s, mode)
                if rule == "norm_mean":
                    gv = l2(Zc[groups].mean(1))
                elif rule == "raw_mean":
                    gv = l2(C[groups].mean(1))
                else:
                    gv = C[groups].sum(1)      # deliberately un-normalised
                g = B // k
                top = np.argpartition(-(Zq @ gv.T), g, axis=1)[:, :g]
                hs.append(np.array([bool(set(gd.tolist()) &
                                         set(groups[top[qi]].ravel().tolist()))
                                    for qi, gd in enumerate(gold)], float))
            out["k%d|%s" % (k, rule)] = float(np.mean(hs))
    return out


def c3_overfetch(res):
    """Cost as a function of budget, at fixed k."""
    out = {}
    for m, e in res["models"].items():
        for mode in ("random", "coherent"):
            for k in KS:
                out["%s|%s|k%d" % (m, mode, k)] = {
                    "B%d" % B: round(e["cells"]["%s|k%d|B%d|cost_total"
                                                % (mode, k, B)]["mean"], 3)
                    for B in BUDGETS}
    return out


def c4_deff(res_native, res_white, mode="random", k=8, B=32):
    rows = []
    for tag, res in (("native", res_native), ("whitened", res_white)):
        for m, e in res["models"].items():
            c = e["cells"]
            pc = c["%s|k%d|B%d|per_chunk" % (mode, k, B)]["mean"]
            tot = c["%s|k%d|B%d|cost_total" % (mode, k, B)]["mean"]
            avg = c["%s|k%d|B%d|cost_avg_only" % (mode, k, B)]["mean"]
            rows.append(dict(model=m, space=tag, D=e["D"], D_eff=e["D_eff"],
                             baseline=pc, cost_total=tot, cost_avg_only=avg,
                             rel_total=tot / pc, rel_avg_only=avg / pc))

    def sp(a, b):
        from scipy.stats import spearmanr
        r = spearmanr(a, b)
        return float(r.statistic), float(r.pvalue)
    de = [r["D_eff"] for r in rows]
    bl = [r["baseline"] for r in rows]
    ct = [r["rel_avg_only"] for r in rows]
    nat = [r for r in rows if r["space"] == "native"]
    stats = {
        "all8_Deff_vs_relavgcost": sp(de, ct),
        "all8_Deff_vs_baseline": sp(de, bl),
        "all8_baseline_vs_relavgcost": sp(bl, ct),
        "native4_Deff_vs_relavgcost": sp([r["D_eff"] for r in nat],
                                         [r["rel_avg_only"] for r in nat]),
        "native4_Deff_vs_baseline": sp([r["D_eff"] for r in nat],
                                       [r["baseline"] for r in nat]),
    }
    return rows, stats


def main():
    ds = os.environ.get("DS", "scifact")
    rn = json.load(open(os.path.join(HERE, "results_%s.json" % ds)))
    rw = json.load(open(os.path.join(HERE, "results_%s_whitened.json" % ds)))
    out = {"dataset": ds}
    out["C1_hubness"] = {m: c1_hubness(ds, m) for m in MODELS}
    out["C2_pooling"] = {m: c2_pooling(ds, m) for m in MODELS}
    out["C3_overfetch"] = c3_overfetch(rn)
    rows, stats = c4_deff(rn, rw)
    out["C4_rows"], out["C4_stats"] = rows, stats
    p = os.path.join(HERE, "controls_%s.json" % ds)
    json.dump(out, open(p, "w"), indent=1)
    print(json.dumps({"C1": out["C1_hubness"], "C4_stats": stats}, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
