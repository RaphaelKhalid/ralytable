"""Controls that try to KILL the finding from measure_real_capacity.py.

C1 near-duplicate rescue: a "miss" is only a real failure if the item that took
   the slot is not a paraphrase of the missed item. For every missed source we
   record its cosine to the nearest retrieved impostor and recompute accuracy
   under a lenient rule (a miss is forgiven if some retrieved item has cosine
   >= tau to it). If lenient accuracy ~= 1.0, the failure is benign.

C2 effective dimensionality: anisotropy (mean pairwise cosine) is only part of
   the story. Participation ratio of the covariance spectrum says how many
   dimensions the embeddings actually use -- if real D_eff << 384, the matched
   D=384 random baseline is unfair and the honest comparison is a random
   baseline at D_eff.

C3 unnormalised averaging: real code often averages raw embeddings. Check the
   result is not an artefact of the pre-normalisation choice.
"""
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
rng = np.random.default_rng(1)
V, D = 7600, 384


def unit(x):
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


sent_raw = np.load(os.path.join(CACHE, "sent.npy")).astype(np.float64)
bag_raw = np.load(os.path.join(CACHE, "bag.npy")).astype(np.float64)
texts = open(os.path.join(CACHE, "texts.txt"), encoding="utf-8").read().split("\n")


def d_eff(E):
    C = np.cov((E - E.mean(0)).T)
    w = np.linalg.eigvalsh(C).clip(min=0)
    return float(w.sum() ** 2 / (w ** 2).sum())


def trial_sets(E, N, trials):
    for _ in range(trials):
        idx = rng.choice(len(E), N, replace=False)
        b = E[idx].sum(0)
        b = b / np.linalg.norm(b)
        top = np.argpartition(-(E @ b), N)[:N]
        yield idx, top


def c1(E, N, taus=(0.9, 0.8, 0.7), trials=200):
    strict, lenient = [], {t: [] for t in taus}
    near = []
    for idx, top in trial_sets(E, N, trials):
        hit = set(top.tolist()) & set(idx.tolist())
        strict.append(len(hit) / N)
        missed = [i for i in idx if i not in hit]
        if missed:
            sims = E[missed] @ E[top].T          # missed x retrieved
            best = sims.max(1)
            near.extend(best.tolist())
        else:
            best = np.array([])
        for t in taus:
            lenient[t].append((len(hit) + int((best >= t).sum())) / N)
    return (np.mean(strict), {t: float(np.mean(v)) for t, v in lenient.items()},
            np.array(near))


print("C2 effective dimensionality (participation ratio, ambient D=384)")
sets = {"minilm": unit(sent_raw), "bagemb": unit(bag_raw),
        "gauss": unit(rng.normal(size=(V, D)))}
for k, E in sets.items():
    print(f"  {k:<8} D_eff = {d_eff(E):7.1f}")

print("\nC1 near-duplicate rescue, minilm, pool=7600, 200 trials")
print(f"{'N':>4} {'strict':>8} {'tau=.9':>8} {'tau=.8':>8} {'tau=.7':>8} "
      f"{'median cos(missed,best retrieved)':>34}")
for N in [5, 10, 20, 50]:
    s, l, near = c1(sets["minilm"], N)
    med = float(np.median(near)) if len(near) else float("nan")
    print(f"{N:>4} {s:>8.3f} {l[0.9]:>8.3f} {l[0.8]:>8.3f} {l[0.7]:>8.3f} "
          f"{med:>34.3f}")

print("\n  example: a missed sentence and the item that took its slot")
idx, top = next(trial_sets(sets["minilm"], 20, 1))
hit = set(top.tolist()) & set(idx.tolist())
missed = [i for i in idx if i not in hit]
if missed:
    m = missed[0]
    j = top[np.argmax(sets["minilm"][m] @ sets["minilm"][top].T)]
    print(f"   MISSED  : {texts[m][:110]}")
    print(f"   RETURNED: {texts[j][:110]}")
    print(f"   cosine  : {sets['minilm'][m] @ sets['minilm'][j]:.3f}")

print("\nC3 unnormalised averaging (minilm), pool=7600, 200 trials")
raw = sent_raw
print(f"{'N':>4} {'norm-then-avg':>14} {'raw-avg':>10}")
for N in [5, 10, 20, 50]:
    a = c1(sets["minilm"], N, trials=200)[0]
    accs = []
    for _ in range(200):
        i = rng.choice(V, N, replace=False)
        b = raw[i].mean(0)
        top = np.argpartition(-(raw @ b / np.linalg.norm(raw, axis=1)), N)[:N]
        accs.append(len(set(top.tolist()) & set(i.tolist())) / N)
    print(f"{N:>4} {a:>14.3f} {np.mean(accs):>10.3f}")

print("\nC4 random baseline matched to D_eff instead of D=384")
for de in [int(d_eff(sets['minilm'])), int(d_eff(sets['bagemb']))]:
    E = unit(rng.normal(size=(V, max(de, 2))))
    row = []
    for N in [5, 10, 20, 50]:
        accs = [len(set(np.argpartition(-(E @ (E[i].sum(0) /
                np.linalg.norm(E[i].sum(0)))), N)[:N].tolist()) & set(i.tolist())) / N
                for i in (rng.choice(V, N, replace=False) for _ in range(200))]
        row.append(f"{np.mean(accs):.3f}")
    print(f"  gauss D={de:<4} N=5,10,20,50 -> " + " ".join(row))
