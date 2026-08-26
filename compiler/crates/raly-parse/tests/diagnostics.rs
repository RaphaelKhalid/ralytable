//! Snapshot tests on the exact text a user reads.
//!
//! These assert character for character, on purpose. Raly's pitch is catching
//! mistakes other languages let through silently, so what a user sees when
//! something is wrong *is* the product. A change to any of these strings
//! should be a change somebody looked at and approved.

mod common;

use common::run;

/// Render the diagnostics for `src` and compare against `expected`, ignoring
/// only the leading blank line and the common indentation of the literal.
fn snapshot(src: &str, expected: &str) {
    let run = run(src);
    let got = run.rendered();
    let want = dedent(expected);
    assert_eq!(got, want, "\n--- got ---\n{got}\n--- want ---\n{want}");
}

fn dedent(text: &str) -> String {
    let text = text.strip_prefix('\n').unwrap_or(text);
    let indent = text
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| l.len() - l.trim_start().len())
        .min()
        .unwrap_or(0);
    let mut out = String::new();
    for line in text.lines() {
        if line.len() >= indent {
            out.push_str(&line[indent..]);
        }
        out.push('\n');
    }
    // The literals are written with a blank line before the closing quote so
    // that the last `= help:` is easy to read. Collapse that to the single
    // trailing newline the renderer actually emits.
    while out.ends_with("\n\n") {
        out.pop();
    }
    out
}

#[test]
fn empty_bundle_explains_that_there_is_no_identity() {
    snapshot(
        "fn f() {\n    bundle()\n}\n",
        r#"
        error[RALY2003]: `bundle()` needs at least one operand
         --> test.raly:2:5
          |
        2 |     bundle()
          |     ^^^^^^^^ this bundle superposes nothing
          |
          = note: superposition has no identity element in any VSA family, so an empty bundle denotes no vector — it is not a zero vector
          = help: pass the operands directly, as in `bundle(a, b, c)`

        "#,
    );
}

#[test]
fn a_space_without_a_family_points_at_both_halves() {
    snapshot(
        "space Concepts = 1024\n",
        r#"
        error[RALY2010]: a space needs a VSA family, not just a dimension
         --> test.raly:1:18
          |
        1 | space Concepts = 1024
          |                  ^^^^ this is the dimension; the family is missing
         ::: test.raly:1:7
          |
        1 | space Concepts = 1024
          |       -------- `Concepts` is declared here
          |
          = note: `MAP<1024>` and `FHRR<1024>` are both 1024 numbers, and mixing them silently produces garbage; the family is part of a vector's identity
          = help: write `space Concepts = MAP[1024]`, or one of `BSC`, `HRR`, `FHRR`

        "#,
    );
}

#[test]
fn a_repeated_role_shows_the_first_occurrence_too() {
    snapshot(
        "type T = Vec[C; roles {A, B, A}]\n",
        r#"
        error[RALY2009]: role `A` appears twice in this schema
         --> test.raly:1:30
          |
        1 | type T = Vec[C; roles {A, B, A}]
          |                              ^ repeated here
         ::: test.raly:1:24
          |
        1 | type T = Vec[C; roles {A, B, A}]
          |                        - first named here
          |
          = note: a role schema is a set: binding is commutative, so a role is either present or absent and cannot be present twice
          = help: remove one of the two `A`s

        "#,
    );
}

#[test]
fn an_unknown_qualifier_suggests_the_nearest_one() {
    snapshot(
        "type T = Vec[C; rolls {A}]\n",
        r#"
        error[RALY2008]: unknown type qualifier `rolls`
         --> test.raly:1:17
          |
        1 | type T = Vec[C; rolls {A}]
          |                 ^^^^^ not a recognised qualifier
          |
          = note: the qualifiers are `load`, `roles`, `clean`, `noisy`
          = help: did you mean `roles`?

        "#,
    );
}

#[test]
fn a_missing_parameter_type_says_why_inference_is_absent() {
    snapshot(
        "fn f(scene) { scene }\n",
        r#"
        error[RALY2006]: parameter `scene` has no type annotation
         --> test.raly:1:6
          |
        1 | fn f(scene) { scene }
          |      ^^^^^ expected `:` and a type after this
          |
          = note: Raly does not infer parameter types: a vector's space, load and role schema are part of its type, and inferring them would move every error to the call site
          = help: annotate it, e.g. `scene: Vec[Concepts]` or `scene: Int`

        "#,
    );
}

#[test]
fn an_unclosed_bracket_points_at_the_opener() {
    snapshot(
        "fn f(a: Int -> Int {\n    a\n}\n",
        r#"
        error[RALY2002]: unclosed `(`
         --> test.raly:1:13
          |
        1 | fn f(a: Int -> Int {
          |             ^^ expected `)` here
         ::: test.raly:1:5
          |
        1 | fn f(a: Int -> Int {
          |     - `(` opened here is never closed
          |
          = help: add `)` to close it

        "#,
    );
}

#[test]
fn a_reserved_operator_says_it_is_not_a_vsa_op() {
    snapshot(
        "fn f(a: V, b: V) -> V {\n    a ^ b\n}\n",
        r#"
        error[RALY2001]: expected an expression, found `^`
         --> test.raly:2:7
          |
        2 |     a ^ b
          |       ^ expected an expression
          |
          = note: `^`, `~`, `@`, `&`, `|` and `?` are reserved but are not expression operators in Raly
          = help: the VSA operations are written as calls: `bind(a, b)`, `bundle(a, b, c)`

        "#,
    );
}

#[test]
fn a_bad_variant_names_the_ones_that_exist() {
    snapshot(
        "fn f(a: V, b: V) -> V {\n    bundle.rightward(a, b)\n}\n",
        r#"
        error[RALY2005]: `bundle` has no variant `rightward`
         --> test.raly:2:12
          |
        2 |     bundle.rightward(a, b)
          |            ^^^^^^^^^ unknown variant
          |
          = note: the variants of `bundle` are `left`
          = help: `bundle.left` is the left-nested binary fold; it is a different function from n-ary `bundle`, not a spelling of it

        "#,
    );
}

#[test]
fn a_pipeline_counts_the_piped_value_as_an_operand() {
    snapshot(
        "fn f(v: V) -> V {\n    v |> unbind\n}\n",
        r#"
        error[RALY2004]: `unbind` takes exactly 2 operands, but 1 was given
         --> test.raly:2:10
          |
        2 |     v |> unbind
          |          ^^^^^^ 1 operand here
          |
          = note: the piped value counts as the first operand, so `unbind` sees 1 in total
          = note: `unbind(v, key)` takes the vector and the key it was bound with

        "#,
    );
}

#[test]
fn several_diagnostics_render_in_source_order_separated_by_blank_lines() {
    snapshot(
        "space A = 1\nfn f(x) { x }\n",
        r#"
        error[RALY2010]: a space needs a VSA family, not just a dimension
         --> test.raly:1:11
          |
        1 | space A = 1
          |           ^ this is the dimension; the family is missing
         ::: test.raly:1:7
          |
        1 | space A = 1
          |       - `A` is declared here
          |
          = note: `MAP<1024>` and `FHRR<1024>` are both 1024 numbers, and mixing them silently produces garbage; the family is part of a vector's identity
          = help: write `space A = MAP[1]`, or one of `BSC`, `HRR`, `FHRR`

        error[RALY2006]: parameter `x` has no type annotation
         --> test.raly:2:6
          |
        2 | fn f(x) { x }
          |      ^ expected `:` and a type after this
          |
          = note: Raly does not infer parameter types: a vector's space, load and role schema are part of its type, and inferring them would move every error to the call site
          = help: annotate it, e.g. `x: Vec[Concepts]` or `x: Int`

        "#,
    );
}
