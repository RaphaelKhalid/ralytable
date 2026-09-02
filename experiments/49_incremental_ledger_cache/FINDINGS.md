# Loop 30 findings

Status: executed.

The falsification target was a cache that reuses stale descendants or
recompiles the entire graph after every local edit. Across five seeds, the
dependency cache and suffix cache preserved fresh outputs for both local and
independent edits; no-invalidation failed both edit classes. All variants
survived node-list reordering. The full graph materialized eight nodes. A local
edit recomputed fewer nodes for suffix/dependency caches (10/20 architecture
runs overall), while the independent branch edit gave savings for suffix and
dependency caches (15/20 overall).

Decision: use content-addressed dependency invalidation, not global suffix or
stale cache reuse. The measurement is a small DAG systems result, not evidence
of learned coder-model capability.
