# Language design precedent for a VSA / differentiable-logic DSL

Scope: what comparable languages got right and wrong, gathered as input to a design decision, not as a design.
Sourcing note: items marked **[searched]** were verified against the web during this write-up; everything else is
from training knowledge and should be re-checked before it becomes load-bearing.

## 1. What existing array/ML languages get right and wrong

**Dex** ([repo](https://github.com/google-research/dex-lang), [Getting to the Point, ICFP 2021](https://arxiv.org/abs/2104.05372))
is the closest precedent and the one to study hardest. Its central move: an array is not "a shape" but an
*eagerly-memoized function from a typed index set to values*, written `n=>Float`. Index sets are ordinary types —
`Fin 10`, a record, a sum, a user-defined enum — so `for i:Layer. ...` type-checks because `Layer` is a type, not
because 12 == 12. Two consequences matter here. (i) Nominal index sets kill exactly the class of bug the brief
names: a hypervector indexed by `Slot` cannot be silently unbound with a key indexed by `Role`, even at identical
width. That is the mechanism to steal — *distinct nominal index types per representation family and per role
space*, not integer shapes with a side-channel of assertions. (ii) Dex's indexing is *pointful*: you write
elementwise code with names and the compiler recovers parallelism, aided by an accumulation effect that lets
reverse-mode AD of in-place updates preserve parallelism **[searched: ICFP paper abstract]**. Readability without
surrendering performance is precisely the auditability requirement.
What to avoid from Dex: it still carries the banner "an experimental research project at an early stage of
development. Expect monstrous bugs and razor-sharp edges", at ~1.7k stars after several years **[searched: repo
front page; not archived]**. A bespoke Haskell-hosted compiler with its own effect system, own AD, own backend and
own notebook UI is why. The idea won; the delivery vehicle did not.

**APL / J / BQN.** Rank polymorphism is the right generalisation of broadcasting: a function declares the rank of
the cells it consumes and the framework handles the frame. Steal the concept — `bind`/`bundle`/`permute` declare
they act on rank-0 hypervectors, and mapping over a batch is a framework operation, never a hand-written axis
index. Avoid tacit point-free style: in J and BQN it makes programs unreadable to everyone but the author, which
directly contradicts an auditability goal.

**Futhark.** Proof that a small team can ship a *narrow* purely-functional array language with a real GPU backend
and real users by refusing scope. Its size-typed arrays (`[n]f32`, with existential sizes at function boundaries)
are the pragmatic middle: enough dependency to catch mismatch, deliberately not full dependent types. The mistake
to note: no host ecosystem — every Futhark program sits behind an FFI boundary, which is exactly the tax a
standalone language pays forever.

**JAX as an embedded DSL.** The reusable lesson is *trace to a small typed IR* (the jaxpr) and expose composable
transforms (`grad`, `vmap`, `jit`); a DSL with its own semantics that inherits Python's ecosystem free. The wrong
part is that the embedding leaks: shape errors surface as tracer errors deep inside a transform stack, Python
control flow silently vanishes, and `jax.numpy` has no vocabulary for "these two axes are different kinds of
thing".

**Halide / TVM.** Algorithm/schedule separation is the most portable idea in the list — one source of truth for
*what*, tuned separately for *how*. Our analogue: the VSA program (roles, bindings, bundles) separate from the
realisation (binary / bipolar / HRR / FHRR, dimension, block sparsity). Halide's failure mode is that schedules
became an expert-only second language and autoscheduling had to be retrofitted for years. If we split, the default
realisation must be inferable.

**Triton.** Succeeded because it was a Python decorator over a familiar mental model (a block of a tensor) and paid
for itself immediately in kernel speed. Confirms the adoption rule: traction follows a concrete day-one win, not
conceptual elegance.

## 2. Shape and unit typing: what works versus what is merely elegant

Ranked by bugs-caught per unit of annotation burden, the only ranking that matters:

- **Nominal index sets (Dex) / size types (Futhark)** — works. Cheap to write, checked at boundaries, no proof
  obligations on the user.
- **Units of measure (F#)** — the strongest evidence in this survey. F# gives erased, *inferred* units
  (`1.0<m/s>`), zero runtime cost, essentially no annotation burden beyond literals, and people genuinely use it.
  VSA representation families (bipolar vs complex-phase vs sparse-block) are structurally identical to units: a
  closed tag set, where binding multiplies tags and bundling requires equality. Copy F#'s model *including
  inference*. Do not copy Fortress's units, which arrived bundled with an unusable research language and died
  with it.
- **Refinement types with an SMT backend (LiquidHaskell, F\*)** — the right tool for numeric side conditions,
  which is exactly where "capacity overflow when bundling k items" lives: `k <= capacity(D, family)` is a linear
  constraint an SMT solver dispatches instantly. This is the one place worth spending real type-system budget.
- **Full dependent types (Idris 2, Agda, Lean)** — elegant, and in practice a tax nobody outside the authors
  pays. Published dependently typed neural-network demos reliably stall at the point where you must prove
  `n + 0 = n`. Reject for user-facing code; acceptable only if a Lean/Idris model is a specification artifact.
- **Python's attempts** — honest ranking: `jaxtyping` works and is widely used *because* it is runtime checking
  with value-level dimension variables. Its own FAQ states that it deliberately does not build on PEP 646 because
  static checking "still isn't yet practical" — the static system cannot express concatenation, stacking or
  broadcasting **[searched: docs.kidger.site/jaxtyping/faq]**. `torchtyping` was superseded by jaxtyping by the
  same author. PEP 646 is implemented in Pyright and Pyre **[searched]**, and nobody ships shape safety on it.

Conclusion: a *closed, nominal, inferred* tag system (family + role space) plus sizes as type-level naturals plus
SMT-checked capacity refinements — and nothing above that line. A type system nobody can write in is a failed type
system, and the failure is always at the point where the user must supply a proof.

## 3. Embedded versus standalone

Standalone successes: Futhark and Halide (in both cases owning the backend *was* the product); Dex
intellectually, not in adoption. Standalone failure, best-funded case: Swift for TensorFlow, archived February
2021 despite having shipped language-level differentiable programming and a 30+ model garden — the AD work
survived into the Swift compiler, the ecosystem did not **[searched: github.com/tensorflow/swift, InfoWorld]**.
Embedded successes: JAX, Triton, `torch.compile`/Dynamo, Numba.

The asymmetry is stark. In the ML/array space over the last decade, essentially every DSL that got users was
embedded in a host people already ran, and essentially every one demanding a new toolchain either died or stayed a
paper. Standalone costs are cumulative and unglamorous: parser, good error messages, LSP, formatter, package
manager, notebook integration — and, decisively, your own autodiff and numerics, or an FFI boundary tax anyway.
For a very small team that is 12–24 months before the first interesting VSA experiment runs.

The hybrid worth taking: an **embedded surface with a real IR we own**. Programs are host values that construct an
explicit typed AST; type, family and capacity checking run over that AST in *our* checker rather than the host's
type system; the checked IR lowers to JAX. This buys ecosystem and autodiff, keeps error messages ours (so they
can be good, which is half the value proposition), and leaves the door open to a standalone parser later that
targets the same IR. The IR is the asset; the syntax is not.

## 4. Autodiff through non-standard primitives

Mechanics that exist and work today:

- **`jax.custom_vjp` / `jax.custom_jvp`** — register forward and backward rules for any primitive. This is the
  standard route for our case: `bind`, `bundle`, `permute`, `unbind`, `cleanup` become primitives with
  hand-written VJPs. For binding as elementwise product or circular convolution the VJP is a two-line expression;
  for permutation it is the inverse permutation. PyTorch's `autograd.Function` is the equivalent.
- **Straight-through estimators** for the discrete parts (sign, threshold, quantise-to-bipolar):
  `x + stop_gradient(quantize(x) - x)`, optionally with a clipped hard-tanh surrogate to avoid gradient blow-up
  outside the linear region. Adjacent: Gumbel-Softmax for discrete choice, and the differentiable-logic line
  (t-norm / probabilistic relaxations of AND-OR, `difflogic`) where logic gates become smooth and trainable.
- **Language-level AD** (Dex, Swift, Zygote, Enzyme) — a research project each time.

Cheapest realistic path, unambiguously: **do not implement autodiff.** Lower the IR to JAX primitives, register
custom VJPs per VSA op, inherit `grad`/`vmap`/`jit`/GPU/TPU. Record the chosen relaxation per op in the IR so an
audit can see which surrogate produced which gradient. Enzyme (LLVM-level, language-agnostic) is the only credible
way to get AD without writing it outside a Python framework.

## 5. Rust specifically

Blunt: Rust is a good *runtime* and a mediocre *autodiff host* today. `burn` is the most complete — its own
autodiff backend plus several compute backends, actively developed — but adopting it means adopting burn's tensor
abstraction, which is the very abstraction we are trying to escape. `candle` is inference-first with thin training
ergonomics. `dfdx` pioneered const-generic compile-time shape checking and is typographically the closest existing
thing to what we want, but has been effectively stalled. Enzyme-based `std::autodiff` is landing as a nightly-only
intrinsic and `#[autodiff]` macro **[searched: doc.rust-lang.org unstable-book, rust-lang/compiler-team#611]** —
real progress, but nightly, LLVM-coupled, and not something to bet a small team's first year on. Cost of
Rust-only: either accept burn's opinions or write reverse-mode AD from scratch, which is a multi-month project
before any VSA research happens. Sensible use of Rust: the checker/compiler and fast CPU hypervector kernels, with
JAX supplying gradients.

## 6. Lessons from failed DSLs

- **Tensor Comprehensions** (Facebook, 2018). Beautiful Einstein-notation surface, polyhedral compilation plus
  autotuning. Compile times ran minutes to hours, the autotuner was fragile, generated kernels frequently lost to
  cuDNN, and it was a research artifact with no product owner. Cause of death: *no immediate win over the
  incumbent, plus maintainer departure*.
- **PlaidML.** Technically sound; it tied its on-ramp to being a Keras backend, and when Keras dropped
  multi-backend support the on-ramp evaporated, while Intel's priorities moved to nGraph and then elsewhere
  **[searched: Wikipedia, plaidml issue tracker]**. Cause of death: *depending on someone else's extension point*.
- **Swift for TensorFlow.** The best-funded example, and it still shut down: users had to leave Python's ecosystem
  to get benefits they did not experience as urgent, Linux tooling was rough, and Google reallocated
  **[searched]**.

The pattern is consistent and it is not about language design. These projects die of (a) no ecosystem on-ramp,
(b) no day-one win over what people already use, (c) a one-or-two-person bus factor with no product owner.
Elegance appears nowhere among the causes; nor, notably, does inelegance.

## The three decisions this forces, and my recommendation on each

**1. Embedded versus standalone → embedded in Python, with our own typed IR and our own checker, lowering to
JAX.** Not "a Python library with nice classes": an explicit AST we own, so that errors, capacity checking and
audit rendering are ours, while ecosystem, accelerators and gradients are free. Keep a standalone parser as a
possible later frontend onto the same IR if the notation ever earns it. Rust, if used at all, is a kernel and
checker component, not the host.

**2. Type system ambition → deliberately mid.** Exactly three mechanisms: (i) nominal representation-family and
role-space tags in the style of F# units of measure, *inferred* rather than annotated; (ii) sizes as type-level
naturals à la Futhark, existential at function boundaries; (iii) SMT-checked refinements for bundle capacity and
unbind-key provenance. No full dependent types, no user-supplied proofs. Checking runs at IR-construction time —
before any array is allocated — rather than in Python's static type checker, because jaxtyping's own experience
says static Python cannot carry this.

**3. Autodiff → inherit it.** Lower every primitive to JAX with `custom_vjp`; straight-through and t-norm
surrogates for discrete ops, chosen per-op and recorded in the IR. Writing our own AD is the single most reliable
way to spend a year and ship nothing.

Risk to manage, taken directly from section 6: there must be a VSA experiment that is visibly easier and safer in
this DSL than in fifty lines of `jax.numpy`, demonstrable within the first month. Without that, the project has no
on-ramp, and on-ramps are what these projects die of.
