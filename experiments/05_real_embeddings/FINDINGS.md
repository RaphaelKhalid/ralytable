# Averaging real embeddings: does the toy capacity decay show up in practice?

**Verdict: yes, and worse -- mean-pooled MiniLM sentence embeddings lose bundled
items 3-5x faster than the matched random-vector baseline, and averaged token
embeddings collapse almost immediately.** The toy result understates the problem
for the workflows people actually run.

Setup: all-MiniLM-L6-v2 over 7600 deduped AG News headlines. Bundle = mean of N
L2-normalised embeddings; score = fraction of the N sources returned in the top-N
cosine neighbours of the bundle over the whole pool. Same protocol as
`experiments/04_capacity`. D = 384 in every condition, so only the vector
*distribution* varies. 200 trials/cell; brackets are 95% CI over trials.

## Retrieval accuracy, pool = 7600, D = 384

| N | chance | MiniLM sentence | MiniLM mean-removed | avg. token emb | random bipolar | random Gaussian |
|---|---|---|---|---|---|---|
| 5 | .0007 | **.738** [.716,.760] | .804 | .073 | 1.000 | 1.000 |
| 10 | .0013 | **.354** [.337,.372] | .533 | .013 | .891 | .997 |
| 20 | .0026 | **.119** [.109,.128] | .295 | .009 | .638 | .861 |
| 50 | .0066 | **.044** [.041,.048] | .159 | .010 | .337 | .521 |
| 100 | .0132 | **.035** [.033,.038] | .119 | .017 | .226 | .336 |

Pool = 1000 is uniformly kinder (MiniLM N=20: .273) -- capacity depends on the
distractor count, as expected. Full grid in `results.json`; figure at
`results/real_embedding_capacity.png`.

At N=10 -- a plausible "average the chunks of a document" size -- a MiniLM centroid
returns **two thirds of the wrong things**, with no error and no signal.

## Mechanism

| set | mean pairwise cosine | D_eff (participation ratio) |
|---|---|---|
| MiniLM sentence | +0.054 | 110.6 |
| avg. token emb | +0.612 | 84.7 |
| random Gaussian | ~0 | 365.7 |

Anisotropy is real but *small* for MiniLM; removing the corpus mean recovers
roughly half the loss (N=20: .119 -> .295), so it is a contributing cause, not the
whole one. The bigger factor is dimensionality collapse: MiniLM uses ~111 of its
384 dimensions. A random Gaussian baseline at D=110 scores .902/.566/.289/.144 at
N=5/10/20/50 -- much closer to MiniLM, but MiniLM is still 1.7-3.3x worse, so
residual correlation structure costs on top of D_eff.

For averaged **token** embeddings the story is different and worse: anisotropy
0.61, and the top-N sets of *different* bundles overlap 81% at N=100 (chance 1.3%).
It does not decay toward chance; it converges on a fixed set of hub sentences and
returns them regardless of the query.

## Attempts to kill the result (all in `controls.py`)

- **Near-duplicate rescue.** A miss would be benign if a paraphrase took the slot.
  Forgiving any miss whose nearest retrieved item has cosine >= 0.7 changes N=20
  accuracy from .118 to .127. Median cosine from a missed item to the best thing
  actually returned is 0.13-0.30 -- the substitutes are unrelated.
- **Normalisation choice.** Averaging raw (unnormalised) embeddings gives the same
  curve (N=20: .116 vs .118).
- **Definitional forcing.** Chance is reported explicitly and every condition uses
  the same D, pool, N, trial count, and scorer; the ranking is not implied by the
  metric. Exact-duplicate texts were removed before embedding.

## Limitations -- not tested

One model (all-MiniLM-L6-v2), one corpus (short English news headlines), one
domain, one pooling rule (mean). Not tested: larger/newer encoders (E5, BGE,
gte, OpenAI ada/3), long documents or real RAG chunks, weighted or SIF-style
pooling, matryoshka embeddings, ANN indexes, top-K with K > N (a real system
might over-fetch), whitening/ABTT beyond plain mean-centring, and steering-vector
stacking in a residual stream (workflow 3 -- not run). The claim is about
mean-pooled MiniLM sentence embeddings and averaged BERT token embeddings on this
corpus, not about embeddings in general.

## Reproduce

    python experiments/05_real_embeddings/embed_corpus.py
    python experiments/05_real_embeddings/measure_real_capacity.py
    python experiments/05_real_embeddings/controls.py
    python experiments/05_real_embeddings/plot.py
