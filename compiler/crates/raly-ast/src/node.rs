//! Node definitions for Raly's syntax tree.
//!
//! These implement the grammar in `compiler/GRAMMAR.md`. Three properties are
//! load-bearing and should survive every later change:
//!
//! 1. **Arenas and ids.** Nodes live in flat `Vec`s and reference each other
//!    by 32-bit [`Id`]. Side tables (types, resolutions) hang off the same
//!    indices.
//! 2. **Totality.** A tree is always produced, even for input that does not
//!    parse. Every significant token in the source lies inside some node's
//!    span; regions the parser could not understand become explicit `Error`
//!    nodes rather than gaps.
//! 3. **Provenance.** Every node carries an [`Origin`]. A node that exists
//!    because of a recovery decision records *which* decision, so a later
//!    phase can decline to blame an expression the user never wrote.

use raly_diag::Span;

use crate::arena::{Arena, Id, Interner, Symbol};

pub type ExprId = Id<Expr>;
pub type ItemId = Id<Item>;
pub type StmtId = Id<Stmt>;
pub type TypeExprId = Id<TypeExpr>;

// -- provenance --------------------------------------------------------------

/// Why a node is in the tree.
///
/// The distinction is cheap to carry and expensive to retrofit: without it, a
/// type error inside a recovered subtree gets reported against source the user
/// never wrote.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Origin {
    /// The node corresponds to text the user actually wrote.
    Source,
    /// The node was synthesised during error recovery, for this reason.
    Recovered(Reason),
}

impl Origin {
    pub fn is_recovered(&self) -> bool {
        matches!(self, Origin::Recovered(_))
    }

    pub fn reason(&self) -> Option<Reason> {
        match self {
            Origin::Recovered(r) => Some(*r),
            Origin::Source => None,
        }
    }
}

/// The specific recovery decision that produced a node.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Reason {
    /// A token appeared where the grammar admits nothing like it.
    UnexpectedToken,
    /// An expression was required and none was there.
    MissingExpr,
    /// A type annotation was required and none was there.
    MissingType,
    /// A name was required and none was there.
    MissingName,
    /// A block or body was required and none was there.
    MissingBody,
    /// An opening bracket was never closed.
    UnclosedDelimiter,
    /// A run of tokens was skipped to resynchronise.
    SkippedTokens,
    /// A reserved keyword whose construct is not implemented yet.
    Unimplemented,
    /// An operation was written with an operand count it does not accept.
    BadArity,
}

impl Reason {
    /// A short phrase, suitable for `note: this node came from ...`.
    pub fn describe(&self) -> &'static str {
        match self {
            Reason::UnexpectedToken => "an unexpected token",
            Reason::MissingExpr => "a missing expression",
            Reason::MissingType => "a missing type annotation",
            Reason::MissingName => "a missing name",
            Reason::MissingBody => "a missing body",
            Reason::UnclosedDelimiter => "an unclosed delimiter",
            Reason::SkippedTokens => "tokens skipped during recovery",
            Reason::Unimplemented => "a construct that is reserved but unimplemented",
            Reason::BadArity => "an operation with the wrong number of operands",
        }
    }
}

// -- the tree ----------------------------------------------------------------

/// One parsed source file.
#[derive(Debug)]
pub struct Ast {
    pub exprs: Arena<Expr>,
    pub items: Arena<Item>,
    pub stmts: Arena<Stmt>,
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
            stmts: Arena::new(),
            types: Arena::new(),
            names: Interner::new(),
            root: Vec::new(),
        }
    }

    pub fn expr(&mut self, kind: ExprKind, span: Span) -> ExprId {
        self.expr_from(kind, span, Origin::Source)
    }

    pub fn expr_from(&mut self, kind: ExprKind, span: Span, origin: Origin) -> ExprId {
        self.exprs.alloc(Expr { kind, span, origin })
    }

    pub fn item(&mut self, kind: ItemKind, span: Span) -> ItemId {
        self.item_from(kind, span, Origin::Source)
    }

    pub fn item_from(&mut self, kind: ItemKind, span: Span, origin: Origin) -> ItemId {
        self.items.alloc(Item { kind, span, origin })
    }

    pub fn stmt(&mut self, kind: StmtKind, span: Span) -> StmtId {
        self.stmt_from(kind, span, Origin::Source)
    }

    pub fn stmt_from(&mut self, kind: StmtKind, span: Span, origin: Origin) -> StmtId {
        self.stmts.alloc(Stmt { kind, span, origin })
    }

    pub fn type_expr(&mut self, kind: TypeExprKind, span: Span) -> TypeExprId {
        self.type_expr_from(kind, span, Origin::Source)
    }

    pub fn type_expr_from(&mut self, kind: TypeExprKind, span: Span, origin: Origin) -> TypeExprId {
        self.types.alloc(TypeExpr { kind, span, origin })
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

    /// A hash of an expression's *shape*, ignoring spans and ignoring the
    /// source order of commutative operands.
    ///
    /// Two expressions with the same structural key denote the same value
    /// modulo the commutativity of [`VsaOp::Bind`] and [`VsaOp::Bundle`]. This
    /// is what makes [`Ast::canonical_order`] a canonical form rather than an
    /// arbitrary one.
    pub fn structural_key(&self, id: ExprId) -> u64 {
        let expr = &self.exprs[id];
        let mut key = mix(SEED, expr.kind.discriminant());
        match &expr.kind {
            ExprKind::Literal(lit) => mix(key, lit.key()),
            ExprKind::Path(segments) => {
                for segment in segments {
                    key = mix(key, segment.symbol.as_u32() as u64);
                }
                key
            }
            ExprKind::Group(inner) => mix(key, self.structural_key(*inner)),
            ExprKind::Unary { op, operand, .. } => {
                mix(mix(key, *op as u64), self.structural_key(*operand))
            }
            ExprKind::Binary { op, lhs, rhs, .. } => {
                key = mix(key, *op as u64);
                key = mix(key, self.structural_key(*lhs));
                mix(key, self.structural_key(*rhs))
            }
            ExprKind::Pipeline { value, stage, .. } => {
                key = mix(key, self.structural_key(*value));
                mix(key, self.structural_key(*stage))
            }
            ExprKind::Call { callee, args } => {
                key = mix(key, self.structural_key(*callee));
                for &arg in args {
                    key = mix(key, self.structural_key(arg));
                }
                key
            }
            ExprKind::Field { base, name } => {
                key = mix(key, self.structural_key(*base));
                mix(key, name.symbol.as_u32() as u64)
            }
            ExprKind::Vsa(call) => {
                key = mix(key, call.op as u64);
                key = mix(key, call.variant_kind.map(|v| v as u64 + 1).unwrap_or(0));
                if call.is_order_insensitive() {
                    // Order-insensitive combination, so that `bundle(a, b)`
                    // and `bundle(b, a)` are indistinguishable by shape.
                    let mut acc = 0u64;
                    for &arg in &call.args {
                        acc = acc.wrapping_add(self.structural_key(arg));
                    }
                    mix(key, acc)
                } else {
                    for &arg in &call.args {
                        key = mix(key, self.structural_key(arg));
                    }
                    key
                }
            }
            ExprKind::List(items) | ExprKind::Tuple(items) => {
                for &item in items {
                    key = mix(key, self.structural_key(item));
                }
                key
            }
            ExprKind::Block { stmts, tail } => {
                key = mix(key, stmts.len() as u64);
                if let Some(tail) = tail {
                    key = mix(key, self.structural_key(*tail));
                }
                key
            }
            ExprKind::If {
                cond,
                then_block,
                else_branch,
            } => {
                key = mix(key, self.structural_key(*cond));
                key = mix(key, self.structural_key(*then_block));
                if let Some(e) = else_branch {
                    key = mix(key, self.structural_key(*e));
                }
                key
            }
            ExprKind::Error => key,
        }
    }

    /// The operands of a commutative operation, in canonical order.
    ///
    /// Sorting by structural key makes commutativity structurally true: two
    /// bundles of the same operands produce the same canonical sequence
    /// regardless of how they were written, so no later pass has to remember
    /// to apply the law. Ties break on allocation order, which is source
    /// order, so the result is deterministic.
    pub fn canonical_order(&self, args: &[ExprId]) -> Vec<ExprId> {
        let mut out = args.to_vec();
        out.sort_by_key(|&id| (self.structural_key(id), id.raw()));
        out
    }
}

const SEED: u64 = 0xcbf2_9ce4_8422_2325;
const PRIME: u64 = 0x0000_0100_0000_01b3;

/// One FNV-1a round.
fn mix(acc: u64, value: u64) -> u64 {
    (acc ^ value).wrapping_mul(PRIME)
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
    pub origin: Origin,
}

/// A top-level declaration. See GRAMMAR.md §2.
#[derive(Debug)]
pub enum ItemKind {
    Import(ImportDecl),
    Space(SpaceDecl),
    Role(RoleDecl),
    TypeAlias(TypeAlias),
    Fn(FnDef),
    Let(LetBinding),
    /// Recovery placeholder. The diagnostic explaining it has already been
    /// issued; later phases should skip this subtree silently. The node's span
    /// still covers the skipped tokens, so the tree stays total.
    Error,
}

/// `import a::b::c`
#[derive(Debug)]
pub struct ImportDecl {
    pub path: Vec<Ident>,
}

/// `space Concepts = MAP[8192] where seed = 42`
///
/// The dimension is an arbitrary expression because it must be a *constant*,
/// and deciding what is constant is the checker's job, not the parser's.
/// Capacity is deliberately absent (GRAMMAR.md §3): it is derived from the
/// dimension and never written by hand.
#[derive(Debug)]
pub struct SpaceDecl {
    pub name: Ident,
    /// `MAP`, `BSC`, `HRR`, `FHRR`, ... resolved later against a builtin table.
    pub family: Option<Ident>,
    pub dim: Option<ExprId>,
    pub attrs: Vec<Attr>,
}

/// `role Subject, Verb, Object in Concepts`
#[derive(Debug)]
pub struct RoleDecl {
    pub names: Vec<Ident>,
    /// The space whose codebook these atoms are drawn from.
    pub space: Option<Ident>,
}

/// One `name = expr` inside a `where` clause.
#[derive(Debug)]
pub struct Attr {
    pub name: Ident,
    pub value: Option<ExprId>,
    pub span: Span,
}

/// `type Scene = Vec[Concepts; load 3]`
#[derive(Debug)]
pub struct TypeAlias {
    pub name: Ident,
    pub ty: Option<TypeExprId>,
}

/// A function definition.
#[derive(Debug)]
pub struct FnDef {
    pub name: Ident,
    pub params: Vec<Param>,
    /// `None` when the source wrote no `-> T`.
    pub return_type: Option<TypeExprId>,
    pub attrs: Vec<Attr>,
    /// `None` only after error recovery; the grammar requires a body.
    pub body: Option<ExprId>,
}

/// A parameter. `ty` is `None` only after recovery — GRAMMAR.md §5.6 makes the
/// annotation mandatory, so a missing one is `RALY2006`.
#[derive(Debug)]
pub struct Param {
    pub name: Ident,
    pub ty: Option<TypeExprId>,
    pub span: Span,
}

/// A `let` binding, used both as an item and as a statement.
#[derive(Debug)]
pub struct LetBinding {
    pub mutable: bool,
    pub name: Ident,
    pub ty: Option<TypeExprId>,
    pub init: Option<ExprId>,
}

// -- statements --------------------------------------------------------------

#[derive(Debug)]
pub struct Stmt {
    pub kind: StmtKind,
    pub span: Span,
    pub origin: Origin,
}

#[derive(Debug)]
pub enum StmtKind {
    Let(LetBinding),
    Return(Option<ExprId>),
    Expr(ExprId),
    /// A nested declaration: `fn`, `space`, `role`, `type`, `import`.
    Item(ItemId),
    Error,
}

// -- expressions -------------------------------------------------------------

#[derive(Debug)]
pub struct Expr {
    pub kind: ExprKind,
    pub span: Span,
    pub origin: Origin,
}

#[derive(Debug)]
pub enum ExprKind {
    Literal(Literal),
    /// A `::`-separated name. A single segment is the common case.
    Path(Vec<Ident>),
    /// A parenthesised expression, kept so formatting and span reporting can
    /// tell `(a)` from `a`.
    Group(ExprId),
    Unary {
        op: UnOp,
        op_span: Span,
        operand: ExprId,
    },
    Binary {
        op: BinOp,
        op_span: Span,
        lhs: ExprId,
        rhs: ExprId,
    },
    /// `value |> stage`.
    ///
    /// Kept rather than desugared to `stage(value, ..)` at parse time, so that
    /// diagnostics about the stage point at the stage the user wrote and a
    /// formatter can reproduce the pipeline. See GRAMMAR.md §8.2.
    Pipeline {
        value: ExprId,
        op_span: Span,
        stage: ExprId,
    },
    Call {
        callee: ExprId,
        args: Vec<ExprId>,
    },
    Field {
        base: ExprId,
        name: Ident,
    },
    /// One of the five VSA primitives.
    Vsa(VsaCall),
    /// `[a, b, c]` — an ordinary collection, *not* a superposition.
    List(Vec<ExprId>),
    /// `()` or `(a, b)`. A one-element parenthesised expression is
    /// [`ExprKind::Group`], not a one-tuple.
    Tuple(Vec<ExprId>),
    Block {
        stmts: Vec<StmtId>,
        tail: Option<ExprId>,
    },
    If {
        cond: ExprId,
        /// Always an [`ExprKind::Block`].
        then_block: ExprId,
        /// A block, or another `If`.
        else_branch: Option<ExprId>,
    },
    Error,
}

impl ExprKind {
    /// A stable per-variant tag, used by [`Ast::structural_key`].
    fn discriminant(&self) -> u64 {
        match self {
            ExprKind::Literal(_) => 1,
            ExprKind::Path(_) => 2,
            ExprKind::Group(_) => 3,
            ExprKind::Unary { .. } => 4,
            ExprKind::Binary { .. } => 5,
            ExprKind::Pipeline { .. } => 6,
            ExprKind::Call { .. } => 7,
            ExprKind::Field { .. } => 8,
            ExprKind::Vsa(_) => 9,
            ExprKind::List(_) => 10,
            ExprKind::Tuple(_) => 11,
            ExprKind::Block { .. } => 12,
            ExprKind::If { .. } => 13,
            ExprKind::Error => 14,
        }
    }
}

/// The five VSA primitives. See GRAMMAR.md §7 for why these are keywords with
/// call syntax rather than infix operators.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum VsaOp {
    Bind,
    Bundle,
    Permute,
    Unbind,
    Cleanup,
}

impl VsaOp {
    pub fn name(&self) -> &'static str {
        match self {
            VsaOp::Bind => "bind",
            VsaOp::Bundle => "bundle",
            VsaOp::Permute => "permute",
            VsaOp::Unbind => "unbind",
            VsaOp::Cleanup => "cleanup",
        }
    }

    /// True for the operations whose operands may be reordered freely.
    ///
    /// Binding is commutative in all four families, and n-ary bundling is a
    /// single simultaneous superposition, so both are order-insensitive. The
    /// `bundle.left` *fold* is not, which is why [`VsaCall`] consults the
    /// variant too.
    pub fn is_commutative(&self) -> bool {
        matches!(self, VsaOp::Bind | VsaOp::Bundle)
    }

    /// Accepted operand counts, as `(min, max)`; `max` of `None` means n-ary.
    pub fn arity(&self, variant: Option<VsaVariant>) -> (usize, Option<usize>) {
        match (self, variant) {
            (VsaOp::Bind, _) => (2, None),
            (VsaOp::Bundle, None) => (1, None),
            (VsaOp::Bundle, Some(VsaVariant::Left)) => (2, None),
            (VsaOp::Permute, _) => (1, Some(2)),
            (VsaOp::Unbind, _) => (2, Some(2)),
            (VsaOp::Cleanup, _) => (1, Some(2)),
        }
    }

    /// The variants this operation accepts after a `.`.
    pub fn variants(&self) -> &'static [&'static str] {
        match self {
            VsaOp::Bundle => &["left"],
            _ => &[],
        }
    }
}

/// A named variant of an operation, written `bundle.left(..)`.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum VsaVariant {
    /// The left-nested binary fold. A *different function* from the n-ary
    /// primitive, because superposition is not associative.
    Left,
}

impl VsaVariant {
    pub fn name(&self) -> &'static str {
        match self {
            VsaVariant::Left => "left",
        }
    }
}

/// A call to one of the VSA primitives.
#[derive(Debug)]
pub struct VsaCall {
    pub op: VsaOp,
    /// The keyword's own span, for diagnostics that must point at the
    /// operation rather than at its operands.
    pub op_span: Span,
    /// `Some` when a variant was written, e.g. `bundle.left`. Retained even
    /// when unrecognised, so diagnostics can quote it.
    pub variant: Option<Ident>,
    pub variant_kind: Option<VsaVariant>,
    /// Operands in the order the user wrote them.
    pub args: Vec<ExprId>,
    /// The same operand ids in canonical order, for order-insensitive
    /// operations. Empty otherwise — an empty `canonical` means "order is
    /// significant here".
    pub canonical: Vec<ExprId>,
}

impl VsaCall {
    /// Whether this particular call's operands form a multiset.
    ///
    /// `bundle` is; `bundle.left` is not, because the fold nests left and
    /// superposition is not associative.
    pub fn is_order_insensitive(&self) -> bool {
        self.op.is_commutative() && self.variant_kind.is_none()
    }

    /// Operands in canonical order where one exists, source order otherwise.
    pub fn operands(&self) -> &[ExprId] {
        if self.canonical.is_empty() {
            &self.args
        } else {
            &self.canonical
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum UnOp {
    /// `-x`
    Neg,
    /// `!x`
    Not,
}

impl UnOp {
    pub fn spelling(&self) -> &'static str {
        match self {
            UnOp::Neg => "-",
            UnOp::Not => "!",
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum BinOp {
    Add,
    Sub,
    Mul,
    Div,
    Eq,
    Lt,
    LtEq,
    Gt,
    GtEq,
}

impl BinOp {
    pub fn spelling(&self) -> &'static str {
        match self {
            BinOp::Add => "+",
            BinOp::Sub => "-",
            BinOp::Mul => "*",
            BinOp::Div => "/",
            BinOp::Eq => "==",
            BinOp::Lt => "<",
            BinOp::LtEq => "<=",
            BinOp::Gt => ">",
            BinOp::GtEq => ">=",
        }
    }
}

/// Literal values, kept as *source text* rather than parsed numbers: deciding
/// that `1e400` saturates, wraps, or is an error is a semantic choice and is
/// not made here.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Literal {
    Int(Symbol),
    Float(Symbol),
    /// The literal's text with the surrounding quotes removed and escapes
    /// *not* yet expanded.
    Str(Symbol),
    Bool(bool),
}

impl Literal {
    fn key(&self) -> u64 {
        match self {
            Literal::Int(s) => 0x01_0000_0000 | s.as_u32() as u64,
            Literal::Float(s) => 0x02_0000_0000 | s.as_u32() as u64,
            Literal::Str(s) => 0x03_0000_0000 | s.as_u32() as u64,
            Literal::Bool(b) => 0x04_0000_0000 | *b as u64,
        }
    }
}

// -- types -------------------------------------------------------------------

#[derive(Debug)]
pub struct TypeExpr {
    pub kind: TypeExprKind,
    pub span: Span,
    pub origin: Origin,
}

/// Type syntax. See GRAMMAR.md §5.
#[derive(Debug)]
pub enum TypeExprKind {
    /// `Path`, or `Path[Args; Quals]`.
    Named {
        path: Vec<Ident>,
        args: Vec<TypeExprId>,
        quals: Vec<TypeQual>,
    },
    /// `(A, B) -> C`
    Fn {
        params: Vec<TypeExprId>,
        ret: Option<TypeExprId>,
    },
    /// `(A, B)`, and `()` for the unit type.
    Tuple(Vec<TypeExprId>),
    Error,
}

/// A qualifier after `;` inside a type argument list.
///
/// These are what make Raly's types more than shapes: they carry the
/// superposition load and the role schema the checker has to track.
#[derive(Debug)]
pub enum TypeQual {
    /// `load 3` — the number of items superposed into this value.
    ///
    /// `capacity` is always `None` out of the parser. Capacity is a function
    /// of the space's dimension and is filled in by the checker; there is no
    /// syntax for writing it. See GRAMMAR.md §5.3.
    Load {
        count: Option<ExprId>,
        capacity: Option<u32>,
        span: Span,
    },
    /// `roles {Subject, Verb}` — a *set*. `names` is sorted; `written` keeps
    /// source order for diagnostics.
    Roles {
        names: Vec<Ident>,
        written: Vec<Ident>,
        span: Span,
    },
    /// `clean` — has been projected onto a codebook.
    Clean(Span),
    /// `noisy` — the residue of an unbind, not yet cleaned up.
    Noisy(Span),
    Error(Span),
}

impl TypeQual {
    pub fn span(&self) -> Span {
        match self {
            TypeQual::Load { span, .. } => *span,
            TypeQual::Roles { span, .. } => *span,
            TypeQual::Clean(span) => *span,
            TypeQual::Noisy(span) => *span,
            TypeQual::Error(span) => *span,
        }
    }

    /// The qualifier keywords the parser accepts, for "did you mean" advice.
    pub const KEYWORDS: &'static [&'static str] = &["load", "roles", "clean", "noisy"];
}
