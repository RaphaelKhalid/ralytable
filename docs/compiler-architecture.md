# Compiler Architecture for Raly: Decisions Expensive to Reverse

`Raly`: a standalone language (own lexer/parser/typechecker/IR, in Rust) over VSA primitives (bind / bundle / permute / unbind / cleanup) plus differentiable discrete-logic ops, with a type system tracking **dimension**, **VSA family**, **superposition load/capacity**, and **role schema**. Where the answer is "that's a cathedral", it says so.

## 1. Query-based / incremental architecture

A demand-driven compiler replaces ordered passes with memoised functions — `type_of` calls `hir_of` calls `parse` — recording dependency edges taken and re-validating lazily via red/green marking with early cutoff. rustc has one but [does **not** use salsa](https://rustc-dev-guide.rust-lang.org/queries/salsa.html); salsa was extracted for the IDE case (rust-analyzer, Astral's `ty`).

Costs exceed the advertising. Matsakis, its author, says the bulk of the work is "figuring out how to introduce effective early cutoff shields and prevent volatile details from sneaking in" ([babysteps](https://smallcultfollowing.com/babysteps/blog/2019/01/29/salsa-incremental-recompilation/)) — the engine is easy, decomposing your compiler is not. Overhead scales with **graph size, not edit size**: rust-analyzer found even a no-op edit traverses the whole graph, ~300ms just validating stdlib queries, hence manual `Durability` tuning ([Durable Incrementality](https://rust-analyzer.github.io/blog/2023/07/24/durable-incrementality.html)). The migration itself caused a **4.3x regression** ([#19404](https://github.com/rust-lang/rust-analyzer/issues/19404)). Cycles **panic by default**, so recursive queries need explicit fixed-point annotations. The API has churned through three incompatible generations; 0.28.x still self-describes as *experimental*.

Decisively: in August 2026 matklad, author of rust-analyzer, argued salsa is over-applied *even there* ([Rust Glancer](https://matklad.github.io/2026/08/21/rust-glancer.html)). His distinction is the one that matters — **incrementality (track updates over time) vs. laziness (defer computation)**; it is laziness, not incrementality, that makes an IDE fast.

**Recommendation: no salsa on day one — over-engineering at this scale.** Adopt its *shape*, which is free: every phase a pure `fn(&Db, Input) -> Output`, no ambient mutable state. That is salsa's required signature, so a later port is mechanical.

**Are passes a mistake?** Nothing single replaced them: queries, immutable-tree-plus-snapshot (Roslyn, TypeScript), and e-graph mid-ends that dissolve *pass ordering* (Cranelift) coexist. For a batch compiler with fixed lowering order an ordered pipeline is fine. What is fatal is **side-effecting passes over mutable global state**. Keep passes; make them pure.

## 2. IR design, MLIR, SSA, e-graphs

**Build our own IR.** MLIR's dialect + progressive-lowering model is conceptually right; adopting the codebase is another matter. Extensibility is realised as C++ classes and TableGen, so a custom dialect means **writing your compiler in C++**. Rust doesn't rescue you: melior's README calls itself "still in the alpha stage", unstable, and admits "some part of the current API is not" type safe ([melior](https://github.com/mlir-rs/melior)); bindings generate against installed LLVM headers, pinning an LLVM version into your build. The C API is fine for *emitting into* existing dialects, poor for *defining your own* — our only reason to want it.

The strongest testimony is Lattner's. In [Democratizing AI Compute, Part 8](https://www.modular.com/blog/democratizing-ai-compute-part-8-what-about-the-mlir-compiler-infrastructure) he describes an "explosion" of AI dialects landing without ownership, says "the once-unified vision for MLIR began to splinter", and concedes no downstream implementation on those dialects "matches CUDA's performance for GenAI LLMs on NVIDIA GPUs." His lesson — scaling "before the core foundations are fully settled... can cause lasting problems" — is our situation exactly. Mojo adopted hard but Modular *owns* MLIR expertise; **TVM** built its own because Relay and MLIR dialects "represent dynamic dimensions as unknown and do not track dynamic shape relations" ([Relax](https://arxiv.org/pdf/2311.02103)). Raly's thesis is tracking exactly what MLIR's tensor dialects discard.

**SSA: yes.** RVSDG and sea-of-nodes are not alternatives — both *build on* SSA. Keep a **typed mid-level IR above the backend** where dimension/family/load/roles survive, and lower late. LLVM is the cautionary tale: its semantics could not justify GVN or loop unswitching because it had *two* forms of deferred UB ([PLDI 2017](https://users.cs.utah.edu/~regehr/papers/undef-pldi17.pdf)); `undef` removal was still ongoing in 2025. **IR semantics is a specification obligation; write it down before the optimiser.**

**E-graphs: right instinct, wrong reason.** The property cited as the good fit is the documented worst case. Commutativity plus associativity, per egg's own maintainers, lets the system rearrange arbitrarily large sums, "resulting in an infinite number of e-classes and causing equality saturation to loop infinitely" ([egg #60](https://github.com/egraphs-good/egg/discussions/60)); commutativity alone generates n! orderings. TENSAT, our closest analogue, won real gains but had to **cap multi-pattern rules at one or two iterations** because they "rapidly explode the e-graph".

The fix is **canonicalise, don't axiomatise**: represent bind as a variadic node over a *sorted multiset*. Associativity becomes flattening, commutativity sorting, unbind-as-inverse cancellation in the smart constructor — both laws structurally true at zero e-graph cost. That choice is worth more than any solver. For a rewrite mid-end later, copy **Cranelift's ægraph**: acyclic, built during a linear pass, trading saturation for bounded cost; it eliminated Cranelift's pass-ordering problem and gets GVN, LICM and rematerialisation free ([Fallin, 2026](https://cfallin.org/blog/2026/04/09/aegraph/)). v0.3, not v0.1.

## 3. Error quality and recovery

Four prerequisites, all cheap now and ruinous to retrofit.

**Error nodes in the tree.** rust-analyzer treats the syntax tree as dynamically typed with error nodes as first-class members. Roc names the philosophy in its compiler source — nodes inserted on semantic errors so it "continues compilation following the 'inform don't block' philosophy" — with the node holding an *index into a diagnostic arena*, not a message. There is no *absent* node, only an explicit malformed one, so downstream stages must branch rather than crash. Have the parser emit an **event stream** rather than building a tree directly, and return `(Tree, Vec<Diagnostic>)` — never `Result<Tree, Error>`.

**Diagnostics as data, not strings.** Elm's `Report { title, region, suggestions, message: Doc }` has three backends — ANSI, string, JSON — so `--report=json` hands editors the same document the terminal gets. rustc adds the key refinement: every suggestion carries an **`Applicability`** marking whether it is mechanically applicable — the precondition for auto-fixes.

**Constraint-based inference with per-constraint provenance.** This decides whether errors point at the right place. Haskell's and ML's failure is Algorithm W's *unification order*: it blames wherever unification happened to fail — typically the last site touched, not the mistake. Helium's fix is forty years old: split inference into **generating, ordering, and solving** constraints over a type graph, attach a message and blame provenance to each, then use heuristics to pick which to remove and hence which expression to blame ([Heeren, Hage & Swierstra](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/helium.pdf)). We don't need the later MaxSMT-style ranking — we need the **separation**, plus a `provenance: Span + Reason` field on every constraint from commit one. Czaplicki, having done this in Elm, reports it "required no significant changes to the type inference algorithm and imposed no noticeable performance cost."

**Filter relevance before rendering; suppress cascades.** Once a node is `Error`-typed it unifies with everything and reports nothing further. Note the ordering separating Elm from TypeScript: Elm diffs types structurally *then* prints, showing a large type with the bad part highlighted; TypeScript prints then truncates blindly, losing "relevant properties that will be subsequently elaborated on" ([#42597](https://github.com/microsoft/TypeScript/issues/42597)). Worse, its `DiagnosticMessageChain` links carry no spans, so nested chains are trees of strings an IDE cannot make clickable.

**Why C++/Haskell errors are bad — avoidable?** Yes; the cause is late checking. C++ templates were unrestricted duck typing checked at *instantiation*, deep in a call chain the user never wrote. C++20 concepts help measurably (Lemire: 55 lines of Clang error → 13) but are **opt-in**, and much of the STL stays unconstrained. **Generic bounds must be mandatory and definition-site checked.** Haskell's is the blame-localisation problem above.

## 4. Type system implementation

The four properties are *not* one problem; the worst available mistake is one mechanism for all four. **No full dependent types** — nothing here requires proofs about values; you'd be building a proof assistant.

**No SMT-backed refinement types.** The strongest negative here, because the failure mode attacks the product. The Liquid Haskell real-world report concedes that "since SMT is nonconstructive by design, new theorem proving techniques may need to be... developed in order to generate readable error messages" ([Vazou et al.](https://goto.ucsd.edu/~nvazou/real_world_liquid.pdf)). An unsat core is not an explanation, and solver instability is the second killer — the same program compiles today and times out tomorrow. A language pitched on explaining silent bugs cannot answer "why?" with a timeout.

**Instead: algebraic types plus four small decidable solvers.**

- **Dimension** has an exact precedent: Kennedy's units of measure. Dimensions form a **free abelian group**; unification reduces to linear Diophantine constraints over integer exponents, composes with Hindley–Milner, and is **decidable with principal types preserved** ([Gundry](https://adam.gundry.co.uk/pub/units-of-measure/unit-inference-2011-06-24.pdf)). Shipped in F# 2.0. Failures print as a concrete residual equation.
- **VSA family** is a finite enum — ordinary HM unification over a nullary constructor. Explicit coercions only.
- **Capacity/load** ("holds 3 of 31") is where to be most conservative: a natural-number term with `+` and constants plus interval bounds — a tiny abstract-interpretation lattice, not an arithmetic theory. Follow **Futhark's** compromise: sizes there are "a restricted subset of a proper dependent type system", existentials deliberately not dependent pairs "to keep the language simple", and where the checker can't see through it you insert an **explicit coercion** ([Futhark](https://futhark-lang.org/blog/2023-05-12-size-type-challenges.html)). A checked coercion with a good message beats a solver that sometimes answers.
- **Role schema** — a set of labels — wants **row polymorphism**, specifically Leijen's [scoped labels](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/scopedlabels.pdf): a fully orthogonal extension to Hindley–Milner where permitting duplicate labels makes it *simpler* than other record systems — a bonus, since binding a role twice is meaningful in VSA rather than an error. `bind` extends a row, `unbind` restricts it; you get "any vector that at least has role `subject`" free, and errors that name the missing label.

**From Dex, steal two things:** arrays as functions over *typed index sets* ([ICFP 2021](https://arxiv.org/pdf/2104.05372)) — for us, a role is a type, not a string key; and its **effects/linearity discipline for autodiff**, where an associative accumulation effect lets reverse-mode AD of in-place updates preserve parallelism. Not its ambition; it wound down. Keep AD a defined transformation on the typed mid-level IR, with types stating which ops are differentiable. Swift for TensorFlow is the warning: its autodiff was good and survived, but [the project was archived](https://github.com/tensorflow/swift) — governance killed it, not the type theory. Keep the lowering boundary narrow and replaceable.

## 5. Failure modes, and the lesson each

**rustc compile times.** Recent wins came from **memory traffic and defaults**, not algorithms: shrinking the AST expression node 72→64 bytes (one cache line) gave 10%+ on some benchmarks; **lld as default linker** cut 30%+ off several ([Nethercote](https://nnethercote.github.io/2026/07/31/how-to-speed-up-the-rust-compiler-in-july-2026.html)). The structural cost is monomorphisation — huge volumes of unoptimised LLVM IR per instantiation, which is why MIR (a *pre-monomorphisation* IR) exists. **Avoidable:** monomorphisation-by-default, crate-as-compilation-unit. **Lesson:** size IR nodes deliberately, optimise pre-instantiation, keep compilation units small.

**LLVM as IR.** Two forms of deferred UB was one too many, and it has no notion of parallelism. **Lesson:** never let your only IR be the lowest one.

**Swift's exponential type checker.** Overload sets become **disjunction constraints** and the solver searches their product: 17 stdlib overloads of `+`, 9 types conforming to `ExpressibleByStringLiteral`, literal defaulting making even `1 + 2` a disjunction. About **six disjunctions in one expression** trips "expression too complex" ([Hooper](https://danielchasehooper.com/posts/why-swift-is-slow/)). The [2025 roadmap](https://forums.swift.org/t/roadmap-for-improving-the-type-checker/82952) does *not* aim for polynomial, only for heuristics so the exponential appears "with pathological examples" — a decade on, Apple cannot fix the complexity class. **Lesson, the sharpest here: do not combine unrestricted operator overloading + protocol-based literal defaulting + implicit conversions + full bidirectional inference. Pick at most two.** For Raly: no implicit conversions, locally-resolved literal defaulting, annotations at function boundaries.

**C++ templates.** Late instantiation-site checking, partly mitigated by opt-in concepts. **Lesson:** definition-site bounds, mandatory.

**TypeScript soundness.** An explicit **non-goal**: soundness is traded to "strike a balance between correctness and productivity" ([design goals](https://github.com/microsoft/TypeScript-wiki/blob/main/TypeScript-Design-Goals.md)), with bivariant method parameters defended as "unsound, but useful and common." Partly retracted: `strictFunctionTypes` fixed standalone functions but left methods bivariant forever, since fixing them would break `Array<T>`. **Lesson:** that unsoundness is a JavaScript-interop tax. We have no legacy corpus and no excuse. What kills you is unsoundness you cannot enumerate.

## 6. Rust implementation stack

- **AST: arena + index, not `Box`/`Rc`** — `Copy` handles, side tables, no lifetime infection, no recursive-drop overflow. `la-arena` or hand-rolled `Idx<T>`; `bumpalo` for in-pass scratch only.
- **Interning:** `lasso`, or ~60 lines of matklad-style `Symbol` — worth rolling yourself to control the `Debug` impl, which dominates snapshot readability.
- **Parsing: hand-written recursive descent + Pratt, `logos` for lexing.** The 2026 evidence is one-directional: Ruff **migrated away from a generated parser to hand-written recursive descent** in v0.4.0 for control, recovery and speed ([Astral](https://astral.sh/blog/ruff-v0.4.0)); rustc, rust-analyzer, Clang, GCC, V8 and Roslyn are all hand-written. `chumsky` is still `1.0.0-alpha` after years, labelled "minimal maintenance", and its nested combinator types cause exactly the §5 monomorphisation bloat in *your* build.
- **CST: not yet.** `rowan`/`cstree` earn their cost with a formatter, refactorings or an IDE — matklad calls incremental reparsing "the 1% use case". Until then a typed AST with `text-size` spans is right; just **separate the parser from the tree it builds**.
- **Rendering:** `annotate-snippets` (rust-lang-owned, what rustc is migrating to) — never couple your internal `Diagnostic` type to a renderer.
- **Testing: rustc-style UI tests** — `.raly` files each with a golden `.stderr`, blessed with a flag. The enforcement mechanism for §3: every diagnostics regression becomes a reviewable diff. `libtest-mimic` plus **`insta`**; fuzz that the parser never panics and every diagnostic has a valid span.

```toml
logos = "0.15"; text-size = "1"; la-arena = "0.3"; indexmap = "2"
lasso = "0.7"; annotate-snippets = "0.12"
# dev: insta, expect-test, libtest-mimic, cargo-fuzz + arbitrary
# deferred: salsa, rowan/cstree, tree-sitter, egg/egglog
```

## THE FIVE DECISIONS, AND MY RECOMMENDATION ON EACH

**1. No salsa; pure `fn(&Db, Input) -> Output` phases with coarse invalidation.**
Salsa's overhead scales with graph size not edit size (a 4.3x regression on rust-analyzer's migration), and matklad now calls it over-applied even there — while pure phases cost nothing and are exactly salsa's required shape.
*Reversal: **low if phases stay pure, catastrophic if not.*** The irreversible part is ambient mutable state — decided implicitly on day one.

**2. Own IR — SSA, typed, above the backend — not MLIR.**
A custom dialect means writing the compiler in C++ (melior is alpha and self-admittedly not fully type-safe), Lattner concedes the AI-dialect layer fragmented, and TVM's stated reason for building its own — MLIR dialects not tracking shape relations — is our value proposition being discarded.
*Reversal: **high; the second-most expensive call here.*** An MLIR emission backend can be added later; rebuilding semantics on someone else's dialects is a rewrite. Mitigate by keeping the autodiff-runtime lowering boundary narrow.

**3. Canonicalise the VSA algebra structurally; defer e-graphs to v0.3, preferring Cranelift-style ægraphs to egg-to-saturation.**
Commutativity + associativity is the documented worst case for equality saturation — egg's maintainers describe infinite e-classes; TENSAT capped multi-pattern rules to avoid explosion. A variadic node over a *sorted multiset* makes both laws structurally true at zero cost.
*Reversal: **medium for the optimiser, high for the representation.*** An e-graph mid-end is additive later; changing how bind is represented after passes depend on it is not.

**4. Algebraic types plus four small decidable solvers — abelian-group unification for dimension (Kennedy/F#), an enum for family, natural-number intervals with explicit coercions for capacity (Futhark's compromise), row polymorphism with scoped labels for role schema. No SMT, no dependent types.**
Each property has a decidable, principal-types-preserving mechanism that composes with Hindley–Milner and fails with a *concrete residual* you can print. SMT fails nonconstructively — "by design", per Liquid Haskell's own authors.
*Reversal: **very high.*** This is the type system; adding or removing a solver changes what programs compile. The near-free sub-decision: **no implicit conversions, locally-resolved literal defaulting, annotations at function boundaries** — the Swift lesson.

**5. Diagnostics as structured data, error nodes in the tree, and per-constraint blame provenance from commit one — enforced by a rustc-style UI test suite.**
The gap between rustc/Elm-class and Haskell/C++-class errors is architectural, not editorial: Helium's split of constraint *generation / ordering / solving*, with provenance on each constraint, is what lets you blame the right expression instead of wherever unification last failed. Czaplicki got this for "an extra bit of info to each type constraint" at no measurable perf cost; rustc, retrofitting, must port *every* diagnostic in the compiler.
*Reversal: **highest of all five.*** A `Span + Reason` field on every constraint is a handful of lines today and a typechecker rewrite in a year; same for error nodes and for never returning `Result<Tree, Error>`. **This is the decision most expensive to get wrong** — cheapest to get right now, hardest to retrofit, and it is the entire product.
