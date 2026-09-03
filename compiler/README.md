# Raly — compiler front end

Infrastructure for the **Raly** language front end. Source files use the
`.raly` extension.

It lexes, parses, resolves names, type-checks, renders diagnostics, and can
describe a program's declared structure in plain English. A typed ledger
sidecar can also execute a small, pure constant subset with replay receipts.
It does not yet lower or execute VSA operations; see
[Not implemented](#not-implemented).

The type system tracks four properties that tensor shapes do not express:
**dimension**, **VSA family**, **superposition load against measured capacity**,
and **role schema**. Each property has a small, decidable solver. See
[`raly-types`](#raly-types).

The concrete grammar is written down in **[GRAMMAR.md](GRAMMAR.md)**, which is
normative: EBNF, the rationale for each decision, and worked examples. Read it
before reading `raly-parse`.

## Building and running

**Rust may not be on `PATH` in a fresh shell.** Prepend it first, every time:

```powershell
# PowerShell
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
```

```bash
# Git Bash
export PATH="$HOME/.cargo/bin:$PATH"
```

Verify before anything else:

```
cargo --version    # expected: cargo 1.98.0 or newer
```

Then, from this directory:

```
cargo build              # zero warnings expected
cargo test --workspace   # 208 passing, 2 ignored doctests
cargo clippy --workspace --all-targets   # clean
cargo fmt --all --check
```

### Trying it

```
cargo run -p raly -- explain examples/explain-me.raly   # what the program means
cargo run -p raly -- explain examples/explain-me.raly --json
cargo run -p raly -- check examples/scene.raly          # exits 0
cargo run -p raly -- check examples/broadcast.raly      # a silent-broadcast error
cargo run -p raly -- check examples/capacity.raly       # a capacity error
cargo run -p raly -- check examples/wrong-role.raly     # a wrong-role unbind
cargo run -p raly -- parse examples/scene.raly          # dumps the tree
cargo run -p raly -- check examples/broken-syntax.raly  # 13 errors, exits 1
cargo run -p raly -- check examples/broken.raly         # lexical errors
cargo run -p raly -- lex   examples/tour.raly
```

| File | What it is |
| --- | --- |
| `examples/scene.raly` | A substantial, valid program: a role-filler scene memory. What real Raly looks like. |
| `examples/capacity.raly` | Well-shaped, silently wrong: a bundle 9 items past what its space can retrieve, plus a space declaring its *measured effective* dimension. |
| `examples/wrong-role.raly` | Unbinding a role that was never bound, and nesting two unbinds with no `cleanup` between. |
| `examples/broadcast.raly` | The PyTorch bug, made impossible: two elementwise operands a tensor library would silently broadcast, plus the explicit `broadcast(v, S)` that says you meant it. |
| `examples/explain-me.raly` | Demonstrates three inferred facts in `raly explain`: the value is at capacity, retrieval is approximate, and the structure is two levels deep. |
| `examples/broken-syntax.raly` | One of each recoverable *syntax* error. All 13 are reported in a single run. |
| `examples/broken.raly` | One of each recoverable *lexical* error. |
| `examples/tour.raly` | Exercises every token class. A lexer fixture, **not** a valid program — `check` reports on it by design. |

Here is the capacity diagnostic:

```
error[RALY5001]: this bundles 40 items into a space that holds 31
  --> examples/capacity.raly:27:5
   |
27 |     bundle(
   |     ^^^^^^^ 40 items superposed here
   | ...continues to line 33
  ::: examples/capacity.raly:13:1
   |
13 | space Small = MAP[1000]
   | ----------------------- `Small` holds 31 items
   |
   = note: 31 is the capacity of `Small` at dimension 1000, measured at 95%
           retrieval in experiments/04_capacity
   = note: past capacity, cleanup returns the wrong atom and accuracy degrades
           towards chance without anything failing at run time
   = help: superpose fewer items, or declare `Small` at dimension 1247, or 2048
           for a power of two
```

`broken.raly` contains examples of the lexical diagnostics:

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

### CLI

| Command | Behaviour |
| --- | --- |
| `raly lex <file>` | Dump every token with its kind, byte span and line:column |
| `raly parse <file>` | Parse and dump the syntax tree to stdout |
| `raly check <file>` | Lex, parse, resolve, type-check, render all diagnostics to stderr, exit non-zero on error |
| `raly explain <file>` | Say, in plain English, what the program represents — derived entirely from its types. `--json` for machine-readable output |

`check` runs every phase on each invocation. Each phase returns a value plus
diagnostics rather than stopping at its first error, so later phases can still
run. Diagnostics are then sorted in source order.

Flags: `--color` / `--no-color` (default off), `--explain` (append each code's
registry description), `--json` (machine-readable `explain` output), `-h`, `-V`.

`explain` also describes the portions of a file whose types are known when
other parts contain errors. Prose goes to stdout, diagnostics to stderr, and
the exit code matches `check`.

Exit codes: `0` success · `1` the input contained errors · `2` bad command line
or unreadable file.

## Crate layout

```
compiler/
├── Cargo.toml                 workspace root (Rust 2021)
├── GRAMMAR.md                 the normative grammar: EBNF, rationale, examples
├── examples/                  .raly files, valid and deliberately broken
└── crates/
    ├── raly-diag/             spans, diagnostics, rendering   [no dependencies]
    ├── raly-lexer/            tokeniser                       [logos]
    ├── raly-ast/              arena AST + visitor
    ├── raly-parse/            recursive-descent parser        [hand-written]
    ├── raly-resolve/          name resolution, two namespaces
    ├── raly-types/            the type checker, four small solvers
    ├── raly-explain/          a program, in plain English     [no dependencies]
    └── raly/                  the `raly` binary
```

### `raly-diag`

This crate defines source spans, stable diagnostic codes, labels, notes, help
text, and plain or colored rendering.

- **Byte-offset spans.** `Span` is `(FileId, start, end)`. Line and column are
  derived only at render time by `SourceMap`, so no phase carries or maintains
  them. Columns count characters, not bytes, and tabs are expanded so carets
  land under the right glyph.
- **Stable codes.** Every diagnostic carries a `Code` like `RALY1002` whose
  meaning never changes and is never reused. Number ranges are reserved per
  phase (`0xxx` driver, `1xxx` lexical, `2xxx` syntax, `3xxx` resolution,
  `4xxx` types, `5xxx` capacity) so later phases need no renumbering. A unit
  test enforces uniqueness and format.
- **Two advice channels.** `note:` states a fact
  (`this vector already holds 7 of 31 items`); `help:` states an action
  (`split the bundle, or declare a wider space`). Keeping them separate makes
  factual context distinct from suggested actions.
- **Primary and secondary labels.** Primary underlines with `^` at the fault
  site; secondary underlines with `-` for supporting context, with its own
  `:::` locator line.
- **Deterministic ASCII by default.** Colour is opt-in and provably changes
  only the bytes, never the layout — there is a test for that. This is why the
  renderer is hand-written rather than using `ariadne` or `codespan-reporting`:
  the output is snapshot-tested character for character, while the crate remains
  dependency-free. The renderer is about 250 lines.
  A different backend can be swapped in behind `Renderer` if that trade stops
  paying.

### `raly-lexer`

Generated with `logos` and wrapped in a hand-written driver. A key property is that
**`lex` is total**: every input, including arbitrary bytes, produces a token
stream and never panics. Unclassifiable text becomes an error token *and* a
diagnostic, so the parser can keep going and report more than one problem per
run.

Recoverable, each with its own code:

- unterminated strings (`RALY1002`) — at end of line or end of file
- unknown escapes (`RALY1003`) — one diagnostic per bad escape, spanning just
  the two characters
- malformed numbers (`RALY1004`) — `123abc`, `0x`, `1e`
- unknown characters (`RALY1001`) — adjacent runs grouped into one diagnostic,
  with targeted hints for homoglyphs (smart quotes, en dashes, `×`, `→`, `≤`,
  non-breaking spaces)

Comments are lexed as trivia rather than discarded, so a formatter or
doc-comment pass has them later.

### `raly-ast`

Arena-based: nodes live in flat `Vec`s and reference each other by 32-bit `Id`
rather than `Box`. This makes side tables for types and resolutions easy to
index, keeps the tree serializable, and avoids borrowing complications during
error recovery. Names are interned to `Symbol`. Every
node carries a `Span`. A generic `Visitor` derives its traversal from the node
definitions, so adding variants later means editing `walk_*` and nothing else.

Two invariants matter more than the node list:

- **The tree is total.** Parsing never fails. Text that could not be understood
  becomes an `Error` node whose span covers the tokens involved, so every
  significant token in a file lies inside some node and later phases can always
  walk the whole thing. There is a test asserting this over both a valid and a
  deliberately broken program.
- **Every node knows why it exists.** `Origin` distinguishes a node the user
  wrote from one recovery synthesised, and names the `Reason` in the latter
  case. A checker can then avoid blaming an expression that was synthesized
  during recovery.

`VsaCall` stores its operands twice: in source order for diagnostics, and in a
**canonical order** derived from `Ast::structural_key`. Binding and n-ary
bundling are commutative, so this makes commutativity structural rather than a
rule each later pass has to remember. `bundle.left` has no canonical order
because the fold is order-dependent.

### `raly-parse`

Hand-written recursive descent, with Pratt precedence climbing for expressions.
No parser generator, and no `Result` anywhere in the crate.

`parse(file, src, tokens) -> Parsed` is a pure function with no ambient state,
global interner, or mutable compiler context. This structure is also compatible
with a future incremental query engine.

**Recovery** is panic mode with bracket-aware synchronisation sets:

- Skipping tracks bracket depth, so one stray token deep inside a call does not
  abandon the enclosing declaration.
- After a diagnostic, further "unexpected token" reports are suppressed until at
  least one token has been consumed. One mistake produces one message — there
  are tests pinning that for six different mistakes.
- Lexical errors are not re-reported. `123abc` is one diagnostic, not two.

Some diagnostics encode algebraic constraints rather than grammar. `bundle()`
is `RALY2003` with a note explaining that superposition has
no identity element in any VSA family, so an empty bundle denotes no vector.
`bundle.foo` is `RALY2005`, and its help says that `bundle.left` is a different
function from `bundle`, not a spelling of it. `space S = 1024` is `RALY2010`,
pointing at both the dimension and the name, because family is part of a
vector's identity.


### `raly-resolve`

`resolve(&Ast) -> Resolved`. Two namespaces (`Value` and `Type`), a scope
stack, and a `DefId` for **every** reference — including the ones it could not
resolve, which get `DefId::ERROR` and a type of `Error`. Nothing downstream has
to branch on "was this resolved?", and nothing cascades.

- **Items are hoisted, `let`s are sequential.** Functions may be mutually
  recursive and a `space` may be used above its declaration; a local is visible
  only after its own `let`, so `let x = x` refers to the outer `x`.
- **Use-before-definition is its own diagnostic** (`RALY3004`), not "unknown
  name". The resolver can see the `let` below and report the more specific
  problem.
- **A space lives in both namespaces.** It is a type in `Vec[Concepts]` and a
  value in `cleanup(v, Concepts)`, which names a codebook to project onto.
- **Shadowing a local is fine and silent; shadowing a `role` is a warning**
  (`RALY3007`). A role is a codebook atom, and a local that hides one silently
  changes what every `bind` naming it computes.
- **Family names resolve here**, against a builtin table, exactly as GRAMMAR.md
  §3 says they should — which is why `MAP` can stay an identifier rather than
  becoming a keyword.
- Suggestions come from a length-scaled Levenshtein threshold that errs towards
  silence, because a wrong suggestion is worse than none.
- `where` attribute values are deliberately *not* resolved. GRAMMAR.md §3 makes
  `where` an extension point whose attributes have no fixed meaning yet, so
  `codebook = fixed` names a mode, not a binding.

### `raly-types`

Decision 4 of `docs/compiler-architecture.md` specifies algebraic types with
one small, decidable solver per property. The current design does not use SMT
or dependent types, which keeps diagnostics tied to domain-specific constraints.

**Dimension — abelian-group unification.** Kennedy's units of measure, as
shipped in F# 2.0. A dimension is a formal product of atoms (integer constants,
and named constants the checker could not fold) with integer exponents;
multiplication adds exponents and division subtracts them. Two dimensions are
equal exactly when their quotient is the identity, and when they are not, the
**residual is what gets printed**:

```
= note: dimensions form an abelian group, and these do not cancel:
        the residual is 1024 / 8192
```

This is more specific than "unification failed." `MAP[2 * BASE_D]` still compares equal to another
`MAP[2 * BASE_D]` even though neither folds to a number.

**Family — a plain enum.** `MAP`, `BSC`, `HRR`, `FHRR`. Mixing them is
`RALY4001`, and the message says what each family *is*, because the reason
there is no conversion is that they have different binding operations over
different alphabets.

Family, dimension and codebook are checked **in that order**, so two spaces that
differ in family get a family error rather than a technically-true and useless
dimension error. Two spaces agreeing on both but still distinct get `RALY4003`:
a space also fixes the codebook, and atoms of one codebook are noise to the
other.

**Capacity and load — natural-number intervals over measured numbers.**
Futhark's compromise, as decision 4 asks. A load is a closed interval; `bundle`
adds intervals, `bind` multiplies them (binding distributes over superposition),
`unbind` collapses to one noisy item, `cleanup` collapses to one clean atom.
Compatibility is **interval intersection**, not equality, so an annotation
narrows what the checker knows rather than asserting something it must prove.

The capacity numbers are measured, not derived. `experiments/04_capacity` found
the largest bundle still retrieved at 95%:

| D | 256 | 512 | 1000 | 2048 |
|---|-----|-----|------|------|
| largest bundle | 7 | 14 | 31 | 71 |

The checker reproduces those four points **exactly** and interpolates linearly
in log–log space between them, extrapolating the nearest segment's exponent
outside the range. A global power-law fit (about `0.0145 · D^1.114`) fits all
four to within 8% and was rejected for exactly that reason: the experiment is
the authority, and a checker that disagrees with it at D=512 is wrong.

Per `experiments/05_real_embeddings`, a bound derived from ambient `D`
overstates real capacity by 3–5×, because real embedding spaces have an
effective dimension far below their nominal one — 110.6 of 384 for MiniLM. A
space may declare what was measured, and the checker uses it and says so:

```raly
space Sentences = MAP[384] where effective = 111
```

**Role schema — row polymorphism with scoped labels.** Leijen's design, as
decision 4 asks. A row is a multiset of labels plus a tail; `bind` extends it,
`unbind` restricts it, and unbinding a label a closed row does not carry is
`RALY4007`. Duplicates are permitted rather than an error, which is what makes
scoped labels simpler than other record systems — and binding one role twice is
a meaningful VSA operation anyway. A `Vec[S]` with no `roles {..}` qualifier is
**open**, so a function can accept any vector carrying `Subject` without naming
the rest; only an explicit schema closes a row, and only a closed row can prove
a role is *absent*.

**The algebra, enforced.** `bundle()` is a parse error because superposition has
no identity (`RALY2003`). `bundle.left` is a *different function* from the n-ary
primitive because bundling is not associative, and using it on three or more
operands is `RALY5003`. `bind` is commutative, so operand order carries no
information and every rule here folds over operands with a commutative combiner.
Nested `unbind` with no `cleanup` between is a warning at depth 2 and an error
at depth 3 (`RALY5002`) — semantics §3 puts usable depth at about 2 at D=1000,
so depth 3 retrieves at close to chance.

**Constraint provenance.** Every
constraint carries a `Span + Reason` (`constraint.rs`) generated at the point
the constraint is *created*, so a failure is reported against the expression
that caused it and the message can say "this is operand 2 of bundle" or "this
is the result of `encode`, whose signature fixes its type" rather than "cannot
unify". Raly has no unification variables to search over — annotations are
mandatory at function boundaries, per GRAMMAR.md §5.6 — so the *ordering* half
of the Helium design is not needed yet. The provenance half is here.

**No implicit conversions.** Following decision 5:
no overload resolution, no literal defaulting across types, annotations at
function boundaries. There is therefore no search, and no expression can be
"too complex". The one inclusion that exists is not a conversion: a `Sym[S]` is
already a vector of load one, so it is accepted where a `Vec[S]` is wanted. The
reverse is not, and the message names `cleanup` as the operation that fixes it.

### No silent broadcasting

In PyTorch, adding a tensor of shape `(32, 1)` to one of shape `(1, 32)` does
not fail. It broadcasts and returns a `(32, 32)` matrix; NumPy behaves the same
way. When that was not intended, the operation can remain unnoticed because
the shapes are not represented in a static type at the call site.

Raly's types carry width and family, so there is. **`bind` and `bundle` -- the
operations that combine their operands position against position -- require
operands of an identical vector type.** A mismatch is `RALY4012`, and the
message names what would have happened silently somewhere else:

```
error[RALY4012]: `bundle` combines its operands position by position, and these two do not have the same type
 --> broadcast-width.raly:8:5
  |
8 |     bundle(a, b)
  |     ^^^^^^ both operands of this must have identical types
 ::: broadcast-width.raly:8:12
  |
8 |     bundle(a, b)
  |            - this one is `MAP[8192]`, in `Wide`
 ::: broadcast-width.raly:8:15
  |
8 |     bundle(a, b)
  |               - this one is `MAP[1024]`, in `Narrow`
  |
  = note: dimensions form an abelian group, and these do not cancel: the
          residual is 8192 / 1024
  = note: a tensor library would not stop here: in NumPy or PyTorch, one
          length-1 axis on either side -- which is what every unsqueeze, batch,
          head or beam dimension adds -- makes (8192, 1) and (1, 1024)
          broadcast to a matrix of shape (8192, 1024), silently, and the first
          thing that looks wrong is a loss curve days later
  = help: if combining them is genuinely what you meant, say so:
          `bundle(.., broadcast(<the second one>, Wide))` re-expresses it in
          `Wide`, and the result is `noisy`, because that reinterpretation
          throws information away
```

**"Identical" is scoped deliberately, to width and family.** Those are the two
shape properties. Load and role schema are *combined* by these operations --
`bundle` adds loads and unions schemas, `bind` multiplies and extends -- so
requiring those to match would break the algebra rather than protect it. Two
spaces agreeing on family and width but differing in **codebook** stay
`RALY4003`: no tensor library has a notion of a codebook to paper over, and
calling that a broadcast error would be a false claim about what happens
elsewhere. The same-width, different-family case is the genuinely silent one --
a tensor library adds a bipolar vector to a phase vector without a word -- and
its `note:` says exactly that.

**The intent stays expressible.** `broadcast(v, S)` re-expresses `v` in `S`,
explicitly, in one greppable word; `v |> broadcast(S)` is the same thing read
in the order the data moves. The result is **`noisy`**, because reinterpreting
a vector across a width or a family is not information-preserving, and an
escape hatch that returned a clean vector would hand back exactly the silence
the rule exists to remove. GRAMMAR.md 7.3 has the full rationale, including why
`broadcast(a, b)` over two vectors was rejected: it would denote an outer
product, which is a matrix, and Raly has no matrix type.

### `raly-explain`

`raly explain <file>` describes the structure represented by the program's
types. For comparison, a conventional `Vec<f32> -> Vec<f32>` signature does
not record the VSA family, load, or roles. Raly can render those declarations
as prose:

```
space Sentences = MAP[384]
  A value of `Sentences` is a list of 384 numbers, where every position holds
  either +1 or -1, and two of them are combined by multiplying position
  against position. [...]
  For `Sentences` that point is 3 items. It was measured at 95% retrieval, not
  derived from a formula. That number comes from the measured effective width
  of 111 this declaration records, not from the 384 written beside the family:
  a real embedding space uses far fewer independent directions than its
  nominal width suggests.
  ! The written width would suggest room for 10 items. The measured width says
    3. Anything sized against the written number is about 3x too optimistic.

fn encode(s: Sym[Sentences], v: Sym[Sentences], o: Sym[Sentences]) -> Vec[Sentences; load 3; roles {Subject, Verb, Object}]
  It takes three values, every one of them one single entry of `Sentences` --
  one of its fixed values, not a combination of several.
  It gives back a value of `Sentences` carrying exactly the keys Subject, Verb
  and Object, holding 3 of the 3 items `Sentences` can hold.
  ! This is exactly at capacity: 3 of the 3 items `Sentences` can hold. One
    more and asking for an item back starts returning a different one, with
    nothing failing to say so.
```

Three rules govern the output:

1. **Plain words.** No term is used that is not defined where it is used.
   Terms such as "bundle," "superposition," "codebook," and "role" are
   replaced with descriptions of the underlying operations.
2. **Only what the types prove.** Where a property is open or unknown, the
   output says so -- a dimension the checker could not fold prints as unknown
   rather than as the placeholder the checker fell back to, and the JSON
   carries `null`.
3. **Say the unwritten.** A `!` marks something that follows from the types
   without appearing in the source: a value at or near capacity, a set of keys
   left open so no key can be proven absent, an extraction that is only
   approximate, and a nesting depth that will need a `cleanup`. In
   `examples/explain-me.raly` none of those four facts is written down
   anywhere, and all four come out.

`--json` gives the same content as data: the numbers the prose was derived
from, not the prose in quotes. The serialiser is hand-written for the same
reason `raly-diag`'s renderer is -- the crate has no dependencies outside the
workspace, and the output is asserted on character for character.

## Tests

208 tests pass (203 unit and integration plus 5 doctests); 2 documentation-only
examples remain explicitly ignored. The suite covers every compiler phase, the
ledger runtime, CLI, golden diagnostics, and doctests.

```
raly-diag    3 unit + 21 integration   source map, spans, rendered output
raly-lexer  32 integration             one group per token class, comments,
                                       string edge cases, recovery, totality
raly-ast     9 unit                    arena, interner, provenance, canonical
                                       operand order, visitor walk and prune
raly-parse  46 grammar                 one per construct, asserted on the dump
            16 recovery                multiple errors per run, no cascades,
                                       error-node provenance, termination
            10 diagnostics             rendered output, character for character
raly-resolve 3 unit                    edit distance, suggestion silence,
                                       family table round-trip
raly-types  17 unit                    capacity anchors and monotonicity,
                                       dimension group laws and residuals,
                                       load intervals, row extend and restrict
raly-explain 5 unit                    prose wrapping, JSON escaping, English
                                       list and count forms, load phrasing
raly-ledger 5 unit                     semantic identity, replay receipts,
                                       divergence localization, invariance
raly         5 unit                    the pipeline reports every phase at once,
                                       and what RALY4012 is and is not for
            18 integration             exit codes, stdout/stderr discipline,
                                       `explain`, `run`, and `--json`
             2 UI                      28 golden files, plus a test that every
                                       3xxx/4xxx/5xxx code has one
             6 explain                 golden prose and JSON over the example
                                       programs, plus the unwritten facts
```

### UI tests

`crates/raly/tests/ui/` holds one `.raly` file per error class, each paired with
the exact rendered output it must produce. This is the enforcement mechanism
decision 5 asks for: a change to what a user reads becomes a reviewable diff
rather than something that drifts while a `contains("RALY4007")` assertion
stays green.

```
RALY_BLESS=1 cargo test -p raly --test ui    # re-record, then read the diff
```

Both the binary and the UI tests go through `raly::compile`, so a golden file
asserts on exactly the bytes a user sees. A second test walks the code registry
and fails if any resolution, type or capacity code has no UI test, which catches
the failure mode where a diagnostic is added and never regression-tested.

Several rendering tests assert on the **exact** text a user sees, character for
character. That is deliberate: a change to diagnostic layout should be a change
somebody had to look at and approve.

Two properties get their own tests because they are the ones that would be
expensive to discover late: that the tree covers every token of both a valid and
a broken program with no gaps, and that fourteen kinds of pathological input
(unbalanced brackets, runs of keywords, empty files) terminate and still yield a
tree.

## Not implemented

The following features are not implemented.

### Not in the type system

- **No polymorphism over spaces.** A function is written against named spaces;
  there is no `fn f[S: Space](v: Vec[S])`. Every generic-looking program has to
  be written once per space. This is the largest gap, and it is the next thing
  a real model would ask for.
- **No *load* coercions.** Decision 4 calls for Futhark-style *explicit*
  coercions where the checker cannot see through a size. `broadcast(v, S)` is
  now exactly that for a **space** — see [No silent
  broadcasting](#no-silent-broadcasting) — but there is still no syntax for
  coercing a *load*, so an annotation whose load the checker cannot satisfy is
  simply an error. Interval intersection absorbs most of what a load coercion
  would be needed for, but not all of it.
- **Row variables are anonymous.** A row is open or closed; there is no way to
  name a tail and thread it through a signature, so "returns whatever roles it
  was given, plus `Time`" cannot be written down.
- **Cleanliness is a flag, not an effect.** `clean`/`noisy` is tracked, and
  unbind depth is counted, but neither participates in an effect system and
  neither can be abstracted over.
- **`bind` does not require a role key.** Binding two plain atoms is allowed
  (it is legal VSA), so a keyed record built with a non-role key produces a
  vector with an empty schema rather than a diagnostic. Only `unbind` insists
  on a declared role.
- **Load through `bind` is an upper bound, not an identity.** Binding is
  modelled as multiplying loads, which is right for bind-distributes-over-bundle
  but conservative when operands share structure.
- **No exhaustive constant folding.** Dimensions and `load` counts fold over
  integer literals, top-level `let` constants, and `+ - * /`. Anything else
  becomes a free variable of the dimension group (so equality still works) or,
  for a `load`, an error.
- **Codebook provenance is not tracked.** A space fixes *which* codebook, and
  two spaces are distinguished by identity, but nothing follows the semantics
  note's `coherence: unknown` marking for learned codebooks. A learned codebook
  invalidates every capacity number in this README, and the compiler cannot
  currently tell.
- **Capacity is one curve.** The measured numbers are for MAP/bipolar, a
  1000-atom codebook, 95% retrieval, flat bundles. Capacity also falls as the
  cleanup pool grows, and the checker does not model that. Nested-structure
  capacity has no agreed closed form and is handled only by the depth rule.

### Not in the compiler at all

- **VSA IR and codegen.** The typed ledger is a sidecar over the checked AST,
  not a lowering IR. There is no optimisation or code-generation backend.
- **Semantics for the VSA operations.** `bind`, `bundle`, `permute`, `unbind`
  and `cleanup` are type-checked and represented in the ledger, but what they
  *compute* is not implemented. `raly run` currently executes only pure
  top-level constants.
- **`struct`, `enum`, `match`, `for`.** Reserved, and parsed to a dedicated
  "recognised but not implemented" diagnostic (`RALY2007`). `for` in particular
  waits on the checker being able to count loop iterations — the checker can
  now count a bundle, but not a loop that bundles once per timestep, which is
  the canonical broken program the semantics note describes.
- **Multi-file compilation.** `SourceMap` holds many files and spans carry a
  `FileId`, but the driver only ever loads one. `import` parses and resolves to
  nothing; multi-segment paths are skipped by name resolution rather than
  reported, because reporting them would be noise until modules exist.
- **Mutation.** `let mut` parses and is otherwise ignored; there is no
  assignment syntax, so mutability has nothing to permit yet.
- **Incrementality.** Phases are pure functions with no ambient state, which is
  salsa's required shape, but there is no query engine, no caching and no
  invalidation. That is decision 1, on purpose.
- **JSON diagnostics and applicability.** `Diagnostic` is structured data and a
  second renderer would be mechanical, but only the ANSI/plain one exists, and
  suggestions do not yet carry a rustc-style `Applicability`.
- **Block comments, raw strings, char literals, literal suffixes.** Not in the
  brief, so not invented.
