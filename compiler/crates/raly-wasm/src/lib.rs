//! WebAssembly bindings for the Raly front end.
//!
//! The browser playground calls [`analyze`] on every keystroke and renders the
//! result itself. Everything crossing the boundary is **data**: tokens carry
//! spans and line/column pairs, diagnostics carry labelled spans and notes.
//! The one pre-rendered string handed over comes straight from the compiler's
//! own [`raly_diag::Renderer`], so the caret output in a browser is
//! character-for-character what the CLI prints.
//!
//! # Stability
//!
//! The shape is designed so a parser can be slotted in later without any
//! change to the API. `analyze` already reports a `phases` object naming each
//! front-end phase and its status; when parsing lands it flips from
//! `"not-implemented"` to `"ok"`, an `ast` field appears alongside `tokens`,
//! and syntax diagnostics simply join the existing `diagnostics` array.
//! Callers written against today's output keep working untouched.

#![deny(missing_debug_implementations)]

use raly_diag::diagnostic::{LabelStyle, NoteKind, Severity};
use raly_diag::{Diagnostic, Renderer, SourceMap, Span};
use raly_lexer::{lex, Token, TokenKind};
use serde::Serialize;
use wasm_bindgen::prelude::*;

/// The name reported for the in-browser buffer in diagnostic locators.
const BUFFER_NAME: &str = "playground.raly";

/// The version of the JSON shape returned by [`analyze`].
const API_VERSION: u32 = 1;

/// Status of one front-end phase.
///
/// Present from day one so that adding `parse` later is not an API change.
#[derive(Serialize, Debug)]
#[serde(rename_all = "kebab-case")]
enum PhaseStatus {
    /// The phase ran to completion.
    Ok,
    /// The phase exists as a plan but is not written yet. Nothing is faked.
    NotImplemented,
}

#[derive(Serialize, Debug)]
struct Phases {
    lex: PhaseStatus,
    parse: PhaseStatus,
    resolve: PhaseStatus,
    typecheck: PhaseStatus,
}

impl Phases {
    fn lexed_only() -> Self {
        Phases {
            lex: PhaseStatus::Ok,
            parse: PhaseStatus::NotImplemented,
            resolve: PhaseStatus::NotImplemented,
            typecheck: PhaseStatus::NotImplemented,
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
    /// Stable identifier, e.g. `"RALY1002"`.
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
    /// Every problem found, in source order.
    diagnostics: Vec<DiagnosticJson>,
    counts: Counts,
    /// All diagnostics plus the summary line, rendered by the compiler.
    /// Empty when there are none.
    rendered: String,
}

fn analyze_inner(source: &str) -> Analysis {
    let mut sources = SourceMap::new();
    let file = sources.add(BUFFER_NAME, source);
    let text = sources.get(file).text().to_string();

    let mut lexed = lex(file, &text);
    lexed.diagnostics.sort_by_position();

    let renderer = Renderer::new(&sources);
    let errors = lexed.diagnostics.count(Severity::Error);
    let warnings = lexed.diagnostics.count(Severity::Warning);
    let advice = lexed.diagnostics.count(Severity::Advice);

    let rendered = if lexed.diagnostics.is_empty() {
        String::new()
    } else {
        let mut out = renderer.render_all(lexed.diagnostics.iter());
        out.push_str(&renderer.summary(errors, warnings));
        out
    };

    Analysis {
        api_version: API_VERSION,
        phases: Phases::lexed_only(),
        tokens: lexed
            .tokens
            .iter()
            .map(|t| TokenJson::new(&sources, t))
            .collect(),
        diagnostics: lexed
            .diagnostics
            .iter()
            .map(|d| DiagnosticJson::new(&sources, &renderer, d))
            .collect(),
        counts: Counts {
            errors,
            warnings,
            advice,
            tokens: lexed.significant().count(),
            lines: sources.get(file).line_count(),
        },
        rendered,
    }
}

/// Lex `source` and return the tokens and diagnostics as structured data.
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
        let a = analyze_inner("let x = 1 |> f\n");
        assert!(a.diagnostics.is_empty());
        assert!(a.rendered.is_empty());
        assert_eq!(a.tokens[0].class, "keyword");
        assert_eq!(a.tokens[0].kind, "Let");
    }

    #[test]
    fn broken_source_reports_spans_and_notes() {
        let a = analyze_inner("fn main() {\n    let g = \"hello\n}\n");
        assert_eq!(a.counts.errors, 1);
        let d = &a.diagnostics[0];
        assert_eq!(d.code, "RALY1002");
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
    }

    #[test]
    fn json_uses_the_documented_shape() {
        let s = analyze_json("let x = 5 \u{d7} 3".to_string());
        assert!(s.contains("\"apiVersion\":1"));
        assert!(s.contains("RALY1001"));
        assert!(s.contains("\"not-implemented\""));
        assert!(s.contains("\"endColumn\""));
    }
}
