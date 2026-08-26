//! Definitions, definition ids, and the builtin tables names resolve against.

use raly_ast::ItemId;
use raly_diag::Span;

/// A handle to a [`Def`] in [`crate::Resolved::defs`].
///
/// Every resolvable reference in a program gets one of these, including
/// references the resolver could not resolve — those get [`DefId::ERROR`], so
/// the checker always has *something* to look at and never has to branch on
/// "was this resolved?".
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Debug)]
pub struct DefId(pub u32);

impl DefId {
    /// The error binding. Always index 0 of `Resolved::defs`.
    pub const ERROR: DefId = DefId(0);

    pub fn index(self) -> usize {
        self.0 as usize
    }
}

/// One thing a name can refer to.
#[derive(Clone, Debug)]
pub struct Def {
    /// The spelling, kept as text so diagnostics do not need the interner.
    pub name: String,
    /// Where it was declared. `None` for builtins, which are declared nowhere.
    pub span: Option<Span>,
    pub kind: DefKind,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum DefKind {
    /// The error binding: resolves against everything, reports nothing.
    Error,
    /// A builtin type constructor or scalar type.
    Builtin(Builtin),
    /// `space Concepts = MAP[8192]`
    Space(ItemId),
    /// `role Subject in Concepts`. `space` is the space it was declared in.
    Role { item: ItemId, space: Option<DefId> },
    /// `type Scene = ...`
    TypeAlias(ItemId),
    /// `fn encode(..) -> ..`
    Fn(ItemId),
    /// The `index`th parameter of the function declared by `item`.
    Param { item: ItemId, index: usize },
    /// A `let`, either a module constant or a local.
    Let { local: bool },
}

impl DefKind {
    /// A noun phrase for diagnostics: "a role", "a space", ...
    pub fn describe(&self) -> &'static str {
        match self {
            DefKind::Error => "an unresolved name",
            DefKind::Builtin(_) => "a builtin type",
            DefKind::Space(_) => "a space",
            DefKind::Role { .. } => "a role",
            DefKind::TypeAlias(_) => "a type alias",
            DefKind::Fn(_) => "a function",
            DefKind::Param { .. } => "a parameter",
            DefKind::Let { local: true } => "a local binding",
            DefKind::Let { local: false } => "a module constant",
        }
    }
}

/// The builtin type names. There are no builtin *values*: `true` and `false`
/// are literals, and the five VSA operations are keywords.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Builtin {
    /// `Vec[S]` — a vector in a space, possibly a superposition.
    Vec,
    /// `Sym[S]` — a single codebook atom of a space.
    Sym,
    Int,
    Float,
    Bool,
    Str,
}

impl Builtin {
    pub fn name(&self) -> &'static str {
        match self {
            Builtin::Vec => "Vec",
            Builtin::Sym => "Sym",
            Builtin::Int => "Int",
            Builtin::Float => "Float",
            Builtin::Bool => "Bool",
            Builtin::Str => "Str",
        }
    }

    pub fn from_name(name: &str) -> Option<Builtin> {
        Builtin::ALL.iter().copied().find(|b| b.name() == name)
    }

    pub const ALL: &'static [Builtin] = &[
        Builtin::Vec,
        Builtin::Sym,
        Builtin::Int,
        Builtin::Float,
        Builtin::Bool,
        Builtin::Str,
    ];
}

/// The VSA families a `space` may name.
///
/// GRAMMAR.md §3 keeps this a bare identifier rather than a keyword precisely
/// so that the table can grow — matrix binding, VDTB — without a lexer change.
/// Resolving the identifier against this table is therefore a name-resolution
/// question, and lives here.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Family {
    /// Multiply-Add-Permute: bipolar, Hadamard binding.
    Map,
    /// Binary Spatter Codes: binary, XOR binding, majority bundling.
    Bsc,
    /// Holographic Reduced Representations: real, circular convolution.
    Hrr,
    /// Fourier HRR: unit-modulus complex, phase addition.
    Fhrr,
}

impl Family {
    pub fn name(&self) -> &'static str {
        match self {
            Family::Map => "MAP",
            Family::Bsc => "BSC",
            Family::Hrr => "HRR",
            Family::Fhrr => "FHRR",
        }
    }

    /// A one-clause description, used in the family-mismatch note.
    pub fn describe(&self) -> &'static str {
        match self {
            Family::Map => "bipolar vectors bound by elementwise product",
            Family::Bsc => "binary vectors bound by XOR and bundled by majority",
            Family::Hrr => "real vectors bound by circular convolution",
            Family::Fhrr => "unit-modulus complex vectors bound by phase addition",
        }
    }

    pub fn from_name(name: &str) -> Option<Family> {
        Family::ALL.iter().copied().find(|f| f.name() == name)
    }

    pub const ALL: &'static [Family] = &[Family::Map, Family::Bsc, Family::Hrr, Family::Fhrr];
}
