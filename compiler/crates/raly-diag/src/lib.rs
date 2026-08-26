//! Spans, diagnostics and diagnostic rendering for the Raly compiler.
//!
//! This crate is the foundation everything else in the compiler is built on,
//! and it deliberately has no dependencies. Raly's pitch is catching mistakes
//! that other languages let through silently, which means the quality of what
//! a user reads when something is wrong *is* the product — not a presentation
//! layer bolted on at the end.
//!
//! Three ideas carry the design:
//!
//! 1. **Byte-offset spans.** [`Span`] is a `(FileId, start, end)` triple of
//!    byte offsets. Line and column are derived only at render time, by
//!    [`SourceMap`], so no phase has to carry or maintain them.
//! 2. **Stable codes.** Every diagnostic has a [`Code`] such as `RALY1002`
//!    whose meaning never changes. See [`code`] for the reserved ranges.
//! 3. **A separate advice channel.** [`Diagnostic::with_note`] states a fact
//!    ("this vector already holds 7 of 31 items"); [`Diagnostic::with_help`]
//!    states an action ("split the bundle, or widen the space to 63"). Keeping
//!    those apart is what stops error messages degenerating into paragraphs.
//!
//! ```
//! use raly_diag::{codes, Diagnostic, Renderer, SourceMap, Span};
//!
//! let mut sources = SourceMap::new();
//! let file = sources.add("greet.raly", "let s = \"hello\n");
//! let diag = Diagnostic::error(codes::UNTERMINATED_STRING, "unterminated string literal")
//!     .with_primary(Span::new(file, 8, 14), "this string is never closed")
//!     .with_help("add a closing quote before the end of the line");
//!
//! let text = Renderer::new(&sources).render(&diag);
//! assert!(text.starts_with("error[RALY1002]: unterminated string literal"));
//! ```

#![deny(missing_debug_implementations)]

pub mod code;
pub mod diagnostic;
pub mod render;
pub mod span;

/// The diagnostic code registry, re-exported under a friendlier name.
pub use crate::code as codes;

pub use crate::code::Code;
pub use crate::diagnostic::{Diagnostic, Diagnostics, Label, LabelStyle, Note, NoteKind, Severity};
pub use crate::render::{RenderConfig, Renderer};
pub use crate::span::{FileId, Location, SourceFile, SourceMap, Span};
