//! Golden tests for `raly explain`.
//!
//! Same discipline as the UI tests, and for the same reason: the output *is*
//! the feature, so a change to what a reader sees should be a diff somebody
//! had to look at and approve, not a drift that a `contains("capacity")`
//! assertion sleeps through.
//!
//! ```text
//! RALY_BLESS=1 cargo test -p raly --test explain
//! ```
//!
//! The subjects are the real example programs in `compiler/examples/`, so
//! there is one copy of each and the examples cannot rot away from what the
//! explainer says about them.

use std::path::{Path, PathBuf};

/// The example programs worth explaining, plus two that do not type-check —
/// explaining is not checking, and a broken program still has types.
const CASES: &[&str] = &[
    "explain-me.raly",
    "scene.raly",
    "capacity.raly",
    "broadcast.raly",
];

fn examples_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../examples")
}

fn golden_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/explain")
}

fn blessing() -> bool {
    std::env::var_os("RALY_BLESS").is_some()
}

fn explained(name: &str) -> (String, String) {
    let source = std::fs::read_to_string(examples_dir().join(name))
        .unwrap_or_else(|e| panic!("cannot read example {name}: {e}"))
        // Normalised so a checkout on Windows and one on Linux agree byte for
        // byte, exactly as the UI tests do.
        .replace("\r\n", "\n");
    let compiled = raly::compile(name.to_string(), source);
    let explanation = compiled.explain();
    (
        raly_explain::render::plain(&explanation),
        raly_explain::render::json(&explanation),
    )
}

fn compare(name: &str, extension: &str, actual: &str, failures: &mut Vec<String>) {
    let golden = golden_dir().join(format!("{name}.{extension}"));
    if blessing() {
        std::fs::create_dir_all(golden_dir()).expect("the golden directory is writable");
        std::fs::write(&golden, actual).expect("a golden file is writable");
        return;
    }
    let expected = std::fs::read_to_string(&golden)
        .unwrap_or_else(|_| {
            panic!(
                "{} has no golden file; run `RALY_BLESS=1 cargo test -p raly --test explain`",
                golden.display()
            )
        })
        .replace("\r\n", "\n");
    if expected != actual {
        failures.push(format!(
            "--- {name}.{extension} ---\nexpected:\n{expected}\nactual:\n{actual}"
        ));
    }
}

#[test]
fn explanations_match_their_golden_files() {
    let mut failures = Vec::new();
    for name in CASES {
        let (plain, json) = explained(name);
        compare(name, "txt", &plain, &mut failures);
        compare(name, "json", &json, &mut failures);
    }
    assert!(
        failures.is_empty(),
        "{} explanation(s) drifted. Re-record with \
         `RALY_BLESS=1 cargo test -p raly --test explain` and read the diff.\n\n{}",
        failures.len(),
        failures.join("\n")
    );
}

/// The three facts nobody wrote down in `explain-me.raly`, all of which follow
/// from the types alone. If any of these stops being said, the feature has
/// quietly become a signature printer.
#[test]
fn the_unwritten_facts_are_flagged() {
    let (plain, _) = explained("explain-me.raly");
    assert!(plain.contains("exactly at capacity"), "{plain}");
    assert!(plain.contains("only approximate"), "{plain}");
    assert!(plain.contains("levels of extraction deep"), "{plain}");
    // And the one about the space itself: a measured effective width is far
    // below the width written in the declaration.
    assert!(plain.contains("The written width would suggest"), "{plain}");
}

/// Rule two of the feature: say only what the types prove. A dimension the
/// checker cannot fold leaves capacity genuinely unknown, and the output has
/// to admit that rather than pick a number.
#[test]
fn unknown_properties_are_said_to_be_unknown() {
    let compiled = raly::compile(
        "m.raly",
        "space S = MAP[width]\nfn f(a: Sym[S]) -> Sym[S] { a }\n",
    );
    let explanation = compiled.explain();
    let plain = raly_explain::render::plain(&explanation);
    let json = raly_explain::render::json(&explanation);
    assert!(
        plain.contains("is unknown, because its width is"),
        "{plain}"
    );
    assert!(json.contains("\"capacity\": null"), "{json}");
    assert!(json.contains("\"dimension\": null"), "{json}");
}

/// Prose is set narrow on purpose, and the flag marker appears once per flag
/// rather than once per line.
#[test]
fn prose_is_wrapped_and_flags_are_marked_once() {
    let (plain, _) = explained("explain-me.raly");
    for line in plain.lines() {
        // Signature lines reproduce a declaration and are allowed to be as
        // long as the declaration is; prose is not.
        if line.starts_with("  ") {
            assert!(line.chars().count() <= 78, "too wide: {line:?}");
        }
    }
    assert_eq!(plain.matches("  ! ").count(), plain.matches('!').count());
}

/// Every example in the repository can be explained, including the ones that
/// are deliberately broken. Explaining is total, like every other phase.
#[test]
fn every_example_can_be_explained() {
    let mut seen = 0;
    for entry in std::fs::read_dir(examples_dir())
        .expect("the examples directory exists")
        .flatten()
    {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("raly") {
            continue;
        }
        let name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap()
            .to_string();
        let source = std::fs::read_to_string(&path).expect("an example is readable");
        let compiled = raly::compile(name.clone(), source);
        let explanation = compiled.explain();
        let plain = raly_explain::render::plain(&explanation);
        assert!(plain.starts_with(&name), "{name}: {plain}");
        assert!(plain.lines().count() >= 2, "{name}: {plain}");
        seen += 1;
    }
    assert!(seen >= 6, "expected several examples, found {seen}");
}

/// The JSON is machine-readable, not the prose in quotes: it carries the
/// numbers the prose was derived from.
#[test]
fn json_carries_the_numbers_behind_the_prose() {
    let (_, json) = explained("explain-me.raly");
    assert!(json.contains("\"capacity_basis\": \"measured effective width\""));
    assert!(json.contains("\"capacity_dimension\": 111"));
    assert!(json.contains("\"dimension\": 384"));
    assert!(json.contains("\"unbind_depth\": 2"));
    assert!(json.contains("\"role_schema_open\": false"));
    assert_eq!(json.matches('{').count(), json.matches('}').count());
    assert_eq!(json.matches('[').count(), json.matches(']').count());
}
