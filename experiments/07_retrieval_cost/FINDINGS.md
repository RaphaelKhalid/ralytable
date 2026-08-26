# Does averaging chunks cost real retrieval accuracy?

**Verdict: yes, and the cost is large -- but almost all of it is the *averaging*,
not the coarser granularity, and effective dimension does NOT reliably predict it
across models.** On BEIR scifact, mean-pooling 8 passages into one document vector
drops hit-rate at a fixed 32-passage budget from .88 to .24 (arbitrary grouping)
or .62 (topically coherent grouping). An index with the *same* grouping and the
same budget, but scoring a group by its best member instead of its mean, gets .72
and .81 -- so ~75% of the loss is destroyed information, not lost resolution.

## The comparability control (the crux)

A group of k is an easier target than a passage, so the two indexes are matched on
**retrieved passages, not retrieved items**. At budget B the per-chunk index takes
the top B passages; the grouped index takes the top B/k groups and expands them to
their members -- exactly B passages. Both are scored identically: *is a gold
passage inside what I returned*. B in {16,32,64}, k in {2,4,8,16}, k divides B. A
third index, **max-group**, uses the identical partition and group budget but
scores a group by max member cosine -- same granularity handicap, no averaging --
so (max-group - avg-group) is the cost of mean-pooling per se.

## Results, scifact, hit-rate @ B=32, 300 queries, 5 grouping seeds

| grouping | k | per-chunk | max-group | avg-group | total cost [95% CI] | of which averaging |
|---|---|---|---|---|---|---|
| arbitrary | 2 | .877 | .837 | .713 | +.164 [.135,.197] | +.124 |
| arbitrary | 4 | .877 | .781 | .459 | +.418 [.380,.459] | +.323 |
| arbitrary | 8 | .877 | .723 | .237 | +.639 [.602,.677] | +.485 |
| arbitrary | 16 | .877 | .635 | .115 | +.762 [.726,.796] | +.521 |
| coherent | 4 | .877 | .847 | .766 | +.111 [.079,.145] | +.081 |
| coherent | 8 | .877 | .814 | .619 | +.257 [.219,.296] | +.195 |
| coherent | 16 | .877 | .732 | .485 | +.392 [.353,.430] | +.247 |

(MiniLM-L6; mpnet/bge/gte are within +-.05 of every cell. CIs are 2000-sample
bootstraps over queries on the paired per-query difference.)

**nfcorpus replicates** (323 queries, 3633 passages, ~38 gold/query, so scored by
recall@32 rather than hit-rate): arbitrary k=8 takes recall .219 -> .046
(max-group .116); coherent k=8 -> .145. Same shape, same ordering.

## Effective dimension

| space | D | D_eff (participation ratio) | frac. of max-group accuracy lost to pooling, k=8 |
|---|---|---|---|
| MiniLM native | 384 | 65.2 | .67 |
| mpnet native | 768 | 66.3 | .66 |
| bge native | 384 | 69.6 | .67 |
| gte native | 384 | 90.0 | .59 |
| MiniLM whitened | 384 | 358.6 | .40 |
| bge whitened | 384 | 377.3 | .41 |
| gte whitened | 384 | 378.3 | .32 |
| mpnet whitened | 768 | 620.6 | .23 |

One clean point: **mpnet has twice MiniLM's nominal dimension, the same D_eff, and
the same averaging cost** -- nominal D predicts nothing here, D_eff at least
survives that test. And PCA-whitening, which raises D_eff 5-9x, roughly halves the
cost for all 4 models on both datasets, despite *lowering* baseline accuracy
(.877 -> .830), so it is not a general "better space" effect.

But across the 4 native models D_eff does not predict the cost (Spearman rho=-.40,
p=.60 on scifact; rho=+.40 on nfcorpus), and D_eff there is rank-identical to
baseline recall (rho=1.0), i.e. **totally confounded with model quality**. Inside
the whitened set the ranking is also wrong (bge D_eff 377 costs more than gte 378,
and mpnet's win coincides with its larger nominal D). The honest statement:
raising D_eff by whitening reduces the cost; the *level* of D_eff across models
does not predict it. Whitening is not a single-variable knob -- it also removes
anisotropy and decorrelates -- so this is evidence for the geometry story, not for
D_eff as a scalar predictor. D_eff and the averaging cost are both
functions of the same covariance: not a tautology (D_eff is query-blind, the cost
is scored against ground-truth relevance) but not independent either.

## Attempts to kill it (`controls.py`)

- **Hubness.** In experiment 05 averaged vectors collapsed onto hub items. Not
  here: mean pairwise overlap of retrieved group sets is .0115 vs .0082 for the
  per-chunk index (chance .0062), and 451 distinct groups of 647 are returned
  across 300 queries. The loss is diffuse misranking, not collapse.
- **Pooling rule.** norm-then-mean vs raw-mean are indistinguishable (k=8: .221 vs
  .233); un-normalised sum is worse (.178). Not a normalisation artefact.
- **Over-fetching.** Quadrupling the budget (B=16->64) shrinks the k=8 arbitrary
  cost only .673 -> .569. You cannot buy the accuracy back cheaply.
- **Coverage.** >=99.8% of gold passages survive grouping in every cell, so the
  ragged-tail drop explains nothing.
- **Ceiling.** gte has the *highest* baseline and the *lowest* cost, so the
  ordering is not a headroom artefact.

## Limitations -- not tested

Two small BEIR datasets, both scientific/biomedical, English, short passages.
Four small encoders (MiniLM-L6, mpnet-base, bge-small, gte-small); no E5, no
Matryoshka, no API embeddings, nothing above 768d. Real chunk boundaries were not
used -- scifact and nfcorpus have one passage per document, so groups are synthetic
(arbitrary, and nearest-neighbour "coherent"); real multi-chunk documents lie
between those two and were not measured. Exact search only, no ANN index. Only
mean pooling; no SIF/weighted pooling, no multi-vector or ColBERT-style late
interaction, no two-stage retrieve-then-rerank (which is what a production system
would do and would likely recover much of the loss). Only recall/hit-rate -- no
downstream answer quality. The claim is about these 4 encoders on these 2 datasets.

## Reproduce

    python experiments/07_retrieval_cost/embed.py scifact
    python experiments/07_retrieval_cost/embed.py nfcorpus
    python experiments/07_retrieval_cost/run.py scifact
    python experiments/07_retrieval_cost/run.py nfcorpus
    python experiments/07_retrieval_cost/controls.py
    DS=nfcorpus python experiments/07_retrieval_cost/controls.py
    python experiments/07_retrieval_cost/plot.py     # results/retrieval_cost.png
