# Loop 40 findings

Status: executed.

The falsification target was an example-level split that lets equivalent
variants cross the train/eval boundary. The dataset contained 36 examples in
12 semantic families. Across five seeds, random example splits leaked an
average 7.4/12 semantic families (and 7.4/12 surface families) into both
partitions. Grouped splits leaked 0/12 for both measures.

Decision: split by canonical semantic family, not by surface example, and
report equivalence-class overlap before interpreting coding scores. This is an
evaluation-integrity probe, not evidence of learned coder-model parity.
