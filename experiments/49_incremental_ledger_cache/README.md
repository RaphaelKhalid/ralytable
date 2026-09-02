# Loop 30: incremental ledger cache

This bounded CPU probe compares full recomputation, no invalidation, suffix
invalidation, and dependency-aware invalidation on a small shared dataflow
DAG. It measures output correctness and the number of re-evaluated nodes after
local edits.

Run:

```text
python experiments/49_incremental_ledger_cache/incremental_probe.py
```
