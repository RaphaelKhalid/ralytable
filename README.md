# Ralytable

Ralytable is an experiment in typed, inspectable intermediate state. Raly is the
experimental language and compiler used to describe that state. The project is
now a falsification-first study of whether explicit representation is causally
necessary for a model's computation, rather than merely readable afterward.

## TL;DR

- The capability result is negative: a 512-code discrete bottleneck performed
  materially worse than a matched dense control on TinyStories text and stories.
- Synthetic audits can expose tested shortcuts involving raw prompts, decorative
  traces, unused fields, identity, replay, provenance, and verification.
- Those audits do not prove that a future learned system has no unknown bypass.
- The compiler type-checks a small pure subset. Vector-symbolic execution, code
  generation, and the learned model bridge are not built.
- No public coding-benchmark result or Qwen/27B comparison is claimed.

## Question

The broad question is:

> Can a model expose internal structure that a person can inspect without giving
> up too much capability?

The sharper question after the failed capability test is:

> Does an answer actually depend on the typed structure the system exposes, or is
> that structure only decoration around a raw prompt or another hidden shortcut?

A successful system must preserve capability while making relevant state
load-bearing. Readability alone is not the target.

## Competing explanations

The experiments distinguish among:

1. Useful explicit state: changing a relevant ledger entry changes dependent
   outputs, while irrelevant metadata and harmless surface changes do not.
2. Decorative or bypassed state: a raw prompt, metadata, position, or another
   field carries the computation despite the displayed trace.
3. Capability cost: the representation is causally used but imposes too much loss
   to be a practical architecture.

These are bounded tests of alternatives, not evidence that a readable trace is
faithful simply because it looks structured.

## Identification logic

The causal audits use interventions and controls:

- change relevant ledger state and check whether dependent outputs change;
- change irrelevant metadata and check that outputs remain invariant;
- remove the raw prompt after parsing to test for a hidden bypass;
- test declaration permutation, identifier renaming, scoped binding, replay,
  unused-field interventions, provenance, effects, and verifier behavior;
- compare raw-shortcut, decorative-trace, flat-state, and deterministic-null
  controls;
- keep search failure, witness discovery, and functional equivalence separate.

A passing synthetic control shows that the audit catches the tested mutant. It is
not evidence that a learned model is safe from every possible shortcut.

## Method at a glance

| Track | Design | Current evidence |
| --- | --- | --- |
| Capability | Matched dense and 512-code discrete transformer models on TinyStories; 29.5M parameters, three seeds | Discrete arm loses on held-out text and blind story comparisons |
| Story quality | 60 held-out prompts, six checkpoints, identical decoding, fixed judge prompt, blind pairwise comparison | Dense wins 152 of 179 model pairs |
| Causal audit | Dependency-free probes for state dependence, raw-path erasure, unused fields, identity, replay, and verifier behavior | Known shortcuts are exposed by targeted controls |
| Typed composition | Bounded primitive library and held-out combinations | 21/21 novel combinations in the typed primitive task |
| Learned parser smoke | Three seeds on two-node list-operation graphs against a matched graph-cross-entropy null | Preregistered relevant-intervention gate failed |
| Compiler | Lexer, parser, resolver, type checker, diagnostics, browser/WebAssembly playground | Small pure subset is usable |

## Primary results

### 1. The discrete bottleneck loses capability on real text

The matched TinyStories comparison used three seeds, 10,631 steps, batch 32,
context 256, and 87,089,152 tokens per run. The dense model had 29,497,856
parameters; the discrete model had 29,563,392, a 0.22% difference.

| | Cross-entropy | Accuracy | Perplexity |
| --- | ---: | ---: | ---: |
| Dense | 1.6608 ± 0.0025 | 58.77% ± 0.11 | 5.26 |
| Codes=512 | 2.2892 ± 0.0789 | 48.85% ± 1.24 | 9.87 |
| Gap | +0.6284 | -9.92 points | 1.88x worse |

All three discrete runs ended with 512 of 512 codes live, so this is not
explained by codebook collapse. The runs are deliberately undertrained at about
0.15x Chinchilla; this is a matched comparison, not a claim about published
TinyStories quality.

### 2. Blind story evaluation reproduces the loss

The preregistered threshold required the dense-minus-discrete 95% interval to
contain zero for grammar and consistency. It did not.

| Criterion | Dense | Discrete | Dense - discrete |
| --- | ---: | ---: | ---: |
| Grammar | 7.00 [6.78, 7.22] | 4.54 [4.27, 4.82] | 2.44 [2.08, 2.79] |
| Consistency | 5.83 [5.58, 6.08] | 3.08 [2.86, 3.30] | 2.72 [2.38, 3.06] |
| Creativity | 4.83 [4.65, 5.02] | 3.61 [3.44, 3.77] | 1.22 [0.97, 1.46] |

The judge preferred the dense completion in 85.4% of 179 pairwise comparisons.
A real-human-text control beat the dense model 93% of the time, while a
dense-vs-dense null returned 0.517 [0.393, 0.638]. The visible failure was
usually referential drift: a kite became a balloon, flag, drum, or trumpet.

### 3. The current learned-parser gate failed

Across seeds 11, 23, and 37, exact held-out graph recovery was 11.5% for the
structured arm versus 0.0% for the matched null. The ledger behaviors required
by the preregistration did not follow:

- execution-equivalent replay: 25.5% structured versus 29.3% null;
- relevant interventions changed predictions 12.2% versus 17.2%, against an 80%
  target;
- unused-field invariance averaged 95.7%, but one seed was 93.2%, below the
  95% per-seed floor;
- both arms reached 100% train-set exact graph and replay accuracy.

This is a three-seed synthetic smoke test over two-node list-operation graphs.
It says nothing directly about Python generation, HumanEval+, a 40M model, or
Qwen. The under-40M run must not start from this result.

## Selected research record

The full record is in experiments/*/FINDINGS.md; each finding links to its
method, controls, and limitations.

| Experiment | Finding |
| --- | --- |
| 01 | An LLM annotator's dependency graph carried no causal information beyond position: rho +0.203 raw and +0.015 after controlling for position. |
| 02 | Committor trajectories were not step-like and retained the position confound. |
| 03 | Step importance decreased with trace depth, then disappeared after conditioning on answer-settledness. |
| 04 | VSA bundling capacity at D=1000 is about 31 items, roughly 3x a literature-summary estimate. |
| 05 | Averaging 10 MiniLM vectors recovered 3; effective dimension was 110 rather than nominal 384. |
| 06 | On a synthetic corpus, the bottleneck reduced top-1 accuracy by about 3 points and improved role prediction by 3.3 points; cross-entropy moved the other way. |
| 07 | On BEIR scifact, realistic averaging reduced recall from 0.877 to 0.619; max-pooling attributed 70–76% of the loss to averaging. |
| 08 | On real text, the 512-code bottleneck increased cross-entropy by 0.63 and reduced accuracy by 9.9 points. |
| 09 | In blind comparisons, the dense model was preferred in 85.4% of pairs; the discrete model mainly lost entity tracking. |
| 13 | Typed legality and public search can multiply performance on generated repair tasks, but the deterministic null often matches full-system correctness. |
| 14 | CPU-only iterative-repair smoke was paused before the planned multi-seed run; it is not repository-level coding. |
| 16 | The EvalPlus 0.3.1 adapter has a local deterministic-pass baseline, but native Windows evaluation is blocked by its POSIX timeout path; no benchmark score is claimed. |

## What the evidence supports

**Observed within the checked-in experiments**

- A 512-code midpoint bottleneck costs substantial TinyStories capability under
  the stated model, data, and training budget.
- Blind story evaluation detects the same quality gap as perplexity.
- Synthetic audits detect the specific bypasses and mutants they were designed
  to test.
- Typed scope and primitive composition can work in bounded symbolic tasks.

**Still proposed or unresolved**

- Whether a trained typed-ledger model can preserve capability.
- Whether its explicit ledger is causally necessary in a learned system.
- Whether the architecture improves coding, systematic generalization, or safety.
- Whether any result transfers beyond the stated data, models, prompts, controls,
  and finite synthetic semantics.

## What actually exists

| Component | Status |
| --- | --- |
| Lexer, diagnostics, AST | Done |
| Grammar and parser | Done, with error recovery and a tree total over input |
| Name resolution | Done, including scopes, two namespaces, and suggestions |
| Type system | Done; the status table reports all four properties, 210 tests passing, and zero warnings |
| Browser playground | Done; the Rust front end is compiled to WebAssembly |
| Typed ledger | First slice: content-addressed sidecar, typed JSON replay receipts, pure constant interpreter |
| Models | A 6.4M toy, a 29.5M TinyStories baseline, and a 512-code variant; none can reason |
| VSA IR and code generation | Not built |
| Learned typed-ledger model | Not built |

Raly tracks vector-space dimension, VSA family, superposition load, and a role
schema. A representative type is:

~~~text
Vec[Concepts; load 3; roles {Subject, Verb, Object}]
~~~

The browser playground can type-check the small pure subset without a local Rust
toolchain:

~~~bash
playground/RUN.bat
python -m http.server -d playground 8000
~~~

Grammar and rationale are in compiler/GRAMMAR.md.

## Claim boundaries and limitations

- The 512-code result uses one codebook size, one transformer family, one
  midpoint insertion point, and a dense control with no matched continuous
  representation. Other designs may behave differently.
- TinyStories is deliberately simple text, and the runs are undertrained.
  Absolute quality is not comparable to published TinyStories numbers.
- Synthetic audits validate the tests against known mutants; they cannot prove
  that a future learned system has no unknown bypass.
- The learned-parser smoke has three seeds and no confidence interval. It does
  not establish Python generation, HumanEval+, Qwen parity, coding capability,
  or safety.
- Experiment 06 used formulaic synthetic text; its smaller gap does not override
  experiment 08 on real text.
- Public benchmark work is planned, not completed. EvalPlus HumanEval+ is a
  benchmark-guided discovery scoreboard with contamination disclosed; MBPP+ is
  the cleaner cross-benchmark check, BigCodeBench-Hard Complete the stretch
  target, and a later time-separated LiveCodeBench slice the freshness audit.
  No public benchmark run is part of this integration.
- Test counts remain attached to their source-specific status records; they are
  not presented here as one consolidated suite total.

## Next falsifiable step

Train the smallest parser that maps paraphrased requirements into ledger graphs
and compare it with a matched flat structured-state baseline. Freeze
semantic-family splits before the run. Evaluate graph and binding recovery,
held-out composition, identifier renaming, declaration permutation,
relevant-state and unused-field interventions, raw-prompt erasure, coverage,
error rate, and abstention.

Downgrade the architecture if the explicit ledger is not causally necessary or
if the matched flat baseline wins on the frozen suite.

## Reproduction

Dependency-free probes:

~~~bash
python experiments/26_no_bypass_causal_audit/causal_audit.py
python experiments/27_ledger_field_steganography/field_audit.py
python experiments/37_scoped_binding_ledger/binding_probe.py
python experiments/54_calibration_shift_probe/calibration_probe.py
python experiments/59_equivalence_aware_split/split_probe.py
python experiments/60_typed_library_novel_composition/library_probe.py
python experiments/63_40m_architecture_budget/architecture_budget.py
~~~

The browser playground is runnable with the commands above. Regenerating model
outputs requires the uncommitted checkpoints and dataset cache described in the
experiment READMEs; committed analysis artifacts remain inspectable without
them.

## Repository map

- compiler/ — Raly compiler workspace, including the wasm crate.
- playground/ — browser playground.
- site/ and web/ — public explanation, landing page, and blind test.
- docs/ — semantics, prior art, and architecture notes.
- experiments/ — experiment code, findings, controls, and reproduction scripts.
- results/ — result artifacts, depending on the experiment.
- preregistrations/ — frozen study plans.
- tools/ — supporting utilities.

The flagship synthesis is in docs/flagship-research-brief.md and the current
plan and risks are in ROADMAP.md.

## Research standards

Claims are measured or cited, confirmatory experiments define failure criteria
in advance, and results are reported with controls and limitations, including
negative results. Promising findings are checked for leakage, confounds, and
simpler explanations before being promoted.

MIT.