# Raly — compiler skeleton

Infrastructure for the **Raly** language front end. Source files use the
`.raly` extension.

This is **scaffolding, not a compiler**. It lexes and it reports errors
beautifully. It does not parse, type-check, or generate code — those are
deliberately absent, see [Deliberately not here yet](#deliberately-not-here-yet).
The language's grammar and semantics are being designed separately; this repo
holds the machinery that grammar will drop into.

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
cargo test               # 71 tests, all passing
cargo clippy --workspace --all-targets   # clean
cargo fmt --all --check
```

### Trying it

```
cargo run -p raly -- lex   examples/tour.raly
cargo run -p raly -- check examples/tour.raly     # exits 0
cargo run -p raly -- check examples/broken.raly   # exits 1
```

`examples/tour.raly` exercises every token class. `examples/broken.raly`
contains one of each recoverable lexical error, and is the fastest way to see
what the diagnostics look like:

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
| `raly check <file>` | Lex, render all diagnostics to stderr, exit non-zero on error |

Flags: `--color` / `--no-color` (default off), `--explain` (append each code's
registry description), `-h`, `-V`.

Exit codes: `0` success · `1` the input contained errors · `2` bad command line
or unreadable file.

## Crate layout

```
compiler/
├── Cargo.toml                 workspace root (Rust 2021)
├── examples/                  .raly files for manual smoke-testing
└── crates/
    ├── raly-diag/             spans, diagnostics, rendering   [no dependencies]
    ├── raly-lexer/            tokeniser                       [logos]
    ├── raly-ast/              provisional arena AST + visitor
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

**The node definitions are explicitly provisional and marked as such in the
source.** They encode no precedence, no evaluation order, and no meaning for
any keyword. `ExprKind::Op` records an operator token verbatim with a flat
operand list precisely so that no precedence decision could be smuggled in
under cover of "scaffolding". Type annotations are stored as opaque source
text for the same reason. Expect `ExprKind`, `ItemKind` and `TypeExprKind` to
be **replaced**, not extended, when the grammar lands; the extension points are
commented in `crates/raly-ast/src/node.rs`.

## Tests

71 tests: 65 unit and integration, plus 3 doctests and the CLI suite.

```
raly-diag   3 unit + 21 integration   source map, spans, rendered output
raly-lexer  32 integration            one group per token class, comments,
                                      string edge cases, recovery, totality
raly-ast    4 unit                    arena, interner, visitor walk and prune
raly        8 integration             exit codes, stdout/stderr discipline
```

Several rendering tests assert on the **exact** text a user sees, character for
character. That is deliberate: a change to diagnostic layout should be a change
somebody had to look at and approve.

## Deliberately not here yet

Nothing below exists, and no part of it is stubbed, faked, or half-written.

- **Parser.** No grammar, no precedence table, no parse function. `raly check`
  stops after lexing. Nothing currently produces an `Ast` except tests building
  one by hand.
- **Type system.** No types, no inference, no checking. This is where the
  interesting design work is happening elsewhere, which is exactly why
  `raly-ast` stores annotations opaquely instead of guessing.
- **Name resolution.** No scopes, no bindings, no symbol table beyond the
  string interner.
- **IR and codegen.** No lowering, no optimisation, no backend. `raly` cannot
  produce an executable and does not pretend to.
- **Semantics for the reserved keywords.** `space`, `bind`, `bundle`,
  `permute`, `unbind` and `cleanup` are reserved words that lex to distinct
  tokens and mean nothing yet. Reserving them now is the only commitment made.
- **Multi-file compilation.** `SourceMap` holds many files and spans carry a
  `FileId`, but the driver only ever loads one. `import` does not resolve.
- **Block comments, raw strings, char literals, literal suffixes.** Not in the
  brief, so not invented.
