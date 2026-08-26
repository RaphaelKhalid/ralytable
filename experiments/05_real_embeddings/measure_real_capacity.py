"""Does the VSA bundling-capacity decay (experiments/04_capacity) show up when you
average REAL embeddings, the way RAG / centroid-retrieval pipelines do?

Protocol mirrors 04_capacity exactly:
  pick N distinct items from a pool of V, bundle them (mean, then normalise),
  take the top-N nearest neighbours of the bundle over the whole pool,
  score = |top-N intersect the N sources| / N.

Conditions (all D=384, so dimension is held fixed and only the vector
distribution changes):
  minilm      real mean-pooled all-MiniLM-L6-v2 sentence embeddings
  minilm_ctr  the same, with the corpus mean subtracted (anisotropy removed)
  bagemb      averaged input token embeddings of the same sentences
  gauss       matched random baseline: iid Gaussian, normalised
  bipolar     the exact 04_capacity operation (+-1 codebook, sign() bundle)

Reported alongside: mean pairwise cosine (anisotropy) of each vector set, the
chance baseline N/V, and a query-independence diagnostic that distinguishes
"decays toward chance" from "collapses to a fixed set of hub items".
"""
import json
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
D = 384
NS = [2, 3, 5, 8, 10, 15, 20, 30, 50, 75, 100]
POOLS = [1000, 7600]
TRIALS = 200
rng = np.random.default_rng(0)


def unit(x):
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def build_sets():
    sent = np.load(os.path.join(CACHE, "sent.npy")).astype(np.float64)
    bag = np.load(os.path.join(CACHE, "bag.npy")).astype(np.float64)
    V = len(sent)
    return {
        "minilm": unit(sent),
        "minilm_ctr": unit(sent - sent.mean(0)),
        "bagemb": unit(bag),
        "gauss": unit(rng.normal(size=(V, D))),
        "bipolar": rng.choice([-1.0, 1.0], size=(V, D)) / np.sqrt(D),
    }


def anisotropy(E, n=2000):
    idx = rng.choice(len(E), min(n, len(E)), replace=False)
    S = E[idx] @ E[idx].T
    iu = np.triu_indices(len(idx), 1)
    return float(S[iu].mean()), float(S[iu].std())


def run(E, V, N, trials=TRIALS, bipolar=False):
    """Returns (per-trial accuracies, per-trial top-N sets)."""
    pool = E[:V]
    accs, tops = [], []
    for _ in range(trials):
        idx = rng.choice(V, N, replace=False)
        b = pool[idx].sum(0)
        if bipolar:  # match 04_capacity's sign() bundle exactly
            b = np.sign(b + 1e-9 * rng.normal(size=D))
        b = b / np.linalg.norm(b)
        top = np.argpartition(-(pool @ b), N)[:N]
        accs.append(len(set(top.tolist()) & set(idx.tolist())) / N)
        tops.append(set(top.tolist()))
    return np.array(accs), tops


def ci95(a):
    m = a.mean()
    h = 1.96 * a.std(ddof=1) / np.sqrt(len(a))
    return m, max(0.0, m - h), min(1.0, m + h)


def hub_overlap(tops, N):
    """Mean Jaccard-ish overlap between top-N sets of DIFFERENT bundles.
    High => the retriever returns the same hub items no matter what you ask."""
    k = min(60, len(tops))
    vals = [len(tops[i] & tops[j]) / N
            for i in range(k) for j in range(i + 1, k)]
    return float(np.mean(vals))


def main():
    sets = build_sets()
    print("mean pairwise cosine (anisotropy), 2000-item sample:")
    aniso = {}
    for k, E in sets.items():
        m, s = anisotropy(E)
        aniso[k] = m
        print(f"  {k:<11} mean={m:+.4f}  sd={s:.4f}")

    rows = []
    for V in POOLS:
        print(f"\n=== pool V={V}, D={D}, {TRIALS} trials, 95% CI over trials ===")
        print(f"{'N':>4} {'chance':>7} " + " ".join(f"{k:>22}" for k in sets))
        for N in NS:
            cells, rec = [], {"V": V, "N": N, "chance": N / V}
            for k, E in sets.items():
                a, tops = run(E, V, N, bipolar=(k == "bipolar"))
                m, lo, hi = ci95(a)
                rec[k] = {"acc": m, "lo": lo, "hi": hi,
                          "hub": hub_overlap(tops, N)}
                cells.append(f"{m:.3f} [{lo:.3f},{hi:.3f}]".rjust(22))
            print(f"{N:>4} {N/V:>7.4f} " + " ".join(cells))
            rows.append(rec)

    print("\nquery-independence (mean overlap between top-N sets of DIFFERENT "
          "bundles; chance = N/V):")
    print(f"{'N':>4} {'chance':>7} " + " ".join(f"{k:>11}" for k in sets))
    for r in [r for r in rows if r["V"] == 7600]:
        print(f"{r['N']:>4} {r['chance']:>7.4f} " +
              " ".join(f"{r[k]['hub']:>11.3f}" for k in sets))

    out = os.path.join(HERE, "results.json")
    with open(out, "w") as f:
        json.dump({"aniso": aniso, "rows": rows, "trials": TRIALS,
                   "D": D, "pools": POOLS}, f, indent=1)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
