//! Error recovery.
//!
//! The property under test throughout: **one run reports every mistake**. A
//! parser that stops at the first error costs a user one edit–compile cycle
//! per mistake, and a parser that cascades costs them the effort of working
//! out which of ten messages is the real one. Both failure modes are asserted
//! against here.

mod common;

use common::{contains_lines, err, ok, run};
use raly_ast::{ExprKind, ItemKind, Origin, Reason};

// -- many errors in one run --------------------------------------------------

#[test]
fn every_broken_item_is_reported_in_one_run() {
    let run = err("space A = 1024\n\
         role B\n\
         fn c(d) { d }\n\
         fn e() { bundle() }\n\
         fn f() { unbind(x) }\n");
    assert_eq!(
        run.codes(),
        [
            "RALY2010", // space with no family
            "RALY2001", // role with no `in`
            "RALY2006", // unannotated parameter
            "RALY2003", // empty bundle
            "RALY2004", // unbind arity
        ],
        "\n{}",
        run.rendered()
    );
}

#[test]
fn an_error_in_one_function_does_not_hide_the_next() {
    let run = err("fn a() { ^ }\nfn b(x) { x }\nfn c() { bundle() }\n");
    assert_eq!(run.codes(), ["RALY2001", "RALY2006", "RALY2003"]);
}

#[test]
fn the_last_item_still_parses_after_everything_before_it_broke() {
    let run = err("fn a( { }\nfn b() -> { }\nfn good(x: Int) -> Int { x }\n");
    assert!(!run.parsed.diagnostics.is_empty());
    // `good` must be a real `Fn` item, not swallowed by recovery.
    let good = run.ast().root.iter().any(|&id| {
        matches!(&run.ast().items[id].kind, ItemKind::Fn(def)
            if run.ast().text(def.name) == "good" && def.body.is_some())
    });
    assert!(
        good,
        "the trailing valid function was lost:\n{}",
        run.dump()
    );
}

#[test]
fn errors_inside_a_block_do_not_abandon_the_rest_of_it() {
    let run = err("fn f() {\n    let a = ^\n    let b = 2\n    b\n}\n");
    assert_eq!(run.codes(), ["RALY2001"]);
    // Both bindings survive.
    contains_lines(&run.dump(), "let `a`");
    contains_lines(&run.dump(), "let `b`");
}

// -- no cascades -------------------------------------------------------------

#[test]
fn one_mistake_produces_exactly_one_diagnostic() {
    for src in [
        "fn f( { }\n",
        "fn f() { let = 1 }\n",
        "space S = \n",
        "type T = Vec[S; ]\n",
        "fn f() -> { }\n",
        "fn f() { bundle.nope(a, b) }\n",
    ] {
        let run = err(src);
        assert_eq!(
            run.parsed.diagnostics.len(),
            1,
            "expected exactly one diagnostic for {src:?}, got:\n{}",
            run.rendered()
        );
    }
}

#[test]
fn a_lexical_error_does_not_also_become_a_syntax_error() {
    // `123abc` is reported once, by the lexer. The parser accepts the token so
    // that the user is not told about the same character twice.
    use raly_diag::SourceMap;
    use raly_lexer::lex;
    use raly_parse::parse;

    let mut sources = SourceMap::new();
    let file = sources.add("t.raly", "fn f() { let a = 123abc\n a }\n");
    let lexed = lex(file, sources.get(file).text());
    assert_eq!(lexed.diagnostics.len(), 1);
    let parsed = parse(file, sources.get(file).text(), &lexed.tokens);
    assert!(
        parsed.diagnostics.is_empty(),
        "the parser repeated a lexical error"
    );
}

// -- recovery leaves a usable tree -------------------------------------------

#[test]
fn recovery_produces_error_nodes_not_gaps() {
    let run = err("fn f() { @ }\n");
    let has_error_expr = run
        .ast()
        .exprs
        .iter()
        .any(|e| matches!(e.kind, ExprKind::Error));
    assert!(has_error_expr, "{}", run.dump());
}

#[test]
fn error_nodes_record_why_they_exist() {
    let run = err("fn f() { @ }\n");
    let reasons: Vec<Reason> = run
        .ast()
        .exprs
        .iter()
        .filter_map(|e| e.origin.reason())
        .collect();
    assert!(
        reasons.contains(&Reason::MissingExpr),
        "expected a MissingExpr provenance, got {reasons:?}"
    );
}

#[test]
fn a_function_with_no_body_is_marked_recovered() {
    let run = err("fn f()\n");
    let marked = run
        .ast()
        .root
        .iter()
        .any(|&id| run.ast().items[id].origin == Origin::Recovered(Reason::MissingBody));
    assert!(marked, "{}", run.dump());
}

#[test]
fn an_unimplemented_construct_is_marked_as_such() {
    let run = err("struct S { }\n");
    assert_eq!(run.codes(), ["RALY2007"]);
    let marked = run
        .ast()
        .root
        .iter()
        .any(|&id| run.ast().items[id].origin == Origin::Recovered(Reason::Unimplemented));
    assert!(marked, "{}", run.dump());
}

#[test]
fn nodes_from_valid_source_are_never_marked_recovered() {
    let run = run("fn f(x: Int) -> Int { let y = x + 1\n y }\n");
    assert!(run.parsed.diagnostics.is_empty());
    assert!(run.ast().exprs.iter().all(|e| e.origin == Origin::Source));
    assert!(run.ast().items.iter().all(|i| i.origin == Origin::Source));
    assert!(run.ast().stmts.iter().all(|s| s.origin == Origin::Source));
    assert!(run.ast().types.iter().all(|t| t.origin == Origin::Source));
}

// -- termination -------------------------------------------------------------

#[test]
fn pathological_input_terminates_and_still_yields_a_tree() {
    // Nothing here is Raly. The requirement is only that parsing finishes,
    // produces a tree, and does not panic.
    for src in [
        "",
        "\n\n\n",
        "}}}}}}",
        ")))",
        "((((((((((",
        "[[[[[[",
        "fn fn fn fn",
        "let let let",
        "bundle bundle bundle",
        ": : : : :",
        "space space space",
        "fn f(((((((((((",
        "type T = Vec[[[[[",
        "|> |> |>",
    ] {
        let run = run(src);
        // A tree exists either way; `root` may be empty for empty input.
        let _ = run.dump();
        assert!(run.ast().items.len() < 10_000, "for {src:?}");
    }
}

#[test]
fn deeply_nested_input_does_not_lose_the_thread() {
    let src = format!(
        "fn f() {{ {} }}\n",
        "bundle(a, ".repeat(20) + &")".repeat(20)
    );
    let run = run(&src);
    let _ = run.dump();
}

#[test]
fn an_unclosed_brace_at_end_of_file_is_reported_once() {
    let run = err("fn f() {\n    let a = 1\n");
    assert_eq!(run.codes(), ["RALY2002"], "\n{}", run.rendered());
}

// -- the shipped example -----------------------------------------------------

#[test]
fn the_broken_example_reports_every_planted_mistake() {
    use raly_diag::SourceMap;
    use raly_lexer::lex;
    use raly_parse::parse;

    let src = include_str!("../../../examples/broken-syntax.raly");
    let mut sources = SourceMap::new();
    let file = sources.add("broken-syntax.raly", src);
    let lexed = lex(file, sources.get(file).text());
    assert!(
        lexed.diagnostics.is_empty(),
        "broken-syntax.raly is meant to lex cleanly; lexical errors live in broken.raly"
    );
    let parsed = parse(file, sources.get(file).text(), &lexed.tokens);

    let codes: Vec<String> = parsed
        .diagnostics
        .iter()
        .map(|d| d.code.to_string())
        .collect();

    // Every syntax code the parser can emit is exercised by this one file.
    for want in [
        "RALY2001", "RALY2002", "RALY2003", "RALY2004", "RALY2005", "RALY2006", "RALY2007",
        "RALY2008", "RALY2009", "RALY2010",
    ] {
        assert!(
            codes.contains(&want.to_string()),
            "{want} missing: {codes:?}"
        );
    }
}

#[test]
fn the_valid_example_parses_without_a_single_diagnostic() {
    let src = include_str!("../../../examples/scene.raly");
    assert!(!ok(src).is_empty());
}
