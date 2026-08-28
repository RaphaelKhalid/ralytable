# Raly Coder private coding benchmark v1

Date: 2026-08-27

## Purpose

This is the primary evaluation for the first Raly Coder experiment. It asks
whether a small model can repair Python repositories through typed executable
actions. It is not a general reasoning benchmark and is not submitted to any
public leaderboard.

The primary endpoint is executable task success: after the agent stops, all
hidden tests pass in a fresh evaluator process. Formatting, trace validity, and
the number of actions are secondary endpoints.

## Task unit

Each task is a versioned repository snapshot plus an issue request. The private
record contains:

- a repository tree containing only Python source and test files;
- a bug seed and task-family identifier;
- a natural-language issue request;
- visible tests, if the task family has them;
- hidden tests, never shown to the model or committed to Git;
- an oracle patch and a symbolic expected outcome, used only by the evaluator.

The repository is generated deterministically from a versioned task generator.
The evaluator materialises a fresh temporary checkout for every trial, applies
the model's patches through the sandbox, and runs hidden tests in a clean
process. A task is not excluded because the model emits malformed actions or
fails tests; those are recorded outcomes.

## Task families

The v1 generator has eight families, each implemented with small standard-
library Python repositories:

1. boundary and off-by-one logic;
2. recursive tree or graph traversal;
3. parser/tokenizer edge cases;
4. state transition and cache invalidation;
5. serialization and round-trip compatibility;
6. error handling and validation;
7. sorting, grouping, and stable ordering;
8. numeric conversion and empty-input behavior.

Every task requires at least one code edit and at least one hidden assertion.
The hidden assertion is not equivalent to a visible example. Tasks may include
visible tests, but the issue request never names the hidden test or oracle
patch. The action API is intentionally sufficient for inspection, editing, and
verification, not arbitrary shell access.

## Fixed split

The split is by generated repository family and seed, not by individual prompt
randomisation:

| split | repositories | tasks | generator seeds | purpose |
|---|---:|---:|---|---|
| train | 48 | 1,152 | 10,000-10,047 | training traces and supervised examples |
| dev | 8 | 192 | 20,000-20,007 | prompt/action-budget selection only |
| private test | 16 | 384 | 30,000-30,015 | one locked primary evaluation |
| private replication | 16 | 384 | 40,000-40,015 | held until after the first verdict |

Each repository contributes 24 tasks. Test repositories use held-out bug
instances and held-out compositions of the same eight families; symbol names,
constants, file layout, and issue wording are independently generated. The
replication split is never used for model, prompt, decoder, or retry decisions.

The committed manifest will contain task IDs, split labels, generator version,
and SHA-256 commitments for each private repository and hidden-test bundle. It
will not contain source, hidden tests, oracle patches, model outputs, or
benchmark scores. The private bundle is stored locally under an ignored path and
backed up only through the project's private storage.

## Agent protocol

All three 9M arms receive the same issue, initial repository snapshot, action
budget, maximum wall-clock time, and sandbox outputs. The dense and free-text
arms use the same executor and may emit ordinary text that the common parser
maps to the same six operations. The Raly arm emits the typed action schema
directly. The scaffold, retry count, temperature, tool-call timeout, and test
feedback policy are fixed before the confirmatory run.

The allowed operations are:

`find_symbol`, `open_file`, `read_region`, `apply_patch`, `run_tests`, and
`inspect_failure`.

The evaluator records the complete action trace, including invalid, truncated,
failed, and abandoned trials. A model may not read the private evaluator,
hidden tests, oracle patch, Git metadata, network, environment secrets, or an
unbounded shell command.

## Metrics and nulls

Primary: paired task success, Raly minus each matched control, with the task as
the analysis unit and seed-level aggregation reported separately.

Secondary: success by family, hidden-test pass fraction, visible-test pass
fraction, patch validity, action count, test invocations, invalid-action rate,
time to first useful read, and failure-inspection usage.

Nulls are explicit:

- no-op patch / unchanged repository;
- oracle patch passed through the same evaluator;
- random valid action policy under the same action budget;
- common scaffold with the model output removed, where applicable.

The oracle defines the reachable ceiling; no-op and random policies define
capability-free floors. None is a substitute for the matched dense baseline.

## Leakage and privacy checks

Before locking v1, run a scanner that checks issue text, visible tests, source
comments, filenames, and generated metadata for hidden-test names, oracle
patch fragments, seed values, and answer literals. The evaluator runs with
network disabled and a clean environment. The benchmark is run locally only;
LiveCodeBench may be run separately as a private external reference, and
SWE-bench results are diagnostic only.

