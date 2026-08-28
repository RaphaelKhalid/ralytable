# Raly Coder v1 sandbox smoke findings

**The deterministic typed-action and eight-family benchmark smokes pass; no
coding-model result has been run yet.** This is a pipeline finding, not
evidence that typed actions improve coding capability or interpretability.

The smoke verified, in one temporary repository:

- `find_symbol`, `open_file`, and `read_region` return typed structured output;
- a relevant read can be masked through the intervention hook without mutating
  the original repository;
- a deliberately failing test run is preserved and searchable through
  `inspect_failure`;
- `apply_patch` is atomic and requires an exact precondition hash and unique
  old text;
- a fixed standard-library `unittest` run changes from failure to pass after
  the patch;
- path traversal and stale patch attempts are rejected;
- the complete trace round-trips as JSONL with before/after state hashes.

The benchmark smoke additionally generated one task from each of the eight
families, verified all eight oracle patches and all eight no-op failures, and
found no hidden-test or oracle-fragment leakage in model-visible text. The full
local bundle has the preregistered 1,152/192/384/384 train/dev/test/replication
task counts and a hash-only manifest; the bundle remains ignored local data.

## What this does not establish

- No 9M dense, free-text-CoT, or Raly model has been trained or evaluated.
- No private benchmark result has been unlocked or evaluated by a model.
- The fixed unittest runner is intentionally narrower than a production Python
  toolchain; pytest compatibility is a later, separately scoped change.
- The intervention hook currently provides a counterfactual read view. The
  model-level selective causal test remains pending.

## Reproduce

Use the bundled Python runtime from the Codex workspace dependencies:

```text
<bundled-python> experiments/12_raly_coder/smoke.py
```

