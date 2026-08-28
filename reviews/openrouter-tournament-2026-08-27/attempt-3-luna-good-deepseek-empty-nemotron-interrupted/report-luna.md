The typed front end is not yet a sound foundation for an IR or backend.  
Several malformed or unresolved programs currently compile cleanly or receive the wrong type.  
The highest-risk defects are silent qualified-name failures, broken return-flow checking, and ignored type arguments.  
The research direction remains viable, but compiler correctness should precede backend work or stronger interpretability claims.  
Fix the semantic escape hatches first, then rerun the full compiler and experiment gates.

## Confirmed defects

### C1 — P1

- **Verdict in one sentence:** Multi-segment names are silently treated as error-typed values instead of producing unresolved-name diagnostics.
- **File and line(s):** `compiler/crates/raly-resolve/src/lib.rs:504-521, 582-612`; `compiler/crates/raly-types/src/lib.rs:720-723`
- **Invariant allegedly violated:** Every unresolved reference receives an error binding and a diagnostic; no invalid source should type-check merely because name resolution skipped it.
- **Minimal reproducer or concrete counterexample:**
  ```raly
  fn f() -> Int {
      missing::name
  }
  ```
- **Expected versus actual result:** Expected an unresolved-name or unsupported-qualified-path error; actual resolution skips the multi-segment path, type inference returns `Ty::Error`, and the function can compile with no diagnostic.
- **Regression test or experiment that would decide it:** Compile the reproducer and assert a nonzero result containing `RALY3001`/`RALY3002`; also test `fn f(x: Missing::T) -> Int { 1 }`.
- **Smallest safe fix:** Emit an explicit diagnostic for unsupported multi-segment expression/type paths until modules exist, rather than omitting the reference mapping.
- **Confidence and what would falsify the finding:** High; falsified only if qualified paths are intentionally valid but deliberately unchecked, which would contradict the resolver’s total-reference contract.

### C2 — P1

- **Verdict in one sentence:** Function result checking treats every block as returning its tail expression, so explicit `return` statements are rejected and unannotated non-unit bodies are accepted as unit functions.
- **File and line(s):** `compiler/crates/raly-types/src/lib.rs:615-641, 884-929`
- **Invariant allegedly violated:** A function’s checked result must agree with all reachable returns and with its declared or inferred function type.
- **Minimal reproducer or concrete counterexample:**
  ```raly
  fn explicit() -> Int {
      return 1;
  }

  fn implicit() {
      1
  }
  ```
- **Expected versus actual result:** `explicit` should compile cleanly, while `implicit` should either infer `Int` or be rejected for returning a value from a unit function; actual `explicit` gets a `Unit`-versus-`Int` mismatch from the empty tail, while `implicit` is recorded as `()`, with no diagnostic.
- **Regression test or experiment that would decide it:** Add tests for a return-only body, returns in both branches of an `if`, and a no-arrow function with a non-unit tail; assert the chosen return contract consistently.
- **Smallest safe fix:** Make return-flow explicit in the checker: treat a guaranteed `return` as terminating control flow, check reachable tails only, and enforce `Unit` or infer the result for omitted return annotations.
- **Confidence and what would falsify the finding:** High; the two counterexamples follow directly from `check_block` returning `Unit` when there is no tail and `check_item` always comparing that result with an explicit annotation.

### C3 — P1

- **Verdict in one sentence:** Closed role schemas ignore multiplicity, allowing a vector carrying a role twice to satisfy a schema declaring it once.
- **File and line(s):** `compiler/crates/raly-types/src/ty.rs:241-247`; `compiler/crates/raly-types/src/lib.rs:1600-1610`
- **Invariant allegedly violated:** Role rows are documented as multisets, so a closed schema must compare role counts, not only role presence.
- **Minimal reproducer or concrete counterexample:**
  ```raly
  space S = MAP[1024]
  role A in S

  fn f(x: Sym[S]) -> Vec[S; roles {A}] {
      bind(A, bind(A, x))
  }
  ```
- **Expected versus actual result:** Expected a closed-schema mismatch, or an explicit duplicate-binding policy; actual `Row` contains `A` twice, `missing_from` checks only key presence, and the program passes.
- **Regression test or experiment that would decide it:** Compile the reproducer and inspect the inferred body row; assert that returning `{A, A}` where `{A}` is required fails.
- **Smallest safe fix:** Make row-difference checks count-aware, using the existing `subsumed_by`-style multiplicity logic; alternatively reject duplicate role bindings consistently.
- **Confidence and what would falsify the finding:** High; `Row::extend` increments counts while `missing_from` only tests `contains`.

### C4 — P1

- **Verdict in one sentence:** Type constructors and aliases silently discard unsupported arguments and qualifiers, so source annotations can state a different type without affecting checking.
- **File and line(s):** `compiler/crates/raly-types/src/lib.rs:366-389, 432-469`; `compiler/crates/raly-types/src/lib.rs:397-424`
- **Invariant allegedly violated:** Every syntactically accepted type argument and qualifier must either participate in the resulting type or produce a diagnostic.
- **Minimal reproducer or concrete counterexample:**
  ```raly
  space S = MAP[1024]
  type Bad = Vec[S, Int]
  type AlsoBad = Vec[S; load 40]
  ```
- **Expected versus actual result:** Expected an invalid-arity/unsupported-qualification diagnostic; actual `Vec` uses only its first argument, and alias lowering ignores arguments and qualifiers, so these declarations are accepted as ordinary vector types.
- **Regression test or experiment that would decide it:** Compile the examples and assert errors for `Vec[S, Int]`, `Int[S]`, and applying `load` to a non-generic alias.
- **Smallest safe fix:** Validate constructor arity and allowed qualifiers before lowering; reject all arguments/qualifiers that aliases and scalar constructors cannot interpret.
- **Confidence and what would falsify the finding:** High; the lowering code demonstrably reads only the first `Vec` argument and bypasses alias-site qualifiers.

### C5 — P2

- **Verdict in one sentence:** Braced Unicode escapes are accepted without validating hexadecimal syntax, code-point range, or even the presence of a closing brace.
- **File and line(s):** `compiler/crates/raly-lexer/src/lib.rs:235-243`
- **Invariant allegedly violated:** Every malformed literal must produce a lexical diagnostic while still yielding a recoverable token.
- **Minimal reproducer or concrete counterexample:**
  ```raly
  let s = "\u{}"
  let t = "\u{not-hex}"
  let u = "\u{1F600"
  ```
- **Expected versus actual result:** Expected `RALY1003`-class invalid-escape diagnostics; actual `check_escapes` consumes until `}` when present and emits nothing, and also accepts an unterminated braced escape.
- **Regression test or experiment that would decide it:** Add lexer tests for empty, non-hex, out-of-range, surrogate, and missing-brace escapes; assert one diagnostic per malformed escape.
- **Smallest safe fix:** Parse and validate the brace contents as a nonempty hexadecimal scalar value, require `}`, and report the exact escape span on failure.
- **Confidence and what would falsify the finding:** High; the current branch has no validation beyond detecting `{` and scanning forward.

### C6 — P2

- **Verdict in one sentence:** The diagnostic renderer assigns the primary locator arrow by label insertion order rather than by label severity.
- **File and line(s):** `compiler/crates/raly-diag/src/render.rs:179-182`
- **Invariant allegedly violated:** Primary labels identify the fault site and must render with `-->`; secondary labels must render as supporting `:::` context.
- **Minimal reproducer or concrete counterexample:**
  ```rust
  Diagnostic::error(code, "m")
      .with_secondary(first_span, "first")
      .with_primary(second_span, "fault")
  ```
- **Expected versus actual result:** Expected the `second_span` primary label to receive `-->`; actual the first inserted secondary receives `-->`, and the primary receives `:::`.
- **Regression test or experiment that would decide it:** Render a diagnostic with secondary-before-primary and assert the arrow and locator order by label style.
- **Smallest safe fix:** Render the primary label as the primary locator regardless of insertion order, or normalize labels before rendering.
- **Confidence and what would falsify the finding:** High; `Diagnostic::focus` already explicitly supports primary labels independent of insertion order, while the renderer does not.

## Strong inferences

### S1 — P2

- **Verdict in one sentence:** User-supplied effective dimensions are trusted without domain validation, allowing zero or implausibly oversized capacities to redefine safety checks.
- **File and line(s):** `compiler/crates/raly-types/src/lib.rs:184-205`; `compiler/crates/raly-types/src/capacity.rs:71-74`
- **Invariant allegedly violated:** A measured effective dimension used for capacity must be a valid positive dimension and should not silently override the nominal space with an invalid value.
- **Minimal reproducer or concrete counterexample:**
  ```raly
  space S = MAP[384] where effective = 0
  space T = MAP[384] where effective = 100000
  ```
- **Expected versus actual result:** Expected rejection or an “unknown effective dimension” diagnostic for invalid measurements; actual `effective = 0` produces capacity `1`, while `100000` produces a much larger capacity, both without errors.
- **Regression test or experiment that would decide it:** Test zero, negative, fractional, and effective-greater-than-nominal values; specify whether each is rejected or treated as unknown.
- **Smallest safe fix:** Validate `effective > 0` and the project’s intended relationship to nominal dimension before using it in `capacity`; otherwise leave capacity unchecked.
- **Confidence and what would falsify the finding:** Medium-high; falsified if the language explicitly intends arbitrary effective values, including zero and values larger than nominal, to be valid measurements.

### S2 — P1

- **Verdict in one sentence:** Interval compatibility and capacity checking use only lower bounds, allowing an exact load annotation to hide a body whose possible runtime load exceeds capacity.
- **File and line(s):** `compiler/crates/raly-types/src/ty.rs:118-139`; `compiler/crates/raly-types/src/lib.rs:1572-1597, 1760-1768`
- **Invariant allegedly violated:** A function accepted under an exact load and capacity annotation must not have a body whose possible load can exceed the declared safe capacity.
- **Minimal reproducer or concrete counterexample:**
  ```raly
  space S = MAP[256] // capacity 7

  fn f(a: Vec[S], b: Vec[S]) -> Vec[S; load 3] {
      bundle(a, b)
  }
  ```
- **Expected versus actual result:** Expected a mismatch or an “unknown/potentially over capacity” diagnostic because each parameter may contain an unbounded load; actual the body has load `[2, unbounded]`, intersects the declared `[3,3]`, and capacity checks only minimum load `2`, so the function passes.
- **Regression test or experiment that would decide it:** Compile this function and a variant returning `Vec[S]`; assert whether exact return loads are guarantees or assumptions, then test calls with concrete over-capacity arguments once execution exists.
- **Smallest safe fix:** Define annotations as guarantees and require interval containment, or retain intersection semantics but emit an uncertainty/possible-overflow diagnostic whenever the interval’s upper bound exceeds capacity.
- **Confidence and what would falsify the finding:** Medium; falsified if load annotations are intentionally non-guaranteeing assumptions and capacity checking is explicitly limited to definite lower-bound overflow.

## Ranked top three

1. **C1 — silent unresolved qualified paths:** invalid programs can compile with no diagnostic and no traceable error binding.
2. **C2 — incorrect function return-flow checking:** valid explicit returns fail while invalid implicit returns are silently typed as unit.
3. **C4 — ignored type arguments and qualifiers:** the type surface can claim load or shape properties that the checker discards.

**Decision:** Continue the typed-language and structured-state direction, but pause IR/backend expansion and any stronger compiler-soundness claims until C1–C4 are fixed and covered by negative tests.