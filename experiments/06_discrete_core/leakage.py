"""Does the codebook beat the raw character at predicting reasoning role?

FINDINGS.md first reported role purity against a shuffle null, which asks "could a
codebook carrying no information score this?". That is the wrong question. The right
one is "could you score this WITHOUT the codebook?" -- and largely you can, because
the corpus format leaks the label: `A` occurs only in `ANSWER:`, `]` only inside a
citation. A code firing on `]` scores 100% on `derived` while understanding nothing.

This measures the character-only baseline the reported excess should have been
compared against.
"""
import collections, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as R

data = [json.loads(l) for l in (HERE / "corpus.jsonl").open(encoding="utf-8")]
text, roles = "", []
for ex in data:
    t, r = R.render(ex)
    text += t
    roles += r

by = collections.defaultdict(collections.Counter)
for ch, ro in zip(text, roles):
    by[ch][ro] += 1

char_purity = sum(c.most_common(1)[0][1] for c in by.values()) / len(text)
base = max(collections.Counter(roles).values()) / len(roles)
CODES = 0.6640  # reported in FINDINGS.md for codes=1024

print(f"corpus: {len(text):,} characters, {len(by)} distinct\n")
print(f"  majority class            {base:.4f}")
print(f"  character alone           {char_purity:.4f}   ({char_purity - base:+.4f})")
print(f"  the 1024 codes            {CODES:.4f}   ({CODES - base:+.4f})")
print(f"\n  codes over character      {CODES - char_purity:+.4f}   <- the honest number")
print(f"  share of excess that is\n  just the character        "
      f"{(char_purity - base) / (CODES - base):.0%}")
