# Ralytable Option C: independent architecture review

Please independently review, improve, or replace the proposal below. Be
creative, but do not oversell. Distinguish established results, inferences,
and speculation. The goal is a useful overnight experiment on an RTX 4060
Laptop with 8.6GB VRAM, not a grand claim that cannot be tested.

## Project context

Ralytable is building both:

- **Raly**, a Rust language/compiler whose type system tracks dimensions,
  roles, VSA family, and estimated superposition load;
- **Ralytable**, a model intended to expose important computation through
  explicit, inspectable internal state.

The compiler has a lexer, parser, resolver, type checker, diagnostics, and a
browser playground. It does not yet execute model programs. The current model
evidence is a 29.5M TinyStories dense baseline and a matched 512-code variant;
the discrete variant loses capability to the dense control. The project must
not claim that the current model reasons or that typed structure is already
causally load-bearing.

Relevant reference: [VibeThinker-3B](https://arxiv.org/abs/2606.16140), a dense
Qwen2.5-Coder-3B model improved using diverse teacher solutions, verification,
difficulty-focused RL, self-distillation, and extra test-time computation.

## Current proposal: Option C

Start with an existing small coder model, probably around 0.5B parameters, and
train a lightweight adapter plus an explicit structured workspace:

```text
request -> coder model -> typed workspace -> named operations -> Python code
                                      \-> tests, errors, and repair state
```

The workspace contains files, symbols, functions, a plan, test results, and
errors. The model emits named operations such as `read`, `edit`, `compile`,
`test`, and `repair`. Each operation has an intervention hook. The model’s
external target language is Python 3 at first because it has mature parsers,
test runners, and hidden-test evaluation. Raly is initially the internal trace
and typed intermediate representation, not the emitted source language.

Compare:

1. ordinary coder LoRA or QLoRA;
2. the same base with Raly-style typed workspace and verifier training;
3. the structured model with residual shortcuts removed or shuffled.

Primary endpoint: hidden-test pass rate on held-out coding tasks. Secondary
endpoints: relevant-operation ablation gap, irrelevant-operation control,
residual leakage, repair success, token count, latency, and peak memory.

The proposed training recipe borrows VibeThinker’s useful parts but improves
them by verifying intermediate state transitions, using fresh or mutated hidden
tests, sampling by uncertainty rather than raw 50% success, and retaining only
verified or causally necessary traces.

The serious run must have a preregistered H0/H1, alpha 0.05, one primary
endpoint, fixed seeds and splits, multiple-comparison handling, a short smoke
test, checkpoints, durable logs, and a held-out replication plan.

## Questions to answer

1. Is this actually a promising architecture, or is the structured workspace
   likely to be decorative scaffolding around a normal neural model?
2. Is Python the right first target? Compare Python, Rust, Raly, and a smaller
   intermediate language in terms of verifier quality, data availability,
   learnability, and startup value.
3. What materially better architecture could replace Option C while remaining
   testable on this hardware? Consider program synthesis, execution traces,
   typed memory, graph/state-space models, neuro-symbolic systems, VSA, sparse
   computation, and verifier-guided search.
4. What is the strongest cheap kill test? What result would make us stop,
   pivot, or downgrade the idea?
5. Which parts of VibeThinker’s recipe are likely causal, and which are merely
   bundled engineering choices? Identify missing ablations and fair controls.
6. Give a concrete overnight plan with approximate memory, data, steps, smoke
   test, metrics, and failure recovery. Do not assume a 3B model can be fully
   trained on 8.6GB VRAM.

## Required response format

- Bottom-line verdict
- Three strongest criticisms
- Three improvements worth adding
- One replacement architecture, if justified
- Recommended language and why
- Exact overnight experiment
- Claims we must not make yet
