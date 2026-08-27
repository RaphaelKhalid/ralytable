# Raly Coder v1 sandbox smoke findings

**The deterministic typed-action sandbox smoke passes; no coding-model result
has been run yet.** This is a pipeline finding, not evidence that typed actions
improve coding capability or interpretability.

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

## What this does not establish

- No 9M dense, free-text-CoT, or Raly model has been trained or evaluated.
- No private benchmark bundle has been populated or unlocked.
- The fixed unittest runner is intentionally narrower than a production Python
  toolchain; pytest compatibility is a later, separately scoped change.
- The intervention hook currently provides a counterfactual read view. The
  model-level selective causal test remains pending.

## Reproduce

Use the bundled Python runtime from the Codex workspace dependencies:

```text
<bundled-python> experiments/12_raly_coder/smoke.py
```

