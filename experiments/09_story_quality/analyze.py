"""Aggregate the judgements into the tables in FINDINGS.md, and rule on the
preregistered threshold.

THE THRESHOLD WAS FIXED BEFORE ANY OUTPUT WAS LOOKED AT:

    Good enough = the discrete model's GRAMMAR and CONSISTENCY scores are
    within noise of the dense model's, even though its perplexity is worse.

"Within noise" is operationalised here as: the 95% confidence interval on the
dense-minus-discrete difference in that criterion contains zero. It is applied
mechanically below; it is not adjusted after seeing the numbers.

Analysis follows the repo rules: each PROMPT is the unit of comparison (the
same prompt was given to every model, so it is its own control), differences
are taken within prompt and aggregated after, and every number is reported with
an interval rather than as a point estimate.
"""
import argparse, collections, json, math, pathlib

HERE = pathlib.Path(__file__).resolve().parent
CRITERIA = ("grammar", "consistency", "creativity")


def mean_ci(xs, conf=1.96):
    """Mean with a normal-approximation 95% interval. Empty -> nan."""
    n = len(xs)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    m = sum(xs) / n
    if n < 2:
        return m, m, m
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    h = conf * math.sqrt(var / n)
    return m, m - h, m + h


def wilson(k, n, z=1.96):
    """Wilson score interval -- correct near 0 and 1, where normal-approx is not."""
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def fmt(m, lo, hi, w=2):
    if m != m:
        return "n/a"
    return f"{m:.{w}f} [{lo:.{w}f}, {hi:.{w}f}]"


def load(path):
    rows = []
    for line in path.open(encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    # dedupe by key, last wins
    return list({r["key"]: r for r in rows}.values())


def family(arm):
    if arm == "human":
        return "human"
    return "dense" if arm.startswith("dense") else "discrete"


def check_scores(rows):
    """An impossible value is a bug. Scores outside 1-10, or non-integers, are
    not outliers to be trimmed -- they mean the judge did not answer the question
    that was asked, and they are counted and excluded loudly."""
    good, bad = [], 0
    for r in rows:
        p = r.get("parsed")
        if not isinstance(p, dict) or any(
                not isinstance(p.get(c), (int, float)) or not (1 <= p[c] <= 10)
                for c in CRITERIA):
            bad += 1
            continue
        good.append(r)
    return good, bad


def absolute(rows, out):
    abs_rows, bad = check_scores([r for r in rows if r["kind"] == "abs"])
    out.append(f"Absolute protocol: {len(abs_rows)} usable judgements, "
               f"{bad} rejected as malformed or out of the 1-10 range.\n")

    by_arm = collections.defaultdict(list)
    for r in abs_rows:
        by_arm[r["arm"]].append(r)

    out.append("### Absolute scores, 1-10, mean [95% CI]\n")
    out.append("| arm | n | grammar | consistency | creativity |")
    out.append("|---|---|---|---|---|")
    per_arm = {}
    for arm in sorted(by_arm, key=lambda a: (family(a) != "human", a)):
        rs = by_arm[arm]
        cells, per_arm[arm] = [], {}
        for c in CRITERIA:
            xs = [r["parsed"][c] for r in rs]
            per_arm[arm][c] = xs
            cells.append(fmt(*mean_ci(xs)))
        out.append(f"| `{arm}` | {len(rs)} | " + " | ".join(cells) + " |")
    out.append("")

    # --- pooled by family, and the paired within-prompt difference -----------
    fam = collections.defaultdict(lambda: collections.defaultdict(dict))
    for r in abs_rows:
        fam[family(r["arm"])][r["i"]][r["arm"]] = r["parsed"]

    out.append("### Pooled by family, and the paired dense - discrete difference\n")
    out.append("The difference is taken WITHIN prompt: for each prompt, the mean "
               "dense score minus the mean discrete score, averaged over seeds "
               "first. Each prompt is its own control.\n")
    out.append("| criterion | dense | discrete | human | dense - discrete | "
               "zero in CI? |")
    out.append("|---|---|---|---|---|---|")
    verdict = {}
    for c in CRITERIA:
        cells = []
        for f in ("dense", "discrete", "human"):
            xs = [s[c] for pr in fam[f].values() for s in pr.values()]
            cells.append(fmt(*mean_ci(xs)))
        diffs = []
        for i in set(fam["dense"]) & set(fam["discrete"]):
            d = [s[c] for s in fam["dense"][i].values()]
            q = [s[c] for s in fam["discrete"][i].values()]
            if d and q:
                diffs.append(sum(d) / len(d) - sum(q) / len(q))
        m, lo, hi = mean_ci(diffs)
        contains0 = lo <= 0 <= hi
        verdict[c] = contains0
        out.append(f"| {c} | {cells[0]} | {cells[1]} | {cells[2]} | "
                   f"{fmt(m, lo, hi)} | {'YES' if contains0 else 'NO'} |")
    out.append("")

    # --- the sanity control that gates everything else ----------------------
    hum = {c: mean_ci([s[c] for pr in fam["human"].values()
                       for s in pr.values()])[0] for c in CRITERIA}
    den = {c: mean_ci([s[c] for pr in fam["dense"].values()
                       for s in pr.values()])[0] for c in CRITERIA}
    dis = {c: mean_ci([s[c] for pr in fam["discrete"].values()
                       for s in pr.values()])[0] for c in CRITERIA}
    passed = all(hum[c] >= max(den[c], dis[c]) for c in ("grammar", "consistency"))
    out.append(f"**Judge sanity control (real human TinyStories text):** "
               f"{'PASS' if passed else 'FAIL'} -- real held-out text scores "
               + ", ".join(f"{c} {hum[c]:.2f} vs dense {den[c]:.2f} / discrete "
                           f"{dis[c]:.2f}" for c in CRITERIA) + ".\n")
    return verdict, passed


def pairwise(rows, out):
    prs = [r for r in rows if r["kind"] == "pair"
           and isinstance(r.get("parsed"), dict)
           and r["parsed"].get("winner") in ("A", "B", "TIE")]
    dropped = sum(1 for r in rows if r["kind"] == "pair") - len(prs)
    out.append(f"### Pairwise protocol: {len(prs)} usable comparisons, "
               f"{dropped} unparseable\n")

    # position bias: how often does the judge pick slot A, across everything?
    a_picks = sum(1 for r in prs if r["parsed"]["winner"] == "A")
    decisive = sum(1 for r in prs if r["parsed"]["winner"] != "TIE")
    p, lo, hi = wilson(a_picks, decisive)
    out.append(f"**Position-bias check.** Across all {decisive} decisive "
               f"comparisons the judge chose the FIRST slot "
               f"{a_picks} times: {fmt(p, lo, hi, 3)}. Side assignment was "
               f"randomised per comparison by a seeded RNG, so under no position "
               f"bias this is 0.5. "
               + ("It is not, so the judge favours one slot and the pairwise "
                  "numbers below are read with that in mind."
                  if not (lo <= 0.5 <= hi) else
                  "0.5 is inside the interval, so no position bias is detected.")
               + "\n")

    out.append("| comparison | n | wins left | wins right | ties | "
               "left win rate among decisive [95% CI] |")
    out.append("|---|---|---|---|---|---|")
    res = {}
    for tag in ("main", "null", "ceiling"):
        sub = [r for r in prs if r["tag"] == tag]
        if not sub:
            continue
        by_pair = collections.defaultdict(list)
        for r in sub:
            by_pair[(r["left"], r["right"])].append(r)
        agg = collections.Counter()
        for (l, rt), rs in sorted(by_pair.items()):
            c = collections.Counter()
            for r in rs:
                w = r["parsed"]["winner"]
                c["tie" if w == "TIE" else
                  ("left" if (w == "A") == (r["a_arm"] == l) else "right")] += 1
            n = sum(c.values())
            dec = c["left"] + c["right"]
            out.append(f"| {tag}: `{l}` vs `{rt}` | {n} | {c['left']} | "
                       f"{c['right']} | {c['tie']} | "
                       f"{fmt(*wilson(c['left'], dec), 3)} |")
            agg.update(c)
        if len(by_pair) > 1:
            n = sum(agg.values())
            dec = agg["left"] + agg["right"]
            out.append(f"| **{tag}: pooled** | {n} | {agg['left']} | {agg['right']} "
                       f"| {agg['tie']} | {fmt(*wilson(agg['left'], dec), 3)} |")
        res[tag] = agg
    out.append("")

    if "main" in res:
        a = res["main"]
        n = sum(a.values())
        out.append(f"Over all {n} dense-vs-discrete comparisons, counting ties as "
                   f"neither: dense wins {a['left']}, discrete wins {a['right']}, "
                   f"tie {a['tie']} ({a['tie'] / n:.1%} of comparisons).")
        p, lo, hi = wilson(a["left"], a["left"] + a["right"])
        out.append(f"Dense win rate among decisive comparisons: {fmt(p, lo, hi, 3)}. "
                   + ("The 50% null is inside the interval: the judge cannot tell "
                      "them apart."
                      if lo <= 0.5 <= hi else
                      "The 50% null is OUTSIDE the interval, so the judge can tell "
                      "them apart.") + "\n")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=pathlib.Path, default=HERE / "judgements.jsonl")
    ap.add_argument("--out", type=pathlib.Path, default=HERE / "results.md")
    a = ap.parse_args()

    rows = load(a.cache)
    out = ["# Results (generated by analyze.py -- do not edit by hand)\n"]
    spend = sum(r.get("cost", 0.0) for r in rows)
    out.append(f"{len(rows)} judge calls, total API spend **${spend:.4f}**.\n")

    verdict, sane = absolute(rows, out)
    res = pairwise(rows, out)

    out.append("## Preregistered threshold\n")
    out.append("> Good enough = the discrete model's grammar and consistency "
               "scores are within noise of the dense model's, even though its "
               "perplexity is worse.\n")
    met = verdict.get("grammar") and verdict.get("consistency")
    out.append(f"- grammar within noise: **{'YES' if verdict.get('grammar') else 'NO'}**")
    out.append(f"- consistency within noise: "
               f"**{'YES' if verdict.get('consistency') else 'NO'}**")
    out.append(f"- judge sanity control: **{'PASS' if sane else 'FAIL'}**\n")
    out.append(f"**THRESHOLD {'MET' if met else 'NOT MET'}."
               + ("" if sane else " (But the judge failed its sanity control, so "
                                  "this ruling carries no weight.)") + "**\n")

    a.out.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
