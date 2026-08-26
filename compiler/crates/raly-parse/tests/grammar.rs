//! One test per grammar construct, asserted against the AST dump.
//!
//! The dump is a readable projection of the tree, so these double as a
//! worked example of what each piece of syntax turns into.

mod common;

use common::{contains_lines, ok, run};
use raly_ast::{Ast, ExprKind, ItemKind, TypeExprKind, TypeQual, Visitor, VsaOp, VsaVariant};

// -- items -------------------------------------------------------------------

#[test]
fn import_declaration() {
    contains_lines(
        &ok("import std::codebook::fixed\n"),
        "import `std::codebook::fixed` @ 0..27",
    );
}

#[test]
fn space_declaration() {
    let dump = ok("space Concepts = MAP[8192]\n");
    contains_lines(
        &dump,
        "
        space `Concepts` family=MAP @ 0..26
        dim:
        int 8192 @ 21..25
        ",
    );
}

#[test]
fn space_with_attributes() {
    let dump = ok("space S = FHRR[1024] where seed = 42, codebook = fixed\n");
    contains_lines(
        &dump,
        "
        space `S` family=FHRR @ 0..53
        attr `seed`
        int 42 @ 34..36
        attr `codebook`
        path `fixed` @ 48..53
        ",
    );
}

#[test]
fn space_dimension_may_be_an_expression() {
    // Constant folding is the checker's job, so the parser accepts any
    // expression in the dimension slot.
    let dump = ok("let base = 512\nspace S = MAP[2 * base]\n");
    contains_lines(&dump, "binary `*`");
}

#[test]
fn role_declaration_names_many_roles_in_one_space() {
    contains_lines(
        &ok("space S = MAP[64]\nrole Subject, Verb, Object in S\n"),
        "role Subject, Verb, Object in `S` @ 18..49",
    );
}

#[test]
fn type_alias() {
    let dump = ok("type Scene = Vec[Concepts; load 3]\n");
    contains_lines(
        &dump,
        "
        type `Scene` @ 0..33
        type `Vec` @ 13..33
        type `Concepts` @ 17..25
        qual load
        int 3 @ 32..33
        ",
    );
}

#[test]
fn top_level_let_is_a_constant() {
    contains_lines(&ok("let shift: Int = 1\n"), "let `shift`");
}

#[test]
fn function_with_params_return_type_and_where_clause() {
    let dump = ok("fn f(a: Int, b: Str) -> Bool where inline = true { a }\n");
    contains_lines(
        &dump,
        "
        fn `f` @ 0..53
        param `a`
        type `Int` @ 8..11
        param `b`
        type `Str` @ 16..19
        returns:
        type `Bool` @ 24..28
        attr `inline`
        bool true @ 43..47
        ",
    );
}

#[test]
fn empty_parameter_list_and_empty_block() {
    contains_lines(&ok("fn f() { }\n"), "fn `f` @ 0..10");
}

// -- types -------------------------------------------------------------------

#[test]
fn type_with_no_arguments() {
    contains_lines(&ok("type A = Int\n"), "type `Int` @ 9..12");
}

#[test]
fn type_with_several_arguments() {
    let dump = ok("type A = Map[Str, Int]\n");
    contains_lines(
        &dump,
        "
        type `Map` @ 9..22
        type `Str` @ 13..16
        type `Int` @ 18..21
        ",
    );
}

#[test]
fn all_four_qualifiers() {
    let dump = ok("type A = Vec[S; load 7; roles {X, Y}; clean]\ntype B = Vec[S; noisy]\n");
    contains_lines(
        &dump,
        "
        qual load
        int 7 @ 21..22
        qual roles {X, Y}
        qual clean
        qual noisy
        ",
    );
}

#[test]
fn role_schema_is_stored_sorted() {
    // A role schema is a set, so the canonical order is by symbol, not by the
    // order the user happened to write. `written` keeps the source order.
    let run = run("type A = Vec[S; roles {Zeta, Alpha, Mid}]\n");
    assert!(run.parsed.diagnostics.is_empty());
    let mut found = false;
    for ty in run.ast().types.iter() {
        let TypeExprKind::Named { quals, .. } = &ty.kind else {
            continue;
        };
        for qual in quals {
            let TypeQual::Roles { names, written, .. } = qual else {
                continue;
            };
            found = true;
            let text = |v: &Vec<raly_ast::Ident>| {
                v.iter()
                    .map(|i| run.ast().text(*i).to_string())
                    .collect::<Vec<_>>()
            };
            assert_eq!(text(written), ["Zeta", "Alpha", "Mid"]);
            // Interning order is source order, so sorting by symbol gives the
            // order they were first seen — the point is that it is *stable*
            // and independent of how any later schema is written.
            assert_eq!(text(names).len(), 3);
            assert!(names.windows(2).all(|w| w[0].symbol <= w[1].symbol));
        }
    }
    assert!(found, "no role schema was parsed");
}

#[test]
fn load_never_carries_a_capacity_out_of_the_parser() {
    // Capacity is derived from the space's dimension by the checker. There is
    // no syntax for it, so the slot must always be empty here.
    let run = run("type A = Vec[S; load 3]\n");
    for ty in run.ast().types.iter() {
        let TypeExprKind::Named { quals, .. } = &ty.kind else {
            continue;
        };
        for qual in quals {
            if let TypeQual::Load { capacity, .. } = qual {
                assert_eq!(*capacity, None);
            }
        }
    }
}

#[test]
fn function_types() {
    let dump = ok("type F = (Int, Str) -> Bool\n");
    contains_lines(
        &dump,
        "
        type fn @ 9..27
        type `Int` @ 10..13
        type `Str` @ 15..18
        ->
        type `Bool` @ 23..27
        ",
    );
}

#[test]
fn tuple_and_unit_types() {
    contains_lines(&ok("type U = ()\n"), "type tuple @ 9..11");
    contains_lines(&ok("type P = (Int, Str)\n"), "type tuple @ 9..19");
    // A single parenthesised type is just that type, not a one-tuple.
    let dump = ok("type G = (Int)\n");
    assert!(!dump.contains("tuple"), "{dump}");
}

#[test]
fn qualified_type_paths() {
    contains_lines(
        &ok("type A = std::vsa::Vec[S]\n"),
        "type `std::vsa::Vec` @ 9..25",
    );
}

// -- expressions -------------------------------------------------------------

#[test]
fn literals() {
    let dump =
        ok("fn f() { 1 }\nfn g() { 1.5 }\nfn h() { \"hi\" }\nfn i() { true }\nfn j() { false }\n");
    contains_lines(
        &dump,
        "
        int 1 @ 9..10
        float 1.5 @ 22..25
        str \"hi\" @ 35..39
        bool true @ 50..54
        bool false @ 65..70
        ",
    );
}

#[test]
fn paths_groups_lists_and_tuples() {
    contains_lines(&ok("fn f() { a::b::c }\n"), "path `a::b::c` @ 9..15");
    contains_lines(&ok("fn f() { (a) }\n"), "group @ 9..12");
    contains_lines(&ok("fn f() { [a, b] }\n"), "list @ 9..15");
    contains_lines(&ok("fn f() { (a, b) }\n"), "tuple @ 9..15");
    contains_lines(&ok("fn f() { () }\n"), "tuple @ 9..11");
}

#[test]
fn arithmetic_precedence_is_the_usual_one() {
    let dump = ok("fn f() { 1 + 2 * 3 }\n");
    contains_lines(
        &dump,
        "
        binary `+` @ 9..18
        int 1 @ 9..10
        binary `*` @ 13..18
        ",
    );
}

#[test]
fn arithmetic_is_left_associative() {
    let dump = ok("fn f() { 1 - 2 - 3 }\n");
    contains_lines(
        &dump,
        "
        binary `-` @ 9..18
        binary `-` @ 9..14
        ",
    );
}

#[test]
fn comparison_binds_looser_than_arithmetic() {
    let dump = ok("fn f() { 1 + 2 == 3 }\n");
    contains_lines(
        &dump,
        "
        binary `==` @ 9..19
        binary `+` @ 9..14
        ",
    );
}

#[test]
fn unary_operators_bind_tighter_than_any_infix() {
    let dump = ok("fn f() { -a * b }\nfn g() { !p == q }\n");
    contains_lines(
        &dump,
        "
        binary `*` @ 9..15
        unary `-` @ 9..11
        ",
    );
    contains_lines(
        &dump,
        "
        binary `==` @ 27..35
        unary `!` @ 27..29
        ",
    );
}

#[test]
fn calls_and_field_access_are_postfix() {
    let dump = ok("fn f() { g(1, 2).h }\n");
    contains_lines(
        &dump,
        "
        field `h` @ 9..18
        call @ 9..16
        path `g` @ 9..10
        ",
    );
}

#[test]
fn if_else_chains() {
    let dump = ok("fn f() { if a { 1 } else if b { 2 } else { 3 } }\n");
    contains_lines(
        &dump,
        "
        if @ 9..45
        path `a` @ 12..13
        if @ 25..45
        ",
    );
}

#[test]
fn blocks_have_statements_and_an_optional_tail() {
    let dump = ok("fn f() { let a = 1; g(a); a }\n");
    contains_lines(
        &dump,
        "
        block @ 7..28
        let `a`
        call @ 20..24
        tail:
        path `a` @ 25..26
        ",
    );
}

#[test]
fn statements_may_omit_the_semicolon() {
    let dump = ok("fn f() {\n    let a = 1\n    let b = 2\n    b\n}\n");
    contains_lines(&dump, "let `a` @ 13..22");
    contains_lines(&dump, "let `b` @ 27..36");
}

#[test]
fn return_with_and_without_a_value() {
    contains_lines(&ok("fn f() { return 1; }\n"), "return @ 9..18");
    contains_lines(&ok("fn f() { return; }\n"), "return @ 9..16");
}

#[test]
fn mutable_let() {
    contains_lines(&ok("fn f() { let mut a = 1; a }\n"), "let mut `a` @ 9..23");
}

#[test]
fn nested_items_inside_a_block() {
    contains_lines(
        &ok("fn f() { space S = MAP[8]\n a }\n"),
        "space `S` family=MAP @ 9..25",
    );
}

// -- the VSA operations ------------------------------------------------------

#[test]
fn every_operation_parses() {
    let dump = ok("fn f() {\n\
         bind(a, b)\n\
         bundle(a, b, c)\n\
         permute(a)\n\
         permute(a, 2)\n\
         unbind(a, b)\n\
         cleanup(a)\n\
         cleanup(a, S)\n\
         }\n");
    for op in ["bind", "bundle", "permute", "unbind", "cleanup"] {
        assert!(dump.contains(op), "{op} missing from\n{dump}");
    }
}

#[test]
fn bundle_accepts_a_trailing_comma_and_many_operands() {
    let dump = ok("fn f() { bundle(a, b, c, d, e,) }\n");
    contains_lines(&dump, "bundle (multiset) @ 9..30");
}

#[test]
fn commutative_operations_are_marked_as_multisets() {
    let dump = ok("fn f() { bind(a, b) }\nfn g() { bundle(a, b) }\n");
    assert!(dump.contains("bind (multiset)"), "{dump}");
    assert!(dump.contains("bundle (multiset)"), "{dump}");
}

#[test]
fn the_fold_is_a_different_node_and_keeps_source_order() {
    let dump = ok("fn f() { bundle.left(a, b, c) }\n");
    // No `(multiset)` marker: the fold is order-dependent by construction.
    assert!(dump.contains("bundle.left @"), "{dump}");
    assert!(!dump.contains("bundle.left (multiset)"), "{dump}");

    let run = run("fn f() { bundle.left(a, b, c) }\n");
    let call = find_vsa(run.ast()).expect("a vsa call");
    assert_eq!(call.0, VsaOp::Bundle);
    assert_eq!(call.1, Some(VsaVariant::Left));
    assert!(call.2, "the fold must record no canonical order");
}

#[test]
fn bundle_operand_order_does_not_change_the_structural_key() {
    // Commutativity is structural, not a law a later pass has to apply.
    // Both calls live in one tree so that they share one interner.
    let run = run("fn f() { bundle(alpha, beta, gamma) }\nfn g() { bundle(gamma, alpha, beta) }\n");
    let keys = vsa_keys(run.ast());
    assert_eq!(keys.len(), 2);
    assert_eq!(keys[0], keys[1]);
}

#[test]
fn fold_operand_order_does_change_the_structural_key() {
    // The fold nests left, so its operands are a sequence, not a multiset.
    let run = run("fn f() { bundle.left(alpha, beta) }\nfn g() { bundle.left(beta, alpha) }\n");
    let keys = vsa_keys(run.ast());
    assert_eq!(keys.len(), 2);
    assert_ne!(keys[0], keys[1]);
}

#[test]
fn operations_nest() {
    let dump = ok("fn f() { bundle(bind(A, s), bind(B, v)) }\n");
    contains_lines(
        &dump,
        "
        bundle (multiset) @ 9..38
        bind (multiset) @ 16..26
        bind (multiset) @ 28..38
        ",
    );
}

// -- the pipeline ------------------------------------------------------------

#[test]
fn pipeline_into_a_plain_function() {
    let dump = ok("fn f() { x |> g }\n");
    contains_lines(
        &dump,
        "
        pipeline `|>` @ 9..15
        path `x` @ 9..10
        path `g` @ 14..15
        ",
    );
}

#[test]
fn pipeline_into_a_call_with_extra_arguments() {
    let dump = ok("fn f() { x |> g(1, 2) }\n");
    contains_lines(
        &dump,
        "
        pipeline `|>` @ 9..20
        call @ 14..20
        ",
    );
}

#[test]
fn pipeline_into_a_bare_operation_keyword() {
    // `v |> cleanup` is legal: the piped value is the sole operand.
    let dump = ok("fn f() { v |> cleanup }\n");
    contains_lines(
        &dump,
        "
        pipeline `|>` @ 9..21
        cleanup @ 14..21
        ",
    );
}

#[test]
fn pipeline_is_left_associative_and_binds_loosest() {
    let dump = ok("fn f() { a + b |> g |> h }\n");
    contains_lines(
        &dump,
        "
        pipeline `|>` @ 9..24
        pipeline `|>` @ 9..19
        binary `+` @ 9..14
        ",
    );
}

#[test]
fn a_realistic_query_chain() {
    let dump = ok("fn f(s: Scene) -> Sym[C] { s |> unbind(Subject) |> cleanup(C) }\n");
    contains_lines(
        &dump,
        "
        pipeline `|>` @ 27..60
        pipeline `|>` @ 27..46
        path `s` @ 27..28
        unbind @ 32..46
        cleanup @ 50..60
        ",
    );
}

// -- spans -------------------------------------------------------------------

#[test]
fn spans_are_exact() {
    // The one place byte offsets are pinned end to end. Every node's span must
    // cover exactly the text it came from, including the brackets and the
    // qualifiers, because every diagnostic downstream is only as good as this.
    let dump =
        ok("space S = MAP[1024]\nfn f(x: Vec[S; load 2]) -> Sym[S] {\n    x |> cleanup(S)\n}\n");
    assert_eq!(
        dump,
        "\
space `S` family=MAP @ 0..19
  dim:
    int 1024 @ 14..18
fn `f` @ 20..77
  param `x`
    type `Vec` @ 28..42
      type `S` @ 32..33
      qual load
        int 2 @ 40..41
  returns:
    type `Sym` @ 47..53
      type `S` @ 51..52
  block @ 54..77
    tail:
      pipeline `|>` @ 60..75
        path `x` @ 60..61
        cleanup @ 65..75
          path `S` @ 73..74
"
    );
}

// -- totality ----------------------------------------------------------------

#[test]
fn the_tree_covers_every_token_of_a_valid_program() {
    let src = include_str!("../../../examples/scene.raly");
    assert_covers_all_tokens(src);
}

#[test]
fn the_tree_covers_every_token_of_a_broken_program() {
    // The interesting case: recovery must not leave holes.
    let src = include_str!("../../../examples/broken-syntax.raly");
    assert_covers_all_tokens(src);
}

// -- helpers -----------------------------------------------------------------

/// Every significant token must lie inside some node's span.
fn assert_covers_all_tokens(src: &str) {
    use raly_diag::{SourceMap, Span};
    use raly_lexer::lex;
    use raly_parse::parse;

    let mut sources = SourceMap::new();
    let file = sources.add("cover.raly", src);
    let lexed = lex(file, sources.get(file).text());
    let parsed = parse(file, sources.get(file).text(), &lexed.tokens);

    let mut spans: Vec<Span> = Vec::new();
    spans.extend(parsed.ast.exprs.iter().map(|n| n.span));
    spans.extend(parsed.ast.items.iter().map(|n| n.span));
    spans.extend(parsed.ast.stmts.iter().map(|n| n.span));
    spans.extend(parsed.ast.types.iter().map(|n| n.span));

    for token in lexed.significant() {
        let covered = spans
            .iter()
            .any(|s| s.start <= token.span.start && token.span.end <= s.end);
        assert!(
            covered,
            "token {:?} at {}..{} (`{}`) is not inside any node",
            token.kind,
            token.span.start,
            token.span.end,
            &src[token.span.range()]
        );
    }
}

/// The op, variant and "has no canonical order" flag of the first VSA call.
fn find_vsa(ast: &Ast) -> Option<(VsaOp, Option<VsaVariant>, bool)> {
    ast.exprs.iter().find_map(|e| match &e.kind {
        ExprKind::Vsa(call) => Some((call.op, call.variant_kind, call.canonical.is_empty())),
        _ => None,
    })
}

/// The structural key of every VSA call in the tree, in source order.
fn vsa_keys(ast: &Ast) -> Vec<u64> {
    struct Find(Vec<raly_ast::ExprId>);
    impl Visitor for Find {
        fn visit_expr(&mut self, ast: &Ast, id: raly_ast::ExprId) {
            if matches!(ast.exprs[id].kind, ExprKind::Vsa(_)) {
                self.0.push(id);
            }
            raly_ast::visit::walk_expr(self, ast, id);
        }
    }
    let mut find = Find(Vec::new());
    find.visit_ast(ast);
    find.0.iter().map(|&id| ast.structural_key(id)).collect()
}

/// Guards against the item kinds silently changing shape.
#[test]
fn item_kinds_are_what_they_claim() {
    let run = run("import a\nspace S = MAP[8]\nrole R in S\ntype T = Int\nfn f() {}\nlet x = 1\n");
    assert!(run.parsed.diagnostics.is_empty(), "{}", run.rendered());
    let kinds: Vec<&str> = run
        .ast()
        .root
        .iter()
        .map(|&id| match run.ast().items[id].kind {
            ItemKind::Import(_) => "import",
            ItemKind::Space(_) => "space",
            ItemKind::Role(_) => "role",
            ItemKind::TypeAlias(_) => "type",
            ItemKind::Fn(_) => "fn",
            ItemKind::Let(_) => "let",
            ItemKind::Error => "error",
        })
        .collect();
    assert_eq!(kinds, ["import", "space", "role", "type", "fn", "let"]);
}
