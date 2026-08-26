# Raly playground

A single page that runs the whole Raly front end in the browser. The
`logos`-based lexer, the recursive-descent parser, name resolution, the type
system and the hand-written diagnostic renderer from `compiler/crates/` are
compiled to WebAssembly; the page analyses the buffer on every keystroke and
draws the result itself. It calls `raly::compile`, the same function the `raly`
binary runs for `raly check`, so the browser cannot drift away from the command
line.

**It is already built.** `playground/wasm/` is committed, so a fresh clone
needs no Rust toolchain — just open the page.

## Run it

Either open `playground/index.html` directly (double-click, or
`file:///.../playground/index.html`), or serve the directory:

```bash
python -m http.server -d playground 8000
# then open http://localhost:8000/
```

Both work. The wasm module is embedded in the page's scripts as base64 rather
than fetched, so there is no `fetch()` to be blocked by a `file://` origin, no
CDN, and no network request of any kind.

## Rebuild the wasm

Rust may not be on `PATH` in a fresh shell. Prepend it first:

```bash
# Git Bash
export PATH="$HOME/.cargo/bin:$PATH"
```

```powershell
# PowerShell
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
```

One-time setup:

```bash
rustup target add wasm32-unknown-unknown
cargo install wasm-bindgen-cli --version 0.2.100
```

Then, from the repository root:

```bash
bash playground/build.sh
```

That runs the host-side tests, builds `raly-wasm` for
`wasm32-unknown-unknown`, runs `wasm-bindgen --target no-modules`, and
regenerates the base64 payload. It rewrites `playground/wasm/` in place; commit
the result so the demo keeps working without a toolchain.

The `wasm-bindgen` CLI version must match the `wasm-bindgen` crate version
pinned in `compiler/crates/raly-wasm/Cargo.toml` (`=0.2.100`). A mismatch
produces a "schema version mismatch" error at build time, not at runtime.

To build the wasm by hand instead:

```bash
cd compiler/crates/raly-wasm
cargo build --release --target wasm32-unknown-unknown
wasm-bindgen --target no-modules --no-typescript \
  --out-dir ../../../playground/wasm --out-name raly_wasm \
  target/wasm32-unknown-unknown/release/raly_wasm.wasm
```

…then re-run `build.sh` (or the Python block inside it) to refresh
`raly_wasm_embedded.js`, which is what the page actually loads.

## What is in here

```
playground/
├── index.html                  the page: markup, CSS, both themes
├── playground.js               editor, highlighting, diagnostics, tooltips
├── examples.js                 the preloaded programs
├── build.sh                    rebuilds wasm/ from compiler/crates/raly-wasm
└── wasm/                       generated, committed
    ├── raly_wasm_bg.wasm       the module (≈100 KB)
    ├── raly_wasm.js            wasm-bindgen glue
    └── raly_wasm_embedded.js   the module base64-encoded into a script
```

No libraries are vendored because none are used: the editor is a `<textarea>`
with a highlight layer behind it, coloured from the real token stream rather
than from a regular expression. Everything the page needs is in this
directory.

## The wasm API

`compiler/crates/raly-wasm` exposes four functions:

| Function | Returns |
| --- | --- |
| `analyze(source)` | The full analysis as a JS object |
| `analyze_json(source)` | The same thing as a JSON string |
| `keywords()` | Every reserved word, as an array of strings |
| `version()` | The compiler version the module was built from |

`analyze` returns **data, not rendered text**, so a caller can build its own
interface:

```jsonc
{
  "apiVersion": 1,
  "phases": { "lex": "ok", "parse": "ok", "resolve": "ok", "typecheck": "ok" },
  "tokens": [
    { "kind": "Let", "class": "keyword", "describe": "`let`", "text": "let",
      "span": { "start": 0, "end": 3, "line": 1, "column": 1,
                "endLine": 1, "endColumn": 4 },
      "trivia": false, "error": false }
  ],
  "diagnostics": [
    { "code": "RALY1002",
      "codeDescription": "a string literal reaches end of line …",
      "severity": "error",
      "message": "unterminated string literal",
      "labels": [ { "style": "primary", "span": { … },
                    "message": "this string is never closed" } ],
      "notes":  [ { "kind": "note", "message": "…" },
                  { "kind": "help", "message": "…" } ],
      "focus":  { … },
      "rendered": "error[RALY1002]: …"          // the compiler's own caret block
    }
  ],
  "items": [
    { "kind": "space", "name": "Sentences", "span": { … } },
    { "kind": "fn", "name": "quad", "span": { … } }
  ],
  "counts": { "errors": 1, "warnings": 0, "advice": 0,
              "tokens": 24, "lines": 7, "items": 2 },
  "rendered": "…"                                // every diagnostic, plus the summary
}
```

Two things worth knowing when writing against it:

- **`span.start` and `span.end` are byte offsets**, not JavaScript string
  indices. They agree for ASCII and diverge the moment a character is not, so
  convert before slicing a string or setting a selection. `playground.js` does
  this in `buildByteMap`.
- **`phases` is the honest part.** All four phases now report `"ok"` because
  all four run, on every call, on every input. Every phase recovers rather than
  bailing out, so a syntax error does not silence name resolution and an
  unresolved name does not silence the type checker: one call reports
  everything that is wrong.
- **`apiVersion` is still 1.** `items` and `counts.items` were added; nothing
  that was already in the shape changed meaning, so a caller written against
  the lexer-only build keeps working.

## What this demo does and does not prove

The whole front end is real, and it is the same code the CLI runs: the caret
blocks on the page are byte-identical to `raly check` on the same file. The
examples are taken from `compiler/crates/raly/tests/ui/` and
`compiler/examples/`, which are covered by the UI test suite, so if the checker
ever stops reporting what an example claims, a test fails before the page does.

What it does not do is run a program. There is no code generation and no
evaluator, so nothing on the page produces a vector. The capacity numbers come
from the bound measured in `experiments/04_capacity`, computed at compile time;
the page reports them, it does not measure them.
