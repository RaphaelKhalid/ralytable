"""Decisive test of prefill: does an injected WRONG premise propagate?

String-matching a prefix is weak evidence. Instead we prefill a trace that
commits to an error (net rate 10 instead of 4). If prefill genuinely conditions
the continuation, the model should carry the error and answer 6, not 15.
If it answers 15, the prefill was ignored and sentence resampling is not
possible through this API path.
"""
import json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gate import call, parts, PROBLEM, ROOT   # reuse plumbing

POISON = (
    "Okay, let me work this out. The pipe fills at 7 litres per minute and the "
    "drain removes 3 litres per minute. So the net rate is 7 + 3 = 10 litres per "
    "minute. The tank holds 60 litres, so"
)

VARIANTS = {
    "assistant_open_think": [
        {"role": "user", "content": PROBLEM},
        {"role": "assistant", "content": "<think>\n" + POISON},
    ],
    "assistant_plain_content": [
        {"role": "user", "content": PROBLEM},
        {"role": "assistant", "content": POISON},
    ],
    "assistant_reasoning_field": [
        {"role": "user", "content": PROBLEM},
        {"role": "assistant", "content": "", "reasoning": POISON},
    ],
    "user_turn_continue": [
        {"role": "user", "content": PROBLEM},
        {"role": "user", "content":
            "Continue this reasoning from exactly where it stops. Do not restart, "
            "do not re-check earlier steps.\n\n" + POISON},
    ],
}

out = {"poison_expected_answer": "6", "true_answer": "15", "variants": {}}
for name, msgs in VARIANTS.items():
    r = call(msgs)
    reasoning, content, usage = parts(r)
    content = content or ""
    m = re.search(r"ANSWER:\s*([\d.]+)", content)
    ans = m.group(1) if m else None
    verdict = ("PREFILL WORKS (error propagated)" if ans == "6"
               else "prefill ignored (model re-derived)" if ans == "15"
               else f"unclear: {ans!r}")
    out["variants"][name] = {
        "answer": ans, "verdict": verdict,
        "reasoning_chars": len(reasoning or ""),
        "content_tail": content[-160:], "cost_usd": usage.get("cost") if usage else None,
    }
    print(f"{name:28} answer={ans!s:6} {verdict}")

p = ROOT / "results" / "g2_poison.json"
p.write_text(json.dumps(out, indent=2))
print("->", p)
