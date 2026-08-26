"""Does the LLM-annotated dependency graph predict measured causal importance?

The released Thought Anchors data carries both, per chunk, in the same file:

  depends_on                          <- an LLM judge's CLAIM about what this step uses
  counterfactual_importance_kl        <- MEASURED by resampling ~100 continuations
  overdeterminedness                  <- how redundantly supported the step is
  chunk_idx                           <- position, the paper's admitted confound

`depends_on` is written by analyze_rollouts.py and then never read again. It is
never checked against the causal measures. This script checks it.

If the claimed graph is causally real, a step that many later steps transitively
depend on should matter more when you resample it. Position is controlled, because
early steps mechanically have more room to matter AND more room to be depended on --
which would manufacture the correlation on its own.
"""
import json, pathlib, sys
import numpy as np, pandas as pd
from scipy import stats

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "math-rollouts"


def descendants(dep, n):
    """dep[i] = chunks i directly uses. Return transitive descendant count per chunk."""
    children = {i: set() for i in range(n)}          # i -> chunks that use i
    for i, parents in dep.items():
        for p in parents:
            if 0 <= p < n:
                children[p].add(i)
    out = {}
    for i in range(n):
        seen, stack = set(), list(children[i])
        while stack:
            c = stack.pop()
            if c in seen:
                continue
            seen.add(c)
            stack.extend(children[c] - seen)
        out[i] = len(seen)
    return out


rows = []
for f in sorted(DATA.rglob("chunks_labeled.json")):
    model = f.relative_to(DATA).parts[0]
    chunks = json.loads(f.read_text(encoding="utf-8"))
    n = len(chunks)
    dep = {}
    for c in chunks:
        i = c["chunk_idx"]
        dep[i] = [int(x) for x in c.get("depends_on", []) if str(x).lstrip("-").isdigit()]
    desc = descendants(dep, n)
    for c in chunks:
        i = c["chunk_idx"]
        rows.append({
            "model": model, "problem": f.parent.name, "chunk_idx": i, "n_chunks": n,
            "rel_pos": i / max(n - 1, 1),
            "in_degree": len(dep[i]),                       # what it claims to use
            "out_degree": sum(i in v for v in dep.values()), # what claims to use it
            "n_descendants": desc[i],
            "frac_descendants": desc[i] / max(n - 1, 1),
            "cf_kl": c.get("counterfactual_importance_kl"),
            "cf_acc": c.get("counterfactual_importance_accuracy"),
            "resamp_kl": c.get("resampling_importance_kl"),
            "overdet": c.get("overdeterminedness"),
            "tags": ",".join(c.get("function_tags", [])),
        })

df = pd.DataFrame(rows).dropna(subset=["cf_kl"])
print(f"{len(df)} chunks | {df.problem.nunique()} problems | {df.model.nunique()} models\n")


def partial_spearman(x, y, z):
    """Spearman(x,y) with z partialled out, on ranks."""
    rx, ry, rz = (stats.rankdata(v) for v in (x, y, z))
    res = []
    for r in (rx, ry):
        b = np.polyfit(rz, r, 1)
        res.append(r - np.polyval(b, rz))
    return stats.pearsonr(res[0], res[1])


TARGET = "cf_kl"
print(f"target = {TARGET} (counterfactual importance, KL)\n")
print(f"{'predictor':18} {'spearman':>9} {'p':>10} {'partial|pos':>12} {'p':>10}")
for pred in ["n_descendants", "frac_descendants", "out_degree", "in_degree", "overdet"]:
    sub = df.dropna(subset=[pred, TARGET])
    r, p = stats.spearmanr(sub[pred], sub[TARGET])
    pr, pp = partial_spearman(sub[pred].values, sub[TARGET].values, sub["rel_pos"].values)
    print(f"{pred:18} {r:9.3f} {p:10.2e} {pr:12.3f} {pp:10.2e}")

print(f"\n{'position sanity check':18}")
r, p = stats.spearmanr(df["rel_pos"], df[TARGET])
print(f"{'rel_pos':18} {r:9.3f} {p:10.2e}   <- the paper's admitted confound")
r, p = stats.spearmanr(df["rel_pos"], df["n_descendants"])
print(f"{'rel_pos ~ n_desc':18} {r:9.3f} {p:10.2e}   <- why partialling is required")

print("\nper model:")
for m, g in df.groupby("model"):
    r, _ = stats.spearmanr(g["n_descendants"], g[TARGET])
    pr, pp = partial_spearman(g["n_descendants"].values, g[TARGET].values, g["rel_pos"].values)
    print(f"  {m:34} n={len(g):5} raw={r:6.3f}  partial={pr:6.3f} (p={pp:.1e})")

print("\nwithin-problem (each trace its own control):")
zs = []
for (m, p_), g in df.groupby(["model", "problem"]):
    if len(g) < 20 or g["n_descendants"].nunique() < 3:
        continue
    r, _ = stats.spearmanr(g["n_descendants"], g[TARGET])
    if not np.isnan(r):
        zs.append(np.arctanh(np.clip(r, -0.999, 0.999)))
zs = np.array(zs)
t, pv = stats.ttest_1samp(zs, 0)
print(f"  {len(zs)} traces | mean rho={np.tanh(zs.mean()):.3f} | t={t:.2f} p={pv:.2e}")

df.to_csv(ROOT / "results" / "claimed_vs_causal.csv", index=False)
print(f"\n-> results/claimed_vs_causal.csv")
