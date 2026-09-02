# Research log

Append-only. Dead ends stay in.

## 2026-08-31 -- autoresearch heartbeat mechinterp-20260831T071743596Z-001

Verdict: the bounded Experiment 17 reproducibility smoke audit passed, so the
dependency-free trust-kernel and candidate path is operational on this
checkout. No candidate was kept or reverted, no GPU job was launched, and no
HumanEval+ or other scientific score was produced.

Question/hypothesis: can the existing trust-kernel, ledger, AR0-AR2 recovery,
receipt, evaluator-contract, and candidate smoke tests run from the current
Windows checkout without changing frozen research code? Baseline/null: no
model execution; raw learned, full-system, and deterministic-null scores are
unmeasured, not zero claims. The current AR2 fixed MAP-Elites result remains
the incumbent.

Exact command and result:

- `PYTHONDONTWRITEBYTECODE=1; C:\\Users\\rapha\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe -m unittest tools.autoresearch_next.tests.test_core -v` — 14 tests passed in 2.305 seconds (`OK`), including candidate learned-parameter and exact-trace-replay checks.

Seed/config: the test suite uses its pre-existing fixed test seeds (including
3, 11, 17, 101, 1201, and 1403); this is a smoke configuration, not a
multi-seed experiment and not confirmatory evidence. Files changed by this
invocation: this append-only log entry only; `autoresearch.lock` was a
transient lease and was released normally.

Validity/limitation: valid engineering smoke result. WSL remains unavailable
(`wsl.exe -l -v` returned `E_ACCESSDENIED`), so the approved PyTorch/RTX 4060
training route cannot be run from this host. The under-40M protocol remains a
review draft and its GPU tournament remains gated on explicit approval. Next
action: re-check WSL access and the validated training environment; if still
blocked, perform the next bounded dependency/environment audit without
launching model work.

## 2026-08-31 -- autoresearch heartbeat 20260831T001245753-456ab4f1

Verdict: the bounded reproducibility-audit iteration was skipped after an
environment check found no usable local Python interpreter and WSL access
denied. No scientific score was produced, no GPU job was launched, and no
candidate was kept or reverted.

Question/hypothesis: can the existing Experiment 17 trust-kernel,
checkpoint/receipt, and candidate smoke tests run from this checkout without
altering the frozen evaluator or benchmark contract? Baseline/null: no model
execution; raw learned, full-system, and deterministic-null scores are all
unmeasured (not zero claims).

Exact commands and observations:

- `PYTHONDONTWRITEBYTECODE=1; python -m unittest tools.autoresearch_next.tests.test_core -v` — failed before launch because `python` is not on PATH.
- `Get-Command py,python3,python,uv,pixi` — only `uv.exe` was found.
- `uv python list; uv python find --system` — cache initialization failed because `C:\Users\rapha\AppData\Local\uv\cache` already exists as a conflicting filesystem entry; no interpreter was found.
- `wsl.exe -l -v` — denied with `E_ACCESSDENIED` while enumerating distributions.

Validity/limitation: valid operational blocker record, not experiment evidence;
no seed/config was executed. The existing under-40M protocol remains a review
draft and its GPU run remains gated on explicit approval. Next action: on a
future invocation, re-check for an already-installed interpreter or restored
WSL access, then run the same bounded local audit before any model work.

## 2026-08-26 -- repo created

Scoping. Direction chosen: reasoning-model interpretability, building on and then
departing from Thought Anchors.

Framing settled: the interesting cut is at the level of *substrate*, not at the level
of patching the resampling estimator. Thought Anchors probes text from the outside
because natural language has no machine-readable dependency structure. If the model
reasons in a substrate where dependencies are explicit, the causal graph can be read
rather than estimated.

Open, unresolved:
- Which cheap reasoning model on OpenRouter exposes usable CoT.
- What the formal substrate actually is (Prolog/Datalog clauses vs. typed steps vs.
  proof terms). Unknown whether models emit any of these reliably enough to study.
- Whether "read-off graph vs. resampled importance" can be compared on a common scale
  at all. This is the load-bearing methodological risk and is not yet solved.

Not yet done: no code, no API calls, no cost measured.

## 2026-08-27 -- overnight autoresearch integration and correction

Verdict: the overnight run found a narrow efficiency/state result, not a
general coder. In the valid Experiment 13 record, typed legality plus
public-example search moved a learned sketch from 52.1% raw pass to 89.6%
full-system hidden pass on a generated synthetic composition family; the
deterministic null also reached 89.6%. The larger state-only controller is a
candidate mechanism that is causally load-bearing in a synthetic control: state
erasure changed 50.0% of raw decisions while an irrelevant placebo preserved
100%. Raw learned, verified full-system, symbolic, and deterministic-null
scores are distinct and must not be merged.

The integration provenance is the completed overnight worktree at
`ef74feb27fffdeeebfa380f2f8b344bb17a4db7f`, descended from `faaf00d`. The
machine facts are RTX 4060 Laptop, 8.6GB VRAM, torch 2.6.0+cu124, bf16
autocast, fused AdamW, and a <=9M learned-parameter gate; the largest logged
model was 54,516 parameters. Experiment 14 is CPU-only smoke evidence and is
paused: its planned multi-seed run was stopped after file-backed package
imports exceeded the short budget.

Scientific correction: the two-parameter predicate gate is supplied-bit
identity/routing, not semantic inference. The `semantic_rule_gate` and
`repository_bundle_gate` nuisance-placebo controls are tautological because
nuisance is absent from the gate, so their historical causal rates are invalid
for causal promotion. All Experiment 13/14 tasks are synthetic or generated.
The actual Raly compiler/runtime was not in the execution path; call this
Raly-style or Raly-inspired research, not Raly-based.

Measurement correction: historical `latency_ms` starts after inference and
includes old-loop evaluation work, so it is not end-to-end latency. New
`run.py` rows separate inference, selection, hidden scoring, and
inference-through-selection. The valid JSONL has 386 rows. The 12-row
oracle-contaminated smoke remains preserved in
`experiments/13_autoresearch_raly_coder/research_log_invalidated_null_oracle.jsonl`
and is excluded from aggregates. The record audit and reproduction path are
in `experiments/13_autoresearch_raly_coder/measurement_audit.py` and its
README; no replacement confirmation results were manufactured.

Next decision: do not promote this architecture. First remove the supplied
label/state shortcut with independently specified tasks where executable state
is necessary but not sufficient, keeping hidden answers scoring-only. Then
test a richer Python surface or repository-local repair. GitHub publication,
pull request, Vercel preview, and production promotion remain separate review
actions and were not performed here.

Public destination (predeclared, not run here): EvalPlus HumanEval+ is the
benchmark-guided discovery scoreboard; task-level failures may be inspected and
optimized against with contamination disclosed, so its tuned score is not held-out
evidence. EvalPlus MBPP+ is the cleaner cross-benchmark generalization check;
BigCodeBench-Hard Complete is the practical stretch target; and a later,
time-separated LiveCodeBench slice is the freshness audit. Autoresearch uses frozen
local proxy tasks. Public prompts/solutions stay out of training; HumanEval+ is the
deliberate, disclosed exception for iterative diagnostic optimization. Future runs
predeclare <=9M learned parameters, raw-controller/full-system/deterministic-null
scores, search/test-time budget, and separate latency fields. No public benchmark
was run or published in this integration.

HumanEval+ execution checkpoint: the official EvalPlus 0.3.1 loader smoke passed
with 164 tasks. The complete deterministic-pass baseline was attempted locally but
native Windows cannot satisfy the official evaluator's POSIX `resource` and
`signal.setitimer`/`SIGALRM` timeout path. It was stopped without modifying the
harness or claiming pass@1. The adapter and append-only result-record/dashboard
code are in `experiments/16_humaneval_plus_baseline/`; the shortest route to a
valid number is a POSIX run with EvalPlus 0.3.1 and the same generated samples.
The baseline has zero learned parameters, no generation/search budget, and no
Raly compiler/runtime. Future candidate records must preserve raw/full/null,
compile rate, pass@1, parameters, search budget, expansions, inference/search/total
latency, wall time, and failure categories. Any HumanEval+-optimized result must
be labeled HumanEval+-tuned; MBPP+ and LiveCodeBench were not run.

## 2026-08-27 -- AR2 conclusion and under-40M decision

AR2 completed successfully after correcting the experiment-generation logic:
1,218 trials and 623,831 receipts passed validation, corruption, recovery, and
reproduction checks. Fixed MAP-Elites scored R=29.33. Adaptive QD-UCB scored
R=30.46, but the paired improvement was inconclusive (+0.82, 95% CI -0.95 to
2.68). The stagnation-aware controller scored R=29.74 (+0.41, 95% CI -0.27 to
1.09), and its blind improvement was also inconclusive. Neither challenger is
promoted. Fixed MAP-Elites remains the incumbent. AR2 used CPU simulation only;
it did not train a model or use the GPU.

Decision: the next experiment must test researcher quality on the real target.
Under identical RTX 4060 GPU minutes, data, evaluator calls, starting code, and
proposer information, compare the fixed MAP-Elites incumbent with a faithful
Karpathy greedy keep/revert controller while each optimizes a real under-40M
Python student. Use matched dense and causally typed-state architectures.
HumanEval+ greedy pass@1 is the finalist capability metric, while separate
counterfactual state interventions gate the interpretability claim. Do not call
the whole neural model fully interpretable merely because it emits typed state.

The review-only protocol is `docs/plan-under-40m-humaneval-plus.md`. It proposes
one 37-39M student, an Apache-2.0 Qwen2.5-Coder-0.5B teacher, immutable
execution-filtered distillation data, and an approximately eight-hour tournament.
The public stretch target is 17/164 HumanEval+ tasks (10.4%) as a
parameter-efficiency milestone. Training, uploads, model publication, and
leaderboard submission still require separate approval.

Product decision: stop treating custom silicon as necessary. A later device can
package existing compute into a private, always-on local companion. Commodity
fit is easy at this scale; the defensible product is the appliance, interaction,
privacy, offline behavior, and legible record. Hardware work must not displace
the model experiment, but model runs should record quantization damage, memory,
latency, energy, and exportability.

## 2026-08-31 -- autoresearch heartbeat mechinterp-20260831T072228495Z-31300

Verdict: the bounded primary-environment recheck remains blocked by WSL
service access denial. No model, GPU, HumanEval+, or proxy scientific score
was produced; AR2 fixed MAP-Elites remains the incumbent.

Question/hypothesis: is the previously validated WSL/PyTorch RTX 4060
training environment available for the next approved under-40M experiment?
Baseline/null: no model execution; raw learned, full-system, and
deterministic-null scores are unmeasured, not zero claims.

Exact commands and observations:

- `wsl.exe --status` and `wsl.exe -l -v` — both returned
  `Wsl/EnumerateDistros/Service/E_ACCESSDENIED`.
- `wsl.exe --version` — WSL 2.7.12.0, kernel 6.18.33.2-2.
- `wsl.exe -d Ubuntu --user root -- bash -lc "set -u; printf WSL_OK; uname -a; if test -x /home/rapha/ralytable-autoresearch-next/.venv/bin/python; then /home/rapha/ralytable-autoresearch-next/.venv/bin/python -c 'import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0), torch.cuda.is_bf16_supported())'; else echo TRAINING_VENV_MISSING; fi"` — failed immediately with `Wsl/Service/E_ACCESSDENIED`.
- Cached Windows interpreter check — Python 3.12.13 is present, but importing
  `torch` raises `ModuleNotFoundError`; no CUDA fallback is authorized.
- `nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits` — RTX 4060 Laptop GPU, 2185 MiB used of 8188 MiB, 17% utilization; no research process was launched.

Seed/config: none; this is an exploratory environment audit, not a
multi-seed experiment or confirmatory result. Files changed by this
invocation: this append-only log entry only; the durable lease was transient
and released normally. The pre-existing `RESEARCH_LOG.md` changes were
preserved.

Validity/limitation: valid operational blocker record. The approved WSL
training route remains unavailable, and the protocol explicitly says to stop
WSL writes after the prior I/O failures; do not install another wheel, churn
the VHD, or start the GPU tournament. Next action: re-check for restored WSL
access or an already-installed validated environment on a later invocation;
if still blocked, perform only a bounded dependency-free audit or document
the unchanged blocker.

## 2026-09-01 -- autonomous 40M interpretable-coder architecture loops

The dedicated dated log is `RESEARCH_LOG_2026-09-01_to_2026-09-02.md`.
Dependency-free loops 02–11 tested typed graph/ledger capacity, duplicate
robustness, beam verification, no-bypass causality, field-level steganography,
40M budget feasibility, compositional scaling, invariant pruning, and a
proof-carrying runtime contract. No LLM was fine-tuned and no benchmark or
Qwen score was produced.

Current design decision: keep a typed program ledger with explicit dataflow,
content-addressed deduplication, typed primitive modules, bounded hypothesis
beam search, deterministic execution verification, conservative abstract
invariants, field-level causal audits, and replayable receipts. The strongest
negative result is that type legality alone does not supply semantic validation
or meaningful search pruning; the strongest positive result is synthetic
support for verifier-guided search and exact typed graph semantics.

Do not claim fully interpretable T3 status until a learned front end passes raw
path, relevant-state, placebo, and every-unused-field interventions. Do not
claim parity with a 27B coder except on a frozen, explicitly scoped task
distribution with retrieval, module coverage, verifier calls, and search
budget reported separately. The PyTorch/WSL training environment remains
unavailable on this host, so the next loop should continue with compiler/runtime
semantics or a learned-parser surrogate without training an LLM.
