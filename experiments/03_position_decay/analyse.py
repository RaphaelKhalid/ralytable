"""Is causal-importance decay with position a runway artifact or early commitment?

Tests:
1. Compare within-trace Spearman of counterfactual_importance_kl against:
   chunk_idx, relative position (chunk_idx/n_chunks), remaining steps (n_chunks-chunk_idx),
   log1p(remaining steps).
2. Length test: bin traces by length (median split), compare importance at matched
   absolute chunk_idx ranges (early window, e.g. chunks 10-25) between short and long traces.
3. Ceiling control: restrict to chunks with accuracy q in [0.3, 0.7] (mid-range, not yet
   near ceiling) and re-run the position correlation within that subset, per trace.

Methodology: within-trace Spearman, Fisher-z averaged across traces, 95% CI via normal
approx on z. No pooling across traces for primary stats.
"""
import json, glob, math
import numpy as np
from scipy import stats

ROOT = "data/math-rollouts"
MODELS = ["deepseek-r1-distill-qwen-14b", "deepseek-r1-distill-llama-8b"]

def load_traces():
    traces = []
    for m in MODELS:
        pattern = f"{ROOT}/{m}/temperature_0.6_top_p_0.95/correct_base_solution/problem_*/chunks_labeled.json"
        for f in glob.glob(pattern):
            chunks = json.load(open(f, encoding="utf-8"))
            if not isinstance(chunks, list) or len(chunks) < 5:
                continue
            traces.append({"model": m, "file": f, "chunks": chunks})
    return traces

def fisher_z_avg(rhos):
    rhos = np.array([r for r in rhos if r is not None and not math.isnan(r)])
    if len(rhos) == 0:
        return None, None, 0
    z = np.arctanh(np.clip(rhos, -0.999999, 0.999999))
    zbar = np.mean(z)
    se = 1.0 / math.sqrt(len(z))  # se of mean of z's, using n traces (conservative: 1/sqrt(n-1) variance per-trace ignored, use n traces as unit)
    se = np.std(z, ddof=1) / math.sqrt(len(z)) if len(z) > 1 else float("nan")
    lo, hi = zbar - 1.96 * se, zbar + 1.96 * se
    return math.tanh(zbar), (math.tanh(lo), math.tanh(hi)), len(z)

def spearman_safe(x, y):
    if len(x) < 5 or np.std(x) == 0 or np.std(y) == 0:
        return None
    r, _ = stats.spearmanr(x, y)
    return r

def main():
    traces = load_traces()
    print(f"Loaded {len(traces)} traces")

    metric = "counterfactual_importance_kl"

    # --- Test 1: reparameterisation ---
    results = {"chunk_idx": [], "relpos": [], "remaining": [], "logremaining": []}
    lengths = []
    for t in traces:
        chunks = t["chunks"]
        n = len(chunks)
        lengths.append(n)
        idx = np.array([c["chunk_idx"] for c in chunks], dtype=float)
        imp = np.array([c.get(metric, np.nan) for c in chunks], dtype=float)
        mask = ~np.isnan(imp)
        idx, imp = idx[mask], imp[mask]
        if len(idx) < 5:
            continue
        remaining = n - idx
        results["chunk_idx"].append(spearman_safe(idx, imp))
        results["relpos"].append(spearman_safe(idx / n, imp))
        results["remaining"].append(spearman_safe(remaining, imp))
        results["logremaining"].append(spearman_safe(np.log1p(remaining), imp))

    print("\n=== Test 1: reparameterisation (metric = counterfactual_importance_kl) ===")
    for k, v in results.items():
        m, ci, n = fisher_z_avg(v)
        print(f"{k:15s} rho={m:+.3f}  CI=[{ci[0]:+.3f},{ci[1]:+.3f}]  n={n}")

    # --- Test 2: length test - importance at matched absolute chunk_idx window (10-25) ---
    med_len = np.median(lengths)
    short_vals, long_vals = [], []
    for t, n in zip(traces, lengths):
        chunks = t["chunks"]
        window = [c for c in chunks if 10 <= c["chunk_idx"] <= 25 and metric in c]
        if not window:
            continue
        vals = [c[metric] for c in window]
        mean_v = np.mean(vals)
        if n <= med_len:
            short_vals.append(mean_v)
        else:
            long_vals.append(mean_v)
    print(f"\n=== Test 2: length test (median trace length = {med_len:.0f}) ===")
    print(f"short traces (n={len(short_vals)}): mean importance @ chunks 10-25 = {np.mean(short_vals):.4f} +/- {np.std(short_vals, ddof=1)/math.sqrt(len(short_vals)):.4f}")
    print(f"long  traces (n={len(long_vals)}): mean importance @ chunks 10-25 = {np.mean(long_vals):.4f} +/- {np.std(long_vals, ddof=1)/math.sqrt(len(long_vals)):.4f}")
    tstat, pval = stats.ttest_ind(short_vals, long_vals)
    print(f"two-sample t-test: t={tstat:.2f}, p={pval:.4f}")
    print("(runway/artifact predicts long-trace chunk-10-25 importance >> short-trace's, since runway is huge either way this test mainly checks whether ABSOLUTE position anchors importance regardless of length)")

    # --- Test 3: ceiling control - restrict to accuracy in [0.3, 0.7] ---
    ceiling_rhos = []
    ceiling_n_chunks = []
    for t in traces:
        chunks = t["chunks"]
        idx, imp = [], []
        for c in chunks:
            q = c.get("accuracy")
            v = c.get(metric)
            if q is None or v is None or math.isnan(v):
                continue
            if 0.3 <= q <= 0.7:
                idx.append(c["chunk_idx"])
                imp.append(v)
        ceiling_n_chunks.append(len(idx))
        if len(idx) >= 5:
            ceiling_rhos.append(spearman_safe(np.array(idx, float), np.array(imp, float)))
        else:
            ceiling_rhos.append(None)

    n_usable = sum(1 for r in ceiling_rhos if r is not None)
    m, ci, n = fisher_z_avg(ceiling_rhos)
    print(f"\n=== Test 3: ceiling control (accuracy q in [0.3,0.7], >=5 chunks/trace required) ===")
    print(f"traces with >=5 mid-q chunks: {n_usable}/{len(traces)}; median mid-q chunks/trace = {np.median(ceiling_n_chunks):.0f}")
    if n:
        print(f"rho (position vs importance, restricted to mid-q) = {m:+.3f}  CI=[{ci[0]:+.3f},{ci[1]:+.3f}]  n_traces={n}")
    else:
        print("insufficient data")

    # full-trace baseline for comparison (already known ~-0.55, recompute here for consistency)
    base_rhos = results["chunk_idx"]
    mb, cib, nb = fisher_z_avg(base_rhos)
    print(f"\n(baseline, all chunks, position vs importance): rho={mb:+.3f} CI=[{cib[0]:+.3f},{cib[1]:+.3f}] n={nb}")

if __name__ == "__main__":
    main()
