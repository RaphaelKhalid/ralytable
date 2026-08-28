# Paused handoff

Research is intentionally paused at this checkpoint. Do not start another
training or recursive-learning run unless the user resumes the loop.

## Last verified state

- Experiment 13 remains the latest committed research result:
  `8d6a787 Test multi-file repository bundle repair`.
- The local dashboard is still served at `http://127.0.0.1:8767/dashboard.html`.
- Experiment 14 was created as a stricter follow-up using isolated temporary
  on-disk packages with `__init__.py -> api.py -> transforms.py/summaries.py`.
- Its 24-task CPU smoke test completed successfully at five updates and one
  seed. Symbolic control passed all public and hidden tasks; the learned raw
  controller passed 37.5% of public and 45.8% of hidden tasks; bounded public
  search passed all public and 95.8% of hidden tasks. The learned gate has two
  parameters and every tested package compiled.
- The planned 128-train/64-held-out, three-seed run was stopped because
  repeated temporary package creation/import made the run exceed the intended
  short budget. Only the Experiment 14 process was stopped; no existing GPU,
  dashboard, or server process was touched.
- This is a CPU-only smoke checkpoint. Its two-parameter gate routes supplied
  predicate bits through fixed branches; it is not semantic inference or
  evidence of repository-level coding.

## Resume point

The harness now contains `RepoSession`, which reuses one file-backed package
for multiple cases and should be benchmarked with a small timing probe before
any larger run. First check generator determinism and compile the script
read-only; then choose a new budget explicitly. The current JSONL log contains
only the smoke checkpoint and must not be presented as a multi-seed result.

## Interpretation

The smoke result is exploratory only. It demonstrates an executable package
boundary and a staged state interface, not general repository-level coding
ability. The next valid research claim requires multiple seeds, frozen held-out
tasks, raw versus verified separation, state-erasure and placebo controls, and
the <=9M learned-parameter gate.
