//! The Raly compilation pipeline, as one pure function.
//!
//! The binary and the UI tests both go through [`compile`], so what a test
//! asserts on is exactly what a user sees. That matters more than it sounds:
//! decision 5 of `docs/compiler-architecture.md` makes diagnostics the
//! product, and a golden test that renders through a second code path is a
//! test of the second code path.
//!
//! ```
//! let compiled = raly::compile("m.raly", "space S = MAP[1024]\n");
//! assert!(!compiled.has_errors());
//! ```

#![deny(missing_debug_implementations)]

use raly_diag::{Diagnostics, FileId, RenderConfig, Renderer, Severity, SourceMap};
use raly_lexer::Token;

/// One file, taken all the way through the front end.
#[derive(Debug)]
pub struct Compilation {
    pub sources: SourceMap,
    pub file: FileId,
    pub tokens: Vec<Token>,
    pub ast: raly_ast::Ast,
    pub resolved: raly_resolve::Resolved,
    pub checked: raly_types::Checked,
    /// Every diagnostic from every phase, in source order.
    pub diagnostics: Diagnostics,
}

impl Compilation {
    pub fn has_errors(&self) -> bool {
        self.diagnostics.has_errors()
    }

    /// What this program *is*, in plain English, derived entirely from its
    /// types. See `raly-explain`.
    pub fn explain(&self) -> raly_explain::Explanation {
        raly_explain::explain(
            &self.ast,
            &self.resolved,
            &self.checked,
            self.sources.get(self.file).name(),
        )
    }

    /// Materialize the typed, content-addressed execution sidecar.
    pub fn ledger(&self) -> Result<raly_ledger::Ledger, raly_ledger::BuildError> {
        raly_ledger::Ledger::build(&self.ast, &self.resolved, &self.checked)
    }

    /// The diagnostics as a user would see them, plus the summary line.
    ///
    /// Empty when nothing was reported, so a clean file has an empty golden
    /// file rather than a file containing a blank line.
    pub fn render(&self, config: RenderConfig) -> String {
        if self.diagnostics.is_empty() {
            return String::new();
        }
        let renderer = Renderer::with_config(&self.sources, config);
        let mut out = renderer.render_all(&self.diagnostics);
        out.push('\n');
        out.push_str(&renderer.summary(
            self.diagnostics.count(Severity::Error),
            self.diagnostics.count(Severity::Warning),
        ));
        out
    }
}

/// Lex, parse, resolve and type-check one source file.
///
/// Every phase recovers, so this reports **everything** that is wrong in one
/// run: a syntax error does not silence name resolution, and an unresolved
/// name does not silence the type checker. No phase returns a `Result`; each
/// returns a value plus diagnostics, and unrecoverable regions become error
/// nodes and error bindings that later phases treat as compatible with
/// anything.
pub fn compile(name: impl Into<String>, text: impl Into<String>) -> Compilation {
    let mut sources = SourceMap::new();
    let file = sources.add(name, text);
    let mut diagnostics = Diagnostics::new();

    let lexed = raly_lexer::lex(file, sources.get(file).text());
    diagnostics.extend(lexed.diagnostics);

    let parsed = raly_parse::parse(file, sources.get(file).text(), &lexed.tokens);
    diagnostics.extend(parsed.diagnostics);

    let resolved = raly_resolve::resolve(&parsed.ast);
    let checked = raly_types::check(&parsed.ast, &resolved);
    // Cloned rather than moved so callers can still inspect the phase output.
    diagnostics.extend(resolved.diagnostics.iter().cloned());
    diagnostics.extend(checked.diagnostics.iter().cloned());
    diagnostics.sort_by_position();

    Compilation {
        sources,
        file,
        tokens: lexed.tokens,
        ast: parsed.ast,
        resolved,
        checked,
        diagnostics,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_clean_file_reports_nothing() {
        let compiled = compile("m.raly", "space S = MAP[1024]\nrole R in S\n");
        assert!(compiled.diagnostics.is_empty());
        assert_eq!(compiled.render(RenderConfig::plain()), "");
    }

    #[test]
    fn every_phase_speaks_in_one_run() {
        // A lexical error, a syntax error, a resolution error and a type error
        // in one file. All four must appear.
        let compiled = compile(
            "m.raly",
            "space S = MAP[1024]\nlet a = \"oops\nlet b = missing\nlet c: Int = true\n",
        );
        let text = compiled.render(RenderConfig::plain());
        assert!(text.contains("RALY1002"), "{text}");
        assert!(text.contains("RALY3001"), "{text}");
        assert!(text.contains("RALY4006"), "{text}");
    }

    /// GRAMMAR.md 7.3 scopes "identical" to width and family. Load and role
    /// schema are *combined* by these operations, not required to match, so
    /// requiring them identical would break the algebra rather than protect
    /// it. This is the test that keeps that decision honest.
    #[test]
    fn differing_load_and_roles_are_not_a_broadcast_question() {
        let compiled = compile(
            "m.raly",
            "space S = MAP[1024]
             role A, B in S
             fn f(x: Vec[S; load 2; roles {A}], y: Vec[S; load 3; roles {B}]) -> Vec[S; load 5]              { bundle(x, y) }
",
        );
        let text = compiled.render(RenderConfig::plain());
        assert!(!text.contains("RALY4012"), "{text}");
        assert!(!compiled.has_errors(), "{text}");
    }

    /// Two spaces agreeing on width and family but not on codebook stay
    /// RALY4003. No tensor library has a notion of a codebook, so there is
    /// nothing for it to have papered over, and calling that a broadcast
    /// error would be a lie about what happens elsewhere.
    #[test]
    fn a_codebook_difference_is_not_a_broadcast_error() {
        let compiled = compile(
            "m.raly",
            "space A = MAP[1024]
space B = MAP[1024]
             fn f(x: Sym[A], y: Sym[B]) -> Vec[A; load 2] { bundle(x, y) }
",
        );
        let text = compiled.render(RenderConfig::plain());
        assert!(text.contains("RALY4003"), "{text}");
        assert!(!text.contains("RALY4012"), "{text}");
    }

    /// The opt-in is the whole point: the intent stays expressible.
    #[test]
    fn an_explicit_broadcast_makes_the_error_go_away() {
        let compiled = compile(
            "m.raly",
            "space Wide = MAP[8192]
space Narrow = MAP[1024]
             fn f(x: Sym[Narrow], y: Sym[Wide]) -> Vec[Narrow; load 2; noisy]              { bundle(x, broadcast(y, Narrow)) }
",
        );
        let text = compiled.render(RenderConfig::plain());
        assert!(!compiled.has_errors(), "{text}");
    }
}
