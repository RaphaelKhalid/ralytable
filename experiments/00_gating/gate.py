"""Three gating checks before any real experiment.

G1  Does the provider return raw reasoning text we can segment?
G2  Can we PREFILL a partial reasoning trace and have the model continue it?
    This is load-bearing: sentence resampling is impossible without it, and the
    black-box half of the project would have to move to local weights.
G3  Will the model emit `[n] from [a],[b]` dependency annotations, and what does
    that cost in accuracy?

Run:  python experiments/00_gating/gate.py
Writes results/gating.json  (raw responses kept for inspection)
"""
import json, os, pathlib, sys, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
API = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("GATE_MODEL", "qwen/qwen3-14b")

# One MATH-style problem with an unambiguous integer answer.
PROBLEM = (
    "A tank is filled by a pipe at 7 litres per minute and drained by another at "
    "3 litres per minute. The tank holds 60 litres and starts empty. Both pipes "
    "run at once. How many minutes until the tank is full? "
    "End your reply with the answer on its own final line as: ANSWER: <number>"
)
TRUE_ANSWER = "15"

ANNOTATED_SUFFIX = """

Write your reasoning as numbered steps. Every step that uses earlier steps must
cite them. Use exactly this format, one step per line:

[1] <statement>
[2] <statement>
[3] from [1],[2]: <statement>

Cite only steps you actually used."""


def key():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip()
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k:
        sys.exit("No OPENROUTER_API_KEY in .env or environment.")
    return k


KEY = key()


def call(messages, **extra):
    body = {"model": MODEL, "messages": messages, "temperature": 0.6, "top_p": 0.95}
    body.update(extra)
    req = urllib.request.Request(
        API,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode()[:600]}


def parts(resp):
    """(reasoning_text, content_text, usage) from a response, tolerating errors."""
    if "_http_error" in resp:
        return None, None, None
    m = resp["choices"][0]["message"]
    return m.get("reasoning"), m.get("content"), resp.get("usage")


def cost(usage):
    return None if not usage else usage.get("cost")


def main():
    results = {"model": MODEL, "checks": {}}

    # ---------------------------------------------------------------- G1
    print(f"[G1] raw reasoning visible?  model={MODEL}")
    r1 = call(
        [{"role": "user", "content": PROBLEM}],
        reasoning={"effort": "low"},
    )
    reasoning, content, usage = parts(r1)
    g1 = {
        "http_error": r1.get("_http_error"),
        "error_body": r1.get("_body"),
        "reasoning_present": bool(reasoning),
        "reasoning_chars": len(reasoning or ""),
        "reasoning_head": (reasoning or "")[:400],
        "content": content,
        "correct": bool(content and content.strip().endswith(TRUE_ANSWER)),
        "usage": usage,
        "cost_usd": cost(usage),
    }
    results["checks"]["G1_reasoning_visible"] = g1
    print(f"     present={g1['reasoning_present']} chars={g1['reasoning_chars']} "
          f"correct={g1['correct']} cost={g1['cost_usd']}")

    # ---------------------------------------------------------------- G2
    # Take the real trace, cut it partway, and try three ways to make the model
    # resume from that exact point. Success = continuation is coherent AND the
    # prefix is not restated from scratch.
    print("[G2] prefill a partial reasoning trace?")
    g2 = {}
    trace = reasoning or ""
    cut = trace[: max(200, len(trace) // 3)] if trace else ""
    g2["prefix_used_chars"] = len(cut)

    if not cut:
        g2["skipped"] = "no reasoning text from G1 to cut"
    else:
        # (a) assistant turn carrying a `reasoning` field
        ra = call(
            [
                {"role": "user", "content": PROBLEM},
                {"role": "assistant", "content": "", "reasoning": cut},
            ],
            reasoning={"effort": "low"},
        )
        rea, cona, ua = parts(ra)
        g2["a_assistant_reasoning_field"] = {
            "http_error": ra.get("_http_error"), "error_body": ra.get("_body"),
            "returned_reasoning_chars": len(rea or ""),
            "prefix_echoed": bool(rea and rea.startswith(cut[:120])),
            "content_tail": (cona or "")[-200:], "cost_usd": cost(ua),
        }

        # (b) assistant turn whose content is an OPEN <think> block
        rb = call(
            [
                {"role": "user", "content": PROBLEM},
                {"role": "assistant", "content": "<think>\n" + cut},
            ]
        )
        reb, conb, ub = parts(rb)
        g2["b_open_think_prefill"] = {
            "http_error": rb.get("_http_error"), "error_body": rb.get("_body"),
            "returned_reasoning_chars": len(reb or ""),
            "content_head": (conb or "")[:300], "content_tail": (conb or "")[-200:],
            "cost_usd": cost(ub),
        }

        # (c) fallback: hand the partial trace back in the user turn
        rc = call(
            [
                {"role": "user", "content": PROBLEM},
                {"role": "user", "content":
                    "Here is the beginning of your reasoning. Continue it from exactly "
                    "where it stops. Do not restart or repeat it.\n\n" + cut},
            ],
            reasoning={"effort": "low"},
        )
        rec, conc, uc = parts(rc)
        g2["c_user_turn_continuation"] = {
            "http_error": rc.get("_http_error"), "error_body": rc.get("_body"),
            "returned_reasoning_chars": len(rec or ""),
            "content_tail": (conc or "")[-200:], "cost_usd": cost(uc),
        }

    results["checks"]["G2_prefill"] = g2
    for k, v in g2.items():
        if isinstance(v, dict):
            print(f"     {k}: err={v.get('http_error')} "
                  f"reasoning_chars={v.get('returned_reasoning_chars')}")

    # ---------------------------------------------------------------- G3
    print("[G3] dependency annotations: format compliance + accuracy")
    import re
    g3 = {"n": 3, "runs": []}
    for i in range(3):
        r = call(
            [{"role": "user", "content": PROBLEM + ANNOTATED_SUFFIX}],
            reasoning={"effort": "low"},
        )
        _, con, u = parts(r)
        con = con or ""
        steps = re.findall(r"^\[(\d+)\](.*)$", con, re.M)
        cites = re.findall(r"^\[(\d+)\]\s*from\s*((?:\[\d+\],?\s*)+):", con, re.M)
        g3["runs"].append({
            "http_error": r.get("_http_error"),
            "n_steps": len(steps),
            "n_steps_with_citations": len(cites),
            "correct": con.strip().endswith(TRUE_ANSWER),
            "cost_usd": cost(u),
            "content": con,
        })
        print(f"     run{i}: steps={len(steps)} cited={len(cites)} "
              f"correct={g3['runs'][-1]['correct']}")
    results["checks"]["G3_annotated"] = g3

    # ---------------------------------------------------------------- cost roll-up
    def walk(o):
        if isinstance(o, dict):
            if o.get("cost_usd"):
                yield float(o["cost_usd"])
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)

    total = sum(walk(results))
    results["total_cost_usd"] = total
    out = ROOT / "results" / "gating.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\ntotal spend this run: ${total:.5f}   ->  {out}")


if __name__ == "__main__":
    main()
