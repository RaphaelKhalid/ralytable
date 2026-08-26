//! Tokeniser for the Raly language.
//!
//! [`lex`] turns source text into a `Vec<Token>` plus a [`Diagnostics`]. It is
//! **total**: every input produces a token stream and never panics. Text the
//! lexer cannot classify becomes an error token *and* a diagnostic, so the
//! parser that arrives later can keep going and report more than one problem
//! per run.
//!
//! ```
//! use raly_diag::SourceMap;
//! use raly_lexer::{lex, TokenKind};
//!
//! let mut sources = SourceMap::new();
//! let file = sources.add("x.raly", "let x = 1 |> f");
//! let lexed = lex(file, sources.get(file).text());
//! assert!(lexed.diagnostics.is_empty());
//! assert_eq!(lexed.significant().next().unwrap().kind, TokenKind::Let);
//! ```

mod token;

pub use token::{Token, TokenKind};

use logos::Logos;
use raly_diag::{codes, Diagnostic, Diagnostics, FileId, Span};

/// The result of lexing one file.
#[derive(Debug)]
pub struct Lexed {
    /// Every token in source order, ending with exactly one [`TokenKind::Eof`].
    /// Includes comments; excludes whitespace.
    pub tokens: Vec<Token>,
    /// Problems found while lexing. Lexing continues past all of them.
    pub diagnostics: Diagnostics,
}

impl Lexed {
    /// Tokens the grammar cares about: everything except trivia and the final
    /// end-of-file marker.
    pub fn significant(&self) -> impl Iterator<Item = &Token> {
        self.tokens
            .iter()
            .filter(|t| !t.is_trivia() && t.kind != TokenKind::Eof)
    }

    pub fn has_errors(&self) -> bool {
        self.diagnostics.has_errors()
    }
}

/// Tokenise `src`, which must be the text of `file`.
///
/// Never panics, never bails out early.
pub fn lex(file: FileId, src: &str) -> Lexed {
    let mut tokens = Vec::new();
    let mut diagnostics = Diagnostics::new();

    let mut lexer = TokenKind::lexer(src);
    // Byte range of a run of consecutive unclassifiable characters, so that
    // `€€€` is one diagnostic rather than three.
    let mut unknown_run: Option<(usize, usize)> = None;

    while let Some(result) = lexer.next() {
        let range = lexer.span();
        match result {
            Ok(kind) => {
                flush_unknown(&mut unknown_run, file, src, &mut diagnostics);
                let span = Span::from_range(file, range.clone());
                match kind {
                    TokenKind::Str => check_escapes(file, src, span, &mut diagnostics),
                    TokenKind::UnterminatedStr => {
                        diagnostics.push(unterminated_string(file, src, span));
                        check_escapes(file, src, span, &mut diagnostics);
                    }
                    TokenKind::MalformedNumber => {
                        diagnostics.push(malformed_number(src, span));
                    }
                    _ => {}
                }
                tokens.push(Token::new(kind, span));
            }
            Err(_) => {
                // Extend the current run if this character is adjacent to it.
                match &mut unknown_run {
                    Some((_, end)) if *end == range.start => *end = range.end,
                    _ => {
                        flush_unknown(&mut unknown_run, file, src, &mut diagnostics);
                        unknown_run = Some((range.start, range.end));
                    }
                }
                tokens.push(Token::new(
                    TokenKind::Error,
                    Span::from_range(file, range.clone()),
                ));
            }
        }
    }
    flush_unknown(&mut unknown_run, file, src, &mut diagnostics);

    tokens.push(Token::new(
        TokenKind::Eof,
        Span::point(file, src.len() as u32),
    ));

    diagnostics.sort_by_position();
    Lexed {
        tokens,
        diagnostics,
    }
}

fn flush_unknown(
    run: &mut Option<(usize, usize)>,
    file: FileId,
    src: &str,
    diagnostics: &mut Diagnostics,
) {
    let Some((start, end)) = run.take() else {
        return;
    };
    let span = Span::from_range(file, start..end);
    let text = &src[start..end];
    let mut diag = Diagnostic::error(
        codes::UNKNOWN_CHARACTER,
        if text.chars().count() == 1 {
            format!("unexpected character `{}` in source", text)
        } else {
            format!("unexpected characters `{}` in source", text)
        },
    )
    .with_primary(span, "not part of Raly's syntax");

    diag = diag.with_note(format!(
        "the offending text is {}",
        text.chars()
            .map(|c| format!("U+{:04X}", c as u32))
            .collect::<Vec<_>>()
            .join(", ")
    ));

    // Homoglyphs are the overwhelmingly common cause here, usually from
    // pasting code out of a document or a chat client.
    if let Some(hint) = text.chars().find_map(homoglyph_hint) {
        diag = diag.with_help(hint.to_string());
    }
    diagnostics.push(diag);
}

/// ASCII replacement advice for characters that look like Raly syntax but are
/// not. Returning `None` means we have nothing useful to add.
fn homoglyph_hint(c: char) -> Option<&'static str> {
    Some(match c {
        '\u{201C}' | '\u{201D}' => {
            "this looks like a typographic double quote; string literals use the ASCII `\"`"
        }
        '\u{2018}' | '\u{2019}' => "this looks like a typographic single quote; try the ASCII `'`",
        '\u{2013}' | '\u{2014}' => {
            "this looks like a dash; subtraction and `->` both use the ASCII `-`"
        }
        '\u{00D7}' => "this looks like a multiplication sign; use the ASCII `*`",
        '\u{2192}' => "this looks like an arrow; write it as the two characters `->`",
        '\u{21D2}' => "this looks like a double arrow; write it as the two characters `=>`",
        '\u{2264}' => "this looks like a less-than-or-equal sign; write it as `<=`",
        '\u{2265}' => "this looks like a greater-than-or-equal sign; write it as `>=`",
        '\u{00A0}' => "this is a non-breaking space; replace it with an ordinary space",
        '#' => "Raly has no `#` syntax; comments start with `//`",
        '$' | '%' | '\\' | '\'' | '`' => return None,
        _ => return None,
    })
}

fn unterminated_string(file: FileId, src: &str, span: Span) -> Diagnostic {
    let ended_at_eof = span.end as usize >= src.len();
    let where_it_stopped = if ended_at_eof {
        "the file ends here, still inside the string"
    } else {
        "the line ends here, still inside the string"
    };
    Diagnostic::error(codes::UNTERMINATED_STRING, "unterminated string literal")
        .with_primary(
            Span::new(file, span.start, span.start + 1),
            "this string is never closed",
        )
        .with_secondary(Span::point(file, span.end), where_it_stopped)
        .with_note("Raly string literals may not span multiple lines")
        .with_help("add a closing `\"` before the end of the line")
}

fn malformed_number(src: &str, span: Span) -> Diagnostic {
    let text = &src[span.range()];
    let mut diag = Diagnostic::error(
        codes::MALFORMED_NUMBER,
        format!("`{text}` is not a valid numeric literal"),
    )
    .with_primary(span, "cannot be read as a number");

    let lower = text.to_ascii_lowercase();
    if lower == "0x" || lower == "0b" {
        diag = diag.with_help(format!(
            "`{text}` needs at least one digit after the base prefix"
        ));
    } else if lower.ends_with('e') {
        diag = diag.with_help("an exponent needs digits after the `e`, as in `1e10`");
    } else if let Some(pos) = text.find(|c: char| c.is_ascii_alphabetic()) {
        let suffix = &text[pos..];
        diag = diag
            .with_note(format!("`{suffix}` is not a recognised numeric suffix"))
            .with_help("Raly has no literal suffixes; write the type separately if you need one");
    }
    diag.with_note("valid forms are `123`, `1_000`, `0xFF`, `0b1010`, `1.5` and `1e10`")
}

/// Walk a string literal's body and report unknown escape sequences.
///
/// Each bad escape gets its own diagnostic with its own two-character span,
/// so a string with three mistakes reports three of them.
fn check_escapes(file: FileId, src: &str, span: Span, diagnostics: &mut Diagnostics) {
    let body = &src[span.range()];
    let base = span.start as usize;
    let mut chars = body.char_indices().peekable();
    // Skip the opening quote.
    chars.next();

    while let Some((i, c)) = chars.next() {
        if c != '\\' {
            continue;
        }
        let Some(&(j, esc)) = chars.peek() else {
            break;
        };
        chars.next();
        match esc {
            'n' | 't' | 'r' | '0' | '\\' | '"' => {}
            'u' => {
                // `\u{...}` — consume the braces so their contents are not
                // re-examined as escapes.
                if chars.peek().map(|&(_, c)| c) == Some('{') {
                    for (_, c) in chars.by_ref() {
                        if c == '}' {
                            break;
                        }
                    }
                } else {
                    diagnostics.push(
                        Diagnostic::error(
                            codes::INVALID_ESCAPE,
                            "`\\u` must be followed by a braced code point",
                        )
                        .with_primary(
                            Span::new(file, (base + i) as u32, (base + j + esc.len_utf8()) as u32),
                            "expected `{` here",
                        )
                        .with_help("write a Unicode escape as `\\u{1F600}`"),
                    );
                }
            }
            other => {
                diagnostics.push(
                    Diagnostic::error(
                        codes::INVALID_ESCAPE,
                        format!("unknown escape sequence `\\{other}`"),
                    )
                    .with_primary(
                        Span::new(file, (base + i) as u32, (base + j + other.len_utf8()) as u32),
                        "not a recognised escape",
                    )
                    .with_note(
                        "the recognised escapes are `\\n`, `\\t`, `\\r`, `\\0`, `\\\\`, `\\\"` and `\\u{...}`",
                    )
                    .with_help(format!(
                        "to write a literal backslash followed by `{other}`, use `\\\\{other}`"
                    )),
                );
            }
        }
    }
}
