"""Fetch the labelled chunk files from the released Thought Anchors rollouts.

Pulls only the small per-problem JSON (problem/chunks/chunks_labeled/base_solution),
not the per-chunk solutions.json (2.3MB each) or the parquet mirror (~18GB).
"""
import json, pathlib, urllib.request, concurrent.futures as cf

REPO = "uzaymacar/math-rollouts"
ROOT = pathlib.Path(__file__).resolve().parents[2] / "data" / "math-rollouts"
WANT = ["problem.json", "chunks.json", "chunks_labeled.json", "base_solution.json"]
MODELS = ["deepseek-r1-distill-qwen-14b", "deepseek-r1-distill-llama-8b"]
UA = {"User-Agent": "curl/8"}


def api(p):
    return json.load(urllib.request.urlopen(urllib.request.Request(
        "https://huggingface.co/api/" + p, headers=UA)))


def grab(path):
    dst = ROOT / path
    if dst.exists():
        return 0
    dst.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://huggingface.co/datasets/{REPO}/resolve/main/{urllib.request.quote(path)}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
        b = r.read()
    dst.write_bytes(b)
    return len(b)


targets = []
for m in MODELS:
    base = f"{m}/temperature_0.6_top_p_0.95/correct_base_solution"
    probs = [e["path"] for e in api(f"datasets/{REPO}/tree/main/{base}")
             if e["type"] == "directory"]
    print(f"{m}: {len(probs)} problems")
    targets += [f"{p}/{w}" for p in probs for w in WANT]

total = 0
with cf.ThreadPoolExecutor(16) as ex:
    for n in ex.map(grab, targets):
        total += n
print(f"{len(targets)} files, {total/1e6:.1f} MB -> {ROOT}")
