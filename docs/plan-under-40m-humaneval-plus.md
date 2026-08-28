# Under-40M HumanEval+ overnight run

Status: **review draft; do not execute without Raphael's final approval.**

## Objective

Train one Python-only student with fewer than 40,000,000 learned parameters that:

1. earns a reproducible, greedy, single-model HumanEval+ pass@1 score;
2. is competitive on parameter efficiency, with a stretch target of at least
   17/164 HumanEval+ tasks (10.4%);
3. exposes a causally load-bearing typed intermediate state rather than a
   decorative chain of thought; and
4. can later be released and submitted publicly with complete provenance.

The overnight run is scientific discovery, not a public action. It will not
upload a model, modify a leaderboard, or publish a result.

## What the earlier work permits us to claim

AR2 compared fixed MAP-Elites, adaptive QD-UCB, and a stagnation-aware variant
over 1,218 trials and 623,831 validated receipts. Fixed MAP-Elites remains the
incumbent: its score was 29.33; adaptive QD-UCB scored 30.46 but its paired
improvement was inconclusive (+0.82, 95% CI -0.95 to 2.68); the stagnation-aware
variant scored 29.74 (+0.41, 95% CI -0.27 to 1.09). Receipt corruption,
recovery, and reproduction checks passed. This was a CPU-only researcher
simulation, not GPU model training and not evidence of better code generation.

Therefore the next run compares the AR2 incumbent against a faithful Karpathy
keep-or-revert controller on the same real training problem. We do not promote
QD-UCB or the stagnation-aware controller.

## Fixed benchmark contract

- **Primary scientific evaluator:** EvalPlus 0.3.1, all 164 HumanEval+ tasks,
  greedy decoding, one sample per task, unmodified official execution tests on
  POSIX/WSL.
- **Leaderboard compatibility check:** also preserve a score under the
  leaderboard's documented HumanEval+ 0.1.10 contract if its submission path
  still requires it. Never silently compare scores from different releases.
- **Discovery set:** a fixed local functional-code proxy and a fixed development
  subset. The full 164-task score is reserved for finalists, not candidate
  selection after every five-minute run.
- **Holdouts:** no HumanEval, MBPP(+), LiveCodeBench solutions, hidden tests, or
  benchmark-derived synthetic solutions enter training. MBPP+ and a later
  time-separated LiveCodeBench slice remain untouched generalization audits.
- Every reported score records model hash, tokenizer hash, data hashes,
  evaluator version, decoding arguments, seed, parameter count, wall time,
  peak VRAM, and raw generated programs.

HumanEval+ is an outcome test, not a reasoning test. The reasoning claim is
gated independently below.

## Student and matched control

Build one approximately 37-39M-parameter decoder, rather than dividing one
night across several sizes:

- 8,192-token Python/code vocabulary with tied input-output embeddings;
- width 512, 12 layers, 8 query heads and 2 key/value heads;
- SwiGLU feed-forward width near 1,344;
- RoPE, RMSNorm, causal attention, 1,024-token training sequences;
- BF16, fused AdamW when validated, and standard exportable PyTorch operations.

Before training, calculate and assert the exact learned-parameter count below
40M. Use the same tokenizer, data order, optimizer budget, decoding budget, and
seeds for two architecture families:

1. **Dense control:** a conventional causal decoder.
2. **Typed-state candidate:** a prompt parser produces an explicit state
   containing signature and types, algorithm family, data flow, control flow,
   invariants, and an AST skeleton. The code decoder receives only that state
   plus a transparent identifier/literal copy table. It cannot attend directly
   to the raw prompt.

The copy table is deliberately narrow: earlier discrete models lost entity
identity, while a broad continuous residual would provide an opaque bypass. The
whole neural model is only eligible for a **T2 causally inspectable** claim. It
is not "fully interpretable" or T3 merely because its state is typed.

## Data and teacher

Use the Apache-2.0 Qwen2.5-Coder-0.5B-Instruct model as a teacher. Generate and
execution-filter the distillation corpus before the timed search so candidate
researchers see identical immutable data. Mix:

- permissively licensed Python source and docstring/function pairs with exact
  provenance;
- teacher-produced typed plan, implementation, tests, and repair/edit sequence;
- execution-filtered synthetic composition tasks that require multiple steps;
- counterfactual pairs that change one requirement while preserving distractors.

Prefer a code-specific tokenizer and from-scratch student. Pythia-31M is a
useful 31M baseline/checkpoint control, but its general-text tokenizer and large
embedding share make it a poor default champion initialization.

## Independent reasoning and interpretability gate

The student must infer state; it is never given answer bits or an oracle plan.
Evaluate on held-out compositional tasks and real Python prompts with:

- exact replay of the emitted typed trace;
- counterfactual edits to types, invariants, branches, and data dependencies;
- irrelevant-state and distractor placebo interventions;
- ablation of the raw-prompt path to prove no hidden bypass exists;
- blind algorithm recovery from state alone.

Promotion gates:

- relevant state interventions change at least 80% of dependent programs;
- irrelevant/placebo interventions preserve at least 95%;
- trace replay is exactly deterministic for 100% of accepted traces;
- no raw-prompt or oracle-state bypass;
- the typed-state candidate beats its compute-matched dense control on the
  frozen internal functional suite and does not lose on the finalist
  HumanEval+ score.

Capability without the causal gate is an ordinary opaque coder. A causal gate
without capability is an interpretability result, not the champion.

## Autoresearch tournament

The editable surface is a small training/model configuration module. The data,
evaluators, receipt schema, budget enforcer, and final benchmark runner are
immutable. Each candidate is a real PyTorch training run on the RTX 4060 Laptop
GPU, not a simulation.

Run two matched arms:

- **KARPATHY:** greedy keep/revert using the current best validation result.
- **RALY-AR:** fixed MAP-Elites, the AR2 incumbent, preserving diverse valid
  candidates across capability, causal-state fidelity, memory, and speed.

Both arms receive the same proposer information, starting code, seed schedule,
data, GPU minutes, and evaluator calls. Suggested eight-hour budget:

1. Environment/data/evaluator smoke and immutable hashes: 30 minutes.
2. Ten candidates per arm at 300 GPU-seconds each: 100 minutes.
3. Top two per arm on a second seed for ten minutes each: 40 minutes.
4. One finalist per arm for approximately two hours each: 240 minutes.
5. Final evaluation, causal interventions, recovery margin: 70 minutes.

Hard invalidation precedes ranking: parameter overflow, data leakage, evaluator
mutation, non-reproducible receipt, OOM, invalid Python rate above the declared
limit, or failed causal/no-bypass checks. Among valid candidates, keep a Pareto
archive rather than collapsing unlike qualities into a tunable weighted score.
For final selection use this lexicographic order:

1. hard validity and causal gates;
2. blind finalist HumanEval+ greedy pass@1;
3. frozen local functional pass rate;
4. validation bits-per-byte;
5. latency, peak VRAM, and simplicity.

This is also the clean test of whether the improved researcher is better than
Karpathy's: compare the best valid final model from each arm under identical
compute, with paired task outcomes and bootstrap confidence intervals. If the
arms are indistinguishable, retire the stronger-researcher claim.

## Success ladder and stopping rules

- **Floor:** at least one HumanEval+ task passes (1/164, 0.61%).
- **Meaningful overnight result:** at least 9/164 (5.5%) with the full causal
  gate, or a statistically credible win over the dense control.
- **Public stretch:** at least 17/164 (10.4%), above the 9.1% historical
  HumanEval+ entry for CodeGen2-1B while using roughly 25 times fewer
  parameters. This is a parameter-efficiency target, not frontier absolute
  competitiveness.

Stop or downgrade the claim if every finalist scores zero, if the structured
model relies on a prompt bypass, if results cannot be reproduced, or if any
benchmark material entered training. Do not choose a champion using a test
score whose failures were repeatedly inspected.

## Public-release gate (later approval required)

After a successful private run and separate approval, prepare model weights and
code, a Hugging Face model card, exact evaluation artifacts, data provenance,
contamination statement, raw/full-system distinction, license audit, and a
reproduction command. The leaderboard number must be the raw single-model
greedy pass@1 result; any Raly search/verifier-assisted result is a separate
system score. Uploading, submitting, commenting, or opening a public benchmark
PR is outside this plan's present authorization.

## Packaged hardware direction

Drop custom silicon. A product can be a dedicated local reasoning/memory
appliance built from an off-the-shelf ARM/Linux or NPU compute module, secure
storage, microphones, battery, physical privacy controls, and phone/PC tethering
in the same product category as a compact console or meeting-memory device.

A 40M model is only about 80MB in BF16, 40MB in INT8, or 20MB at four bits, so
model fit is not the differentiator. The appeal must be private ownership,
always-on capture and recall, tactile UX, offline reliability, and a legible
local reasoning record. Develop in this order: software agent, reference
enclosure, companion appliance, then a production device. During model research
track quantization damage, RAM, latency, energy, and standard-op exportability so
the software path remains compatible with existing hardware.

## References

- Karpathy autoresearch fixed-time protocol:
  https://github.com/karpathy/autoresearch/blob/master/program.md
- EvalPlus official repository and HumanEval+ evaluator:
  https://github.com/evalplus/evalplus
- EvalPlus public leaderboard:
  https://evalplus.github.io/leaderboard.html
- EvalPlus paper: https://arxiv.org/abs/2305.01210
- Qwen2.5-Coder-0.5B-Instruct:
  https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct
- Pythia-31M: https://huggingface.co/EleutherAI/pythia-31m
- AST-T5 structure-aware pretraining: https://arxiv.org/abs/2401.03003
- Synthetic edit-sequence training: https://arxiv.org/abs/2410.02749
