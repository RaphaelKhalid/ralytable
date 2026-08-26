"""Blind LLM judging of the story completions, two protocols plus controls.

THE JUDGE IS AN INSTRUMENT AND IS TREATED AS ONE. Three things are built in
rather than hoped for:

  1. THE JUDGE NEVER SEES A MODEL NAME. The prompt templates below contain no
     slot for one; `--show-prompt` prints a real, fully rendered judge prompt
     so the writeup can show that.
  2. A HUMAN-TEXT CONTROL. Real held-out TinyStories continuations are judged
     as if they were completions, under the arm name `human`. If the judge does
     not rank real human writing top, the judge is broken and no other number
     here means anything.
  3. A POSITION-BIAS CONTROL. In the pairwise protocol which arm appears first
     is randomised and recorded, so the rate at which the judge picks the first
     slot can be measured directly. A same-quality pair (dense seed 0 against
     dense seed 1) is judged too: two draws from the same distribution should
     split 50/50, so any departure is the instrument, not the models.

Every call is appended to a JSONL cache keyed by its identity, so a rerun costs
nothing and an interrupted run resumes. Spend is read from OpenRouter's own
usage accounting, never estimated.
"""
import argparse, concurrent.futures as cf, json, os, pathlib, random, re, sys, threading, time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
MODEL = "~deepseek/deepseek-v4-flash-latest"
API = "https://openrouter.ai/api/v1/chat/completions"

# --- the judge prompts. No model name, config, or hint of one appears here. ---

ABS_PROMPT = """The following exercise: the student is given the beginning of a story. The student needs to complete it into a full story. The exercise tests the student's language abilities and creativity.

The beginning of the story is:
---
{prompt}
---

The student's completion is:
---
{completion}
---

Grade the student's completion on three separate criteria, each on an integer scale from 1 to 10, where 1 is very poor and 10 is excellent:

- GRAMMAR: is the writing grammatically correct and fluent English?
- CONSISTENCY: does the completion follow coherently from the given beginning, and does it stay internally consistent about characters, objects and events?
- CREATIVITY: is the story interesting and imaginative rather than bland or repetitive?

Judge only what is written. Reply with exactly one line of JSON and nothing else:
{{"grammar": <int>, "consistency": <int>, "creativity": <int>}}"""

PAIR_PROMPT = """Two students were each given the same beginning of a story and asked to complete it into a full story.

The beginning of the story is:
---
{prompt}
---

Completion A:
---
{a}
---

Completion B:
---
{b}
---

Which completion is better overall, taking grammar, consistency with the beginning, and creativity together? If the two are of genuinely comparable quality and you could not reliably tell them apart, say TIE.

Reply with exactly one line of JSON and nothing else:
{{"winner": "A" | "B" | "TIE"}}"""


def api_key():
    p = HERE.parents[1] / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip()
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k:
        sys.exit("no OPENROUTER_API_KEY in .env or environment")
    return k


SPEND = [0.0]
LOCK = threading.Lock()


def call(prompt, key, max_tokens=60, retries=4):
    """One judge call. Returns (text, cost). Cost comes from the API, not a guess."""
    body = json.dumps({
        "model": MODEL, "temperature": 0.0, "max_tokens": max_tokens,
        "reasoning": {"enabled": False},          # this model deliberates by
                                                  # default and would otherwise
                                                  # spend the whole budget on it
        "usage": {"include": True},
        "messages": [{"role": "user", "content": prompt}]}).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                API, data=body,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.load(r)
            m = d["choices"][0]["message"]
            cost = float((d.get("usage") or {}).get("cost") or 0.0)
            with LOCK:
                SPEND[0] += cost
            return (m.get("content") or m.get("reasoning") or ""), cost
        except Exception:
            if attempt == retries - 1:
                return "", 0.0
            time.sleep(2 ** attempt)
    return "", 0.0


JSON_RE = re.compile(r"\{[^{}]*\}")


def parse_json(text):
    m = JSON_RE.search(text or "")
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


class Cache:
    """Append-only JSONL of finished judgements, keyed by task identity."""

    def __init__(self, path):
        self.path = path
        self.rows = {}
        if path.exists():
            for line in path.open(encoding="utf-8"):
                line = line.strip()
                if line:
                    r = json.loads(line)
                    self.rows[r["key"]] = r
        self.f = path.open("a", encoding="utf-8")
        self.lock = threading.Lock()

    def put(self, row):
        with self.lock:
            self.rows[row["key"]] = row
            self.f.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.f.flush()


def build_tasks(gen, seed):
    """Every judge call this experiment makes, deterministic given `seed`.

    Pairwise sides are assigned by a seeded RNG and the assignment is stored,
    so the position-bias check reads the same randomisation the judge saw.
    """
    comps = gen["completions"]
    n = len(gen["prompts"])
    arms = sorted(comps)
    tasks = []

    for arm in arms:
        for i in range(n):
            tasks.append({"kind": "abs", "key": f"abs|{arm}|{i}", "arm": arm, "i": i,
                          "prompt": ABS_PROMPT.format(prompt=gen["prompts"][i],
                                                      completion=comps[arm][i])})

    dense = sorted(a for a in arms if a.startswith("dense"))
    disc = sorted(a for a in arms if a.startswith("codes="))
    pairs = []
    # Main test: each dense seed against a discrete seed. Pairing every dense
    # arm with every discrete arm would multiply the call count for no extra
    # power, so the shorter list is cycled.
    for j, d in enumerate(dense):
        if disc:
            pairs.append(("main", d, disc[j % len(disc)]))
    # Null control: two dense seeds. Same distribution, so the truth is 50/50 --
    # this is what the judge's own noise floor and position bias look like.
    if len(dense) >= 2:
        pairs.append(("null", dense[0], dense[1]))
    # Ceiling control: real human text against a model.
    if dense:
        pairs.append(("ceiling", "human", dense[0]))

    rng = random.Random(seed)
    for tag, x, y in pairs:
        for i in range(n):
            flip = rng.random() < 0.5           # does arm x go in slot A?
            a_arm, b_arm = (x, y) if flip else (y, x)
            tasks.append({
                "kind": "pair", "key": f"pair|{tag}|{x}|{y}|{i}", "tag": tag,
                "left": x, "right": y, "a_arm": a_arm, "b_arm": b_arm, "i": i,
                "prompt": PAIR_PROMPT.format(prompt=gen["prompts"][i],
                                             a=comps[a_arm][i], b=comps[b_arm][i])})
    return tasks


def run(tasks, cache, key, workers, cap):
    todo = [t for t in tasks if t["key"] not in cache.rows]
    print(f"{len(tasks)} judgements, {len(tasks) - len(todo)} cached, {len(todo)} to do")
    done = [0]
    t0 = time.time()

    def work(t):
        if SPEND[0] > cap:
            return
        text, cost = call(t["prompt"], key)
        obj = parse_json(text)
        row = {k: v for k, v in t.items() if k != "prompt"}
        row["raw"] = (text or "")[:400]
        row["parsed"] = obj
        row["cost"] = cost
        cache.put(row)
        with LOCK:
            done[0] += 1
            if done[0] % 50 == 0 or done[0] == len(todo):
                el = time.time() - t0
                print(f"  {done[0]}/{len(todo)}  ${SPEND[0]:.4f}  {el:.0f}s", flush=True)

    if todo:
        with cf.ThreadPoolExecutor(workers) as ex:
            list(ex.map(work, todo))
    if SPEND[0] > cap:
        print(f"WARNING: spend cap ${cap} hit; some judgements missing")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", type=pathlib.Path, default=HERE / "generations.json")
    ap.add_argument("--cache", type=pathlib.Path, default=HERE / "judgements.jsonl")
    ap.add_argument("--seed", type=int, default=2024)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--cap", type=float, default=2.0, help="hard spend cap in USD")
    ap.add_argument("--show-prompt", action="store_true",
                    help="print one rendered prompt of each kind and exit")
    a = ap.parse_args()

    gen = json.loads(a.gen.read_text(encoding="utf-8"))
    tasks = build_tasks(gen, a.seed)

    if a.show_prompt:
        for kind in ("abs", "pair"):
            t = next(x for x in tasks if x["kind"] == kind)
            print(f"===== {kind} =====\n{t['prompt']}\n")
        return

    cache = Cache(a.cache)
    run(tasks, cache, api_key(), a.workers, a.cap)
    total = sum(r.get("cost", 0.0) for r in cache.rows.values())
    bad = sum(1 for r in cache.rows.values() if r["parsed"] is None)
    print(f"done. {len(cache.rows)} judgements, {bad} unparseable, "
          f"total API spend ${total:.4f}")


if __name__ == "__main__":
    main()
