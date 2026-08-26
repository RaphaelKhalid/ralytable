//! rustc-style UI tests: every `.raly` file in `tests/ui/` is compiled and its
//! rendered diagnostics compared, character for character, against the `.stderr`
//! file beside it.
//!
//! This is the enforcement mechanism decision 5 of
//! `docs/compiler-architecture.md` asks for. Diagnostics are the product, so a
//! change to what a user reads should be a diff somebody had to look at and
//! approve — not something that drifts silently while a `contains("RALY4007")`
//! assertion stays green.
//!
//! To re-record after a deliberate change:
//!
//! ```text
//! RALY_BLESS=1 cargo test -p raly --test ui
//! ```
//!
//! Then read the diff. If it is not an improvement, it is a regression.
//!
//! Files are compiled under their bare file name rather than their path, so
//! the golden output does not depend on where the repository is checked out.

use std::path::{Path, PathBuf};

use raly_diag::RenderConfig;

fn ui_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/ui")
}

fn blessing() -> bool {
    std::env::var_os("RALY_BLESS").is_some()
}

#[test]
fn rendered_diagnostics_match_their_golden_files() {
    let dir = ui_dir();
    let mut cases: Vec<PathBuf> = std::fs::read_dir(&dir)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", dir.display()))
        .filter_map(|entry| entry.ok().map(|e| e.path()))
        .filter(|p| p.extension().and_then(|e| e.to_str()) == Some("raly"))
        .collect();
    cases.sort();
    assert!(!cases.is_empty(), "no UI tests found in {}", dir.display());

    let mut failures = Vec::new();
    for case in &cases {
        let name = case
            .file_name()
            .and_then(|n| n.to_str())
            .expect("a UI test has a name")
            .to_string();
        let source = std::fs::read_to_string(case).expect("a UI test is readable");
        // Normalised so a repository checked out on Windows and one on Linux
        // produce byte-identical output.
        let source = source.replace("\r\n", "\n");
        let compiled = raly::compile(name.clone(), source);
        let actual = compiled.render(RenderConfig::plain());

        let golden = case.with_extension("stderr");
        if blessing() {
            std::fs::write(&golden, &actual).expect("a golden file is writable");
            continue;
        }
        let expected = std::fs::read_to_string(&golden)
            .unwrap_or_else(|_| {
                panic!(
                    "{} has no golden file; run `RALY_BLESS=1 cargo test -p raly --test ui`",
                    name
                )
            })
            .replace("\r\n", "\n");
        if expected != actual {
            failures.push(format!(
                "--- {name} ---\nexpected:\n{expected}\nactual:\n{actual}"
            ));
        }
    }

    assert!(
        failures.is_empty(),
        "{} UI test(s) drifted. Re-record with `RALY_BLESS=1 cargo test -p raly --test ui` \
         and read the diff.\n\n{}",
        failures.len(),
        failures.join("\n")
    );
}

/// Every UI test should exercise a code, and every code the type-checking
/// phases can emit should have a UI test. This catches the failure mode where
/// a diagnostic is added and never regression-tested.
#[test]
fn every_resolution_and_type_code_has_a_ui_test() {
    let dir = ui_dir();
    let mut seen = String::new();
    for entry in std::fs::read_dir(&dir)
        .expect("the ui directory exists")
        .flatten()
    {
        if entry.path().extension().and_then(|e| e.to_str()) == Some("stderr") {
            seen.push_str(&std::fs::read_to_string(entry.path()).unwrap_or_default());
        }
    }
    let mut missing = Vec::new();
    for (code, _) in raly_diag::code::REGISTRY {
        let text = code.as_str();
        let phase = &text[4..5];
        if matches!(phase, "3" | "4" | "5") && !seen.contains(text) {
            missing.push(text);
        }
    }
    assert!(
        missing.is_empty(),
        "these codes have no UI test: {missing:?}"
    );
}
