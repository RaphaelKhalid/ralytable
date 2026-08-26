//! Rendering diagnostics to text, with source context and carets.
//!
//! Output is deliberately plain ASCII and deterministic so it can be asserted
//! on in tests and diffed in CI. Colour is opt-in and is the only thing that
//! varies with the terminal.
//!
//! The shape is the familiar rustc one:
//!
//! ```text
//! error[RALY1002]: unterminated string literal
//!   --> greet.raly:2:13
//!    |
//!  2 |     let s = "hello
//!    |             ^^^^^^ this string is never closed
//!    |
//!    = help: add a closing quote before the end of the line
//! ```

use std::fmt::Write as _;

use crate::diagnostic::{Diagnostic, LabelStyle, Severity};
use crate::span::{SourceMap, Span};

/// Presentation options for [`Renderer`].
#[derive(Clone, Copy, Debug)]
pub struct RenderConfig {
    /// Emit ANSI colour escapes.
    pub color: bool,
    /// Columns a tab expands to when printing source lines.
    pub tab_width: usize,
    /// Print the code's registry description under the message.
    pub explain_codes: bool,
}

impl Default for RenderConfig {
    fn default() -> Self {
        RenderConfig {
            color: false,
            tab_width: 4,
            explain_codes: false,
        }
    }
}

impl RenderConfig {
    /// Deterministic, colour-free output. The default, and what tests use.
    pub fn plain() -> Self {
        RenderConfig::default()
    }

    pub fn with_color(mut self, color: bool) -> Self {
        self.color = color;
        self
    }

    pub fn with_explain_codes(mut self, explain: bool) -> Self {
        self.explain_codes = explain;
        self
    }
}

const RESET: &str = "\x1b[0m";
const BOLD: &str = "\x1b[1m";
const RED: &str = "\x1b[31m";
const YELLOW: &str = "\x1b[33m";
const BLUE: &str = "\x1b[34m";
const CYAN: &str = "\x1b[36m";
const GREEN: &str = "\x1b[32m";

/// Turns [`Diagnostic`]s into printable text against a [`SourceMap`].
#[derive(Debug)]
pub struct Renderer<'a> {
    sources: &'a SourceMap,
    config: RenderConfig,
}

impl<'a> Renderer<'a> {
    pub fn new(sources: &'a SourceMap) -> Self {
        Renderer {
            sources,
            config: RenderConfig::plain(),
        }
    }

    pub fn with_config(sources: &'a SourceMap, config: RenderConfig) -> Self {
        Renderer { sources, config }
    }

    /// Render one diagnostic. The result always ends with a newline.
    pub fn render(&self, diag: &Diagnostic) -> String {
        let mut out = String::new();
        self.write(&mut out, diag);
        out
    }

    /// Render several diagnostics, separated by a blank line.
    pub fn render_all<'d>(&self, diags: impl IntoIterator<Item = &'d Diagnostic>) -> String {
        let mut out = String::new();
        for (i, d) in diags.into_iter().enumerate() {
            if i > 0 {
                out.push('\n');
            }
            self.write(&mut out, d);
        }
        out
    }

    /// A one-line tally such as `error: 2 errors, 1 warning`.
    pub fn summary(&self, errors: usize, warnings: usize) -> String {
        let mut parts = Vec::new();
        if errors > 0 {
            parts.push(format!(
                "{errors} error{}",
                if errors == 1 { "" } else { "s" }
            ));
        }
        if warnings > 0 {
            parts.push(format!(
                "{warnings} warning{}",
                if warnings == 1 { "" } else { "s" }
            ));
        }
        if parts.is_empty() {
            return String::new();
        }
        let level = if errors > 0 {
            Severity::Error
        } else {
            Severity::Warning
        };
        format!(
            "{}: {}\n",
            self.paint(level.as_str(), self.severity_color(level), true),
            parts.join(", ")
        )
    }

    // -- internals ---------------------------------------------------------

    fn severity_color(&self, s: Severity) -> &'static str {
        match s {
            Severity::Error => RED,
            Severity::Warning => YELLOW,
            Severity::Advice => GREEN,
        }
    }

    fn paint(&self, text: &str, color: &str, bold: bool) -> String {
        if !self.config.color {
            return text.to_string();
        }
        let b = if bold { BOLD } else { "" };
        format!("{b}{color}{text}{RESET}")
    }

    fn write(&self, out: &mut String, diag: &Diagnostic) {
        let color = self.severity_color(diag.severity);
        let header = format!("{}[{}]", diag.severity.as_str(), diag.code);
        let _ = writeln!(
            out,
            "{}: {}",
            self.paint(&header, color, true),
            self.paint(&diag.message, "", true)
        );

        // Gutter is sized to the widest line number we are about to print.
        let width = diag
            .labels
            .iter()
            .map(|l| {
                let file = self.sources.get(l.span.file);
                digits(file.location(l.span.start).line)
            })
            .max()
            .unwrap_or(1);
        let bar = self.paint("|", BLUE, true);
        let pad = " ".repeat(width);

        for (i, label) in diag.labels.iter().enumerate() {
            let file = self.sources.get(label.span.file);
            let loc = file.location(label.span.start);
            let arrow = if i == 0 { "-->" } else { ":::" };
            let _ = writeln!(
                out,
                "{pad}{} {}:{}:{}",
                self.paint(arrow, BLUE, true),
                file.name(),
                loc.line,
                loc.column
            );
            let _ = writeln!(out, "{pad} {bar}");

            let line_idx = loc.line - 1;
            let line_range = file.line_range(line_idx);
            let line_text = file.line_text(line_idx);
            let (rendered, start_col, span_cols) = self.layout(
                line_text,
                line_range.start as u32,
                label.span,
                line_range.end,
            );

            let number = self.paint(&format!("{:>width$}", loc.line, width = width), BLUE, true);
            let _ = writeln!(out, "{number} {bar} {rendered}");

            let (marker, marker_color) = match label.style {
                LabelStyle::Primary => ('^', color),
                LabelStyle::Secondary => ('-', CYAN),
            };
            let underline: String = std::iter::repeat_n(marker, span_cols).collect();
            let tail = if label.message.is_empty() {
                String::new()
            } else {
                format!(" {}", label.message)
            };
            let _ = writeln!(
                out,
                "{pad} {bar} {}{}",
                " ".repeat(start_col),
                self.paint(&format!("{underline}{tail}"), marker_color, true)
            );

            // A span that runs past this line: say so rather than silently
            // pretending it ended at the line break.
            if file.line_index(label.span.end) > line_idx {
                let end_line = file.location(label.span.end).line;
                let _ = writeln!(
                    out,
                    "{pad} {bar} {}",
                    self.paint(
                        &format!("...continues to line {end_line}"),
                        marker_color,
                        false
                    )
                );
            }
        }

        let has_extra = self.config.explain_codes || !diag.notes.is_empty();
        if !diag.labels.is_empty() && has_extra {
            let _ = writeln!(out, "{pad} {bar}");
        }
        for note in &diag.notes {
            let _ = writeln!(
                out,
                "{pad} {} {}: {}",
                self.paint("=", BLUE, true),
                self.paint(note.kind.as_str(), "", true),
                note.message
            );
        }
        if self.config.explain_codes {
            let _ = writeln!(
                out,
                "{pad} {} {}: {} is {}",
                self.paint("=", BLUE, true),
                self.paint("code", "", true),
                diag.code,
                diag.code.description()
            );
        }
    }

    /// Expand tabs in a source line and work out where the underline goes, in
    /// *display* columns. Returns `(rendered_line, start_col, width)`.
    fn layout(
        &self,
        line_text: &str,
        line_start: u32,
        span: Span,
        line_end: usize,
    ) -> (String, usize, usize) {
        let tw = self.config.tab_width;
        let rel_start = (span.start.saturating_sub(line_start) as usize).min(line_text.len());
        let rel_end = ((span.end as usize).min(line_end))
            .saturating_sub(line_start as usize)
            .clamp(rel_start, line_text.len());

        let start_col = display_width(&line_text[..rel_start], tw, 0);
        let end_col = display_width(&line_text[rel_start..rel_end], tw, start_col);
        let width = (end_col - start_col).max(1);

        let mut rendered = String::with_capacity(line_text.len());
        let mut col = 0usize;
        for ch in line_text.chars() {
            if ch == '\t' {
                let next = (col / tw + 1) * tw;
                rendered.extend(std::iter::repeat_n(' ', next - col));
                col = next;
            } else {
                rendered.push(ch);
                col += 1;
            }
        }
        (rendered, start_col, width)
    }
}

/// Display width of `s` when printing begins at column `from`.
fn display_width(s: &str, tab_width: usize, from: usize) -> usize {
    let mut col = from;
    for ch in s.chars() {
        if ch == '\t' {
            col = (col / tab_width + 1) * tab_width;
        } else {
            col += 1;
        }
    }
    col
}

fn digits(mut n: u32) -> usize {
    let mut d = 1;
    while n >= 10 {
        n /= 10;
        d += 1;
    }
    d
}
