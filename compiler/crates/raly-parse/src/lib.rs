//! A hand-written recursive-descent parser for the Raly language.
//!
//! The grammar it implements is written down in `compiler/GRAMMAR.md`, which
//! is normative: where the two disagree, one of them is a bug. Read that first
//! for *why* the language looks the way it does; this crate is the *how*.
//!
//! # Shape
//!
//! ```
//! use raly_diag::SourceMap;
//! use raly_lexer::lex;
//! use raly_parse::parse;
//!
//! let mut sources = SourceMap::new();
//! let file = sources.add("m.raly", "space S = MAP[1024]\n");
//! let lexed = lex(file, sources.get(file).text());
//! let parsed = parse(file, sources.get(file).text(), &lexed.tokens);
//!
//! assert!(parsed.diagnostics.is_empty());
//! assert_eq!(parsed.ast.root.len(), 1);
//! ```
//!
//! [`parse`] is a pure function of its inputs: no ambient state, no global
//! interner, no `&mut` compiler context. That is the shape an incremental
//! query engine would demand later, and keeping it costs nothing now.
//!
//! # It never fails
//!
//! There is no `Result` in this crate's public API, and none in its internals
//! either. A file that does not parse still yields a tree — with `Error` nodes
//! covering the regions the parser could not understand — plus a list of
//! diagnostics. Three things depend on that:
//!
//! * **Multiple errors per run.** Bailing on the first one means a user fixes
//!   ten mistakes in ten edit–compile cycles.
//! * **Downstream phases.** Name resolution and type checking can walk a
//!   broken file and report what they *can* see, instead of going silent
//!   behind a syntax error.
//! * **Tooling.** An editor asks for a tree on every keystroke, and most
//!   keystrokes leave the file syntactically invalid.
//!
//! Every `Error` node records *why* it exists via [`raly_ast::Origin`], so a
//! later phase can decline to blame an expression the user never wrote.
//!
//! # Recovery strategy
//!
//! Panic mode with bracket-aware synchronisation sets, described in
//! GRAMMAR.md §10. Two details matter in practice:
//!
//! * Skipping tracks bracket depth, so one stray token deep inside a call does
//!   not abandon the enclosing declaration.
//! * After a diagnostic, further "unexpected token" reports are suppressed
//!   until at least one token has been consumed successfully. One mistake
//!   produces one message.

#![deny(missing_debug_implementations)]

mod cursor;
mod exprs;
mod items;
mod types;

pub mod dump;

use raly_ast::Ast;
use raly_diag::{Diagnostics, FileId};
use raly_lexer::Token;

use crate::cursor::Parser;

/// The result of parsing one file: always a tree, plus whatever went wrong.
#[derive(Debug)]
pub struct Parsed {
    /// Total over the input. Every significant token lies inside some node.
    pub ast: Ast,
    /// Syntax problems only. Lexical diagnostics come from [`raly_lexer::lex`]
    /// and are not repeated here.
    pub diagnostics: Diagnostics,
}

impl Parsed {
    pub fn has_errors(&self) -> bool {
        self.diagnostics.has_errors()
    }
}

/// Parse `tokens`, which must be the tokens of `src`, which must be the text
/// of `file`.
///
/// Never panics and never bails out early.
pub fn parse(file: FileId, src: &str, tokens: &[Token]) -> Parsed {
    let mut parser = Parser::new(file, src, tokens);
    parser.parse_program();
    let (ast, mut diagnostics) = parser.finish();
    diagnostics.sort_by_position();
    Parsed { ast, diagnostics }
}
