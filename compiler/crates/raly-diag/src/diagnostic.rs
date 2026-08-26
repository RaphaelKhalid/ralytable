//! The `Diagnostic` type and its builder.

use crate::code::Code;
use crate::span::Span;

/// How serious a diagnostic is. Only [`Severity::Error`] fails a compilation.
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Debug)]
pub enum Severity {
    /// Compilation cannot produce output. Sets a non-zero exit code.
    Error,
    /// Suspicious but compilable.
    Warning,
    /// Purely informational; used for "see also" style output.
    Advice,
}

impl Severity {
    pub fn as_str(&self) -> &'static str {
        match self {
            Severity::Error => "error",
            Severity::Warning => "warning",
            Severity::Advice => "advice",
        }
    }
}

/// Whether a label is the thing that went wrong, or supporting evidence.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum LabelStyle {
    /// The site of the problem. Rendered with `^`.
    Primary,
    /// Related context elsewhere in the source. Rendered with `-`.
    Secondary,
}

/// A span with a short message rendered underneath the source line.
#[derive(Clone, Debug)]
pub struct Label {
    pub style: LabelStyle,
    pub span: Span,
    /// May be empty, in which case only the underline is drawn.
    pub message: String,
}

impl Label {
    pub fn primary(span: Span, message: impl Into<String>) -> Self {
        Label {
            style: LabelStyle::Primary,
            span,
            message: message.into(),
        }
    }

    pub fn secondary(span: Span, message: impl Into<String>) -> Self {
        Label {
            style: LabelStyle::Secondary,
            span,
            message: message.into(),
        }
    }
}

/// The kind of trailing footnote attached to a diagnostic.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum NoteKind {
    /// Explains *why* the code is wrong, or states a fact the user may not know.
    ///
    /// This is the channel for quantitative context, e.g.
    /// `note: this vector already holds 7 of 31 items`.
    Note,
    /// Tells the user *what to do about it*. Should be actionable.
    Help,
}

impl NoteKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            NoteKind::Note => "note",
            NoteKind::Help => "help",
        }
    }
}

/// A footnote printed after the source snippet.
#[derive(Clone, Debug)]
pub struct Note {
    pub kind: NoteKind,
    pub message: String,
}

/// One complete problem report.
///
/// Build these with the fluent constructors rather than struct literals, so
/// that adding fields later stays a non-breaking change.
#[derive(Clone, Debug)]
pub struct Diagnostic {
    pub severity: Severity,
    pub code: Code,
    pub message: String,
    pub labels: Vec<Label>,
    pub notes: Vec<Note>,
}

impl Diagnostic {
    fn new(severity: Severity, code: Code, message: impl Into<String>) -> Self {
        Diagnostic {
            severity,
            code,
            message: message.into(),
            labels: Vec::new(),
            notes: Vec::new(),
        }
    }

    pub fn error(code: Code, message: impl Into<String>) -> Self {
        Diagnostic::new(Severity::Error, code, message)
    }

    pub fn warning(code: Code, message: impl Into<String>) -> Self {
        Diagnostic::new(Severity::Warning, code, message)
    }

    pub fn advice(code: Code, message: impl Into<String>) -> Self {
        Diagnostic::new(Severity::Advice, code, message)
    }

    pub fn with_label(mut self, label: Label) -> Self {
        self.labels.push(label);
        self
    }

    /// Shorthand for `.with_label(Label::primary(span, message))`.
    pub fn with_primary(self, span: Span, message: impl Into<String>) -> Self {
        self.with_label(Label::primary(span, message))
    }

    /// Shorthand for `.with_label(Label::secondary(span, message))`.
    pub fn with_secondary(self, span: Span, message: impl Into<String>) -> Self {
        self.with_label(Label::secondary(span, message))
    }

    /// Attach a `note:` footnote — a fact that explains the error.
    pub fn with_note(mut self, message: impl Into<String>) -> Self {
        self.notes.push(Note {
            kind: NoteKind::Note,
            message: message.into(),
        });
        self
    }

    /// Attach a `help:` footnote — an action the user can take.
    pub fn with_help(mut self, message: impl Into<String>) -> Self {
        self.notes.push(Note {
            kind: NoteKind::Help,
            message: message.into(),
        });
        self
    }

    /// The span the diagnostic should be sorted and jumped to by, if any:
    /// the first primary label, else the first label.
    pub fn focus(&self) -> Option<Span> {
        self.labels
            .iter()
            .find(|l| l.style == LabelStyle::Primary)
            .or(self.labels.first())
            .map(|l| l.span)
    }
}

/// A collection of diagnostics produced by one phase or one whole run.
///
/// Phases push into this and keep going wherever they can; the driver decides
/// when to stop. Nothing in the compiler should bail out on the first error if
/// recovery is possible, because the point of Raly is telling users everything
/// that is wrong in one pass.
#[derive(Default, Debug)]
pub struct Diagnostics {
    items: Vec<Diagnostic>,
}

impl Diagnostics {
    pub fn new() -> Self {
        Diagnostics::default()
    }

    pub fn push(&mut self, diagnostic: Diagnostic) {
        self.items.push(diagnostic);
    }

    pub fn extend(&mut self, others: impl IntoIterator<Item = Diagnostic>) {
        self.items.extend(others);
    }

    pub fn iter(&self) -> std::slice::Iter<'_, Diagnostic> {
        self.items.iter()
    }

    pub fn len(&self) -> usize {
        self.items.len()
    }

    pub fn is_empty(&self) -> bool {
        self.items.is_empty()
    }

    pub fn count(&self, severity: Severity) -> usize {
        self.items.iter().filter(|d| d.severity == severity).count()
    }

    pub fn has_errors(&self) -> bool {
        self.items.iter().any(|d| d.severity == Severity::Error)
    }

    /// Sort by source position so output order matches reading order.
    pub fn sort_by_position(&mut self) {
        self.items.sort_by_key(|d| {
            d.focus()
                .map(|s| (s.file.0, s.start, s.end))
                .unwrap_or((u32::MAX, u32::MAX, u32::MAX))
        });
    }

    pub fn into_vec(self) -> Vec<Diagnostic> {
        self.items
    }
}

impl<'a> IntoIterator for &'a Diagnostics {
    type Item = &'a Diagnostic;
    type IntoIter = std::slice::Iter<'a, Diagnostic>;
    fn into_iter(self) -> Self::IntoIter {
        self.items.iter()
    }
}

impl IntoIterator for Diagnostics {
    type Item = Diagnostic;
    type IntoIter = std::vec::IntoIter<Diagnostic>;
    fn into_iter(self) -> Self::IntoIter {
        self.items.into_iter()
    }
}

impl FromIterator<Diagnostic> for Diagnostics {
    fn from_iter<T: IntoIterator<Item = Diagnostic>>(iter: T) -> Self {
        Diagnostics {
            items: iter.into_iter().collect(),
        }
    }
}
