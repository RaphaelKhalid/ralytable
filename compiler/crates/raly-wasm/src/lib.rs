//! WebAssembly bindings for the Raly front end.
//!
//! The browser playground calls [`analyze`] on every keystroke and renders the
//! result itself. Everything crossing the boundary is **data**: tokens carry
//! spans and line/column pairs, diagnostics carry labelled spans and notes.
//! The one pre-rendered string handed over comes straight from the compiler's
//! own [`raly_diag::Renderer`], so the caret output in a browser is
//! character-for-character what the CLI prints.
//!
//! # What runs
//!
//! [`analyze`] calls [`raly::compile`], the same function the `raly` binary
//! runs for `raly check`. Lexing, parsing, name resolution and type checking
//! all happen in one pass, and every diagnostic from every phase is reported
//! together. Nothing here reimplements the driver, so the browser cannot drift
//! away from the command line.
//!
//! # Stability
//!
//! The JSON shape is the one the lexer-only build published, extended rather
//! than redesigned: `tokens`, `diagnostics`, `counts`, `rendered` and `phases`
//! all mean what they meant. `phases` now reports `ok` for all four phases
//! because all four run, and an `items` array names the top-level
//! declarations the parser built.

#![deny(missing_debug_implementations)]

use raly_ast::{Ast, ItemKind};
use raly_diag::diagnostic::{LabelStyle, NoteKind, Severity};
use raly_diag::{Diagnostic, RenderConfig, Renderer, SourceMap, Span};
use raly_lexer::{Token, TokenKind};
use serde::Serialize;
use wasm_bindgen::prelude::*;

/// The name reported for the in-browser buffer in diagnostic locators.
const BUFFER_NAME: &str = "playground.raly";

/// The version of the JSON shape returned by [`analyze`].
///
/// Still 1: every field the lexer-only build emitted is still emitted, with
/// the same meaning. New fields were added; none were removed or repurposed.
const API_VERSION: u32 = 1;

/// Status of one front-end phase.
#[derive(Serialize, Debug)]
#[serde(rename_all = "kebab-case")]
enum PhaseStatus {
    /// The phase ran to completion.
    Ok,
}

#[derive(Serialize, Debug)]
struct Phases {
    lex: PhaseStatus,
    parse: PhaseStatus,
    resolve: PhaseStatus,
    typecheck: PhaseStatus,
}

impl Phases {
    /// Every front-end phase runs on every call, so every one reports `ok`.
    /// Each phase recovers rather than bailing out, which is what makes that
    /// true even for input full of errors.
    fn all_ran() -> Self {
        Phases {
            lex: PhaseStatus::Ok,
            parse: PhaseStatus::Ok,
            resolve: PhaseStatus::Ok,
            typecheck: PhaseStatus::Ok,
        }
    }
}

/// A byte range plus the 1-based line/column pair at each end.
#[derive(Serialize, Debug)]
#[serde(rename_all = "camelCase")]
struct SpanJson {
    start: u32,
    end: u32,
    line: u32,
    column: u32,
    end_line: u32,
    end_column: u32,
}

impl SpanJson {
    fn new(sources: &SourceMap, span: Span) -> Self {
        let file = sources.get(span.file);
        let start = file.location(span.start);
        let end = file.location(span.end);
        SpanJson {
            start: span.start,
            end: span.end,
            line: start.line,
            column: start.column,
            end_line: end.line,
            end_column: end.column,
        }
    }
}

/// One token, with everything a syntax highlighter needs.
#[derive(Serialize, Debug)]
#[serde(rename_all = "camelCase")]
struct TokenJson {
    /// The variant name, e.g. `"Ident"`, `"Pipeline"`, `"UnterminatedStr"`.
    kind: String,
    /// A coarse bucket for colouring: `keyword`, `ident`, `number`, `string`,
    /// `comment`, `punct`, `error` or `eof`.
    class: &'static str,
    /// Human-readable name, exactly as diagnostics spell it.
    describe: &'static str,
    /// The source text the token was lexed from.
    text: String,
    span: SpanJson,
    trivia: bool,
    error: bool,
}

impl TokenJson {
    fn new(sources: &SourceMap, token: &Token) -> Self {
        TokenJson {
            kind: format!("{:?}", token.kind),
            class: class_of(token.kind),
            describe: token.kind.describe(),
            text: sources.snippet(token.span).to_string(),
            span: SpanJson::new(sources, token.span),
            trivia: token.is_trivia(),
            error: token.kind.is_error(),
        }
    }
}

/// The highlighting bucket a token kind belongs to.
fn class_of(kind: TokenKind) -> &'static str {
    use TokenKind::*;
    match kind {
        LineComment => "comment",
        Ident => "ident",
        Int | Float => "number",
        Str => "string",
        UnterminatedStr | MalformedNumber | Error => "error",
        Eof => "eof",
        k if k.is_keyword() => "keyword",
        _ => "punct",
    }
}

/// One top-level declaration the parser built, so the page can show that a
/// tree exists rather than only a token stream.
#[derive(Serialize, Debug)]
struct ItemJson {
    /// `space`, `role`, `type`, `fn`, `let`, `import` or `error`.
    kind: &'static str,
    /// The declared name, or the names of a multi-name `role` joined with
    /// `", "`. Empty for `import` and for recovery placeholders.
    name: String,
    span: SpanJson,
}

impl ItemJson {
    fn all(sources: &SourceMap, ast: &Ast) -> Vec<ItemJson> {
        ast.root
            .iter()
            .map(|id| {
                let item = &ast.items[*id];
                let name = |ident: &raly_ast::Ident| ast.names.resolve(ident.symbol).to_string();
                let (kind, name) = match &item.kind {
                    ItemKind::Import(_) => ("import", String::new()),
                    ItemKind::Space(d) => ("space", name(&d.name)),
                    ItemKind::Role(d) => (
                        "role",
                        d.names.iter().map(name).collect::<Vec<_>>().join(", "),
                    ),
                    ItemKind::TypeAlias(d) => ("type", name(&d.name)),
                    ItemKind::Fn(d) => ("fn", name(&d.name)),
                    ItemKind::Let(d) => ("let", name(&d.name)),
                    ItemKind::Error => ("error", String::new()),
                };
                ItemJson {
                    kind,
                    name,
                    span: SpanJson::new(sources, item.span),
                }
            })
            .collect()
    }
}

#[derive(Serialize, Debug)]
struct LabelJson {
    /// `"primary"` (the fault site, drawn with `^`) or `"secondary"`
    /// (supporting context, drawn with `-`).
    style: &'static str,
    span: SpanJson,
    message: String,
}

#[derive(Serialize, Debug)]
struct NoteJson {
    /// `"note"` states a fact; `"help"` states an action. Never blurred.
    kind: &'static str,
    message: String,
}

#[derive(Serialize, Debug)]
#[serde(rename_all = "camelCase")]
struct DiagnosticJson {
    /// Stable identifier, e.g. `"RALY5001"`.
    code: String,
    /// The registry's one-line explanation of that code.
    code_description: &'static str,
    /// `"error"`, `"warning"` or `"advice"`.
    severity: &'static str,
    message: String,
    labels: Vec<LabelJson>,
    notes: Vec<NoteJson>,
    /// The span the editor should jump to when this diagnostic is clicked:
    /// the first primary label, else the first label of any style.
    focus: Option<SpanJson>,
    /// This one diagnostic as the compiler renders it: ASCII, no colour.
    rendered: String,
}

impl DiagnosticJson {
    fn new(sources: &SourceMap, renderer: &Renderer<'_>, diag: &Diagnostic) -> Self {
        DiagnosticJson {
            code: diag.code.as_str().to_string(),
            code_description: diag.code.description(),
            severity: diag.severity.as_str(),
            message: diag.message.clone(),
            labels: diag
                .labels
                .iter()
                .map(|label| LabelJson {
                    style: match label.style {
                        LabelStyle::Primary => "primary",
                        LabelStyle::Secondary => "secondary",
                    },
                    span: SpanJson::new(sources, label.span),
                    message: label.message.clone(),
                })
                .collect(),
            notes: diag
                .notes
                .iter()
                .map(|note| NoteJson {
                    kind: match note.kind {
                        NoteKind::Note => "note",
                        NoteKind::Help => "help",
                    },
                    message: note.message.clone(),
                })
                .collect(),
            focus: diag.focus().map(|span| SpanJson::new(sources, span)),
            rendered: renderer.render(diag),
        }
    }
}

#[derive(Serialize, Debug)]
struct Counts {
    errors: usize,
    warnings: usize,
    advice: usize,
    tokens: usize,
    lines: u32,
    /// Top-level declarations the parser built.
    items: usize,
}

/// Everything one call to [`analyze`] produces.
#[derive(Serialize, Debug)]
#[serde(rename_all = "camelCase")]
struct Analysis {
    /// Version of this API's shape, bumped only on a breaking change.
    api_version: u32,
    /// Which front-end phases ran. Nothing here is ever faked.
    phases: Phases,
    /// Every token in source order, including comments and the final `Eof`.
    tokens: Vec<TokenJson>,
    /// The top-level declarations, in source order.
    items: Vec<ItemJson>,
    /// Every problem found by every phase, in source order.
    diagnostics: Vec<DiagnosticJson>,
    counts: Counts,
    /// All diagnostics plus the summary line, rendered by the compiler,
    /// byte-for-byte as `raly check` prints them. Empty when there are none.
    rendered: String,
}

fn analyze_inner(source: &str) -> Analysis {
    let compiled = raly::compile(BUFFER_NAME, source);
    let sources = &compiled.sources;
    let renderer = Renderer::new(sources);

    Analysis {
        api_version: API_VERSION,
        phases: Phases::all_ran(),
        tokens: compiled
            .tokens
            .iter()
            .map(|t| TokenJson::new(sources, t))
            .collect(),
        items: ItemJson::all(sources, &compiled.ast),
        diagnostics: compiled
            .diagnostics
            .iter()
            .map(|d| DiagnosticJson::new(sources, &renderer, d))
            .collect(),
        counts: Counts {
            errors: compiled.diagnostics.count(Severity::Error),
            warnings: compiled.diagnostics.count(Severity::Warning),
            advice: compiled.diagnostics.count(Severity::Advice),
            tokens: compiled
                .tokens
                .iter()
                .filter(|t| !t.is_trivia() && t.kind != TokenKind::Eof)
                .count(),
            lines: sources.get(compiled.file).line_count(),
            items: compiled.ast.root.len(),
        },
        rendered: compiled.render(RenderConfig::plain()),
    }
}

/// Run the whole front end over `source` and return tokens, declarations and
/// diagnostics as structured data.
///
/// Total: any input, including arbitrary bytes and empty text, produces a
/// result rather than a panic or an exception.
#[wasm_bindgen]
pub fn analyze(source: String) -> Result<JsValue, JsValue> {
    serde_wasm_bindgen::to_value(&analyze_inner(&source))
        .map_err(|e| JsValue::from_str(&e.to_string()))
}

/// The same analysis as a JSON string, for callers that would rather parse it
/// themselves, and for testing on the host.
#[wasm_bindgen]
pub fn analyze_json(source: String) -> String {
    serde_json::to_string(&analyze_inner(&source))
        .unwrap_or_else(|e| format!("{{\"error\":\"{e}\"}}"))
}

/// Every reserved word in Raly, so a highlighter need not hard-code them.
#[wasm_bindgen]
pub fn keywords() -> Vec<String> {
    KEYWORDS.iter().map(|s| (*s).to_string()).collect()
}

const KEYWORDS: &[&str] = &[
    "space", "bind", "bundle", "permute", "unbind", "cleanup", "let", "fn", "type", "struct",
    "enum", "match", "if", "else", "for", "in", "return", "import", "where", "mut", "true",
    "false",
];

/// The compiler version this wasm module was built from.
#[wasm_bindgen]
pub fn version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clean_source_has_no_diagnostics() {
        let a = analyze_inner("space S = MAP[1024]\nrole R in S\n");
        assert!(a.diagnostics.is_empty());
        assert!(a.rendered.is_empty());
        assert_eq!(a.tokens[0].class, "keyword");
        assert_eq!(a.tokens[0].kind, "Space");
        assert_eq!(a.counts.items, 2);
        assert_eq!(a.items[0].kind, "space");
        assert_eq!(a.items[1].name, "R");
    }

    #[test]
    fn broken_source_reports_spans_and_notes() {
        let a = analyze_inner("fn main() {\n    let g = \"hello\n}\n");
        let d = a
            .diagnostics
            .iter()
            .find(|d| d.code == "RALY1002")
            .expect("the unterminated string is still reported");
        assert!(d.labels.iter().any(|l| l.style == "primary"));
        assert!(d.notes.iter().any(|n| n.kind == "help"));
        assert_eq!(d.focus.as_ref().unwrap().line, 2);
        assert!(d.rendered.contains('^'));
    }

    #[test]
    fn empty_input_is_total() {
        let a = analyze_inner("");
        assert_eq!(a.counts.tokens, 0);
        assert_eq!(a.tokens.len(), 1);
        assert!(a.diagnostics.is_empty());
        assert!(a.items.is_empty());
    }

    #[test]
    fn the_capacity_error_reaches_the_browser() {
        let a = analyze_inner(concat!(
            "space Sentences = MAP[384] where effective = 111\n",
            "\n",
            "fn f(a: Sym[Sentences], b: Sym[Sentences],\n",
            "     c: Sym[Sentences], d: Sym[Sentences]) -> Vec[Sentences] {\n",
            "    bundle(a, b, c, d)\n",
            "}\n",
        ));
        let d = a
            .diagnostics
            .iter()
            .find(|d| d.code == "RALY5001")
            .expect("RALY5001 must be reachable from the playground");
        assert!(d.message.contains("holds 3"), "{}", d.message);
        assert!(d.rendered.contains('^'));
        assert!(d.notes.iter().any(|n| n.kind == "help"));
        assert!(a.rendered.contains("RALY5001"));
    }

    #[test]
    fn every_phase_speaks_in_one_run() {
        let a = analyze_inner(
            "space S = MAP[1024]\nlet a = \"oops\nlet b = missing\nlet c: Int = true\n",
        );
        let codes: Vec<&str> = a.diagnostics.iter().map(|d| d.code.as_str()).collect();
        assert!(codes.contains(&"RALY1002"), "{codes:?}");
        assert!(codes.contains(&"RALY3001"), "{codes:?}");
        assert!(codes.contains(&"RALY4006"), "{codes:?}");
    }

    #[test]
    fn json_uses_the_documented_shape() {
        let s = analyze_json("let x = 5 \u{d7} 3".to_string());
        assert!(s.contains("\"apiVersion\":1"));
        assert!(s.contains("RALY1001"));
        assert!(s.contains("\"endColumn\""));
        assert!(!s.contains("not-implemented"));
        assert!(s.contains("\"typecheck\":\"ok\""));
    }
}
