# Raly Coder v1 sandbox and benchmark artifacts

This directory contains the first local coding-action surface. It is an
engineering gate, not a model result.

- `schema.py` defines the six typed model-facing actions.
- `sandbox.py` executes them with safe relative paths, exact patch
  preconditions, a fixed unittest runner, failure inspection, trace hashes,
  and a read-state intervention hook.
- `api_census.py` records the standard-library implementation vocabulary.
- `smoke.py` runs the deterministic one-minute gate.
- `generator.py` creates the deterministic eight-family private bundle and
  hash-only split manifest.
- `leakage.py` scans model-visible text for hidden-test, oracle, and seed leaks.
- `evaluator.py` runs common hidden-test evaluation and no-op/oracle baselines.
- `benchmark_smoke.py` runs the cheap end-to-end generation, privacy, and
  evaluator gate.
- `docs/raly-coder-benchmark-2026-08-27.md` defines the private benchmark and
  fixed split.
- `preregistrations/12_raly_coder_first_coding.md` is the locked-run plan; it
  must be committed before any confirmatory model run.

The private repository bundle, hidden tests, oracle patches, model outputs,
checkpoints, and scores are not stored in Git. No public benchmark leaderboard
is used.

Run locally with:

```text
<bundled-python> experiments/12_raly_coder/api_census.py
<bundled-python> experiments/12_raly_coder/smoke.py
<bundled-python> experiments/12_raly_coder/benchmark_smoke.py
```

Generate the ignored local bundle only after reviewing the preregistration:

```text
<bundled-python> experiments/12_raly_coder/generator.py --output data/private/raly-coder-v1
<bundled-python> experiments/12_raly_coder/leakage.py --bundle data/private/raly-coder-v1
```

