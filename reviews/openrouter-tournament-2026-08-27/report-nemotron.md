**Bottom-line verdict**

1. The Raly compiler is a complete, well-tested front end (lex → parse → resolve → type-check → explain) with **zero execution capability** — no IR, no codegen, no backend, no runtime.  
2. Experiment 11 (“typed-state mediation”) uses a **hand-written Python DSL + interpreter** that shares **no types, operations, or provenance** with Raly; the “compiler constraint” is a token filter on LLM output, not a compilation target.  
3. The four properties the type system tracks (dimension, VSA family, superposition load, role schema) have **no semantic implementation** — `bind`/`bundle`/etc. are keywords that type-check but do not compute.  
4. **No intervention hooks exist at runtime**; provenance (`Blame`) is diagnostic-only. The structured-state experiment’s `corrupt_state` operates on Python objects, not compiled artifacts.  
5. The critical path to “Raly programs run” requires: a minimal typed IR lowering the four VSA operations, a differentiable interpreter for that IR, and a provenance-carrying runtime that maps `Blame` → intervention points. None of this exists.

---

### Eight material issues

#### 1. P0 — No IR or backend exists; the compiler cannot execute anything
**File:** `compiler/crates/raly/README.md:568-572`, `compiler/GRAMMAR.md:447-453`  
**Invariant violated:** “Raly type-checks but cannot execute” (HANDOFF.md:26) is acknowledged but no path to execution is implemented.  
**Counterexample:** `raly check examples/scene.raly` succeeds; `raly run examples/scene.raly` does not exist.  
**Expected vs actual:** A typed IR lowering `bind`/`bundle`/`permute`/`unbind`/`cleanup`/`broadcast` to executable ops with gradient support; actual = type-checker stops at `Ty::Vec`.  
**Deciding experiment:** Write a 20-line Raly program that encodes a scene, queries a role, and prints the result end-to-end without Python glue.  
**Smallest safe fix:** Define a `raly-ir` crate with a `Mir` enum (typed, SSA, one variant per VSA op), a `lower::lower(ast, resolved, checked) -> Mir`, and a `raly-interp` crate with `eval(mir) -> Value` + `grad(mir) -> Grad`.  
**Confidence:** 1.0 — explicitly documented as missing in four places. Falsified only if a hidden `codegen` module exists.

#### 2. P0 — Experiment 11’s DSL is not Raly; zero type/operation overlap
**File:** `experiments/11_typed_state_mediation/dsl.py:1-218`, `compiler/GRAMMAR.md:247-275`  
**Invariant violated:** “Raly should become an executable, typed intermediate representation for the parts of the model whose semantics we want to inspect” (PROJECT_GUIDE.md:254-255).  
**Counterexample:** DSL ops = `input | filter_gt | sort_asc | unique | count | return`; Raly ops = `bind | bundle | permute | unbind | cleanup | broadcast`. No mapping exists.  
**Expected vs actual:** Experiment 11 should compile Raly → IR → interpreter; actual = Python DSL with `Slot.type_name: str` ("List[Int]") instead of `Vec[Space; load; roles]`.  
**Deciding experiment:** Port one Experiment 11 task (`filter_sort_unique`) to Raly source, compile to IR, run in interpreter, get identical result.  
**Smallest safe fix:** Add a `raly-std` prelude with `List[Int]` as `Vec[IntSpace; load *; roles {}]` and implement the six DSL ops as Raly `fn`s over that space.  
**Confidence:** 1.0 — the DSL and Raly grammar are in the same repo and visibly disjoint.

#### 3. P0 — No runtime intervention hooks; provenance is diagnostic-only
**File:** `compiler/crates/raly-types/src/constraint.rs:1-108`, `experiments/11_typed_state_mediation/dsl.py:231-249`  
**Invariant violated:** “Causal intervention hooks attached to named operations” (PROJECT_GUIDE.md:263).  
**Counterexample:** `Blame` carries `Span + Reason` for error messages; `corrupt_state(mode="relevant")` mutates a Python `dict` — no connection.  
**Expected vs actual:** A runtime that can `intervene(mir, blame_span, new_value)` and re-evaluate; actual = no runtime.  
**Deciding experiment:** In the interpreter, change the value bound to `Subject` at `encode` line 19 and verify `subject_of` changes.  
**Smallest safe fix:** Extend `Mir` with `NodeId`, store `Blame.node_id` during lowering, add `Interpreter::set_node(node_id, value)` + `recompute_from(node_id)`.  
**Confidence:** 1.0 — provenance exists only in `raly-types` for diagnostics; no runtime exists to use it.

#### 4. P1 — VSA operations have no semantics implementation (not even a reference interpreter)
**File:** `compiler/crates/raly-types/src/lib.rs:1040-1441`, `docs/semantics/vsa-and-discrete-ops.md:7-13`  
**Invariant violated:** “What they *compute* is not implemented anywhere” (compiler/README.md:615).  
**Counterexample:** `check_bind` computes `load.multiply`, `roles.union` — but returns a `Ty`, not a vector. No `bind(a,b) -> Vec` function exists.  
**Expected vs actual:** A `VsaKernel` trait with `bind(a: &Vec, b: &Vec) -> Vec` + `grad`; actual = type algebra only.  
**Deciding experiment:** Implement `bind` for MAP (Hadamard product) in Rust, compile `fn f(a,b) { bind(a,b) }`, run it, compare to NumPy.  
**Smallest safe fix:** Add `raly-kernels` crate with `trait VsaKernel { fn bind(&self, a: &Array1<f32>, b: &Array1<f32>) -> Array1<f32>; … }` and a `MapKernel` impl.  
**Confidence:** 0.99 — explicitly admitted in README. Falsified if a `kernels` directory exists outside the snapshot.

#### 5. P1 — Capacity tracking is compile-time only; no runtime enforcement
**File:** `compiler/crates/raly-types/src/capacity.rs:65-99`, `compiler/crates/raly-types/src/lib.rs:1760-1813`  
**Invariant violated:** “Past capacity, cleanup returns the wrong atom and accuracy degrades towards chance without anything failing at run time” (diagnostic note) — but nothing *can* fail at runtime because there is no runtime.  
**Counterexample:** `bundle(a,b,c,d)` in a `capacity=3` space emits `RALY5001` at compile time; if it somehow ran, it would silently degrade.  
**Expected vs actual:** Runtime `cleanup` should panic or return `Err` when `load > capacity`; actual = no runtime.  
**Deciding experiment:** Run a bundle of 4 items in a capacity-3 space through the interpreter; expect `CapacityExceeded` error.  
**Smallest safe fix:** In `raly-interp`, make `cleanup` check `vec.load.minimum() > space.capacity` and return `InterpError::CapacityExceeded`.  
**Confidence:** 0.95 — the diagnostic message *claims* runtime behaviour that cannot be tested.

#### 6. P1 — No differentiable path through VSA ops; autodiff is a “later” promise
**File:** `docs/compiler-architecture.md:56-57`, `docs/semantics/vsa-and-discrete-ops.md:74-93`  
**Invariant violated:** “Keep AD a defined transformation on the typed mid-level IR” (compiler-architecture.md:56).  
**Counterexample:** The semantics doc (§5) lists STE, Gumbel, VQ gradients — all biased — but the compiler has no IR to attach estimator tags to.  
**Expected vs actual:** `Mir` nodes carry `Estimator::Ste | Gumbel | Vq` and `grad` walks the graph; actual = no IR, no grad.  
**Deciding experiment:** Write `fn f(x) { bundle(x, x) }`, compute `grad(f, x)` in interpreter, verify it matches `2 * x` (MAP bundling gradient).  
**Smallest safe fix:** Add `Estimator` enum to `Mir`, implement `backward` on `raly-interp` using `autodiff` crate, start with STE for `bundle`.  
**Confidence:** 0.9 — architecture doc explicitly defers this; semantics doc details the hard choices.

#### 7. P2 — Experiment 11’s “compiler constraint” is a token filter, not a type-driven decoder
**File:** `experiments/11_typed_state_mediation/smoke.py:163-185`, `compiler/crates/raly-wasm/src/lib.rs:1-364`  
**Invariant violated:** “The compiler constraint did prevent wrong-type returns” (Experiment 11 FINDINGS.md:73) — but it’s a `prefix_allowed_tokens_fn` over string operations, not a typed AST constraint.  
**Counterexample:** `valid_candidates` returns `["filter_gt s0 5 -> s1", …]` as strings; the LLM is constrained to these strings, not to well-typed Raly ASTs.  
**Expected vs actual:** Constrained decoding should use `raly-wasm`’s type checker to reject ill-typed completions; actual = regex allow-list.  
**Deciding experiment:** Feed an ill-typed Raly completion (e.g., `bundle(sym, int)`) to the constrained decoder; it should be rejected by type-checker, not by string filter.  
**Smallest safe fix:** Expose `raly-types::check` via `raly-wasm`, run it on each candidate completion string, filter by `!diagnostics.has_errors()`.  
**Confidence:** 0.95 — the code shows string-based filtering; `raly-wasm` does full type-checking but isn’t used for constrained decoding.

#### 8. P2 — Learned codebooks invalidate all capacity numbers; type system cannot express this
**File:** `compiler/crates/raly-types/src/lib.rs:167-223`, `docs/semantics/vsa-and-discrete-ops.md:63-69`  
**Invariant violated:** “Codebook provenance is not tracked… A learned codebook invalidates every capacity number… and the compiler cannot currently tell” (compiler/README.md:600-604).  
**Counterexample:** `space S = MAP[1000] where effective = 111` uses measured capacity; if `codebook = learned` were allowed, capacity would be unknown but the checker would still use 31.  
**Expected vs actual:** `SpaceInfo.capacity_basis` has `Effective | Nominal`; needs `Learned { coherence: f32 }` with `capacity = None`.  
**Deciding experiment:** Declare `space S = MAP[1000] where codebook = learned`; `bundle` 10 items should warn “capacity unknown” not error “exceeds 31”.  
**Smallest safe fix:** Add `CapacityBasis::Learned { coherence: Option<f32> }`, make `capacity` return `None` for `Learned`, adjust `check_capacity` to emit warning not error.  
**Confidence:** 0.9 — explicitly listed as “not in the type system” with `coherence: unknown` mentioned in semantics doc.

---

### Ranked top three

| Rank | ID  | Why it blocks the project direction |
|------|-----|-------------------------------------|
| 1    | 1   | **No IR/backend = Raly is a linter, not a language.** Every other issue (intervention, gradients, capacity at runtime) presupposes an executable artifact. |
| 2    | 3   | **No intervention hooks = “causal legibility” is a slogan.** The whole research bet is “intervene on a discrete code during training and require the output to change” (HANDOFF.md:129); without a runtime that maps `Blame` → mutable state, this is untestable. |
| 3    | 2   | **Experiment 11 is disconnected from Raly.** The only “structured-state experiment” uses a throwaway Python DSL. Until it compiles Raly → IR → interpreter, the compiler has no user and no feedback loop. |

---

### Kill / Continue decision

**Continue — but only after Issues 1, 2, 3 are resolved in sequence.**  
The compiler front end is genuinely excellent (198 tests, zero warnings, great diagnostics, WASM playground). The type system design (abelian-group dimensions, row-polymorphic roles, measured capacity) is the right substrate for the research hypothesis. **However**, the project cannot claim “Raly compiles to an inspectable, intervenable runtime” until a minimal IR + interpreter + provenance-carrying runtime exists and Experiment 11 runs on it. The next milestone must be **“Raly runs the `filter_sort_unique` task end-to-end”** — not another experiment, not a bigger model, not a language feature.