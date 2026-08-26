//! Tests for spans, the source map, and rendered diagnostic output.
//!
//! The rendering tests assert on the *exact* text a user sees. That is
//! deliberate: this is the crate whose output is the product, so a change to
//! the layout should be a change someone had to look at and approve.

use raly_diag::{
    codes, Diagnostic, Diagnostics, Label, RenderConfig, Renderer, Severity, SourceMap, Span,
};

// -- source map --------------------------------------------------------------

#[test]
fn locations_are_one_based() {
    let mut sources = SourceMap::new();
    let id = sources.add("a.raly", "abc\ndef\n");
    let file = sources.get(id);
    assert_eq!(file.location(0).line, 1);
    assert_eq!(file.location(0).column, 1);
    assert_eq!(file.location(2).column, 3);
    assert_eq!(file.location(4).line, 2);
    assert_eq!(file.location(4).column, 1);
}

#[test]
fn columns_count_characters_not_bytes() {
    let mut sources = SourceMap::new();
    // Each of these is three bytes in UTF-8.
    let id = sources.add("a.raly", "\u{4F60}\u{597D}x");
    let file = sources.get(id);
    assert_eq!(file.location(6).column, 3, "byte 6 is the third character");
}

#[test]
fn an_offset_at_end_of_file_still_resolves() {
    let mut sources = SourceMap::new();
    let id = sources.add("a.raly", "abc");
    let file = sources.get(id);
    assert_eq!(file.location(3).line, 1);
    assert_eq!(file.location(3).column, 4);
    // And past the end, rather than panicking.
    assert_eq!(file.location(99).line, 1);
}

#[test]
fn line_text_excludes_the_terminator() {
    let mut sources = SourceMap::new();
    let id = sources.add("a.raly", "abc\r\ndef\n");
    let file = sources.get(id);
    assert_eq!(file.line_text(0), "abc");
    assert_eq!(file.line_text(1), "def");
    assert_eq!(file.line_count(), 3, "the trailing newline opens a line 3");
}

#[test]
fn spans_merge_and_measure() {
    let mut sources = SourceMap::new();
    let id = sources.add("a.raly", "let x = 1");
    let a = Span::new(id, 0, 3);
    let b = Span::new(id, 8, 9);
    assert_eq!(a.merge(b), Span::new(id, 0, 9));
    assert_eq!(a.len(), 3);
    assert!(Span::point(id, 4).is_empty());
    assert_eq!(sources.snippet(a), "let");
}

#[test]
fn an_out_of_range_span_yields_empty_text_rather_than_panicking() {
    let mut sources = SourceMap::new();
    let id = sources.add("a.raly", "short");
    assert_eq!(sources.snippet(Span::new(id, 100, 200)), "");
}

// -- rendering ---------------------------------------------------------------

#[test]
fn a_simple_error_renders_with_source_context_and_a_caret() {
    let mut sources = SourceMap::new();
    let src = "fn main() {\n    let greeting = \"hello\n}\n";
    let file = sources.add("greet.raly", src);

    let diag = Diagnostic::error(codes::UNTERMINATED_STRING, "unterminated string literal")
        .with_primary(Span::new(file, 31, 37), "this string is never closed")
        .with_note("Raly string literals may not span multiple lines")
        .with_help("add a closing quote before the end of the line");

    let rendered = Renderer::new(&sources).render(&diag);

    let expected = "\
error[RALY1002]: unterminated string literal
 --> greet.raly:2:20
  |
2 |     let greeting = \"hello
  |                    ^^^^^^ this string is never closed
  |
  = note: Raly string literals may not span multiple lines
  = help: add a closing quote before the end of the line
";
    assert_eq!(rendered, expected, "\n--- got ---\n{rendered}");
}

#[test]
fn the_note_and_help_channels_stay_distinct_and_ordered() {
    // The motivating case for having two channels at all: a capacity error
    // wants to state a fact and then propose an action.
    let mut sources = SourceMap::new();
    let src = "let scene = bundle(a, b, c)\n";
    let file = sources.add("scene.raly", src);

    let diag = Diagnostic::error(codes::UNKNOWN_CHARACTER, "vector capacity exceeded")
        .with_primary(Span::new(file, 12, 27), "this bundle overflows")
        .with_note("this vector already holds 7 of 31 items")
        .with_help("split the bundle, or declare a wider space");

    let rendered = Renderer::new(&sources).render(&diag);
    let note_at = rendered.find("= note:").expect("note channel");
    let help_at = rendered.find("= help:").expect("help channel");
    assert!(note_at < help_at, "facts before advice:\n{rendered}");
    assert!(rendered.contains("= note: this vector already holds 7 of 31 items"));
    assert!(rendered.contains("= help: split the bundle, or declare a wider space"));
}

#[test]
fn a_secondary_label_renders_with_dashes_and_its_own_locator() {
    let mut sources = SourceMap::new();
    let src = "let x = 1\nlet x = 2\n";
    let file = sources.add("dup.raly", src);

    let diag = Diagnostic::error(codes::UNKNOWN_CHARACTER, "name defined twice")
        .with_label(Label::primary(Span::new(file, 14, 15), "redefined here"))
        .with_label(Label::secondary(
            Span::new(file, 4, 5),
            "first defined here",
        ));

    let rendered = Renderer::new(&sources).render(&diag);
    let expected = "\
error[RALY1001]: name defined twice
 --> dup.raly:2:5
  |
2 | let x = 2
  |     ^ redefined here
 ::: dup.raly:1:5
  |
1 | let x = 1
  |     - first defined here
";
    assert_eq!(rendered, expected, "\n--- got ---\n{rendered}");
}

#[test]
fn a_zero_width_span_still_gets_one_caret() {
    let mut sources = SourceMap::new();
    let file = sources.add("eof.raly", "let x =");
    let diag = Diagnostic::error(codes::UNKNOWN_CHARACTER, "expected an expression")
        .with_primary(Span::point(file, 7), "the file ends here");
    let rendered = Renderer::new(&sources).render(&diag);
    assert!(
        rendered.contains("  |        ^ the file ends here"),
        "{rendered}"
    );
}

#[test]
fn tabs_are_expanded_so_carets_line_up() {
    let mut sources = SourceMap::new();
    // A tab, then `let`, then a tab, then `x`.
    let file = sources.add("tabs.raly", "\tlet\tx");
    let diag = Diagnostic::error(codes::UNKNOWN_CHARACTER, "example")
        .with_primary(Span::new(file, 5, 6), "here");
    let rendered = Renderer::new(&sources).render(&diag);

    let source_line = rendered.lines().nth(3).unwrap();
    let caret_line = rendered.lines().nth(4).unwrap();
    let caret_col = caret_line.find('^').unwrap();
    assert_eq!(
        source_line.as_bytes()[caret_col],
        b'x',
        "caret should sit under `x`:\n{rendered}"
    );
    assert!(!source_line.contains('\t'), "tabs must be expanded");
}

#[test]
fn the_gutter_widens_for_large_line_numbers() {
    let mut sources = SourceMap::new();
    let src = "\n".repeat(120) + "let x = 1\n";
    let file = sources.add("long.raly", src);
    // Byte 120 is the start of line 121.
    let diag = Diagnostic::error(codes::UNKNOWN_CHARACTER, "example")
        .with_primary(Span::new(file, 124, 125), "here");
    let rendered = Renderer::new(&sources).render(&diag);
    assert!(rendered.contains("   --> long.raly:121:5"), "{rendered}");
    assert!(rendered.contains("121 | let x = 1"), "{rendered}");
}

#[test]
fn a_multi_line_span_says_where_it_continues_to() {
    let mut sources = SourceMap::new();
    let src = "fn f() {\n    body\n}\n";
    let file = sources.add("multi.raly", src);
    let diag = Diagnostic::error(codes::UNKNOWN_CHARACTER, "unclosed block")
        .with_primary(Span::new(file, 7, 19), "starts here");
    let rendered = Renderer::new(&sources).render(&diag);
    assert!(
        rendered.contains("...continues to line 3"),
        "a multi-line span must not pretend to end at the line break:\n{rendered}"
    );
}

#[test]
fn severities_and_codes_appear_in_the_header() {
    let mut sources = SourceMap::new();
    let file = sources.add("s.raly", "x\n");
    type Build = fn(raly_diag::Code, &'static str) -> Diagnostic;
    for (build, expected) in [
        (Diagnostic::error as Build, "error[RALY1001]: msg"),
        (Diagnostic::warning as Build, "warning[RALY1001]: msg"),
        (Diagnostic::advice as Build, "advice[RALY1001]: msg"),
    ] {
        let diag =
            build(codes::UNKNOWN_CHARACTER, "msg").with_primary(Span::new(file, 0, 1), "here");
        let rendered = Renderer::new(&sources).render(&diag);
        assert!(rendered.starts_with(expected), "{rendered}");
    }
}

#[test]
fn a_diagnostic_with_no_labels_still_renders() {
    let sources = SourceMap::new();
    let diag = Diagnostic::error(codes::IO_ERROR, "could not read `missing.raly`")
        .with_note("the system cannot find the file specified");
    let rendered = Renderer::new(&sources).render(&diag);
    assert_eq!(
        rendered,
        "error[RALY0001]: could not read `missing.raly`\n  = note: the system cannot find the file specified\n"
    );
}

#[test]
fn explain_mode_appends_the_registry_description() {
    let mut sources = SourceMap::new();
    let file = sources.add("s.raly", "x\n");
    let diag = Diagnostic::error(codes::UNTERMINATED_STRING, "msg")
        .with_primary(Span::new(file, 0, 1), "here");
    let config = RenderConfig::plain().with_explain_codes(true);
    let rendered = Renderer::with_config(&sources, config).render(&diag);
    assert!(
        rendered.contains("= code: RALY1002 is a string literal reaches end of line"),
        "{rendered}"
    );
}

#[test]
fn colour_is_off_by_default_and_adds_no_escapes() {
    let mut sources = SourceMap::new();
    let file = sources.add("s.raly", "x\n");
    let diag = Diagnostic::error(codes::UNKNOWN_CHARACTER, "msg")
        .with_primary(Span::new(file, 0, 1), "here");

    let plain = Renderer::new(&sources).render(&diag);
    assert!(!plain.contains('\u{1b}'));

    let colored =
        Renderer::with_config(&sources, RenderConfig::plain().with_color(true)).render(&diag);
    assert!(colored.contains('\u{1b}'));
    // Colour must not change the layout, only the bytes around it.
    let stripped: String = strip_ansi(&colored);
    assert_eq!(stripped, plain);
}

fn strip_ansi(s: &str) -> String {
    let mut out = String::new();
    let mut chars = s.chars();
    while let Some(c) = chars.next() {
        if c == '\u{1b}' {
            for c in chars.by_ref() {
                if c == 'm' {
                    break;
                }
            }
        } else {
            out.push(c);
        }
    }
    out
}

// -- collection --------------------------------------------------------------

#[test]
fn diagnostics_track_severity_and_sort_by_position() {
    let mut sources = SourceMap::new();
    let file = sources.add("s.raly", "aaaa\nbbbb\n");
    let mut diags = Diagnostics::new();
    diags.push(
        Diagnostic::error(codes::UNKNOWN_CHARACTER, "second")
            .with_primary(Span::new(file, 5, 6), ""),
    );
    diags.push(
        Diagnostic::warning(codes::BAD_EXTENSION, "first").with_primary(Span::new(file, 0, 1), ""),
    );

    assert!(diags.has_errors());
    assert_eq!(diags.count(Severity::Error), 1);
    assert_eq!(diags.count(Severity::Warning), 1);

    diags.sort_by_position();
    let messages: Vec<&str> = diags.iter().map(|d| d.message.as_str()).collect();
    assert_eq!(messages, vec!["first", "second"]);
}

#[test]
fn render_all_separates_diagnostics_with_a_blank_line() {
    let mut sources = SourceMap::new();
    let file = sources.add("s.raly", "ab\n");
    let diags: Diagnostics = vec![
        Diagnostic::error(codes::UNKNOWN_CHARACTER, "one").with_primary(Span::new(file, 0, 1), ""),
        Diagnostic::error(codes::UNKNOWN_CHARACTER, "two").with_primary(Span::new(file, 1, 2), ""),
    ]
    .into_iter()
    .collect();

    let rendered = Renderer::new(&sources).render_all(&diags);
    assert!(rendered.contains("\n\nerror[RALY1001]: two"), "{rendered}");
}

#[test]
fn the_summary_pluralises() {
    let sources = SourceMap::new();
    let renderer = Renderer::new(&sources);
    assert_eq!(renderer.summary(1, 0), "error: 1 error\n");
    assert_eq!(renderer.summary(2, 1), "error: 2 errors, 1 warning\n");
    assert_eq!(renderer.summary(0, 3), "warning: 3 warnings\n");
    assert_eq!(renderer.summary(0, 0), "");
}

#[test]
fn focus_prefers_the_primary_label() {
    let mut sources = SourceMap::new();
    let file = sources.add("s.raly", "abcdef\n");
    let diag = Diagnostic::error(codes::UNKNOWN_CHARACTER, "m")
        .with_secondary(Span::new(file, 0, 1), "")
        .with_primary(Span::new(file, 4, 5), "");
    assert_eq!(diag.focus().unwrap().start, 4);
}
