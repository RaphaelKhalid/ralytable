//! Node definitions.
//!
//! # ⚠ PROVISIONAL
//!
//! **Raly's grammar is being designed separately and has not landed yet.**
//! Everything in this module is scaffolding chosen to prove out the arena, the
//! spans and the visitor — not a claim about what Raly programs look like.
//! Nothing here encodes semantics: no precedence table, no evaluation order,
//! no type rules, no meaning for any keyword.
//!
//! When the real grammar arrives, expect to replace [`ExprKind`], [`ItemKind`]
//! and [`TypeExprKind`] wholesale. What should survive unchanged is the shape
//! around them: [`Ast`] owning arenas, every node carrying a [`Span`], names
//! interned to [`Symbol`], and the [`crate::visit`] traversal deriving itself
//! from whatever variants exist. Add variants there and the extension points
//! marked `EXTENSION POINT` below are the only places that need edits.

use raly_diag::Span;

use crate::arena::{Arena, Id, Interner, Symbol};

pub type ExprId = Id<Expr>;
pub type ItemId = Id<Item>;
pub type TypeExprId = Id<TypeExpr>;

/// One parsed source file.
#[derive(Debug)]
pub struct Ast {
    pub exprs: Arena<Expr>,
    pub items: Arena<Item>,
    pub types: Arena<TypeExpr>,
    pub names: Interner,
    /// Top-level items, in source order.
    pub root: Vec<ItemId>,
}

impl Default for Ast {
    fn default() -> Self {
        Ast::new()
    }
}

impl Ast {
    pub fn new() -> Self {
        Ast {
            exprs: Arena::new(),
            items: Arena::new(),
            types: Arena::new(),
            names: Interner::new(),
            root: Vec::new(),
        }
    }

    pub fn expr(&mut self, kind: ExprKind, span: Span) -> ExprId {
        self.exprs.alloc(Expr { kind, span })
    }

    pub fn item(&mut self, kind: ItemKind, span: Span) -> ItemId {
        self.items.alloc(Item { kind, span })
    }

    pub fn type_expr(&mut self, kind: TypeExprKind, span: Span) -> TypeExprId {
        self.types.alloc(TypeExpr { kind, span })
    }

    /// Intern an identifier's text and pair it with its span.
    pub fn ident(&mut self, text: &str, span: Span) -> Ident {
        Ident {
            symbol: self.names.intern(text),
            span,
        }
    }

    pub fn text(&self, ident: Ident) -> &str {
        self.names.resolve(ident.symbol)
    }
}

/// A name plus where it was written.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Ident {
    pub symbol: Symbol,
    pub span: Span,
}

// -- items -------------------------------------------------------------------

#[derive(Debug)]
pub struct Item {
    pub kind: ItemKind,
    pub span: Span,
}

/// EXTENSION POINT: top-level declarations. Two placeholders only.
#[derive(Debug)]
pub enum ItemKind {
    Fn(FnDef),
    Let(LetBinding),
    /// Emitted by recovery when an item could not be parsed at all. Carries no
    /// payload on purpose: the diagnostic explaining it has already been
    /// issued, and later phases should skip this subtree silently.
    Error,
}

/// A function definition. PROVISIONAL: no generics, no effects, no `where`
/// clause, no attributes — all of which the real grammar may well want.
#[derive(Debug)]
pub struct FnDef {
    pub name: Ident,
    pub params: Vec<Param>,
    /// `None` when the source wrote no `-> T`.
    pub return_type: Option<TypeExprId>,
    /// `None` for a declaration with no body, or after error recovery.
    pub body: Option<ExprId>,
}

#[derive(Debug)]
pub struct Param {
    pub name: Ident,
    pub ty: Option<TypeExprId>,
    pub span: Span,
}

/// A `let` binding. PROVISIONAL: the name is a plain identifier because
/// pattern syntax has not been designed.
#[derive(Debug)]
pub struct LetBinding {
    pub mutable: bool,
    pub name: Ident,
    pub ty: Option<TypeExprId>,
    pub init: Option<ExprId>,
}

// -- expressions -------------------------------------------------------------

#[derive(Debug)]
pub struct Expr {
    pub kind: ExprKind,
    pub span: Span,
}

/// EXTENSION POINT: the expression grammar.
///
/// Deliberately tiny. There is no `Binary`, `If`, `Match` or `Bundle` variant
/// because adding one would mean choosing precedence and meaning, which is not
/// this crate's job. [`ExprKind::Op`] exists instead: it records the operator
/// token verbatim with a flat operand list, so a front end can be exercised
/// end to end before the grammar exists, and so it is obvious at review time
/// that no precedence decision has been smuggled in.
#[derive(Debug)]
pub enum ExprKind {
    Literal(Literal),
    /// A `::`-separated name. A single segment is the common case.
    Path(Vec<Ident>),
    /// A parenthesised expression, kept in the tree so that formatting and
    /// span reporting can tell `(a)` from `a`.
    Group(ExprId),
    /// PROVISIONAL. An operator token applied to operands, with no claim about
    /// arity, associativity, precedence or meaning.
    Op {
        /// Span of the operator token itself, for diagnostics.
        op: Span,
        operands: Vec<ExprId>,
    },
    Call {
        callee: ExprId,
        args: Vec<ExprId>,
    },
    /// A block. Statement syntax is undesigned, so a block is just items
    /// followed by an optional trailing expression.
    Block {
        items: Vec<ItemId>,
        tail: Option<ExprId>,
    },
    /// Recovery placeholder; see [`ItemKind::Error`].
    Error,
}

/// EXTENSION POINT: literal forms.
///
/// Values are kept as the *source text* rather than parsed numbers. Deciding
/// that `1e400` saturates, wraps, or is an error is a semantic choice, and it
/// is not being made here.
#[derive(Debug)]
pub enum Literal {
    Int(Symbol),
    Float(Symbol),
    /// The literal's text with the surrounding quotes removed and escapes
    /// *not* yet expanded.
    Str(Symbol),
    Bool(bool),
}

// -- types -------------------------------------------------------------------

#[derive(Debug)]
pub struct TypeExpr {
    pub kind: TypeExprKind,
    pub span: Span,
}

/// EXTENSION POINT: type syntax.
///
/// Raly's type system is where the interesting design work is happening, and
/// none of it is settled. Until it is, an annotation is stored opaquely: the
/// span it occupied, and the interned source text. That is enough to echo an
/// annotation back in a diagnostic and enough to round-trip a source file,
/// while committing to nothing.
#[derive(Debug)]
pub enum TypeExprKind {
    /// Unparsed annotation text, verbatim.
    Opaque(Symbol),
    Error,
}
