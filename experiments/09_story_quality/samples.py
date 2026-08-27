"""Write samples.md: a blind, human-readable side-by-side of the completions.

The scores in FINDINGS.md are one LLM's opinion. This file exists so a person
can form their own, without being told which model wrote which. Arms are
labelled A and B, the assignment is randomised per prompt by a seeded RNG, and
the key is at the very bottom of the file so it cannot be read by accident
while reading the stories.

Prompts are the FIRST n of the generation set in their existing order. Nothing
is ranked, filtered or selected on quality.
"""
import argparse, json, pathlib, random

HERE = pathlib.Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", type=pathlib.Path, default=HERE / "generations.json")
    ap.add_argument("--out", type=pathlib.Path, default=HERE / "samples.md")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=555)
    ap.add_argument("--dense", default="dense_s0")
    ap.add_argument("--discrete", default="codes=512_s0")
    a = ap.parse_args()

    gen = json.loads(a.gen.read_text(encoding="utf-8"))
    c = gen["completions"]
    for arm in (a.dense, a.discrete):
        if arm not in c:
            raise SystemExit(f"arm {arm} not in generations.json: {sorted(c)}")

    m = gen["meta"]
    rng = random.Random(a.seed)
    L = ["# Side-by-side completions, blind",
         "",
         f"{a.n} prompts, taken in order from the generation set -- not selected "
         "on quality. Each prompt is the opening of a held-out TinyStories "
         "validation story. Both completions use identical sampling settings "
         f"(temperature {m['temperature']}, top-k {m['top_k']}, "
         f"{m['max_new_tokens']} new tokens).",
         "",
         "One of A and B is the dense model, the other is the 512-code discrete "
         "bottleneck; which is which is randomised per prompt. **The key is at "
         "the bottom of this file.** Read first, then look.",
         ""]

    key = []
    for i in range(a.n):
        flip = rng.random() < 0.5
        aa, bb = (a.dense, a.discrete) if flip else (a.discrete, a.dense)
        key.append((i + 1, aa, bb))
        L += [f"## Prompt {i + 1}", "",
              "> " + gen["prompts"][i].strip().replace("\n", "\n> "), "",
              "**A.** " + c[aa][i].strip().replace("\n", " "), "",
              "**B.** " + c[bb][i].strip().replace("\n", " "), "", "---", ""]

    L += ["", "", "## Key", "",
          "| prompt | A | B |", "|---|---|---|"]
    for i, aa, bb in key:
        L.append(f"| {i} | `{aa}` | `{bb}` |")
    L += ["", "`dense_*` is the dense baseline (val CE 1.659). "
              "`codes=512_*` is the discrete bottleneck (val CE 2.252). "
              "The two are parameter-matched to within 0.25%."]

    a.out.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {a.out} ({a.n} prompts)")


if __name__ == "__main__":
    main()
