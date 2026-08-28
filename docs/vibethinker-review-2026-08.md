# VibeThinker-3B review

Reviewed 2026-08-27 against the authors' technical report and repository.

## Verdict

VibeThinker-3B is strong evidence that a small dense model can become very
good at verifiable mathematics and coding through specialised post-training.
It is not evidence that a 3B model has the broad knowledge or general ability
of Opus, and it is not an interpretable-by-construction architecture. It is a
valuable baseline and training recipe for Ralytable, not the new architecture
we are looking for.

## What it actually is

The base is Qwen2.5-Coder-3B, a conventional dense language model. The paper's
contribution is primarily the post-training pipeline:

1. SFT data is expanded into multiple valid solution paths and filtered with
   answer checks, code execution, and model voting.
2. A second SFT stage concentrates on difficult, long solutions.
3. MGPO-style on-policy RL samples several answers per prompt and upweights
   prompts where the model is around 50% correct. That is a sensible way to
   avoid spending updates on problems that are already trivial or currently
   impossible.
4. Math, code, and STEM RL are run with different verifiers. The report uses a
   single 64K context window to avoid training the model to truncate long
   reasoning.
5. Verified trajectories are self-distilled back into one model, prioritising
   traces the student currently models poorly.
6. A final instruction-RL stage improves constraint following.

The paper also adds CLR, a test-time method. It samples 32 full trajectories,
extracts five claims from each, asks the model to validate them, and selects
the answer with the highest reliability-weighted support. This raises scores
without changing model weights, so it is inference-time compute, not a smaller
model suddenly containing all the capability of a 1T model.

## What the reported results establish

The report gives VibeThinker-3B 94.3 on AIME26, 80.2 Pass@1 on LiveCodeBench
v6, and 70.2 on GPQA-Diamond. With CLR, the reported AIME26 score rises to
97.1 and GPQA-Diamond to 72.9. The paper evaluates math with repeated samples,
code by execution, and lists a 123/128 result on recent LeetCode contests.

The pattern matters more than the headline: it is excellent on tasks with a
clear verifier, while its gap is larger on broad scientific knowledge. That is
consistent with the authors' own distinction between a compact reasoning core
and broad parameter coverage.

## What it does not establish

- The comparison models are taken from reports, leaderboards, or official
  records, so the table is not a single controlled head-to-head run.
- The math results use many sampled generations and CLR uses additional model
  calls. They should be compared with equal inference budgets, not just the
  number printed beside a one-shot model.
- The 123/128 coding result is encouraging but small. It needs independent
  replication and confidence intervals before being treated as a stable rate.
- The report does not provide a clean component-by-component ablation that
  isolates how much came from data, SFT, MGPO, self-distillation, long context,
  or test-time scaling. The report describes the choices, but description is
  not the same as causal attribution.
- Nothing in the method makes hidden computation legible. The model can still
  produce a persuasive but unfaithful explanation.

## What we should borrow

Borrow the training logic, not the claim that it is our architecture:

- generate diverse candidate solutions before filtering for correctness;
- use verifiers wherever possible;
- train first for correctness, then separately test shorter solutions;
- sample problems near the current capability boundary;
- keep a held-out task family and equalise test-time compute;
- use teacher models to generate data, while measuring how much the student
  actually learns rather than counting teacher quality as student quality.

For a code-only Ralytable model, this is a plausible route. The corpus can be
mostly code, tests, documentation, and technical problem statements, with a
small interface vocabulary. It should be evaluated on fresh repositories and
hidden tests, not only training-style coding prompts. A narrow coding model
could be useful at 200M to 3B parameters, but that is a specialist product
claim, not a route to broad Opus-level conversation.

## Where Ralytable can be different

Our architecture experiment should compare the same VibeThinker-style data and
verifier pipeline across:

- a conventional dense baseline;
- a dense model with the full post-training recipe;
- a structured-memory model whose reads, writes, and operations are explicit;
- the structured model with its residual path removed or shuffled.

The primary claim would be causal legibility: if the model says a named object
or operation carried the answer, intervening on that object should change the
answer, while an irrelevant intervention should not. That is a measurable
difference from post-hoc reasoning traces. It is not guaranteed to work.

Do not combine this architecture comparison with a new learning rule. First
use ordinary backpropagation to learn whether the structure helps. Only then
compare a typed local credit-assignment method against backprop on the same
model and task.

## Sources

- [VibeThinker-3B technical report](https://arxiv.org/abs/2606.16140)
- [VibeThinker official repository](https://github.com/WeiboAI/VibeThinker)
