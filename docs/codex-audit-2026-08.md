# Codex audit and architecture plan

Date: 2026-08-27

## Short version

Ralytable is a serious research prototype, not yet a new model architecture or
a frontier-model competitor.

The compiler is the strongest thing built so far. It has a real front end,
useful type errors, a browser demo, and a type system that records properties
ordinary tensor code leaves implicit. The model is currently a baseline study:
a 29.5M-parameter transformer on TinyStories, plus a 512-code discrete
midpoint. The discrete model lost materially to its dense control on held-out
text and blind story judging. It cannot reason.

That negative result makes the next question sharper:

> Can a structured internal state preserve the things a single vector
> bottleneck loses, while making the important computation causally inspectable?

That is the experiment that can tell us whether there is a model idea here.

## Scorecard

These are judgement scores, not benchmark measurements. The evidence behind
each score is listed so the scores can move.

| area | score | why |
|---|---:|---|
| Experimental discipline | 4/5 | Multiple controls, seeds, confidence intervals, preregistered story judging, and several negative results. Some older copy still needs continual auditing. |
| Compiler foundation | 3/5 | Lexer, parser, resolver, type checker, diagnostics, explain mode, and browser/WASM path pass the compiler gate. There is no IR, code generation, runtime, or differentiable backend. |
| Model capability | 1/5 | The 29.5M dense baseline writes simple text; the discrete model is worse. There is no evidence of open-ended reasoning or broad question answering. |
| Actual interpretability | 2/5 | The type-level contracts are promising. The first model's role codes were partly character leakage and its citation structure was not shown to be load-bearing. |
| Architecture novelty | 2/5 | A typed VSA/discrete modelling language is a plausible narrow intersection. VSA language models, differentiable gates, concept bottlenecks, discrete latent models, and sparse interpretable networks already exist. The model architecture itself is not new yet. |
| Research payoff | 3/5 | A causal legibility benchmark or a structured state that survives the current failure could be a meaningful contribution. Both can also fail cleanly. |
| Startup readiness | 1/5 | There is a browser demo and a plausible embedding diagnostic, but no validated user, deployment, revenue, or model advantage. |

The score I would try to move first is actual interpretability, from 2 to 3,
by showing that an intervention on a named internal object changes the result
in the predicted way while an irrelevant intervention does not. Capability
comes next. A prettier trace is not enough.

## What the existing evidence really says

- The compiler has 198 tests and passes build, tests, clippy with warnings
  denied, and formatting. It type-checks; it does not execute a model.
- On TinyStories, the dense control reached validation cross-entropy 1.6608 and
  accuracy 58.77%. The 512-code model reached 2.2892 and 48.85%. These are
  matched, undertrained experiments, not a claim about absolute model quality.
- In the blind story test, the dense model won 152 of 179 valid pairwise
  comparisons. The dense-versus-dense null was 31 of 60, so the judge did not
  simply pick the first model every time.
- In the earlier synthetic experiment, code role purity was 0.664, but the
  majority-class baseline was 0.580 and a raw-character predictor reached
  0.6314. That is why code purity is not currently our main legibility metric.
- The retrieval experiment found a possible product-shaped problem: averaging
  passage embeddings can lose recall, and a max-pooling control isolated much
  of the loss to averaging. It does not prove a general law about all embedding
  systems.

The positive compiler result and the negative model result are compatible. A
language can make a representation contract explicit without proving that a
model trained through that representation will use it well.

## Architecture routes worth exploring

### 1. Structured working memory

The model has a continuous perceptual encoder, then a small typed table of
entity, event, and relation slots. A controller performs named operations such
as read, write, compare, update, and emit. The output head sees the table and a
small continuous residual, but not an unconstrained hidden state.

Why this is worth testing: the TinyStories failure was loss of identity across
time. A table gives identity somewhere explicit to live instead of asking one
quantized vector to carry every fact.

Risk: this is close in spirit to memory networks, slot attention, concept
bottlenecks, and neural-symbolic systems. The novelty would need to be the
typed semantics plus a causal training objective, not the phrase “memory
slots”.

First kill test: on a synthetic entity-tracking task, mask the slot predicted
to contain the queried entity. The answer should fall substantially. Mask an
irrelevant slot as a negative control. If both interventions have similar
effects, the slots are decoration.

### 2. VSA-typed memory

Represent a record as a typed binding of roles to values, for example
Subject, Relation, and Object. Bundle records into a space with a tracked load.
Use permutation or a role-specific operator to preserve order. The model learns
to write and retrieve these records, while Raly checks dimension, family, load,
and role compatibility.

Why it is interesting: this makes the model's intended data structure compact
and inspectable, and it connects directly to the compiler.

Risk: VSA capacity and retrieval degrade with load. A learned codebook can also
break assumptions that hold for fixed random codebooks. The current repository
has measured those risks; it has not solved them.

First kill test: compare typed VSA memory against a dense key-value memory at
the same parameter count and memory bandwidth on exact multi-fact retrieval.
Include fixed random codes, learned codes, and a shuffled-code null.

### 3. A learned discrete operator program

Instead of quantizing the whole hidden state, the model predicts a short
sequence of typed operations. Each operation consumes and produces explicit
objects. The vocabulary is not “all thoughts”; it is a small set of operators,
roles, and values. The final answer is generated only after the program runs.

Why it is interesting: the inspectable object is the computation graph, not a
claim about what a neuron means. This is closer to a program with learned
arguments than to a transformer with an explanation channel.

Risk: discrete operation selection is difficult to optimize, and a fixed
operator set may simply fail on tasks outside its grammar. Straight-through
estimators can hide a train/test mismatch.

First kill test: train on short programs and test on longer compositions with
held-out operator sequences. If training accuracy is good but compositional
generalisation is chance, the program is memorising templates.

### 4. Predictive or energy-based structured state

Replace one backward pass through the structured core with local prediction
errors or an equilibrium update. Each typed state predicts the next state, and
training reduces local errors as well as final answer loss.

Why it is worth keeping alive: it could provide a natural local learning rule
for a state machine and make intermediate errors inspectable.

Risk: the alternatives to backpropagation are not established replacements for
large language-model training. Equilibrium methods require iterative settling;
predictive coding and target propagation introduce auxiliary models or local
objectives; forward-forward needs positive and negative examples. This should
be a second-stage comparison, not mixed into the first architecture test.

First kill test: on the same tiny task and same parameter count, compare
backpropagation, a local target update, and the forward-forward rule. Match
optimizer steps and wall-clock time, not just epochs.

## Recommendation

The best next model is a hybrid, but not the vague kind:

1. A small continuous encoder handles language perception.
2. A typed working-memory core stores a bounded number of entities and facts.
3. A controller emits named operations over that memory.
4. A verifier checks the operation trace against the task state.
5. A small decoder emits the answer.
6. Every memory read, write, and operation has an intervention hook.

This is not being presented as an already-novel architecture. It is the
smallest design that directly attacks the observed failure and connects to
Raly's strengths. If it works, the contribution may be the combination of
typed semantics, causal training, and a capability/legibility measurement. If
it fails, we learn that explicit structure did not buy us what we hoped.

The continuous residual should be treated as hostile until proven otherwise.
It may smuggle the entire answer around the supposedly interpretable core.
Every experiment must include a residual-off condition and a probe for whether
the answer is recoverable without the named structure.

## Proposed overnight experiment

### Question

Does an explicit structured memory support exact multi-step question answering
and causal inspection better than a matched dense model or a single VQ
bottleneck?

This is a narrow, verifiable task. It is not a claim that the resulting model
can reason generally.

### Dataset

Generate the dataset deterministically in Python, not with an LLM:

- entities with unique names;
- facts such as “Ava is north of Ben”;
- two to six composable relation steps;
- distractor facts;
- questions whose answers are exact entity names or relation values;
- train on chains of length two to four;
- test on held-out names, relation combinations, and chains of length five to
  six.

Keep the generator seed and split in the experiment directory. Include a
majority/random answer baseline and a symbolic solver that defines the
reachable ceiling.

### Arms

- Dense transformer, matched parameter count.
- Existing single-vector VQ bottleneck, matched parameter count.
- Typed slot memory: eight entity slots, relation fields, named read/write
  operations, and a small residual path.
- Optional VSA memory only if the first three arms pass the smoke test.

Use the same tokeniser, context length, optimiser, token budget, and number of
seeds. Do not introduce a new learning rule in the same first comparison.

### Measurements

- Exact answer accuracy, with random and symbolic baselines.
- Accuracy by chain length and by number of distractors.
- Causal necessity: intervene on the named relevant slot or operation and
  measure the answer drop.
- Negative control: intervene on an irrelevant slot or operation.
- Sufficiency: retain only the predicted relevant structure and measure what
  remains.
- Residual leakage: answer probe with the residual enabled and disabled.
- Wall-clock time, peak memory, parameters, and bytes moved.
- Human-readable trace examples sampled before looking at aggregate results.

### Proposed gate

These are proposed preregistered thresholds, not results:

- the structured arm must beat the random baseline by a wide margin and retain
  useful accuracy on the longer held-out chains;
- the relevant intervention must cause at least three times the accuracy drop
  of the irrelevant intervention, with the ratio computed per seed;
- disabling the residual must not erase the entire effect;
- if the structured arm is more than five percentage points below the dense
  arm on in-distribution accuracy and shows no held-out generalisation gain,
  stop this variant;
- if all arms fail, fix the task or data generator before inventing a larger
  architecture.

The key null is not “the structured model has a readable trace”. It is “a
baseline or a post-hoc probe could do the same thing without using the
structure”.

### Run plan

First run a five-minute smoke test with roughly 100 batches and one seed per
arm. It passes only if loss falls, the symbolic ceiling is reachable by the
task generator, interventions execute, logs survive a closed terminal, and the
dashboard reports the run. Then run the full sweep overnight with three seeds.
Use W&B plus the local dashboard, checkpoints, resume, and a stop file. Never
start the full run until the smoke output has been inspected.

Before the full run, copy `preregistrations/TEMPLATE.md` to a numbered file and
fill in H0, H1, the one primary endpoint, alpha = 0.05 two-sided, the
within-seed analysis, the multiple-comparison rule, and the kill criteria. The
smoke test can reveal broken plumbing; it cannot tune the hypotheses or count
as confirmatory evidence.

## Backpropagation: what we should and should not do

Backpropagation is not popular because nobody imagined alternatives. It gives
the exact gradient of a differentiable objective and maps efficiently onto the
matrix operations current accelerators are built to execute.

There are credible alternatives:

- **Feedback alignment** replaces the exact backward weights with fixed random
  feedback and showed useful learning in small deep networks. It does not yet
  establish a competitive recipe for training a language model.
- **Target propagation** sends targets through approximate inverse mappings and
  can handle stochastic or discrete units. The inverse models are an additional
  source of error, especially as depth grows.
- **Forward-forward** trains layers with positive and negative examples using
  local goodness objectives. The original paper calls its demonstrations
  preliminary and focuses on small problems.
- **Equilibrium propagation** uses a free phase and a weakly clamped phase in an
  energy-based system. It can recover gradients under its assumptions, but
  iterative settling and energy constraints change the compute tradeoff.
- **Predictive coding** uses local prediction errors and can approximate
  backpropagation along computation graphs. It is an interesting fit for
  structured state, but approximation is not the same as a demonstrated
  language-model advantage.

The reason these have not simply replaced backpropagation is practical as well
as theoretical: they often need extra passes, negative samples, inverse
networks, fixed-point iterations, symmetric or tied connections, or local
objectives whose gradients do not match the final task. Backprop has its own
problems, but those alternatives must beat it on the same task, parameter
budget, hardware, wall-clock time, and final metric.

Our candidate contribution is narrower and testable: use backprop as an oracle
to establish whether the structured model is capable, then compare a typed
local credit-assignment rule on exactly the same model. A possible rule is
typed target propagation: every named state object receives a local target
from the verifier, and updates are made from the mismatch between the current
object and that target. It is a hypothesis, not a claim.

Do not combine a new architecture and a new learning rule in the first
experiment. If both change and the result improves, we will not know why.

## How Raly should absorb the model

Do not port the entire project to Raly immediately. Raly cannot execute yet,
and Python has the mature GPU, data, and optimisation ecosystem needed for
fast research.

The sensible sequence is:

1. Add a small executable interpreter for typed memory operations on CPU.
2. Define an IR that preserves spaces, roles, loads, operation names, and
   intervention points.
3. Add a PyTorch backend or bindings so the same Raly program can call GPU
   kernels while training stays in Python.
4. Make the model's structured core generated from or checked against Raly.
5. Add a Rust GPU/runtime backend only when profiling shows a real bottleneck.
6. Port data and training orchestration after the semantics and runtime have
   stabilised.

The goal is not to replace Python for its own sake. The goal is that the
representation whose semantics matter is written once, checked once, and
executed consistently in the notebook, the trainer, the browser demo, and
eventually a production runtime.

## Startup-shaped avenues

The model startup is the highest-upside and highest-risk route. It currently
has no capability advantage to sell.

The nearer routes are:

- a diagnostic that measures what embedding aggregation costs on a customer's
  retrieval pipeline;
- a model compiler/linter that catches mismatched spaces, role errors, and
  known capacity risks before training;
- an auditing benchmark and agent interface where success requires finding a
  hidden property that black-box shortcuts cannot trivially recover.

These can be pursued in parallel with the model research because they do not
depend on claiming that Ralytable is already a strong language model.

## Decision after the overnight run

- **Structured state wins capability and passes intervention tests:** build the
  Raly IR around that state and scale the task family.
- **Structured state is causal but costs capability:** keep it as an audit or
  safety architecture; investigate better memory and training before claiming
  a general LM.
- **Structured state is readable but not causal:** reject the architecture as
  decorative and move to a different substrate.
- **All arms fail:** debug the task and implementation against the symbolic
  solver before making architectural conclusions.
