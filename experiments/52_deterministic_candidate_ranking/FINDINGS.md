# Loop 33 findings

Status: executed.

The falsification target was candidate selection dependent on input order or
unverified scores. Exact ranking passed near-ties, proof filtering, semantic
ties, and all permutation checks 5/5. Float ranking tied it on this bounded
case. Input-order argmax failed the original and semantic-tie cases because it
selected candidate 0 instead of the lower-complexity/signature candidate 1;
aggregate reorder agreement was only 14/15 because one shuffled order happened
to agree. The high-score invalid candidate was filtered by the typed variants.

Decision: rank only proof-valid candidates with an exact score representation
and explicit deterministic tie keys `(score, complexity, signature)`. This is
a narrow search contract, not evidence of learned coder-model capability.
