//! The shape of an explanation.
//!
//! Two renderings hang off this: plain English for a reader, and JSON for a
//! tool. Keeping the model separate from both is what stops the JSON from
//! being "the prose, in quotes" — a machine wants the *numbers* the prose was
//! derived from, and a reader wants none of them naked.

/// One file, explained.
#[derive(Clone, Debug)]
pub struct Explanation {
    pub file: String,
    /// A one-line census: what kinds of thing this file declares.
    pub headline: String,
    pub items: Vec<Described>,
}

/// One declaration, explained.
#[derive(Clone, Debug)]
pub struct Described {
    /// `space`, `role`, `type` or `fn`.
    pub kind: &'static str,
    pub name: String,
    /// The declaration written back out, as close to source as the tree allows.
    pub signature: String,
    /// What it is and what it does, in ordinary words. One entry per sentence
    /// group, so a renderer can decide how to break lines.
    pub summary: Vec<String>,
    /// Things that follow from the types without being written down.
    pub notable: Vec<String>,
    /// The same content a machine would want, without the prose.
    pub facts: Vec<(&'static str, Fact)>,
}

impl Described {
    pub(crate) fn new(kind: &'static str, name: impl Into<String>) -> Described {
        Described {
            kind,
            name: name.into(),
            signature: String::new(),
            summary: Vec::new(),
            notable: Vec::new(),
            facts: Vec::new(),
        }
    }

    pub(crate) fn say(&mut self, sentence: impl Into<String>) {
        self.summary.push(sentence.into());
    }

    pub(crate) fn flag(&mut self, sentence: impl Into<String>) {
        self.notable.push(sentence.into());
    }

    pub(crate) fn fact(&mut self, key: &'static str, value: Fact) {
        self.facts.push((key, value));
    }
}

/// A machine-readable value.
///
/// [`Fact::Unknown`] exists on purpose and renders as JSON `null`: the whole
/// discipline of this feature is to say only what the types prove, so "the
/// compiler could not tell" has to be representable rather than omitted.
#[derive(Clone, PartialEq, Debug)]
pub enum Fact {
    Text(String),
    Number(u64),
    Bool(bool),
    List(Vec<String>),
    Unknown,
}

impl Fact {
    pub(crate) fn text(value: impl Into<String>) -> Fact {
        Fact::Text(value.into())
    }

    /// `Some(n)` becomes a number and `None` becomes [`Fact::Unknown`].
    pub(crate) fn maybe_number(value: Option<u64>) -> Fact {
        match value {
            Some(n) => Fact::Number(n),
            None => Fact::Unknown,
        }
    }
}
