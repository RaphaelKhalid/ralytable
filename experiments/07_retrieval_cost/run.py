"""Does mean-pooling passages into group vectors cost real retrieval accuracy?

Three indexes over the SAME corpus, evaluated at a MATCHED passage budget B:

  per-chunk   retrieve top-B passages directly.                    (baseline)
  avg-group   partition passages into groups of k, represent each group by the
              L2-normalised mean of its members, retrieve top B/k groups, expand
              to their members -> exactly B passages.
  max-group   identical grouping and identical B/k group budget, but a group is
              scored by the MAX cosine over its members instead of by its mean.

A query counts as a hit if any gold passage is in the B passages returned.  All
three therefore return exactly B passages and are scored by the same rule, which
is the comparability control: retrieving a group is not credited as easier than
retrieving a passage, because a group costs k slots of the budget.

max-group isolates the cost of AVERAGING from the cost of COARSE GRANULARITY:
same grouping, same group budget, no information destruction, so
(max-group - avg-group) is attributable to the mean-pooling itself.

Grouping modes: "random" (arbitrary chunk co-location) and "coherent" (each
group is a passage plus its nearest neighbours, mimicking chunks of one real
document).  Coherent grouping is the charitable case.

Also: an intervention test of the effective-dimension hypothesis -- PCA-whiten
the space (which raises D_eff to ~D by construction) and re-measure the cost.
"""
import os
import json
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

MODELS = ["minilm", "mpnet", "bge", "gte"]
KS = [2, 4, 8, 16]
BUDGETS = [16, 32, 64]
SEEDS = [0, 1, 2, 3, 4]
NBOOT = 2000


def l2(X):
    return X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)


def d_eff(X):
    """Participation ratio of the covariance spectrum of unit-norm embeddings."""
    Z = l2(X)
    Z = Z - Z.mean(0, keepdims=True)
    lam = np.linalg.eigvalsh(np.cov(Z, rowvar=False))
    lam = np.clip(lam, 0, None)
    return float(lam.sum() ** 2 / max((lam ** 2).sum(), 1e-30))


def whiten(C, Q, eps=1e-3):
    mu = C.mean(0, keepdims=True)
    cov = np.cov(C - mu, rowvar=False)
    w, V = np.linalg.eigh(cov)
    W = V @ np.diag(1.0 / np.sqrt(np.clip(w, 0, None) + eps * w.max())) @ V.T
    return (C - mu) @ W, (Q - mu) @ W


def group_assign(C, k, seed, mode):
    """Return an (ngroup, k) array of member indices."""
    n = C.shape[0]
    rng = np.random.default_rng(seed)
    if mode == "random":
        order = rng.permutation(n)
    else:
        Z = l2(C)
        unused = np.ones(n, bool)
        order = np.empty(n, int)
        pos = 0
        for s in rng.permutation(n):
            if not unused[s]:
                continue
            sims = Z @ Z[s]
            sims[~unused] = -np.inf
            take = np.argpartition(-sims, min(k, int(unused.sum())) - 1)[:k]
            take = take[unused[take]]
            order[pos:pos + len(take)] = take
            unused[take] = False
            pos += len(take)
        order = order[:pos]
    ngroup = len(order) // k
    return order[:ngroup * k].reshape(ngroup, k)


def eval_all(C, Q, gold, k, seed, mode, budgets):
    """gold: per-query arrays of corpus indices. Returns {B: {name: hitvec}}."""
    Zc, Zq = l2(C), l2(Q)
    groups = group_assign(C, k, seed, mode)
    kept = groups.ravel()
    gvec = l2(Zc[groups].mean(1))
    Sg = Zq @ gvec.T
    Sc = Zq @ Zc.T
    Smax = Sc[:, kept].reshape(Sc.shape[0], groups.shape[0], k).max(2)

    out = {}
    for B in budgets:
        g = B // k
        top_c = np.argpartition(-Sc, B, axis=1)[:, :B]
        top_g = np.argpartition(-Sg, g, axis=1)[:, :g]
        top_m = np.argpartition(-Smax, g, axis=1)[:, :g]
        hits = {n: [] for n in ("per_chunk", "avg_group", "max_group",
                                "per_chunk_rec", "avg_group_rec", "max_group_rec")}
        for qi, gd in enumerate(gold):
            gs = set(gd.tolist())
            got = set(top_c[qi].tolist())
            hits["per_chunk"].append(bool(gs & got))
            hits["per_chunk_rec"].append(len(gs & got) / len(gs))
            for name, tg in (("avg_group", top_g), ("max_group", top_m)):
                got = set(groups[tg[qi]].ravel().tolist())
                hits[name].append(bool(gs & got))
                hits[name + "_rec"].append(len(gs & got) / len(gs))
        out[B] = {n: np.array(v, float) for n, v in hits.items()}
    keptset = set(kept.tolist())
    out["coverage"] = float(np.mean([len(set(g.tolist()) & keptset) > 0
                                     for g in gold]))
    return out


def boot_ci(x, seed=0):
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), (NBOOT, len(x)))
    b = x[idx].mean(1)
    return float(x.mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def run(ds, whitened, models=MODELS):
    meta = json.load(open(os.path.join(CACHE, ds + "_meta.json")))
    cids, qids, pos = meta["cids"], meta["qids"], meta["pos"]
    cidx = {c: i for i, c in enumerate(cids)}
    gold = [np.array([cidx[d] for d in pos[q]]) for q in qids]

    res = {"dataset": ds, "whitened": whitened, "n_queries": len(qids),
           "n_passages": len(cids), "seeds": SEEDS, "budgets": BUDGETS,
           "ks": KS, "models": {}}
    for m in models:
        C = np.load(os.path.join(CACHE, ds + "_" + m + "_corpus.npy"))
        Q = np.load(os.path.join(CACHE, ds + "_" + m + "_queries.npy"))
        if whitened:
            C, Q = whiten(C, Q)
        de = d_eff(C)
        entry = {"D": int(C.shape[1]), "D_eff": de, "cells": {}, "coverage": {}}
        print("[%s%s] %s: D=%d D_eff=%.1f" %
              (ds, " whitened" if whitened else "", m, C.shape[1], de), flush=True)
        for mode in ("random", "coherent"):
            acc, cov = {}, []
            for k in KS:
                for s in SEEDS:
                    r = eval_all(C, Q, gold, k, s, mode, BUDGETS)
                    cov.append(r["coverage"])
                    for B in BUDGETS:
                        for name, v in r[B].items():
                            acc.setdefault((k, B, name), []).append(v)
            for (k, B, name), vs in acc.items():
                mu, lo, hi = boot_ci(np.mean(vs, 0))
                entry["cells"]["%s|k%d|B%d|%s" % (mode, k, B, name)] = dict(
                    mean=mu, lo=lo, hi=hi,
                    per_seed=[float(v.mean()) for v in vs])
            for k in KS:
                for B in BUDGETS:
                    pc = np.mean(acc[(k, B, "per_chunk")], 0)
                    av = np.mean(acc[(k, B, "avg_group")], 0)
                    mx = np.mean(acc[(k, B, "max_group")], 0)
                    pcr = np.mean(acc[(k, B, "per_chunk_rec")], 0)
                    avr = np.mean(acc[(k, B, "avg_group_rec")], 0)
                    mxr = np.mean(acc[(k, B, "max_group_rec")], 0)
                    for nm, a, b in (("cost_total", pc, av),
                                     ("cost_avg_only", mx, av),
                                     ("cost_granularity", pc, mx),
                                     ("rec_cost_total", pcr, avr),
                                     ("rec_cost_avg_only", mxr, avr)):
                        mu, lo, hi = boot_ci(a - b)
                        entry["cells"]["%s|k%d|B%d|%s" % (mode, k, B, nm)] = dict(
                            mean=mu, lo=lo, hi=hi)
            entry["coverage"][mode] = float(np.mean(cov))
        res["models"][m] = entry
    name = "results_%s%s.json" % (ds, "_whitened" if whitened else "")
    p = os.path.join(HERE, name)
    json.dump(res, open(p, "w"), indent=1)
    print("wrote", p)
    return res


if __name__ == "__main__":
    dsname = sys.argv[1] if len(sys.argv) > 1 else "scifact"
    run(dsname, False)
    run(dsname, True)
