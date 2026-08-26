//! End-to-end tests for the `raly` binary: exit codes and stream discipline.

use std::process::Command;

fn raly() -> Command {
    Command::new(env!("CARGO_BIN_EXE_raly"))
}

/// Write a temp file next to the test binary and return its path.
fn temp_file(name: &str, contents: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join("raly-cli-tests");
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join(name);
    std::fs::write(&path, contents).unwrap();
    path
}

#[test]
fn check_succeeds_on_a_clean_file() {
    let path = temp_file(
        "clean.raly",
        "// fine\nspace S = MAP[1024]\nrole R in S\nlet x: Int = 1\n",
    );
    let output = raly().arg("check").arg(&path).output().unwrap();
    assert_eq!(output.status.code(), Some(0));
    assert!(
        output.stderr.is_empty(),
        "{:?}",
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn check_exits_non_zero_on_error_and_writes_to_stderr() {
    let path = temp_file("bad.raly", "let s = \"unclosed\n");
    let output = raly().arg("check").arg(&path).output().unwrap();
    assert_eq!(output.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("error[RALY1002]"), "{stderr}");
    assert!(stderr.contains("error: 1 error"), "{stderr}");
    assert!(output.stdout.is_empty(), "check prints nothing on stdout");
}

#[test]
fn a_warning_alone_does_not_fail_the_run() {
    // Wrong extension is a warning, so the exit code stays 0.
    let path = temp_file("clean.txt", "let x = 1\n");
    let output = raly().arg("check").arg(&path).output().unwrap();
    assert_eq!(output.status.code(), Some(0));
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("warning[RALY0002]"), "{stderr}");
}

#[test]
fn lex_dumps_tokens_to_stdout() {
    let path = temp_file("tokens.raly", "let x = 1\n");
    let output = raly().arg("lex").arg(&path).output().unwrap();
    assert_eq!(output.status.code(), Some(0));
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("KIND"), "{stdout}");
    assert!(stdout.contains("Let"), "{stdout}");
    assert!(stdout.contains("Eof"), "{stdout}");
}

#[test]
fn a_missing_file_exits_two() {
    let output = raly()
        .arg("check")
        .arg("definitely-not-here.raly")
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("RALY0001"), "{stderr}");
}

#[test]
fn a_bad_command_line_exits_two() {
    for args in [
        vec!["check"],              // no file
        vec!["nonsense", "f.raly"], // no command; `nonsense` is read as the file
        vec!["lex", "--bogus", "f.raly"],
    ] {
        let output = raly().args(&args).output().unwrap();
        assert_eq!(output.status.code(), Some(2), "for {args:?}");
    }
}

#[test]
fn help_and_version_exit_zero() {
    for flag in ["--help", "-h", "--version", "-V"] {
        let output = raly().arg(flag).output().unwrap();
        assert_eq!(output.status.code(), Some(0), "for {flag}");
        assert!(!output.stdout.is_empty(), "for {flag}");
    }
}

#[test]
fn colour_is_opt_in() {
    let path = temp_file("bad2.raly", "let s = \"unclosed\n");
    let plain = raly().arg("check").arg(&path).output().unwrap();
    assert!(!plain.stderr.contains(&0x1b));

    let colored = raly()
        .args(["check", "--color"])
        .arg(&path)
        .output()
        .unwrap();
    assert!(colored.stderr.contains(&0x1b));
}

// -- parsing -----------------------------------------------------------------

/// The repository's example files, resolved relative to this crate.
fn example(name: &str) -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../examples")
        .join(name)
}

#[test]
fn check_accepts_the_substantial_example() {
    let output = raly()
        .arg("check")
        .arg(example("scene.raly"))
        .output()
        .unwrap();
    assert_eq!(
        output.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    // The one thing it does say is the deliberate `bundle.left` demonstration:
    // the fold is a different function from the n-ary primitive, and the
    // checker says so without failing the build.
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("warning[RALY5003]"), "{stderr}");
    assert!(!stderr.contains("error["), "{stderr}");
}

#[test]
fn check_reports_every_planted_syntax_error_in_one_run() {
    let output = raly()
        .arg("check")
        .arg(example("broken-syntax.raly"))
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&output.stderr);
    for code in [
        "RALY2001", "RALY2002", "RALY2003", "RALY2004", "RALY2005", "RALY2006", "RALY2007",
        "RALY2008", "RALY2009", "RALY2010",
    ] {
        assert!(
            stderr.contains(code),
            "{code} missing from:
{stderr}"
        );
    }
    // Well over the one-error-per-run bar the whole design exists to clear.
    assert!(stderr.contains("errors"), "{stderr}");
}

#[test]
fn parse_dumps_the_tree_to_stdout() {
    let path = temp_file(
        "dump.raly",
        "space S = MAP[64]
role R in S
",
    );
    let output = raly().arg("parse").arg(&path).output().unwrap();
    assert_eq!(output.status.code(), Some(0));
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("space `S` family=MAP"), "{stdout}");
    assert!(stdout.contains("role R in `S`"), "{stdout}");
    assert!(output.stderr.is_empty());
}

#[test]
fn parse_still_dumps_a_tree_for_a_broken_file() {
    // The parser never fails, so `parse` always has something to print.
    let path = temp_file(
        "dump-bad.raly",
        "fn f( { }
",
    );
    let output = raly().arg("parse").arg(&path).output().unwrap();
    assert_eq!(output.status.code(), Some(1));
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("fn `f`"), "{stdout}");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("RALY2002"), "{stderr}");
}

#[test]
fn check_reports_lexical_and_syntactic_errors_together() {
    let path = temp_file(
        "both.raly",
        "let s = \"unclosed
fn f( { }
",
    );
    let output = raly().arg("check").arg(&path).output().unwrap();
    assert_eq!(output.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("RALY1002"), "{stderr}");
    assert!(stderr.contains("RALY2002"), "{stderr}");
}

// -- explaining --------------------------------------------------------------

#[test]
fn explain_writes_prose_to_stdout_and_exits_zero() {
    let output = raly()
        .arg("explain")
        .arg(example("explain-me.raly"))
        .output()
        .unwrap();
    // `explain-me.raly` carries one deliberate warning and no errors.
    assert_eq!(output.status.code(), Some(0));
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("This file declares"), "{stdout}");
    assert!(stdout.contains("exactly at capacity"), "{stdout}");
    // Diagnostics keep to stderr even here, so the prose stays pipeable.
    assert!(!stdout.contains("warning["), "{stdout}");
}

#[test]
fn explain_json_is_machine_readable() {
    let output = raly()
        .args(["explain", "--json"])
        .arg(example("explain-me.raly"))
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.starts_with('{'), "{stdout}");
    assert!(stdout.trim_end().ends_with('}'), "{stdout}");
    assert!(stdout.contains("\"capacity\": 3"), "{stdout}");
    assert!(stdout.contains("\"kind\": \"space\""), "{stdout}");
}

#[test]
fn explain_still_describes_a_file_that_does_not_check() {
    // Explaining is not checking. A program with errors still has types, and
    // "what is this meant to be?" is a question people ask precisely then.
    let output = raly()
        .arg("explain")
        .arg(example("broadcast.raly"))
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stdout.contains("This file declares"), "{stdout}");
    assert!(stderr.contains("error[RALY4012]"), "{stderr}");
}
