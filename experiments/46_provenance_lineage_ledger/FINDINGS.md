# Loop 27 findings

Status: executed.

The falsification target was value-only state or one-hop parent metadata that
loses upstream causes after a transformation chain. The recursive lineage
ledger passed original composition, node reordering, live-edge sensitivity,
unreachable-placebo handling, and source-label changes 5/5 across five seeds.
Value-only and one-hop metadata failed all five cases. The base output lineage
was `{file_a.py:1, file_b.py:4}`; changing the live normalization edge to use
file B reduced it to `{file_b.py:4}`.

Decision: preserve recursive source lineage as explicit dataflow state. This
is a narrow provenance contract, not evidence of learned coder-model
capability.
