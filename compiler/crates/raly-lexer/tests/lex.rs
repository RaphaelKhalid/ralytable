//! Lexer tests, one group per token class plus recovery behaviour.

use raly_diag::{Diagnostic, FileId, Severity, SourceMap};
use raly_lexer::{lex, Lexed, TokenKind};

const F: FileId = FileId(0);

/// Lex a snippet and return the kinds of every significant token.
fn kinds(src: &str) -> Vec<TokenKind> {
    lex(F, src).significant().map(|t| t.kind).collect()
}

/// Lex a snippet, asserting it produced no diagnostics.
fn clean(src: &str) -> Lexed {
    let lexed = lex(F, src);
    assert!(
        lexed.diagnostics.is_empty(),
        "expected clean lex of {src:?}, got {:#?}",
        lexed.diagnostics
    );
    lexed
}

fn errors(src: &str) -> Vec<Diagnostic> {
    lex(F, src).diagnostics.into_vec()
}

// -- identifiers -------------------------------------------------------------

#[test]
fn identifiers() {
    for src in [
        "x",
        "abc",
        "Abc",
        "a1",
        "a_b_c",
        "_private",
        "camelCase",
        "T9",
    ] {
        assert_eq!(kinds(src), vec![TokenKind::Ident], "for {src:?}");
    }
}

#[test]
fn bare_underscore_is_not_an_identifier() {
    assert_eq!(kinds("_"), vec![TokenKind::Underscore]);
    assert_eq!(
        kinds("_ _x"),
        vec![TokenKind::Underscore, TokenKind::Ident],
        "`_` alone is the wildcard token; `_x` is a name"
    );
}

#[test]
fn keywords_are_reserved_and_beat_identifiers() {
    let keywords = [
        ("let", TokenKind::Let),
        ("fn", TokenKind::Fn),
        ("type", TokenKind::Type),
        ("struct", TokenKind::Struct),
        ("enum", TokenKind::Enum),
        ("match", TokenKind::Match),
        ("if", TokenKind::If),
        ("else", TokenKind::Else),
        ("for", TokenKind::For),
        ("in", TokenKind::In),
        ("return", TokenKind::Return),
        ("import", TokenKind::Import),
        ("space", TokenKind::Space),
        ("role", TokenKind::Role),
        ("bind", TokenKind::Bind),
        ("bundle", TokenKind::Bundle),
        ("permute", TokenKind::Permute),
        ("unbind", TokenKind::Unbind),
        ("cleanup", TokenKind::Cleanup),
        ("broadcast", TokenKind::Broadcast),
        ("where", TokenKind::Where),
        ("mut", TokenKind::Mut),
        ("true", TokenKind::True),
        ("false", TokenKind::False),
    ];
    for (src, expected) in keywords {
        assert_eq!(kinds(src), vec![expected], "for keyword {src:?}");
        assert!(expected.is_keyword(), "{src:?} should report as a keyword");
        // A keyword is only a keyword when it stands alone.
        assert_eq!(
            kinds(&format!("{src}s")),
            vec![TokenKind::Ident],
            "{src:?} should not be reserved as a prefix"
        );
    }
}

// -- numbers -----------------------------------------------------------------

#[test]
fn integer_literals() {
    for src in [
        "0",
        "7",
        "123",
        "1_000_000",
        "0xFF",
        "0xdead_beef",
        "0b1010",
        "0B1",
    ] {
        assert_eq!(kinds(src), vec![TokenKind::Int], "for {src:?}");
    }
}

#[test]
fn float_literals() {
    for src in ["1.5", "0.0", "1_000.5", "3.14e10", "2.0E-3", "1e10", "5e+7"] {
        assert_eq!(kinds(src), vec![TokenKind::Float], "for {src:?}");
    }
}

#[test]
fn trailing_dot_is_not_part_of_a_float() {
    // `1.` must stay two tokens so that field or method syntax stays open to
    // the grammar.
    assert_eq!(kinds("1."), vec![TokenKind::Int, TokenKind::Dot]);
    assert_eq!(
        kinds("1.2.3"),
        vec![TokenKind::Float, TokenKind::Dot, TokenKind::Int]
    );
}

#[test]
fn malformed_numbers_recover() {
    for src in ["123abc", "0x", "0b", "1e", "9z"] {
        let lexed = lex(F, src);
        assert_eq!(
            lexed.significant().map(|t| t.kind).collect::<Vec<_>>(),
            vec![TokenKind::MalformedNumber],
            "for {src:?}"
        );
        assert_eq!(lexed.diagnostics.len(), 1, "for {src:?}");
        assert_eq!(
            lexed.diagnostics.iter().next().unwrap().code.as_str(),
            "RALY1004",
            "for {src:?}"
        );
    }
}

#[test]
fn a_malformed_number_does_not_swallow_the_rest_of_the_line() {
    assert_eq!(
        kinds("let n = 123abc + 1"),
        vec![
            TokenKind::Let,
            TokenKind::Ident,
            TokenKind::Eq,
            TokenKind::MalformedNumber,
            TokenKind::Plus,
            TokenKind::Int,
        ]
    );
}

// -- strings -----------------------------------------------------------------

#[test]
fn string_literals() {
    for src in [
        r#""""#,
        r#""hello""#,
        r#""with spaces and 123""#,
        r#""a \"quoted\" word""#,
        r#""tab\there""#,
        r#""back\\slash""#,
        r#""null\0end""#,
        r#""emoji \u{1F600}""#,
        r#""// not a comment""#,
    ] {
        let lexed = clean(src);
        assert_eq!(
            lexed.significant().map(|t| t.kind).collect::<Vec<_>>(),
            vec![TokenKind::Str],
            "for {src:?}"
        );
    }
}

#[test]
fn a_string_spans_its_quotes() {
    let lexed = clean(r#"let s = "hi""#);
    let string = lexed
        .significant()
        .find(|t| t.kind == TokenKind::Str)
        .unwrap();
    assert_eq!(string.span.start, 8);
    assert_eq!(string.span.end, 12, "the closing quote is inside the span");
}

#[test]
fn unterminated_string_at_end_of_line_recovers() {
    let src = "let s = \"hello\nlet t = 1\n";
    let lexed = lex(F, src);
    assert_eq!(lexed.diagnostics.len(), 1);
    let diag = lexed.diagnostics.iter().next().unwrap();
    assert_eq!(diag.code.as_str(), "RALY1002");
    assert_eq!(diag.severity, Severity::Error);
    // The next line still lexes normally: recovery, not a cascade.
    assert_eq!(
        lexed.significant().map(|t| t.kind).collect::<Vec<_>>(),
        vec![
            TokenKind::Let,
            TokenKind::Ident,
            TokenKind::Eq,
            TokenKind::UnterminatedStr,
            TokenKind::Let,
            TokenKind::Ident,
            TokenKind::Eq,
            TokenKind::Int,
        ]
    );
}

#[test]
fn unterminated_string_at_end_of_file_recovers() {
    let lexed = lex(F, "\"oops");
    assert_eq!(lexed.diagnostics.len(), 1);
    let diag = lexed.diagnostics.iter().next().unwrap();
    assert_eq!(diag.code.as_str(), "RALY1002");
    assert!(diag
        .notes
        .iter()
        .any(|n| n.message.contains("multiple lines")));
}

#[test]
fn an_escaped_quote_does_not_terminate_a_string() {
    assert_eq!(kinds(r#""a\"b" 1"#), vec![TokenKind::Str, TokenKind::Int]);
}

#[test]
fn unknown_escapes_are_reported_once_each() {
    let diags = errors(r#""\q and \z""#);
    assert_eq!(diags.len(), 2, "one diagnostic per bad escape");
    for diag in &diags {
        assert_eq!(diag.code.as_str(), "RALY1003");
        assert!(diag.notes.iter().any(|n| n.message.contains("recognised")));
    }
    // The spans point at the two-character escape, not the whole string.
    assert_eq!(diags[0].focus().unwrap().len(), 2);
}

#[test]
fn a_bad_escape_still_yields_a_string_token() {
    let lexed = lex(F, r#"let s = "\q""#);
    assert!(lexed.has_errors());
    assert!(lexed.significant().any(|t| t.kind == TokenKind::Str));
}

#[test]
fn unicode_escape_requires_braces() {
    let diags = errors(r#""\u12""#);
    assert_eq!(diags.len(), 1);
    assert_eq!(diags[0].code.as_str(), "RALY1003");
    assert!(diags[0].message.contains("braced code point"));
    assert!(diags[0]
        .notes
        .iter()
        .any(|n| n.kind == raly_diag::NoteKind::Help && n.message.contains("u{1F600}")));
}

#[test]
fn unicode_escape_rejects_non_scalar_values() {
    for source in [r#""\u{}""#, r#""\u{110000}""#, r#""\u{D800}""#] {
        let diags = errors(source);
        assert_eq!(diags.len(), 1, "one diagnostic for {source:?}");
        assert_eq!(diags[0].code.as_str(), "RALY1003");
        assert!(diags[0].message.contains("valid scalar"));
    }
}

// -- comments ----------------------------------------------------------------

#[test]
fn line_comments_are_trivia_not_syntax() {
    let lexed = clean("let x = 1 // trailing\nlet y = 2");
    assert_eq!(
        lexed.significant().map(|t| t.kind).collect::<Vec<_>>(),
        vec![
            TokenKind::Let,
            TokenKind::Ident,
            TokenKind::Eq,
            TokenKind::Int,
            TokenKind::Let,
            TokenKind::Ident,
            TokenKind::Eq,
            TokenKind::Int,
        ]
    );
    // But the comment is still in the raw stream, for a future formatter.
    let comment = lexed
        .tokens
        .iter()
        .find(|t| t.kind == TokenKind::LineComment)
        .expect("comment token retained");
    assert!(comment.is_trivia());
    assert_eq!(comment.span.start, 10);
}

#[test]
fn a_comment_stops_at_the_newline() {
    let lexed = clean("// one\n// two\n");
    let comments: Vec<_> = lexed
        .tokens
        .iter()
        .filter(|t| t.kind == TokenKind::LineComment)
        .collect();
    assert_eq!(comments.len(), 2);
    assert_eq!(comments[0].span.end, 6, "must not include the newline");
}

#[test]
fn a_comment_at_end_of_file_without_a_newline() {
    let lexed = clean("let x = 1 // done");
    assert_eq!(lexed.tokens.last().unwrap().kind, TokenKind::Eof);
}

#[test]
fn division_is_not_a_comment() {
    assert_eq!(
        kinds("a / b"),
        vec![TokenKind::Ident, TokenKind::Slash, TokenKind::Ident]
    );
    // `///` is a comment, and comments are trivia, so nothing significant.
    assert!(kinds("///").is_empty());
    assert_eq!(lex(F, "///").tokens[0].kind, TokenKind::LineComment);
}

// -- operators and brackets --------------------------------------------------

#[test]
fn every_operator_lexes_as_one_token() {
    let cases = [
        ("->", TokenKind::Arrow),
        ("=>", TokenKind::FatArrow),
        ("|>", TokenKind::Pipeline),
        ("::", TokenKind::ColonColon),
        (":", TokenKind::Colon),
        (",", TokenKind::Comma),
        (";", TokenKind::Semi),
        (".", TokenKind::Dot),
        ("=", TokenKind::Eq),
        ("==", TokenKind::EqEq),
        ("+", TokenKind::Plus),
        ("-", TokenKind::Minus),
        ("*", TokenKind::Star),
        ("/", TokenKind::Slash),
        ("@", TokenKind::At),
        ("|", TokenKind::Pipe),
        ("&", TokenKind::Amp),
        ("^", TokenKind::Caret),
        ("~", TokenKind::Tilde),
        ("<", TokenKind::Lt),
        (">", TokenKind::Gt),
        ("<=", TokenKind::LtEq),
        (">=", TokenKind::GtEq),
        ("?", TokenKind::Question),
        ("!", TokenKind::Bang),
        ("_", TokenKind::Underscore),
        ("(", TokenKind::LParen),
        (")", TokenKind::RParen),
        ("[", TokenKind::LBracket),
        ("]", TokenKind::RBracket),
        ("{", TokenKind::LBrace),
        ("}", TokenKind::RBrace),
    ];
    for (src, expected) in cases {
        assert_eq!(kinds(src), vec![expected], "for operator {src:?}");
    }
}

#[test]
fn multi_character_operators_win_over_their_prefixes() {
    assert_eq!(kinds("=="), vec![TokenKind::EqEq]);
    assert_eq!(kinds("= ="), vec![TokenKind::Eq, TokenKind::Eq]);
    assert_eq!(kinds("::"), vec![TokenKind::ColonColon]);
    assert_eq!(kinds(": :"), vec![TokenKind::Colon, TokenKind::Colon]);
    assert_eq!(kinds("|>"), vec![TokenKind::Pipeline]);
    assert_eq!(kinds("| >"), vec![TokenKind::Pipe, TokenKind::Gt]);
    assert_eq!(kinds("->"), vec![TokenKind::Arrow]);
    assert_eq!(kinds("- >"), vec![TokenKind::Minus, TokenKind::Gt]);
}

#[test]
fn operators_need_no_surrounding_whitespace() {
    assert_eq!(
        kinds("f(x)|>g"),
        vec![
            TokenKind::Ident,
            TokenKind::LParen,
            TokenKind::Ident,
            TokenKind::RParen,
            TokenKind::Pipeline,
            TokenKind::Ident,
        ]
    );
}

// -- structure and recovery --------------------------------------------------

#[test]
fn whitespace_is_dropped_and_eof_is_appended_exactly_once() {
    let lexed = clean("  \t\r\n  let\n\n");
    assert_eq!(
        lexed
            .tokens
            .iter()
            .filter(|t| t.kind == TokenKind::Eof)
            .count(),
        1
    );
    assert_eq!(lexed.tokens.last().unwrap().kind, TokenKind::Eof);
    let eof = lexed.tokens.last().unwrap();
    assert!(eof.span.is_empty(), "eof is a zero-width point");
}

#[test]
fn the_empty_file_lexes() {
    let lexed = clean("");
    assert_eq!(lexed.tokens.len(), 1);
    assert_eq!(lexed.tokens[0].kind, TokenKind::Eof);
}

#[test]
fn spans_are_contiguous_and_ordered() {
    let src = "let x = 1 // c\nlet y = \"s\"";
    let lexed = clean(src);
    let mut previous_end = 0;
    for token in &lexed.tokens {
        assert!(
            token.span.start >= previous_end,
            "token {token:?} moved backwards"
        );
        assert!(token.span.end as usize <= src.len());
        previous_end = token.span.end;
    }
}

#[test]
fn unknown_characters_recover_and_group() {
    let lexed = lex(F, "let x = 1 \u{20AC}\u{20AC}\u{20AC} + 2");
    assert_eq!(
        lexed.diagnostics.len(),
        1,
        "a run of unknown characters is one diagnostic, not three"
    );
    let diag = lexed.diagnostics.iter().next().unwrap();
    assert_eq!(diag.code.as_str(), "RALY1001");
    assert_eq!(diag.focus().unwrap().len(), 9, "three 3-byte characters");
    // Everything after the bad run still lexes.
    let tail: Vec<_> = lexed
        .significant()
        .skip_while(|t| t.kind != TokenKind::Plus)
        .map(|t| t.kind)
        .collect();
    assert_eq!(tail, vec![TokenKind::Plus, TokenKind::Int]);
}

#[test]
fn separated_unknown_characters_are_separate_diagnostics() {
    let lexed = lex(F, "\u{20AC} x \u{20AC}");
    assert_eq!(lexed.diagnostics.len(), 2);
}

#[test]
fn a_smart_quote_gets_a_targeted_hint() {
    let lexed = lex(F, "let s = \u{201C}hello\u{201D}");
    let diag = lexed.diagnostics.iter().next().unwrap();
    assert_eq!(diag.code.as_str(), "RALY1001");
    assert!(
        diag.notes
            .iter()
            .any(|n| n.message.contains("typographic double quote")),
        "expected a homoglyph hint, got {:#?}",
        diag.notes
    );
}

#[test]
fn diagnostics_come_back_in_source_order() {
    let lexed = lex(F, "\u{20AC} 1e 0x");
    let starts: Vec<u32> = lexed
        .diagnostics
        .iter()
        .map(|d| d.focus().unwrap().start)
        .collect();
    let mut sorted = starts.clone();
    sorted.sort_unstable();
    assert_eq!(starts, sorted);
}

#[test]
fn lexing_arbitrary_bytes_never_panics() {
    // Not a correctness claim about any particular output — just that the
    // lexer is total, which the parser will rely on.
    let inputs = [
        "\u{0}\u{1}\u{2}",
        "\"\\",
        "\"\\\\",
        "0x0x0x",
        "....",
        "\u{1F600}",
        "let\u{0}x",
        "\"unterminated \\",
    ];
    for src in inputs {
        let lexed = lex(F, src);
        assert_eq!(
            lexed.tokens.last().unwrap().kind,
            TokenKind::Eof,
            "for {src:?}"
        );
    }
}

#[test]
fn a_real_snippet_lexes_clean() {
    let mut sources = SourceMap::new();
    let src = "\
// bind a role to a filler
fn compose(subject: Symbol, mut n: Int) -> Symbol where n >= 0 {
    let scene = bundle(bind(subject, ROLE), permute(subject, 1))
    scene |> cleanup
}
";
    let file = sources.add("compose.raly", src);
    let lexed = lex(file, sources.get(file).text());
    assert!(lexed.diagnostics.is_empty(), "{:#?}", lexed.diagnostics);
    assert!(lexed.significant().any(|t| t.kind == TokenKind::Where));
    assert!(lexed.significant().any(|t| t.kind == TokenKind::Pipeline));
    assert!(lexed.significant().any(|t| t.kind == TokenKind::GtEq));
}
