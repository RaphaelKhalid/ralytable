# Raly — compiler front end

Infrastructure for the **Raly** language front end. Source files use the
`.raly` extension.

It **lexes, parses, and reports errors beautifully**. It does not type-check or
generate code — those are deliberately absent, see
[Deliberately not here yet](#deliberately-not-here-yet).

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
cargo test --workspace   # 154 tests, all passing
cargo clippy --workspace --all-targets   # clean
cargo fmt --all --check
```

### Trying it

```
cargo run -p raly -- check examples/scene.raly          # exits 0
cargo run -p raly -- parse examples/scene.raly          # dumps the tree
cargo run -p raly -- check examples/broken-syntax.raly  # 13 errors, exits 1
cargo run -p raly -- check examples/broken.raly         # lexical errors
cargo run -p raly -- lex   examples/tour.raly
```

| File | What it is |
| --- | --- |
| `examples/scene.raly` | A substantial, valid program: a role-filler scene memory. What real Raly looks like. |
| `examples/broken-syntax.raly` | One of each recoverable *syntax* error. All 13 are reported in a single run. |
| `examples/broken.raly` | One of each recoverable *lexical* error. |
| `examples/tour.raly` | Exercises every token class. A lexer fixture, **not** a valid program — `check` reports on it by design. |

`broken.raly` is the fastest way to see what the diagnostics look like:

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
| `raly check <file>` | Lex, parse, render all diagnostics to stderr, exit non-zero on error |

Flags: `--color` / `--no-color` (default off), `--explain` (append each code's
registry description), `-h`, `-V`.

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
    └── raly/                  the `raly` binary
```

### `raly-diag` — the important one

Built first and treated as the product, not as plumbing. Raly's entire pitch is
catching mistakes other languages let through silently, so what a user reads
when something is wrong *is* the deliverable.

- **Byte-offset spans.** `Span` is `(FileId, start, end)`. Line and column are
  derived only at render time by `SourceMap`, so no phase carries or maintains
  them. Columns count characters, not bytes, and tabs are expanded so carets
  land under the right glyph.
- **Stable codes.** Every diagnostic carries a `Code` like `RALY1002` whose
  meaning never changes and is never reused. Number ranges are reserved per
  phase (`0xxx` driver, `1xxx` lexical, `2xxx` syntax, `3xxx` resolution,
  `4xxx` types, `5xxx` capacity) so later phases need no renumbering. A unit
  test enforces uniqueness and format.
- **Two advice channels, kept apart.** `note:` states a fact
  (`this vector already holds 7 of 31 items`); `help:` states an action
  (`split the bundle, or declare a wider space`). Blurring the two is how error
  messages turn into paragraphs nobody reads. The capacity errors the type
  system will eventually need are exactly this shape, and the channel is here
  waiting for them.
- **Primary and secondary labels.** Primary underlines with `^` at the fault
  site; secondary underlines with `-` for supporting context, with its own
  `:::` locator line.
- **Deterministic ASCII by default.** Colour is opt-in and provably changes
  only the bytes, never the layout — there is a test for that. This is why the
  renderer is hand-written rather than using `ariadne` or `codespan-reporting`:
  the output is snapshot-asserted character-for-character in tests, and having
  no dependency in the crate everything else builds on is worth the ~250 lines.
  A different backend can be swapped in behind `Renderer` if that trade stops
  paying.

### `raly-lexer`

`logos`-generated, wrapped in a hand-written driver. The key property is that
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
  non-breaking spaces), which is where these almost always come from

Comments are lexed as trivia rather than discarded, so a formatter or
doc-comment pass has them later.

### `raly-ast`

Arena-based: nodes live in flat `Vec`s and reference each other by 32-bit `Id`
rather than `Box`. That is not a micro-optimisation — it makes side tables
(types, resolutions) trivial to hang off the same indices, keeps the tree
serialisable, and sidesteps the lifetime problems that make `&'ast Node` trees
painful to build during error recovery. Names are interned to `Symbol`. Every
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
  case. A checker can then decline to blame an expression that is not really
  there. This is the cheap-now, expensive-later kind of decision: the gap
  between good and bad error messages is mostly provenance.

`VsaCall` stores its operands twice: in source order for diagnostics, and in a
**canonical order** derived from `Ast::structural_key`. Binding and n-ary
bundling are commutative, so this makes commutativity structurally true rather
than a law each later pass has to remember. `bundle.left` deliberately gets no
canonical order — the fold is order-dependent, and that asymmetry in the AST is
the point.

### `raly-parse`

Hand-written recursive descent, with Pratt precedence climbing for expressions.
No parser generator, and no `Result` anywhere in the crate.

`parse(file, src, tokens) -> Parsed` is a pure function: no ambient state, no
global interner, no `&mut` compiler context threaded through. That is the shape
an incremental query engine would demand later, and keeping it costs nothing
now.

**Recovery** is panic mode with bracket-aware synchronisation sets:

- Skipping tracks bracket depth, so one stray token deep inside a call does not
  abandon the enclosing declaration.
- After a diagnostic, further "unexpected token" reports are suppressed until at
  least one token has been consumed. One mistake produces one message — there
  are tests pinning that for six different mistakes.
- Lexical errors are not re-reported. `123abc` is one diagnostic, not two.

The interesting diagnostics are the ones that encode the algebra rather than the
grammar. `bundle()` is `RALY2003` with a note explaining that superposition has
no identity element in any VSA family, so an empty bundle denotes no vector.
`bundle.foo` is `RALY2005`, and its help says that `bundle.left` is a different
function from `bundle`, not a spelling of it. `space S = 1024` is `RALY2010`,
pointing at both the dimension and the name, because family is part of a
vector's identity.

## Tests

154 tests: 150 unit and integration, plus 4 doctests.

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
raly        13 integration             exit codes, stdout/stderr discipline
```

Several rendering tests assert on the **exact** text a user sees, character for
character. That is deliberate: a change to diagnostic layout should be a change
somebody had to look at and approve.

Two properties get their own tests because they are the ones that would be
expensive to discover late: that the tree covers every token of both a valid and
a broken program with no gaps, and that fourteen kinds of pathological input
(unbalanced brackets, runs of keywords, empty files) terminate and still yield a
tree.

## Deliberately not here yet

Nothing below exists, and no part of it is stubbed, faked, or half-written.

- **Type system.** No types, no inference, no checking. Nothing verifies that a
  `load 3` is within capacity, that two vectors share a space, or that a role
  schema is satisfied. The AST *carries* every annotation the checker will need
  — space, load, role schema, cleanliness — and checks none of them.
- **Constant folding.** A space's dimension is stored as an arbitrary
  expression. Deciding that `2 * BASE_D` is a constant, and what it evaluates
  to, is the checker's job.
- **Name resolution.** No scopes, no bindings, no symbol table beyond the
  string interner.
- **IR and codegen.** No lowering, no optimisation, no backend. `raly` cannot
  produce an executable and does not pretend to.
- **Semantics for the operations.** `bind`, `bundle`, `permute`, `unbind` and
  `cleanup` parse, and their arities are enforced. What they *compute* is not
  implemented anywhere.
- **`struct`, `enum`, `match`, `for`.** Reserved, and parsed to a dedicated
  "recognised but not implemented" diagnostic (`RALY2007`) rather than a
  confusing syntax error. `for` in particular waits on the checker being able to
  count loop iterations against a space's capacity.
- **Multi-file compilation.** `SourceMap` holds many files and spans carry a
  `FileId`, but the driver only ever loads one. `import` does not resolve.
- **Block comments, raw strings, char literals, literal suffixes.** Not in the
  brief, so not invented.
