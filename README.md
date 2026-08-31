# Ralytable

Ralytable is a research project about building models with typed, inspectable intermediate state. **Raly** is the experimental language and compiler used to describe that state.

The central question is whether making a model's internal structure explicit can make its computation easier to inspect without giving up too much capability. That has not been established. The current discrete model performed worse than its matched dense control, and the compiler can type-check programs but cannot run them yet.

See [ROADMAP.md](ROADMAP.md) for the current plan, open questions, and risks.

## Try it

The compiler runs in a browser and does not require a local Rust toolchain.

```
playground/RUN.bat          # Windows, double-click it
python -m http.server -d playground 8000   # anything else
```

The playground uses the same Rust front end as the command-line tool, compiled to WebAssembly. It checks Raly as you type, underlines errors, and lets you jump from a diagnostic to the relevant source.

## What actually exists

| | status |
|---|---|
| Lexer, diagnostics, AST | done |
| Grammar and parser | done, error recovery, tree total over input |
| Browser playground | done |
| Name resolution | done, scopes, two namespaces, suggestions |
| Type system | done, all four properties, 198 tests, zero warnings |
| Models | a 6.4M toy plus a 29.5M TinyStories baseline and 512-code variant; none can reason |
| IR, codegen | not built |
| The model | not built |

Here is a representative diagnostic:

```
error[RALY1002]: unterminated string literal
 --> examples/broken.raly:2:20
  |
2 |     let greeting = "hello
  |                    ^ this string is never closed
 ::: examples/broken.raly:2:26
  |
2 |     let greeting = "hello
  |                          - the line ends here, still inside the string
  |
  = note: Raly string literals may not span multiple lines
  = help: add a closing `"` before the end of the line
```

## What the type system tracks

Raly tracks four properties that a tensor shape alone does not express: vector-space dimension, VSA family, superposition load (`load 3` against a capacity derived from the dimension), and a role schema. Roles are known at compile time; the values bound to them are supplied at runtime.

```
Vec[Concepts; load 3; roles {Subject, Verb, Object}]
```

If a type records which roles are present, a function signature can describe part of what a vector represents without running the program. The research question is whether this kind of declared structure can remain useful and causally important in a capable learned model.

The capacity bound comes from `experiments/04_capacity`. When a space declares a measured effective dimension, Raly uses that value instead of the nominal dimension. In `experiments/07_retrieval_cost`, nominal dimension did not predict the measured retrieval cost:

```
error[RALY5001]: this bundles 4 items into a space that holds 3
 --> capacity-effective.raly:7:5
  |
7 |     bundle(a, b, c, d)
  |     ^^^^^^^^^^^^^^^^^^ 4 items superposed here
 ::: capacity-effective.raly:4:1
  |
4 | space Sentences = MAP[384] where effective = 111
  | ------- `Sentences` holds 3 items (from its measured effective dimension 111, not its nominal one)
  |
  = note: past capacity, cleanup returns the wrong atom and accuracy degrades
          towards chance without anything failing at run time
  = help: superpose fewer items, or declare `Sentences` at dimension 147
```

Grammar and rationale: [compiler/GRAMMAR.md](compiler/GRAMMAR.md).

## Findings

These are results from experiments in this repository. Each finding links to its methods, controls, and limitations.

| | |
|---|---|
| [01](experiments/01_claimed_vs_causal/FINDINGS.md) | In this experiment, an LLM annotator's dependency graph over reasoning traces carried no causal information beyond position: rho +0.203 raw and +0.015 after controlling for position. |
| [03](experiments/03_position_decay/FINDINGS.md) | Step importance decreased with trace depth, but the effect disappeared after conditioning on how settled the answer already was. |
| [04](experiments/04_capacity/FINDINGS.md) | VSA bundling capacity at D=1000 is about 31 items, roughly 3x what a literature summary implied. |
| [05](experiments/05_real_embeddings/FINDINGS.md) | Averaging 10 MiniLM sentence vectors allowed recovery of 3. The measured effective dimension was 110 rather than the nominal 384, and mean-centring recovered about half of the gap. |
| [07](experiments/07_retrieval_cost/FINDINGS.md) | On BEIR scifact, averaging chunks into document vectors reduced recall from 0.877 to 0.619 with realistic grouping. A max-pooling control attributed 70–76% of the loss to averaging rather than coarser granularity. mpnet had twice MiniLM's nominal dimension but similar effective dimension and cost. |
| [08](experiments/08_tinystories/FINDINGS.md) | On real text, the discrete bottleneck increased cross-entropy by 0.63 and reduced accuracy by 9.9 points at matched parameter counts, with three seeds per model and non-overlapping intervals. All 512 codes remained active. This supersedes finding 06's smaller estimate from a synthetic corpus. |
| [09](experiments/09_story_quality/FINDINGS.md) | In blind comparisons, the dense model was preferred in 85.4% of pairs. The discrete model's main visible failure was losing track of entities across a story. You can inspect the same samples in the [blind test](https://ralytable.vercel.app/blind-test.html). |
| [06](experiments/06_discrete_core/FINDINGS.md) | On a synthetic corpus, a discrete bottleneck reduced top-1 accuracy by about 3 points and improved role prediction by 3.3 points beyond the raw-character baseline at matched parameter counts. Cross-entropy moved in the other direction, so the capability metrics disagreed. |
| [02](experiments/02_committor/FINDINGS.md) | Committor trajectories were not step-like and retained the position confound the metric was intended to remove. |
| [13](experiments/13_autoresearch_raly_coder/FINDINGS.md) | Typed legality and public search can multiply performance on generated repair tasks, but the deterministic null often matches full-system correctness. A state-only controller is causally load-bearing in a synthetic control; the two-parameter predicate gates are supplied-bit routing, not semantic inference. |
| [14](experiments/14_iterative_repo_repair/PAUSED_HANDOFF.md) | CPU-only smoke of file-backed iterative repair; paused before the planned multi-seed run. It remains a generated micro-repository control, not repository-level coding. |
| [16](experiments/16_humaneval_plus_baseline/README.md) | Official EvalPlus 0.3.1 HumanEval+ adapter and local deterministic-pass baseline. Native Windows evaluation is blocked by EvalPlus's POSIX timeout path; no benchmark score is claimed. |

## Repo

```
compiler/      the Raly compiler (7 crates in the workspace, plus a wasm crate)
playground/    browser playground, wasm
site/          landing page
docs/          semantics, prior art, compiler architecture, language precedent
experiments/   every experiment, with its findings and the code to reproduce
```

## Current priorities

1. **Break the label/state shortcut.** Test independently specified tasks where executable state is necessary but not sufficient, with a held-out verifier and no supplied answer bit.
2. **Test richer Python and repository-local repair.** Keep raw learned, verified full-system, symbolic, and deterministic-null results separate.
3. **Inspect individual codes.** The current measurements show that codes carry some role information, but individual codes have not been characterized systematically.
4. **Phase 2 properly:** more seeds, real text, a matched continuous control, and more than one architecture family.
5. **An IR and a backend**, so Raly programs run rather than only type-check.

The explicit public destination is a coding-benchmark ladder. EvalPlus HumanEval+
is the benchmark-guided discovery scoreboard: task-level failures may be inspected
and optimized against, with that contamination disclosed, so its tuned score is not
held-out evidence. EvalPlus MBPP+ is the cleaner cross-benchmark generalization
check; BigCodeBench-Hard Complete is the practical stretch target; and a later,
time-separated LiveCodeBench slice is the freshness audit. Autoresearch development
uses separate frozen local proxy tasks, and public prompts/solutions never enter
training. Before any run, preregister <=9M learned parameters, raw-controller versus
full-system scores, search/test-time budget, separate latency fields, and the
deterministic-null comparison. No public benchmark run or result is part of this
integration.

Full plan in [ROADMAP.md](ROADMAP.md).

## Research standards

Claims are measured or cited, and confirmatory experiments define their failure criteria in advance. Results are reported with their controls and limitations, including negative results. Promising findings are checked for leakage, confounds, and simpler explanations before being promoted.

MIT.
