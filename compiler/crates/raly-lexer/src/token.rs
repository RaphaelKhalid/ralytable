//! The token set.
//!
//! The operator and keyword lists here are fixed by the language brief. The
//! *meaning* of each keyword is not decided in this crate — the lexer only
//! promises that these words are reserved and will never be usable as
//! identifiers, so the grammar can claim them later without a breaking change.

use logos::Logos;
use raly_diag::Span;

/// A lexical token: a kind plus the byte range it came from.
///
/// Tokens carry no text. Call [`crate::Lexed::text`] or index the source with
/// [`Span::range`] when the spelling is needed; this keeps tokens `Copy` and
/// keeps the source the single owner of its own bytes.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Token {
    pub kind: TokenKind,
    pub span: Span,
}

impl Token {
    pub fn new(kind: TokenKind, span: Span) -> Self {
        Token { kind, span }
    }

    /// Trivia is anything the grammar ignores: currently comments only.
    /// Whitespace is dropped by the lexer and never becomes a token.
    pub fn is_trivia(&self) -> bool {
        self.kind.is_trivia()
    }
}

/// Every kind of token Raly recognises.
///
/// `Error` is emitted in place of text the lexer could not classify, so that
/// token positions stay aligned with the source and later phases can keep
/// going. Every `Error` token has a matching diagnostic.
#[derive(Logos, Clone, Copy, PartialEq, Eq, Hash, Debug)]
#[logos(skip r"[ \t\r\n\f]+")]
pub enum TokenKind {
    // -- trivia -------------------------------------------------------------
    /// `// ...` to the end of the line. Retained rather than discarded so a
    /// formatter or doc-comment pass can use it later.
    #[regex(r"//[^\r\n]*", allow_greedy = true)]
    LineComment,

    // -- literals and names -------------------------------------------------
    #[regex(r"[A-Za-z][A-Za-z0-9_]*")]
    #[regex(r"_[A-Za-z0-9_]+")]
    Ident,

    #[regex(r"[0-9][0-9_]*")]
    #[regex(r"0[xX][0-9a-fA-F][0-9a-fA-F_]*")]
    #[regex(r"0[bB][01][01_]*")]
    Int,

    #[regex(r"[0-9][0-9_]*\.[0-9][0-9_]*([eE][+-]?[0-9][0-9_]*)?")]
    #[regex(r"[0-9][0-9_]*[eE][+-]?[0-9][0-9_]*")]
    Float,

    /// A complete, closed string literal. Escape sequences inside are checked
    /// separately, so a `Str` token may still have produced diagnostics.
    #[regex(r#""([^"\\\r\n]|\\[^\r\n])*""#)]
    Str,

    /// A string literal that reached a newline or end of file with no closing
    /// quote. Recoverable: the token is still produced.
    #[regex(r#""([^"\\\r\n]|\\[^\r\n])*"#)]
    UnterminatedStr,

    /// Digits followed by letters, e.g. `123abc`, `0x`, `1e`. Recoverable.
    #[regex(r"[0-9][0-9a-zA-Z_]*", priority = 1)]
    MalformedNumber,

    // -- keywords -----------------------------------------------------------
    #[token("let")]
    Let,
    #[token("fn")]
    Fn,
    #[token("type")]
    Type,
    #[token("struct")]
    Struct,
    #[token("enum")]
    Enum,
    #[token("match")]
    Match,
    #[token("if")]
    If,
    #[token("else")]
    Else,
    #[token("for")]
    For,
    #[token("in")]
    In,
    #[token("return")]
    Return,
    #[token("import")]
    Import,
    #[token("space")]
    Space,
    #[token("bind")]
    Bind,
    #[token("bundle")]
    Bundle,
    #[token("permute")]
    Permute,
    #[token("unbind")]
    Unbind,
    #[token("cleanup")]
    Cleanup,
    #[token("where")]
    Where,
    #[token("mut")]
    Mut,
    #[token("true")]
    True,
    #[token("false")]
    False,

    // -- operators and punctuation -----------------------------------------
    #[token("->")]
    Arrow,
    #[token("=>")]
    FatArrow,
    #[token("|>")]
    Pipeline,
    #[token("::")]
    ColonColon,
    #[token(":")]
    Colon,
    #[token(",")]
    Comma,
    #[token(";")]
    Semi,
    #[token(".")]
    Dot,
    #[token("==")]
    EqEq,
    #[token("=")]
    Eq,
    #[token("+")]
    Plus,
    #[token("-")]
    Minus,
    #[token("*")]
    Star,
    #[token("/")]
    Slash,
    #[token("@")]
    At,
    #[token("|")]
    Pipe,
    #[token("&")]
    Amp,
    #[token("^")]
    Caret,
    #[token("~")]
    Tilde,
    #[token("<=")]
    LtEq,
    #[token(">=")]
    GtEq,
    #[token("<")]
    Lt,
    #[token(">")]
    Gt,
    #[token("?")]
    Question,
    #[token("!")]
    Bang,
    #[token("_")]
    Underscore,

    // -- brackets -----------------------------------------------------------
    #[token("(")]
    LParen,
    #[token(")")]
    RParen,
    #[token("[")]
    LBracket,
    #[token("]")]
    RBracket,
    #[token("{")]
    LBrace,
    #[token("}")]
    RBrace,

    /// Text the lexer could not classify at all. Always accompanied by a
    /// diagnostic; never panics.
    Error,

    /// Synthetic zero-width token at the end of input. Always last.
    Eof,
}

impl TokenKind {
    pub fn is_trivia(&self) -> bool {
        matches!(self, TokenKind::LineComment)
    }

    /// True for kinds that only exist to keep recovery going.
    pub fn is_error(&self) -> bool {
        matches!(
            self,
            TokenKind::Error | TokenKind::UnterminatedStr | TokenKind::MalformedNumber
        )
    }

    pub fn is_keyword(&self) -> bool {
        use TokenKind::*;
        matches!(
            self,
            Let | Fn
                | Type
                | Struct
                | Enum
                | Match
                | If
                | Else
                | For
                | In
                | Return
                | Import
                | Space
                | Bind
                | Bundle
                | Permute
                | Unbind
                | Cleanup
                | Where
                | Mut
                | True
                | False
        )
    }

    /// A short human-readable name, for use in diagnostic messages.
    pub fn describe(&self) -> &'static str {
        use TokenKind::*;
        match self {
            LineComment => "a comment",
            Ident => "an identifier",
            Int => "an integer literal",
            Float => "a float literal",
            Str => "a string literal",
            UnterminatedStr => "an unterminated string literal",
            MalformedNumber => "a malformed numeric literal",
            Let => "`let`",
            Fn => "`fn`",
            Type => "`type`",
            Struct => "`struct`",
            Enum => "`enum`",
            Match => "`match`",
            If => "`if`",
            Else => "`else`",
            For => "`for`",
            In => "`in`",
            Return => "`return`",
            Import => "`import`",
            Space => "`space`",
            Bind => "`bind`",
            Bundle => "`bundle`",
            Permute => "`permute`",
            Unbind => "`unbind`",
            Cleanup => "`cleanup`",
            Where => "`where`",
            Mut => "`mut`",
            True => "`true`",
            False => "`false`",
            Arrow => "`->`",
            FatArrow => "`=>`",
            Pipeline => "`|>`",
            ColonColon => "`::`",
            Colon => "`:`",
            Comma => "`,`",
            Semi => "`;`",
            Dot => "`.`",
            EqEq => "`==`",
            Eq => "`=`",
            Plus => "`+`",
            Minus => "`-`",
            Star => "`*`",
            Slash => "`/`",
            At => "`@`",
            Pipe => "`|`",
            Amp => "`&`",
            Caret => "`^`",
            Tilde => "`~`",
            LtEq => "`<=`",
            GtEq => "`>=`",
            Lt => "`<`",
            Gt => "`>`",
            Question => "`?`",
            Bang => "`!`",
            Underscore => "`_`",
            LParen => "`(`",
            RParen => "`)`",
            LBracket => "`[`",
            RBracket => "`]`",
            LBrace => "`{`",
            RBrace => "`}`",
            Error => "an unrecognised character",
            Eof => "end of file",
        }
    }
}
