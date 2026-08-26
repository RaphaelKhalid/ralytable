//! Byte-offset spans and the source map they point into.

use std::fmt;
use std::ops::Range;

/// Identifies one source file inside a [`SourceMap`].
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Debug)]
pub struct FileId(pub u32);

/// A half-open byte range `[start, end)` within a single file.
///
/// Byte offsets (not char offsets) are the canonical currency of the whole
/// compiler: the lexer emits them, later phases copy them around, and
/// rendering is the only place that ever converts them to line/column.
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub struct Span {
    pub file: FileId,
    pub start: u32,
    pub end: u32,
}

impl Span {
    pub fn new(file: FileId, start: u32, end: u32) -> Self {
        debug_assert!(start <= end, "span start must not exceed end");
        Span { file, start, end }
    }

    /// Build a span from a `Range<usize>`, as produced by most lexers.
    pub fn from_range(file: FileId, range: Range<usize>) -> Self {
        Span::new(file, range.start as u32, range.end as u32)
    }

    /// A zero-width span, used for "the compiler expected something here".
    pub fn point(file: FileId, at: u32) -> Self {
        Span::new(file, at, at)
    }

    pub fn range(&self) -> Range<usize> {
        self.start as usize..self.end as usize
    }

    pub fn len(&self) -> u32 {
        self.end - self.start
    }

    pub fn is_empty(&self) -> bool {
        self.start == self.end
    }

    /// The smallest span covering both inputs.
    pub fn merge(self, other: Span) -> Span {
        debug_assert_eq!(self.file, other.file, "cannot merge spans across files");
        Span::new(
            self.file,
            self.start.min(other.start),
            self.end.max(other.end),
        )
    }
}

impl fmt::Debug for Span {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}:{}..{}", self.file.0, self.start, self.end)
    }
}

/// A 1-based line/column pair, for display only.
///
/// `column` counts Unicode scalar values, not bytes, so a caret drawn under an
/// identifier containing non-ASCII text lines up in a terminal.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Location {
    pub line: u32,
    pub column: u32,
}

/// One file's text plus a precomputed line index.
pub struct SourceFile {
    name: String,
    text: String,
    /// Byte offset of the start of each line. Always begins with 0.
    line_starts: Vec<u32>,
}

impl SourceFile {
    fn new(name: String, text: String) -> Self {
        let mut line_starts = vec![0u32];
        for (i, b) in text.bytes().enumerate() {
            if b == b'\n' {
                line_starts.push(i as u32 + 1);
            }
        }
        SourceFile {
            name,
            text,
            line_starts,
        }
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn text(&self) -> &str {
        &self.text
    }

    pub fn line_count(&self) -> u32 {
        self.line_starts.len() as u32
    }

    /// 0-based index of the line containing `offset`. Offsets past the end of
    /// the file clamp to the last line, so EOF diagnostics always render.
    pub fn line_index(&self, offset: u32) -> u32 {
        let offset = offset.min(self.text.len() as u32);
        match self.line_starts.binary_search(&offset) {
            Ok(i) => i as u32,
            Err(i) => i as u32 - 1,
        }
    }

    /// Byte range of a 0-based line, excluding its line terminator.
    pub fn line_range(&self, line: u32) -> Range<usize> {
        let start = self.line_starts[line as usize] as usize;
        let mut end = self
            .line_starts
            .get(line as usize + 1)
            .map(|&n| n as usize)
            .unwrap_or(self.text.len());
        let bytes = self.text.as_bytes();
        if end > start && bytes[end - 1] == b'\n' {
            end -= 1;
        }
        if end > start && bytes[end - 1] == b'\r' {
            end -= 1;
        }
        start..end
    }

    pub fn line_text(&self, line: u32) -> &str {
        &self.text[self.line_range(line)]
    }

    pub fn location(&self, offset: u32) -> Location {
        let line = self.line_index(offset);
        let line_start = self.line_starts[line as usize] as usize;
        let offset = (offset as usize).min(self.text.len());
        let column = self.text[line_start..offset].chars().count() as u32 + 1;
        Location {
            line: line + 1,
            column,
        }
    }
}

/// Owns every file the compiler has read. Spans are meaningless without it.
#[derive(Default)]
pub struct SourceMap {
    files: Vec<SourceFile>,
}

impl SourceMap {
    pub fn new() -> Self {
        SourceMap::default()
    }

    pub fn add(&mut self, name: impl Into<String>, text: impl Into<String>) -> FileId {
        let id = FileId(self.files.len() as u32);
        self.files.push(SourceFile::new(name.into(), text.into()));
        id
    }

    pub fn get(&self, id: FileId) -> &SourceFile {
        &self.files[id.0 as usize]
    }

    /// The text a span covers. Returns `""` for out-of-range spans rather than
    /// panicking: diagnostics must never crash the compiler.
    pub fn snippet(&self, span: Span) -> &str {
        self.get(span.file).text.get(span.range()).unwrap_or("")
    }
}

// Hand-written so that debugging the compiler never dumps whole source files
// into a log.
impl fmt::Debug for SourceFile {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("SourceFile")
            .field("name", &self.name)
            .field("bytes", &self.text.len())
            .field("lines", &self.line_starts.len())
            .finish()
    }
}

impl fmt::Debug for SourceMap {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_list().entries(self.files.iter()).finish()
    }
}
