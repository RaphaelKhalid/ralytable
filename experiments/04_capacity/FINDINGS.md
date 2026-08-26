# VSA bundling capacity, measured rather than cited

The semantics research quoted M* = Theta(D / ln N) and, for D=1000, "about 10 items".
The form is right; the constant is not, and the constant is what a type system has to
carry. So it was measured.

## Protocol

Random bipolar codebook, bundle N distinct atoms, check whether all N come back as the
top-N nearest neighbours of the bundle. `measure_capacity.py`.

## Result

Retrieval accuracy, MAP/bipolar, 1000-item codebook:

| D | N=5 | N=10 | N=15 | N=20 | N=30 | N=50 |
|---|---|---|---|---|---|---|
| 256 | 0.99 | 0.83 | 0.77 | 0.66 | 0.55 | 0.46 |
| 512 | 1.00 | 0.99 | 0.95 | 0.88 | 0.79 | 0.68 |
| 1000 | 1.00 | 1.00 | 1.00 | 0.99 | 0.94 | 0.86 |
| 2048 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 |

Largest N at 95% retrieval: **D=256 -> 7, D=512 -> 14, D=1000 -> 31, D=2048 -> 71.**

So roughly 3x more headroom at D=1000 than the literature summary implied.

## Limitations

- D=4096 and D=10000 never failed within the search range, so those are censored, not
  measured.
- A 1000-item codebook is small. A larger cleanup memory means more distractors and
  lower capacity; capacity is a function of the retrieval pool as well as D.
- Random codebooks only. Capacity guarantees rest on quasi-orthogonality, and a
  *learned* codebook has no pressure to preserve it. Whether these numbers survive
  gradient descent is the open question that gates the whole learnable-VSA premise.

## Consequence for the language

The capacity type needs a concrete number, and it should not be derived from ambient D.
`experiments/05_real_embeddings` found that real embedding spaces have an effective
dimension far below their nominal one (110.6 of 384 for MiniLM), which would make a
D-derived capacity bound overstate real capacity by 3-5x. The type must carry a
measured effective dimension per space.
