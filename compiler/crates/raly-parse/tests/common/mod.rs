//! Shared harness for the parser test suites.
//!
//! Compiled into every test binary, so not every helper is used by every one.

#![allow(dead_code)]

use raly_ast::Ast;
use raly_diag::{RenderConfig, Renderer, SourceMap};
use raly_lexer::lex;
use raly_parse::{dump, parse, Parsed};

pub struct Run {
    pub sources: SourceMap,
    pub parsed: Parsed,
}

impl Run {
    pub fn ast(&self) -> &Ast {
        &self.parsed.ast
    }

    pub fn dump(&self) -> String {
        dump::dump(&self.parsed.ast)
    }

    /// Every diagnostic code, in source order.
    pub fn codes(&self) -> Vec<String> {
        self.parsed
            .diagnostics
            .iter()
            .map(|d| d.code.to_string())
            .collect()
    }

    pub fn rendered(&self) -> String {
        let renderer = Renderer::with_config(&self.sources, RenderConfig::plain());
        renderer.render_all(&self.parsed.diagnostics)
    }
}

/// Lex and parse `src`. Lexical diagnostics are asserted absent, so that a
/// parser test never accidentally passes because of a tokeniser complaint.
pub fn run(src: &str) -> Run {
    let mut sources = SourceMap::new();
    let file = sources.add("test.raly", src);
    let lexed = lex(file, sources.get(file).text());
    assert!(
        lexed.diagnostics.is_empty(),
        "this fixture was meant to lex cleanly, but did not"
    );
    let parsed = parse(file, sources.get(file).text(), &lexed.tokens);
    Run { sources, parsed }
}

/// Parse `src`, asserting it produces no diagnostics, and return the dump.
pub fn ok(src: &str) -> String {
    let run = run(src);
    assert!(
        run.parsed.diagnostics.is_empty(),
        "expected a clean parse, got:\n{}",
        run.rendered()
    );
    run.dump()
}

/// Parse `src`, asserting it produces at least one diagnostic.
pub fn err(src: &str) -> Run {
    let run = run(src);
    assert!(
        !run.parsed.diagnostics.is_empty(),
        "expected diagnostics, got a clean parse:\n{}",
        run.dump()
    );
    run
}

/// Assert that `haystack` contains every line of `needle`, in order, ignoring
/// indentation and ignoring byte offsets.
///
/// Offsets are stripped so that these tests assert *structure* — what nests
/// inside what, and in what order — without breaking every time an unrelated
/// character moves. Exact spans are pinned separately by `spans_are_exact`,
/// and covered wholesale by the totality tests.
pub fn contains_lines(haystack: &str, needle: &str) {
    let stripped: Vec<String> = haystack.lines().map(strip_spans).collect();
    let mut lines = stripped.iter().map(String::as_str);
    for want in needle
        .trim()
        .lines()
        .map(str::trim)
        .filter(|l| !l.is_empty())
    {
        let want = strip_spans(want);
        let want = want.as_str();
        assert!(
            lines.any(|got| got == want),
            "expected to find\n  {want}\nin\n{haystack}"
        );
    }
}

/// Remove a trailing ` @ 12..34` from a dump line, keeping any `[recovered]`
/// marker that follows it, and normalise indentation.
fn strip_spans(line: &str) -> String {
    let line = line.trim();
    let Some(at) = line.rfind(" @ ") else {
        return line.to_string();
    };
    let tail = &line[at + 3..];
    let (span, marker) = match tail.find("  [") {
        Some(i) => (&tail[..i], &tail[i..]),
        None => (tail, ""),
    };
    let is_span = span
        .split_once("..")
        .is_some_and(|(a, b)| is_digits(a) && is_digits(b));
    if !is_span {
        return line.to_string();
    }
    format!("{}{}", &line[..at], marker)
}

fn is_digits(s: &str) -> bool {
    !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())
}
