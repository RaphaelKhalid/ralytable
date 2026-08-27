# Experiment 14: iterative multi-file repository repair

This experiment tests a stricter version of the typed executable-state route.
Each task is a small repository written to disk in an isolated temporary
directory. `__init__.py` imports `api.py`; `api.py` composes a transform module
and a summary module, each containing one repair hole. The system must choose
two repairs in dependency order, re-run the package, and expose the second
diagnostic only after the first repair has changed the executable state.

The learned component is a two-parameter predicate gate. It receives one typed
state bit at each stage and routes the request's true or false branch. This is a
supplied-bit identity/routing task, not semantic inference. The request parser,
candidate patch library, compiler, package loader, public-test search, and
hidden tests are kept outside the learned parameter count and are reported
separately. The raw learned result is the two patches selected with no search;
the verified result is bounded public-test search followed by frozen hidden
tests. The 24-task result is CPU-only smoke evidence and the larger run is
paused.

This is still a generated micro-repository benchmark, not a claim of general
repository-level coding ability. Its purpose is to test a causal mechanism and
an execution boundary with stronger controls than the in-memory bundle.

## Smoke

```powershell
C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/14_iterative_repo_repair/iterative_repo_repair.py --device cpu --updates 5 --train-count 24 --eval-count 24 --seeds 11
```

## Frozen run

```powershell
C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/14_iterative_repo_repair/iterative_repo_repair.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37
```

The run records JSONL rows in `research_log.jsonl`. No public benchmark answers
or external repositories are used.
