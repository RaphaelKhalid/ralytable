//! The token cursor, the diagnostic helpers, and the recovery machinery.
//!
//! Everything in this module exists to serve one property: **the parser never
//! fails**. There is no `Result` anywhere in the crate. A production that
//! cannot be parsed emits a diagnostic, synthesises an `Error` node whose span
//! covers the tokens involved, resynchronises, and carries on. That is what
//! lets one run report every mistake in a file instead of the first.

use raly_ast::{Ast, Ident, Origin, Reason};
use raly_diag::{codes, Diagnostic, Diagnostics, FileId, Span};
use raly_lexer::{Token, TokenKind};

/// Tokens that can begin a top-level item, and therefore make safe places to
/// resume after a mess. `}` and `;` are included because they end the
/// construct the mess was probably inside.
pub(crate) const ITEM_STARTS: &[TokenKind] = &[
    TokenKind::Fn,
    TokenKind::Let,
    TokenKind::Space,
    TokenKind::Role,
    TokenKind::Type,
    TokenKind::Import,
    TokenKind::Struct,
    TokenKind::Enum,
];

/// Stop tokens for recovery inside a parameter list. `{` and `->` are here so
/// that a malformed parameter cannot swallow the function's body.
pub(crate) const PARAM_STOPS: &[TokenKind] = &[
    TokenKind::Comma,
    TokenKind::RParen,
    TokenKind::LBrace,
    TokenKind::Arrow,
    TokenKind::Fn,
    TokenKind::Let,
    TokenKind::Space,
    TokenKind::Role,
    TokenKind::Type,
    TokenKind::Import,
];

/// Stop tokens for recovery inside a block.
pub(crate) const STMT_STARTS: &[TokenKind] = &[
    TokenKind::Fn,
    TokenKind::Let,
    TokenKind::Space,
    TokenKind::Role,
    TokenKind::Type,
    TokenKind::Import,
    TokenKind::Return,
    TokenKind::If,
    TokenKind::Semi,
    TokenKind::RBrace,
];

pub(crate) struct Parser<'a> {
    pub(crate) file: FileId,
    src: &'a str,
    /// Significant tokens only — trivia removed — always ending in `Eof`.
    tokens: Vec<Token>,
    pos: usize,
    pub(crate) ast: Ast,
    pub(crate) diags: Diagnostics,
    /// True while a diagnostic has been reported and nothing has been consumed
    /// since. Suppresses the cascade of follow-on complaints that one mistake
    /// would otherwise produce.
    silenced: bool,
}

impl<'a> Parser<'a> {
    pub(crate) fn new(file: FileId, src: &'a str, tokens: &[Token]) -> Self {
        let mut significant: Vec<Token> = tokens
            .iter()
            .copied()
            .filter(|t| !t.is_trivia() && t.kind != TokenKind::Eof)
            .collect();
        let eof = tokens
            .iter()
            .rev()
            .find(|t| t.kind == TokenKind::Eof)
            .copied()
            .unwrap_or_else(|| Token::new(TokenKind::Eof, Span::point(file, src.len() as u32)));
        significant.push(eof);

        Parser {
            file,
            src,
            tokens: significant,
            pos: 0,
            ast: Ast::new(),
            diags: Diagnostics::new(),
            silenced: false,
        }
    }

    // -- inspection ---------------------------------------------------------

    pub(crate) fn position(&self) -> usize {
        self.pos
    }

    pub(crate) fn peek(&self) -> TokenKind {
        self.tokens[self.pos].kind
    }

    pub(crate) fn peek_at(&self, n: usize) -> TokenKind {
        self.tokens
            .get(self.pos + n)
            .map(|t| t.kind)
            .unwrap_or(TokenKind::Eof)
    }

    pub(crate) fn span(&self) -> Span {
        self.tokens[self.pos].span
    }

    /// The span of the token just consumed, or a zero-width span at the start
    /// of the file if nothing has been.
    pub(crate) fn prev_span(&self) -> Span {
        if self.pos == 0 {
            Span::point(self.file, 0)
        } else {
            self.tokens[self.pos - 1].span
        }
    }

    /// A zero-width span immediately after the previous token — where a
    /// missing token *should have been*.
    pub(crate) fn after_prev(&self) -> Span {
        Span::point(self.file, self.prev_span().end)
    }

    pub(crate) fn at(&self, kind: TokenKind) -> bool {
        self.peek() == kind
    }

    pub(crate) fn at_eof(&self) -> bool {
        self.peek() == TokenKind::Eof
    }

    pub(crate) fn text(&self, span: Span) -> &'a str {
        self.src.get(span.range()).unwrap_or("")
    }

    // -- consumption --------------------------------------------------------

    pub(crate) fn bump(&mut self) -> Token {
        let token = self.tokens[self.pos];
        if token.kind != TokenKind::Eof {
            self.pos += 1;
            // Real progress: the next mistake is a new mistake, not an echo.
            self.silenced = false;
        }
        token
    }

    pub(crate) fn eat(&mut self, kind: TokenKind) -> bool {
        if self.at(kind) {
            self.bump();
            true
        } else {
            false
        }
    }

    /// Consume `kind` or report `RALY2001`. Returns `None` on failure; the
    /// caller decides what to synthesise, and must not bail out.
    pub(crate) fn expect(&mut self, kind: TokenKind, purpose: &str) -> Option<Token> {
        if self.at(kind) {
            return Some(self.bump());
        }
        self.unexpected(&format!("expected {} {}", kind.describe(), purpose));
        None
    }

    /// Consume a closing bracket, or report it as unclosed with the opening
    /// bracket as a secondary label.
    pub(crate) fn expect_close(&mut self, kind: TokenKind, open: Span) -> Option<Token> {
        if self.at(kind) {
            return Some(self.bump());
        }
        if !self.silenced {
            let opener = self.text(open);
            let diag = Diagnostic::error(codes::UNCLOSED_DELIMITER, format!("unclosed `{opener}`"))
                .with_primary(self.span(), format!("expected {} here", kind.describe()))
                .with_secondary(open, format!("`{opener}` opened here is never closed"))
                .with_help(format!("add {} to close it", kind.describe()));
            self.diags.push(diag);
            self.silenced = true;
        }
        None
    }

    /// Report `RALY2001` against the current token, unless silenced.
    pub(crate) fn unexpected(&mut self, label: &str) {
        if self.silenced {
            return;
        }
        let found = self.peek();
        let mut diag = Diagnostic::error(
            codes::UNEXPECTED_TOKEN,
            format!("{}, found {}", label, found.describe()),
        )
        .with_primary(self.span(), label.to_string());

        if let Some(note) = reserved_operator_note(found) {
            diag = diag.with_note(note).with_help(
                "the VSA operations are written as calls: `bind(a, b)`, `bundle(a, b, c)`",
            );
        }
        if found.is_error() {
            // The lexer has already explained this token; do not repeat it,
            // just say why the parser stopped.
            diag = diag.with_note("this token was already reported as a lexical error");
        }
        self.diags.push(diag);
        self.silenced = true;
    }

    pub(crate) fn push(&mut self, diag: Diagnostic) {
        self.diags.push(diag);
    }

    /// Report a diagnostic and enter the suppression window.
    pub(crate) fn push_silencing(&mut self, diag: Diagnostic) {
        self.diags.push(diag);
        self.silenced = true;
    }

    pub(crate) fn is_silenced(&self) -> bool {
        self.silenced
    }

    // -- recovery -----------------------------------------------------------

    /// Skip tokens until one of `stops` is reached at bracket depth zero, or
    /// end of file. Returns the span covering everything skipped, so the
    /// caller can build an `Error` node that keeps the tree total.
    ///
    /// Depth tracking is what stops a stray token inside a nested call from
    /// abandoning the whole enclosing item.
    pub(crate) fn sync(&mut self, stops: &[TokenKind]) -> Span {
        let start = self.span().start;
        let mut end = start;
        let mut depth = 0i32;

        while !self.at_eof() {
            let kind = self.peek();
            match kind {
                TokenKind::LParen | TokenKind::LBracket | TokenKind::LBrace => depth += 1,
                TokenKind::RParen | TokenKind::RBracket | TokenKind::RBrace => {
                    if depth == 0 && stops.contains(&kind) {
                        break;
                    }
                    depth -= 1;
                    if depth < 0 {
                        // A closer for a bracket we never opened: hand it back
                        // to whoever is waiting for it.
                        break;
                    }
                }
                _ if depth == 0 && stops.contains(&kind) => break,
                _ => {}
            }
            end = self.span().end;
            self.pos += 1;
        }

        // Only a skip that actually consumed something counts as progress.
        // Otherwise a `sync` that stopped immediately would un-silence the
        // parser and let the same mistake be reported a second time by the
        // caller that is about to fail on the very same token.
        if end > start {
            self.silenced = false;
        }
        Span::new(self.file, start, end.max(start))
    }

    // -- node construction --------------------------------------------------

    /// Intern the text of a token as an identifier.
    pub(crate) fn ident_of(&mut self, token: Token) -> Ident {
        let text = self.text(token.span);
        self.ast.ident(text, token.span)
    }

    /// A synthetic identifier for a name that was missing, so that later
    /// phases have something to hold. Never collides with a real name.
    pub(crate) fn missing_ident(&mut self, span: Span) -> Ident {
        self.ast.ident("<missing>", span)
    }

    pub(crate) fn recovered(reason: Reason) -> Origin {
        Origin::Recovered(reason)
    }

    /// Span from `start` to the end of the last consumed token.
    pub(crate) fn span_from(&self, start: Span) -> Span {
        start.merge(self.prev_span())
    }

    /// Hand back the tree and the diagnostics. Consumes the parser.
    pub(crate) fn finish(self) -> (Ast, Diagnostics) {
        (self.ast, self.diags)
    }
}

/// Operators the lexer recognises but the expression grammar does not use.
///
/// Saying so explicitly is worth a lot here: a user reaching for `a ^ b` is
/// almost always reaching for a VSA operation, and GRAMMAR.md §8.1 explains
/// why those are deliberately not infix.
fn reserved_operator_note(kind: TokenKind) -> Option<&'static str> {
    matches!(
        kind,
        TokenKind::Caret
            | TokenKind::Tilde
            | TokenKind::At
            | TokenKind::Amp
            | TokenKind::Pipe
            | TokenKind::Question
    )
    .then_some(
        "`^`, `~`, `@`, `&`, `|` and `?` are reserved but are not expression operators in Raly",
    )
}
