//! The `raly` compiler driver.
//!
//! Five subcommands exist today:
//!
//! * `raly lex <file>` — dump the spanned token stream.
//! * `raly parse <file>` — dump the syntax tree.
//! * `raly check <file>` — lex, parse, resolve, type-check, render every
//!   diagnostic, exit non-zero on error.
//! * `raly explain <file>` — say, in plain English, what the program
//!   represents, derived entirely from its types.
//! * `raly run <file>` — execute the small, pure constant subset through the
//!   typed ledger and emit deterministic receipts internally.
//!
//! Every phase recovers and every phase returns a value plus diagnostics
//! rather than a `Result`, so **one run reports everything that is wrong** —
//! lexical, syntactic, resolution and type problems together, sorted into
//! source order. A syntax error does not silence the type checker.
//!
//! Argument parsing is hand-rolled. The surface is four flags wide; a
//! dependency would cost more to review than it saves, and `clap` can be
//! dropped in unchanged the moment the CLI grows real subcommands.

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use raly_diag::{codes, Diagnostic, Diagnostics, RenderConfig, Renderer, SourceMap};
use raly_lexer::TokenKind;
use raly_parse::dump;

const USAGE: &str = "\
raly — the Raly compiler

USAGE:
    raly <COMMAND> [OPTIONS] <FILE>

COMMANDS:
    lex <file>      Tokenise a file and print each token with its span
    parse <file>    Parse a file and print the syntax tree
    check <file>    Lex and parse a file, and report any problems found
    explain <file>  Say what the program represents, in plain English
    run <file>      Execute pure top-level constants through the typed ledger

OPTIONS:
    --color         Force ANSI colour in diagnostics
    --no-color      Disable ANSI colour (the default)
    --explain       Print each diagnostic code's registry description
    --json          With `explain`, emit machine-readable JSON instead of prose
    -h, --help      Print this message
    -V, --version   Print the version

EXIT CODES:
    0   success
    1   the input contained errors
    2   the command line was wrong, or a file could not be read
";

fn main() -> ExitCode {
    match run() {
        Ok(code) => code,
        Err(message) => {
            eprintln!("error: {message}");
            eprintln!("\ntry `raly --help`");
            ExitCode::from(2)
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Command {
    Lex,
    Parse,
    Check,
    Explain,
    Run,
}

fn run() -> Result<ExitCode, String> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() {
        print!("{USAGE}");
        return Ok(ExitCode::from(2));
    }

    let mut command: Option<Command> = None;
    let mut path: Option<PathBuf> = None;
    let mut config = RenderConfig::plain();
    let mut json = false;

    for arg in &args {
        match arg.as_str() {
            "-h" | "--help" => {
                print!("{USAGE}");
                return Ok(ExitCode::SUCCESS);
            }
            "-V" | "--version" => {
                println!("raly {}", env!("CARGO_PKG_VERSION"));
                return Ok(ExitCode::SUCCESS);
            }
            "--color" => config.color = true,
            "--no-color" => config.color = false,
            "--explain" => config.explain_codes = true,
            "--json" => json = true,
            "lex" if command.is_none() => command = Some(Command::Lex),
            "parse" if command.is_none() => command = Some(Command::Parse),
            "check" if command.is_none() => command = Some(Command::Check),
            "explain" if command.is_none() => command = Some(Command::Explain),
            "run" if command.is_none() => command = Some(Command::Run),
            other if other.starts_with('-') => {
                return Err(format!("unknown option `{other}`"));
            }
            other if path.is_none() => path = Some(PathBuf::from(other)),
            other => return Err(format!("unexpected extra argument `{other}`")),
        }
    }

    let command =
        command.ok_or("no command given; expected `lex`, `parse`, `check`, `explain` or `run`")?;
    let path = path.ok_or("no input file given")?;

    let text = match std::fs::read_to_string(&path) {
        Ok(text) => text,
        Err(err) => {
            // A missing file is a user error, not a compiler error, so it goes
            // through the same diagnostic channel as everything else — just
            // without a span to point at.
            let diag = Diagnostic::error(
                codes::IO_ERROR,
                format!("could not read `{}`", path.display()),
            )
            .with_note(err.to_string());
            let empty = SourceMap::new();
            let renderer = Renderer::with_config(&empty, config);
            eprint!("{}", renderer.render(&diag));
            return Ok(ExitCode::from(2));
        }
    };

    // One pure call does every phase. The binary and the UI tests share it, so
    // a golden test asserts on exactly the bytes a user sees.
    let mut compiled = raly::compile(path.display().to_string(), text);
    let mut extension = Diagnostics::new();
    check_extension(&path, &mut extension);
    compiled.diagnostics.extend(extension);
    compiled.diagnostics.sort_by_position();

    let mut runtime_failed = false;
    match command {
        Command::Lex => print_tokens(&compiled.sources, &compiled.tokens),
        Command::Parse => print!("{}", dump::dump(&compiled.ast)),
        Command::Check => {}
        Command::Explain => {
            // Explaining is not checking: a file with errors still gets
            // described as far as its types are known, because "what is this
            // program?" is a question people ask precisely when it does not
            // work yet. The diagnostics still go to stderr below.
            let explanation = compiled.explain();
            if json {
                print!("{}", raly_explain::render::json(&explanation));
            } else {
                print!("{}", raly_explain::render::plain(&explanation));
            }
        }
        Command::Run if !compiled.has_errors() => match compiled.ledger() {
            Ok(ledger) => match ledger.execute_constants(&compiled.ast, &compiled.resolved) {
                Ok(execution) => {
                    for constant in execution.constants {
                        println!("{} = {}", constant.name, constant.value);
                    }
                }
                Err(error) => {
                    eprintln!("error: cannot execute this Raly subset: {error}");
                    runtime_failed = true;
                }
            },
            Err(error) => {
                eprintln!("error: could not build the execution ledger: {error}");
                runtime_failed = true;
            }
        },
        Command::Run => {}
    }

    eprint!("{}", compiled.render(config));

    if compiled.has_errors() || runtime_failed {
        Ok(ExitCode::from(1))
    } else {
        Ok(ExitCode::SUCCESS)
    }
}

/// A warning, not an error: the wrong extension never stops a compile, but it
/// is almost always a mistake worth surfacing.
fn check_extension(path: &Path, diagnostics: &mut Diagnostics) {
    let ext = path.extension().and_then(|e| e.to_str());
    if ext == Some("raly") {
        return;
    }
    let found = match ext {
        Some(ext) => format!("`.{ext}`"),
        None => "no extension".to_string(),
    };
    diagnostics.push(
        Diagnostic::warning(
            codes::BAD_EXTENSION,
            format!("`{}` does not look like a Raly source file", path.display()),
        )
        .with_note(format!("Raly sources use `.raly`; this file has {found}"))
        .with_help("rename the file, or pass the right one"),
    );
}

fn print_tokens(sources: &SourceMap, tokens: &[raly_lexer::Token]) {
    // Column widths chosen so the common cases line up without wrapping in an
    // 80-column terminal.
    println!("{:>6}  {:<18} {:<16} TEXT", "OFFSET", "KIND", "SPAN");
    for token in tokens {
        let span = token.span;
        let text = sources.snippet(span);
        let display = if token.kind == TokenKind::Eof {
            "<eof>".to_string()
        } else {
            escape_for_display(text)
        };
        let loc = sources.get(span.file).location(span.start);
        println!(
            "{:>6}  {:<18} {:<16} {}",
            format!("{}:{}", loc.line, loc.column),
            format!("{:?}", token.kind),
            format!("{}..{}", span.start, span.end),
            display
        );
    }
}

/// Make a token's text safe and single-line for tabular output.
fn escape_for_display(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for ch in text.chars() {
        match ch {
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c => out.push(c),
        }
    }
    out
}
