# Ralytable

I think that within a few years you won't be allowed to deploy a model you can't explain, and almost nobody is building for that yet.

**Raly** is a language whose type system describes what a model represents. **Ralytable** is the wider model and research project. The name is the pitch: typed and inspectable structure rather than a post-hoc explanation.

Full plan and honest risks: [ROADMAP.md](ROADMAP.md).

## Try it

The compiler runs in your browser. No install, no toolchain.

```
playground/RUN.bat          # Windows, double-click it
python -m http.server -d playground 8000   # anything else
```

That is the real Rust compiler cross-compiled to WebAssembly, 102KB. Type Raly, get live errors with inline squiggles, click a diagnostic to jump to it.

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

The diagnostics are the part I'd point at first:

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

Four things, none of which PyTorch can see: vector space dimension, VSA family, superposition load (`load 3` out of a capacity derived from D), and a role schema (which roles are bound into a vector; the roles are static, the values bound to them are runtime).

```
Vec[Concepts; load 3; roles {Subject, Verb, Object}]
```

The second half is the point. If the type knows which roles are in a vector, the type signature is a description of what the model represents, readable without running it. That is interpretability living in the type system rather than in an archaeology pass over trained weights.

The capacity bound is not a guess; it comes from `experiments/04_capacity`, and where a space declares a measured effective dimension it uses that instead of the nominal one, because `experiments/07_retrieval_cost` showed nominal dimension predicts nothing:

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

Everything here was measured, not cited, and independently re-derived before I believed it.

| | |
|---|---|
| [01](experiments/01_claimed_vs_causal/FINDINGS.md) | An LLM annotator's dependency graph over reasoning traces carries no causal information beyond position. rho +0.203 raw, +0.015 once position is controlled. Structure has to be built in, not requested. |
| [03](experiments/03_position_decay/FINDINGS.md) | The decay of step importance with depth is not a measurement artifact. It vanishes when you condition on how decided the answer already is. Models commit early; the rest is follow through. |
| [04](experiments/04_capacity/FINDINGS.md) | VSA bundling capacity at D=1000 is about 31 items, roughly 3x what a literature summary implied. |
| [05](experiments/05_real_embeddings/FINDINGS.md) | Real embeddings are worse at this than random noise. Average 10 MiniLM sentence vectors and you recover 3. Effective dimension is 110 of a nominal 384, and mean-centring recovers only half. |
| [07](experiments/07_retrieval_cost/FINDINGS.md) | And it costs real accuracy. On BEIR scifact, averaging chunks into document vectors drops recall from 0.877 to 0.619 with realistic grouping, and 70-76% of that loss is the averaging itself rather than coarser granularity, isolated with a max-pooling control. mpnet has twice MiniLM's nominal dimension, the same effective dimension, and the same cost; nominal D predicts nothing. |
| [08](experiments/08_tinystories/FINDINGS.md) | On real text the discrete bottleneck costs 0.63 cross-entropy and 9.9 points of accuracy at matched parameters, three seeds each, non-overlapping intervals. All 512 codes stayed live, so this is the cost of the bottleneck working. It overturns finding 06, which measured a third of that on a synthetic corpus. |
| [09](experiments/09_story_quality/FINDINGS.md) | And the stories are worse to read, not just worse on paper. Blind judging against a threshold committed before any text existed: dense wins 85.4% of pairwise comparisons. The failure is not grammar, it is losing track of what is being talked about. A [blind test](https://ralytable.vercel.app/blind-test.html) lets you try it yourself. |
| [06](experiments/06_discrete_core/FINDINGS.md) | A discrete bottleneck costs about 3 points of top-1 accuracy and buys 3.3 points of role legibility over what the raw character already tells you, at matched parameters. Cross-entropy actually improves, so the two capability metrics disagree and both are real. Bigger alphabets get more capable and more legible together, which is the opposite of the tradeoff I expected. |
| [02](experiments/02_committor/FINDINGS.md) | A negative result on my own idea: committor trajectories are not step-like and inherit the same position confound they were meant to remove. |
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

## What's next

1. **Break the label/state shortcut.** Test independently specified tasks where executable state is necessary but not sufficient, with a held-out verifier and no supplied answer bit.
2. **Test richer Python and repository-local repair.** Keep raw learned, verified full-system, symbolic, and deterministic-null results separate.
3. **Look inside the codebook.** I measured that codes carry role information and never looked at what any single code responds to.
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

## How I work

Every claim is measured or cited; motivating sentences that sound good and aren't known don't get written. Kill criteria go in before the experiment. Negative results ship, and several of the findings above are negative, which is the point rather than an embarrassment. Anything exciting gets attacked before it gets believed.

MIT.
