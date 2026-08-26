# Ralytable

I think that within a few years you won't be allowed to deploy a model you can't explain, and almost nobody is building for that yet.

**Raly** is a language whose type system understands what a model represents. **Ralytable** is the model built in it. The name is the pitch; a model you can actually relate to, because you can read what it's doing.

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
| Lexer, diagnostics, AST | done, 154 tests, zero warnings |
| Grammar and parser | done, error recovery, total over input |
| Browser playground | done |
| Name resolution, type system, IR, codegen | not built |
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

## What the type system will track

Four things, none of which PyTorch can see: vector space dimension, VSA family, superposition load (`load 3` out of a capacity derived from D), and a role schema (which roles are bound into a vector; the roles are static, the values bound to them are runtime).

```
Vec[Concepts; load 3; roles {Subject, Verb, Object}]
```

The second half is the point. If the type knows which roles are in a vector, the type signature is a description of what the model represents, readable without running it. That is interpretability living in the type system rather than in an archaeology pass over trained weights.

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
| [02](experiments/02_committor/FINDINGS.md) | A negative result on my own idea: committor trajectories are not step-like and inherit the same position confound they were meant to remove. |

## Repo

```
compiler/      the Raly compiler (Rust workspace, 4 crates)
playground/    browser playground, wasm
site/          landing page
docs/          semantics, prior art, compiler architecture, language precedent
experiments/   every experiment, with its findings and the code to reproduce
```

## How I work

Every claim is measured or cited; motivating sentences that sound good and aren't known don't get written. Kill criteria go in before the experiment. Negative results ship, and several of the findings above are negative, which is the point rather than an embarrassment. Anything exciting gets attacked before it gets believed.

MIT.
