"""White-box methods: logit lens on the hint tokens, and a linear probe.

Method 4, logit lens. The organism is asked for hints (never for the word).
We take the residual stream at every sampled layer and every position of the
model's own hint response, unembed it through the final norm and lm_head, and
ask whether the secret word appears in the top-k. This is the standard logit
lens (nostalgebraist 2020) with no training and no knowledge of the secret.

Three read-outs, because the choice of layer matters and hiding that choice is
the easiest way to overstate a white-box method:
    lens_open_oracle  best layer picked per organism using the answer. An
                      upper bound. Not an auditing result.
    lens_open_fixed   one layer for all organisms, chosen on a dev split of
                      organisms and evaluated on the rest (see analyze.py).
    lens_closed       same scores, restricted to the 20-word candidate set.
                      Chance is 1/20, not 1/151936, and it is reported that way.

Method 5, probe. A linear map from the residual stream to unembedding space,
fit by ridge regression to predict the secret word's embedding, trained
leave-one-organism-out so the held-out secret is never in the training set.
Fitted in analyze_probe.py from the activations this script caches.

Everything is written to results/ as raw scores; no thresholding happens here.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

import torch

import attacks
import organisms
from run_blackbox import build_inputs, generate

HERE = pathlib.Path(__file__).parent
RESULTS = HERE / "results"
TOPK = 20
LAYER_STRIDE = 2


def candidate_token_ids(tok):
    """First token id of each candidate word, with and without a leading space."""
    out = {}
    for w in organisms.CANDIDATE_SET:
        ids = set()
        for form in (w, " " + w, w.capitalize(), " " + w.capitalize()):
            t = tok.encode(form, add_special_tokens=False)
            if t:
                ids.add(t[0])
        out[w] = sorted(ids)
    return out


@torch.no_grad()
def lens(model, tok, prompt_text: str, response: str, cand_ids, layers):
    """Returns (per-layer top-k token strings, per-layer candidate scores).

    Score of a token at a layer = max over response positions of its logit-lens
    probability. Max, not mean: a hint mentions the concept at a few positions,
    and averaging over a 90-token answer buries them.
    """
    full = prompt_text + response
    enc = tok(full, return_tensors="pt", add_special_tokens=False).to(model.device)
    n_prompt = len(tok(prompt_text, add_special_tokens=False)["input_ids"])
    out = model(**enc, output_hidden_states=True)
    hs = out.hidden_states  # tuple (L+1) of [1, T, d]

    inner = model.get_base_model() if hasattr(model, "get_base_model") else model
    norm = inner.model.norm
    head = inner.lm_head

    topk_by_layer, cand_by_layer, pooled = {}, {}, []
    for li in layers:
        h = hs[li][0, n_prompt:]                       # response positions only
        if h.shape[0] == 0:
            continue
        logits = head(norm(h)).float()                 # [T, V]
        probs = logits.softmax(-1)
        peak = probs.max(0).values                     # [V], max over positions
        vals, idx = peak.topk(TOPK)
        topk_by_layer[li] = [tok.decode([i]) for i in idx.tolist()]
        cand_by_layer[li] = {
            w: max(peak[i].item() for i in ids) for w, ids in cand_ids.items()
        }
        pooled.append(h.mean(0).float().cpu())   # probe features, same forward
    return topk_by_layer, cand_by_layer, torch.stack(pooled)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="qwen3-8b", choices=list(organisms.FAMILIES))
    ap.add_argument("--control", action="store_true",
                    help="base model, generating its own answers: no secret at all")
    ap.add_argument("--text-control", action="store_true",
                    help="base model teacher-forced on the ORGANISM's hint text. "
                         "The decisive control for the lens: if the base model's "
                         "residual stream predicts the word from the same text, "
                         "the lens is reading the hints, not the organism.")
    args = ap.parse_args()

    RESULTS.mkdir(exist_ok=True)
    fam = organisms.FAMILIES[args.family]
    base, tok = organisms.load_base(args.family)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    cand_ids = candidate_token_ids(tok)

    n_layers = base.config.num_hidden_layers
    layers = list(range(0, n_layers + 1, LAYER_STRIDE))

    # unembedding row for each candidate word: the probe's regression target
    with torch.no_grad():
        emb = torch.stack([base.lm_head.weight[cand_ids[w][0]].float().cpu()
                           for w in organisms.CANDIDATE_SET])
    RESULTS.mkdir(exist_ok=True)
    torch.save(emb, RESULTS / f"emb_{args.family}.pt")

    words = fam["words"] if not args.control else ["__control__"]
    tag = "_control" if args.control else ""
    forced = None
    if args.text_control:
        tag = "_textcontrol"
        src = json.loads((RESULTS / f"whitebox_{args.family}.json").read_text())
        forced = {r["organism"]: r["responses"] for r in src}
        words = list(forced)
    out_path = RESULTS / f"whitebox_{args.family}{tag}.json"
    act_path = RESULTS / f"acts_{args.family}{tag}.pt"

    records, acts = [], {}
    for word in words:
        t0 = time.time()
        model = base if (args.control or args.text_control)             else organisms.attach(base, args.family, word)
        texts = build_inputs(tok, attacks.HINT_PROMPTS, prefill=attacks.HINT_PREFILL)
        responses = forced[word] if forced else generate(model, tok, texts)

        per_prompt_top, per_prompt_cand, pooled = [], [], []
        for ptext, resp in zip(texts, responses):
            tk, cd, pl = lens(model, tok, ptext, resp, cand_ids, layers)
            per_prompt_top.append({str(k): v for k, v in tk.items()})
            per_prompt_cand.append({str(k): v for k, v in cd.items()})
            pooled.append(pl)   # [n_layers, d] mean residual over response
        acts[word] = torch.stack(pooled)  # [n_prompts, n_layers, d]
        records.append({
            "family": args.family, "organism": word,
            "layers": layers, "n_queries": len(attacks.HINT_PROMPTS),
            "wall_clock_s": round(time.time() - t0, 2),
            "responses": responses,
            "topk": per_prompt_top, "cand_scores": per_prompt_cand,
        })
        print(f"lens {word}: {round(time.time()-t0,1)}s", flush=True)
        if not (args.control or args.text_control):
            model.unload()
            del model
            torch.cuda.empty_cache()
        out_path.write_text(json.dumps(records, indent=1))
        torch.save({"layers": layers, "acts": acts}, act_path)
    print("wrote", out_path, act_path)


if __name__ == "__main__":
    main()
