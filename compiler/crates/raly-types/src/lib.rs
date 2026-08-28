//! The Raly type checker.
//!
//! This is the product. Raly exists to catch, at compile time, four classes of
//! mistake that a tensor library cannot see at all — and the entire value of
//! catching them is in what the message says, so the diagnostics here are
//! written with as much care as the algorithms.
//!
//! # Four properties, four small solvers
//!
//! Decision 4 of `docs/compiler-architecture.md` is binding: **algebraic types
//! plus small decidable solvers, one per property. No SMT, no dependent
//! types.** SMT fails nonconstructively — an unsat core is not an explanation —
//! and a language pitched on explaining silent bugs cannot answer "why?" with
//! a timeout.
//!
//! | Property | Mechanism | Where |
//! |---|---|---|
//! | Dimension | abelian-group unification, Kennedy's units of measure; failure prints a concrete residual | [`dim`] |
//! | Family | a plain enum; mixing families is an error | `raly_resolve::Family` |
//! | Capacity / load | natural-number intervals over *measured* capacity | [`ty::Load`], [`capacity`] |
//! | Role schema | row polymorphism with scoped labels, after Leijen | [`ty::Row`] |
//!
//! # The algebra it enforces
//!
//! From `docs/semantics/vsa-and-discrete-ops.md`:
//!
//! * `bundle` is n-ary and has **no identity**, so `bundle()` denotes no
//!   vector — reported by the parser as `RALY2003`.
//! * Bundling is **not associative**, so `bundle.left` is a different function
//!   from `bundle`; using the fold is a warning (`RALY5003`).
//! * `bind` is commutative, so operand order carries no information; the AST
//!   stores a canonical order and the checker never depends on source order.
//! * Superposition load **adds** across `bundle` and **multiplies** across
//!   `bind`, and a bundle past its space's capacity is `RALY5001`.
//! * Nested `unbind` with no `cleanup` between degrades provably: depth 2 is a
//!   warning, depth 3 an error (`RALY5002`).
//!
//! # Shape
//!
//! ```ignore
//! let resolved = raly_resolve::resolve(&ast);
//! let checked = raly_types::check(&ast, &resolved);
//! ```
//!
//! [`check`] is pure — `fn(&Db, Input) -> Output`, no ambient mutable state —
//! and, like every other phase, returns a value plus diagnostics rather than a
//! `Result`. An expression whose type could not be determined gets
//! [`Ty::Error`], which is compatible with everything and reports nothing
//! further, so one mistake produces one message.

#![deny(missing_debug_implementations)]

pub mod capacity;
pub mod constraint;
pub mod dim;
pub mod ty;

pub use constraint::{Blame, Reason};
pub use dim::Dim;
pub use ty::{CapacityBasis, Load, Names, Row, SpaceId, SpaceInfo, Ty, VecTy};

use std::collections::{HashMap, HashSet};

use raly_ast::{
    Ast, BinOp, ExprId, ExprKind, Ident, ItemId, ItemKind, Literal, StmtId, StmtKind, TypeExprId,
    TypeExprKind, TypeQual, UnOp, VsaCall, VsaOp, VsaVariant,
};
use raly_diag::{codes, Diagnostic, Diagnostics, Span};
use raly_resolve::{Builtin, DefId, DefKind, Family, Resolved};

/// Everything type checking learned about one file.
#[derive(Debug)]
pub struct Checked {
    /// Every `space` declaration, with its folded dimension and its capacity.
    pub spaces: Vec<SpaceInfo>,
    /// Expression node id -> inferred type.
    pub expr_types: HashMap<u32, Ty>,
    /// Item node id -> the type the item declares: a `Ty::Fn` for a function,
    /// the expansion for a type alias, the annotated or inferred type for a
    /// `let`. Populated for **every** item, including ones nothing references,
    /// because `raly explain` describes a program rather than checking it.
    pub item_types: HashMap<u32, Ty>,
    pub diagnostics: Diagnostics,
}

impl Checked {
    pub fn type_of(&self, expr: ExprId) -> Option<&Ty> {
        self.expr_types.get(&expr.raw())
    }

    /// The type an item declares, for the explainer.
    pub fn type_of_item(&self, item: ItemId) -> Option<&Ty> {
        self.item_types.get(&item.raw())
    }

    pub fn has_errors(&self) -> bool {
        self.diagnostics.has_errors()
    }
}

/// Type-check a resolved file.
///
/// Never panics and never bails out early.
pub fn check(ast: &Ast, resolved: &Resolved) -> Checked {
    let mut checker = Checker::new(ast, resolved);
    checker.run();
    checker.finish()
}

// -- the checker -------------------------------------------------------------

#[derive(Debug)]
struct Checker<'a> {
    ast: &'a Ast,
    resolved: &'a Resolved,
    spaces: Vec<SpaceInfo>,
    space_of_def: HashMap<DefId, SpaceId>,
    /// Lowered type annotations, keyed by node, so lowering twice costs
    /// nothing and never duplicates a diagnostic.
    type_cache: HashMap<u32, Ty>,
    def_types: HashMap<DefId, Ty>,
    in_progress: HashSet<DefId>,
    alias_stack: Vec<u32>,
    /// The enclosing function's `(result type, name, span of the annotation)`.
    return_types: Vec<(Ty, String, Option<Span>)>,
    expr_types: HashMap<u32, Ty>,
    item_types: HashMap<u32, Ty>,
    diagnostics: Diagnostics,
}

impl<'a> Checker<'a> {
    fn new(ast: &'a Ast, resolved: &'a Resolved) -> Self {
        Checker {
            ast,
            resolved,
            spaces: Vec::new(),
            space_of_def: HashMap::new(),
            type_cache: HashMap::new(),
            def_types: HashMap::new(),
            in_progress: HashSet::new(),
            alias_stack: Vec::new(),
            return_types: Vec::new(),
            expr_types: HashMap::new(),
            item_types: HashMap::new(),
            diagnostics: Diagnostics::new(),
        }
    }

    fn finish(mut self) -> Checked {
        self.diagnostics.sort_by_position();
        Checked {
            spaces: self.spaces,
            expr_types: self.expr_types,
            item_types: self.item_types,
            diagnostics: self.diagnostics,
        }
    }

    fn run(&mut self) {
        self.collect_spaces();
        let root = self.ast.root.clone();
        for item in root {
            self.check_item(item);
        }
    }

    // -- spaces --------------------------------------------------------------

    /// Fold every `space` declaration's dimension and derive its capacity.
    ///
    /// Done up front and for the whole file, because items are hoisted: a
    /// function above a `space` may still mention it.
    fn collect_spaces(&mut self) {
        let items = self.all_items();
        for item in items {
            let ItemKind::Space(space) = &self.ast.items[item].kind else {
                continue;
            };
            let name = self.ast.text(space.name).to_string();
            let decl_span = self.ast.items[item].span;
            let dim_expr = space.dim;
            let dim_span = dim_expr.map(|e| self.ast.exprs[e].span);
            let family = self.resolved.family_of(item);
            let effective = space
                .attrs
                .iter()
                .find(|a| self.ast.text(a.name) == "effective")
                .and_then(|a| a.value);

            let folded = dim_expr.and_then(|e| self.fold_dim(e, &mut HashSet::new()));
            if folded.is_none() {
                if let Some(expr) = dim_expr {
                    if !self.ast.exprs[expr].origin.is_recovered() {
                        self.report_non_constant_dimension(expr, &name);
                    }
                }
            }
            let dim_known = folded.is_some();
            let dim = folded.clone().unwrap_or_else(Dim::one);
            let effective_value = effective.and_then(|e| self.fold_int(e, &mut HashSet::new()));
            let nominal = folded.as_ref().and_then(|d| d.as_constant());
            let (capacity_dim, basis) = match effective_value {
                Some(value) => (Some(u64::from(value)), CapacityBasis::Effective),
                None => (nominal, CapacityBasis::Nominal),
            };

            let id = SpaceId(self.spaces.len() as u32);
            let def = self.resolved.def_of_item(item).unwrap_or(DefId::ERROR);
            self.spaces.push(SpaceInfo {
                def,
                name,
                decl_span,
                dim_span,
                family,
                dim,
                dim_known,
                capacity_dim,
                capacity_basis: basis,
                capacity: capacity_dim.map(capacity::capacity),
            });
            self.space_of_def.insert(def, id);
        }
    }

    /// Every item in the file, including ones nested inside function bodies.
    fn all_items(&self) -> Vec<ItemId> {
        let mut out = Vec::new();
        let mut queue: Vec<ItemId> = self.ast.root.clone();
        while let Some(item) = queue.pop() {
            out.push(item);
            if let ItemKind::Fn(f) = &self.ast.items[item].kind {
                if let Some(body) = f.body {
                    self.collect_nested_items(body, &mut queue);
                }
            }
        }
        out.sort_by_key(|i| i.raw());
        out
    }

    fn collect_nested_items(&self, expr: ExprId, out: &mut Vec<ItemId>) {
        if let ExprKind::Block { stmts, tail } = &self.ast.exprs[expr].kind {
            for &stmt in stmts {
                match &self.ast.stmts[stmt].kind {
                    StmtKind::Item(item) => out.push(*item),
                    StmtKind::Expr(inner) => self.collect_nested_items(*inner, out),
                    _ => {}
                }
            }
            if let Some(tail) = tail {
                self.collect_nested_items(*tail, out);
            }
        }
    }

    fn space_info(&self, id: SpaceId) -> Option<&SpaceInfo> {
        self.spaces.get(id.index())
    }

    // -- constant folding ----------------------------------------------------

    /// Fold an expression to a dimension.
    ///
    /// Anything that does not fold to a number but *names* something becomes a
    /// free variable of the dimension group rather than an error, so
    /// `MAP[2 * BASE_D]` still compares equal to another `MAP[2 * BASE_D]`
    /// even though neither is a number.
    fn fold_dim(&self, expr: ExprId, seen: &mut HashSet<DefId>) -> Option<Dim> {
        match &self.ast.exprs[expr].kind {
            ExprKind::Literal(Literal::Int(sym)) => {
                let text = self.ast.names.resolve(*sym).replace('_', "");
                text.parse::<u64>().ok().map(Dim::constant)
            }
            ExprKind::Group(inner) => self.fold_dim(*inner, seen),
            ExprKind::Path(segments) if segments.len() == 1 => {
                let def = self.resolved.expr_ref(expr)?;
                if def == DefId::ERROR || !seen.insert(def) {
                    return None;
                }
                let folded = match self.resolved.def(def).kind {
                    DefKind::Let { .. } => self
                        .let_initialiser(def)
                        .and_then(|e| self.fold_dim(e, seen)),
                    _ => None,
                };
                seen.remove(&def);
                folded.or_else(|| Some(Dim::variable(self.resolved.def(def).name.clone())))
            }
            ExprKind::Binary { op, lhs, rhs, .. } => {
                let left = self.fold_dim(*lhs, seen)?;
                let right = self.fold_dim(*rhs, seen)?;
                match op {
                    BinOp::Mul => Some(left.multiply(&right)),
                    BinOp::Div => Some(left.divide(&right)),
                    BinOp::Add | BinOp::Sub => {
                        let (a, b) = (left.as_constant()?, right.as_constant()?);
                        let value = if *op == BinOp::Add {
                            a.checked_add(b)?
                        } else {
                            a.checked_sub(b)?
                        };
                        Some(Dim::constant(value))
                    }
                    _ => None,
                }
            }
            _ => None,
        }
    }

    /// Fold an expression to a plain natural number, for `load` counts and for
    /// `where effective = ...`.
    fn fold_int(&self, expr: ExprId, seen: &mut HashSet<DefId>) -> Option<u32> {
        self.fold_dim(expr, seen)
            .and_then(|d| d.as_constant())
            .and_then(|n| u32::try_from(n).ok())
    }

    fn let_initialiser(&self, def: DefId) -> Option<ExprId> {
        for &item in &self.ast.root {
            if let ItemKind::Let(binding) = &self.ast.items[item].kind {
                if self.resolved.def_of_item(item) == Some(def) {
                    return binding.init;
                }
            }
        }
        None
    }

    // -- lowering type annotations -------------------------------------------

    fn lower_type(&mut self, id: TypeExprId) -> Ty {
        if let Some(ty) = self.type_cache.get(&id.raw()) {
            return ty.clone();
        }
        // No placeholder is reserved here. Type *expressions* form a finite
        // tree, so the only way to recurse forever is through an alias, and
        // `alias_stack` catches that with a diagnostic. Reserving an error
        // placeholder would cut the cycle silently instead.
        let lowered = self.lower_type_uncached(id);
        self.type_cache.insert(id.raw(), lowered.clone());
        lowered
    }

    fn lower_type_uncached(&mut self, id: TypeExprId) -> Ty {
        let node = &self.ast.types[id];
        let span = node.span;
        match &node.kind {
            TypeExprKind::Error => Ty::Error,
            TypeExprKind::Tuple(elems) => {
                let elems = elems.clone();
                if elems.is_empty() {
                    return Ty::Unit;
                }
                Ty::Tuple(elems.into_iter().map(|e| self.lower_type(e)).collect())
            }
            TypeExprKind::Fn { params, ret } => {
                let (params, ret) = (params.clone(), *ret);
                let params = params.into_iter().map(|p| self.lower_type(p)).collect();
                let ret = ret.map(|r| self.lower_type(r)).unwrap_or(Ty::Unit);
                Ty::Fn {
                    params,
                    ret: Box::new(ret),
                }
            }
            TypeExprKind::Named { path, args, quals } => {
                let args = args.clone();
                let quals = describe_quals(quals);
                let type_name = path
                    .first()
                    .map(|ident| self.ast.text(*ident).to_string())
                    .unwrap_or_else(|| "type".to_string());
                let Some(def) = self.resolved.type_ref(id) else {
                    return Ty::Error;
                };
                match self.resolved.def(def).kind {
                    DefKind::Error => Ty::Error,
                    DefKind::Space(item) => {
                        self.reject_type_application(&type_name, args.len(), quals.len(), 0, span);
                        self.space_of_item(item).map(Ty::Space).unwrap_or(Ty::Error)
                    }
                    DefKind::TypeAlias(item) => {
                        self.reject_type_application(&type_name, args.len(), quals.len(), 0, span);
                        self.lower_alias(item, span)
                    }
                    DefKind::Builtin(Builtin::Int) => {
                        self.reject_type_application(&type_name, args.len(), quals.len(), 0, span);
                        Ty::Int
                    }
                    DefKind::Builtin(Builtin::Float) => {
                        self.reject_type_application(&type_name, args.len(), quals.len(), 0, span);
                        Ty::Float
                    }
                    DefKind::Builtin(Builtin::Bool) => {
                        self.reject_type_application(&type_name, args.len(), quals.len(), 0, span);
                        Ty::Bool
                    }
                    DefKind::Builtin(Builtin::Str) => {
                        self.reject_type_application(&type_name, args.len(), quals.len(), 0, span);
                        Ty::Str
                    }
                    DefKind::Builtin(Builtin::Sym) => {
                        self.reject_type_application(&type_name, args.len(), quals.len(), 1, span);
                        let space = self.space_argument(&args, "Sym", span);
                        Ty::Sym { space, role: None }
                    }
                    DefKind::Builtin(Builtin::Vec) => {
                        if args.len() != 1 {
                            self.reject_type_application(&type_name, args.len(), 0, 1, span);
                        }
                        let space = self.space_argument(&args, "Vec", span);
                        let vec = self.build_vec(id, space, &quals, span);
                        Ty::vector(vec)
                    }
                    _ => Ty::Error,
                }
            }
        }
    }

    fn lower_alias(&mut self, item: ItemId, span: Span) -> Ty {
        if self.alias_stack.contains(&item.raw()) {
            let name = match &self.ast.items[item].kind {
                ItemKind::TypeAlias(alias) => self.ast.text(alias.name).to_string(),
                _ => "?".to_string(),
            };
            self.diagnostics.push(
                Diagnostic::error(
                    codes::RECURSIVE_TYPE,
                    format!("the type alias `{name}` is defined in terms of itself"),
                )
                .with_primary(span, "this expansion never terminates")
                .with_note("Raly type aliases are expanded, not boxed, so a cycle has no size")
                .with_help("break the cycle, or introduce a `space` instead"),
            );
            return Ty::Error;
        }
        let target = match &self.ast.items[item].kind {
            ItemKind::TypeAlias(alias) => alias.ty,
            _ => None,
        };
        let Some(target) = target else {
            return Ty::Error;
        };
        self.alias_stack.push(item.raw());
        let ty = self.lower_type(target);
        self.alias_stack.pop();
        ty
    }

    fn reject_type_application(
        &mut self,
        name: &str,
        actual_args: usize,
        qualifier_count: usize,
        expected_args: usize,
        span: Span,
    ) {
        if actual_args != expected_args {
            self.diagnostics.push(
                Diagnostic::error(
                    codes::BAD_ARGUMENT_COUNT,
                    format!(
                        "type `{name}` expects {expected_args} argument(s), found {actual_args}"
                    ),
                )
                .with_primary(span, "invalid type application")
                .with_help("remove the extra type arguments"),
            );
        }
        if qualifier_count > 0 {
            self.diagnostics.push(
                Diagnostic::error(
                    codes::UNKNOWN_TYPE_QUALIFIER,
                    format!("type `{name}` does not accept qualifiers"),
                )
                .with_primary(span, "qualifier is not meaningful here")
                .with_help("put `load`, `roles`, or `clean` on a vector type"),
            );
        }
    }

    fn space_of_item(&self, item: ItemId) -> Option<SpaceId> {
        let def = self.resolved.def_of_item(item)?;
        self.space_of_def.get(&def).copied()
    }

    /// The first type argument of `Vec[..]` or `Sym[..]`, which must be a space.
    fn space_argument(
        &mut self,
        args: &[TypeExprId],
        constructor: &'static str,
        span: Span,
    ) -> Option<SpaceId> {
        let Some(&first) = args.first() else {
            self.diagnostics.push(
                Diagnostic::error(
                    codes::TYPE_MISMATCH,
                    format!("`{constructor}` needs to know which space it is in"),
                )
                .with_primary(span, format!("write `{constructor}[<space>]`"))
                .with_note(
                    "a space fixes the family, the dimension and the codebook, and a vector \
                     has no identity without one",
                )
                .with_help("declare one with `space <name> = MAP[1024]`"),
            );
            return None;
        };
        let lowered = self.lower_type(first);
        match lowered {
            Ty::Space(id) => Some(id),
            Ty::Error => None,
            other => {
                let found = self.show(&other);
                let arg_span = self.ast.types[first].span;
                self.diagnostics.push(
                    Diagnostic::error(codes::TYPE_MISMATCH, "expected a space")
                        .with_primary(arg_span, format!("this is `{found}`, not a space"))
                        .with_note(Reason::SpaceArgument { constructor }.context())
                        .with_help("name a `space` declaration here"),
                );
                None
            }
        }
    }

    fn build_vec(
        &mut self,
        id: TypeExprId,
        space: Option<SpaceId>,
        quals: &[QualInfo],
        span: Span,
    ) -> VecTy {
        let mut load = Load::any();
        let mut roles = Row::unknown();
        let mut clean = None;
        let mut role_index = 0usize;
        for qual in quals {
            match *qual {
                QualInfo::Load { count, span } => {
                    match count.and_then(|c| self.fold_int(c, &mut HashSet::new())) {
                        Some(n) => load = Load::exactly(n),
                        None => {
                            if let Some(count) = count {
                                if !self.ast.exprs[count].origin.is_recovered() {
                                    self.diagnostics.push(
                                        Diagnostic::error(
                                            codes::LOAD_MISMATCH,
                                            "a `load` must be a compile-time constant",
                                        )
                                        .with_primary(span, "this does not fold to a number")
                                        .with_note(Reason::LoadAnnotation.context())
                                        .with_help("write a literal, or a top-level `let`"),
                                    );
                                }
                            }
                        }
                    }
                }
                QualInfo::Roles { count } => {
                    let mut row = Row::closed_empty();
                    for _ in 0..count {
                        if let Some(def) = self.resolved.role_ref(id, role_index) {
                            if def != DefId::ERROR {
                                row.extend(def);
                            }
                        }
                        role_index += 1;
                    }
                    roles = row;
                }
                QualInfo::Clean => clean = Some(true),
                QualInfo::Noisy => clean = Some(false),
                QualInfo::Other => {}
            }
        }
        // An annotation can exceed capacity all by itself, and saying so at
        // the declaration is more useful than waiting for a call site.
        if load.is_exact() {
            if let Some(space) = space {
                self.check_capacity(space, load.minimum(), span, CapacitySite::Annotation);
            }
        }
        VecTy {
            space,
            load,
            roles,
            clean,
            depth: 0,
        }
    }

    // -- types of definitions ------------------------------------------------

    fn def_type(&mut self, def: DefId) -> Ty {
        if let Some(ty) = self.def_types.get(&def) {
            return ty.clone();
        }
        if !self.in_progress.insert(def) {
            return Ty::Error;
        }
        let kind = self.resolved.def(def).kind;
        let ty = match kind {
            DefKind::Error | DefKind::Builtin(_) | DefKind::TypeAlias(_) => Ty::Error,
            DefKind::Space(item) => self.space_of_item(item).map(Ty::Space).unwrap_or(Ty::Error),
            DefKind::Role { space, .. } => {
                let space_id = space
                    .filter(|s| *s != DefId::ERROR)
                    .and_then(|s| self.space_of_def.get(&s).copied());
                Ty::Sym {
                    space: space_id,
                    role: Some(def),
                }
            }
            DefKind::Fn(item) => self.fn_signature(item),
            DefKind::Param { item, index } => {
                let annotation = match &self.ast.items[item].kind {
                    ItemKind::Fn(f) => f.params.get(index).and_then(|p| p.ty),
                    _ => None,
                };
                annotation.map(|t| self.lower_type(t)).unwrap_or(Ty::Error)
            }
            DefKind::Let { local: false } => self.module_constant_type(def),
            // Locals are recorded as their `let` is checked; a lookup that
            // misses is a use the resolver has already reported.
            DefKind::Let { local: true } => Ty::Error,
        };
        self.in_progress.remove(&def);
        self.def_types.insert(def, ty.clone());
        ty
    }

    fn module_constant_type(&mut self, def: DefId) -> Ty {
        let item = self.ast.root.iter().copied().find(|&i| {
            matches!(self.ast.items[i].kind, ItemKind::Let(_))
                && self.resolved.def_of_item(i) == Some(def)
        });
        let Some(item) = item else { return Ty::Error };
        let (annotation, init) = match &self.ast.items[item].kind {
            ItemKind::Let(binding) => (binding.ty, binding.init),
            _ => return Ty::Error,
        };
        match annotation {
            Some(annotation) => self.lower_type(annotation),
            None => init.map(|e| self.infer(e)).unwrap_or(Ty::Error),
        }
    }

    fn fn_signature(&mut self, item: ItemId) -> Ty {
        let (params, ret) = match &self.ast.items[item].kind {
            ItemKind::Fn(f) => (
                f.params.iter().map(|p| p.ty).collect::<Vec<_>>(),
                f.return_type,
            ),
            _ => return Ty::Error,
        };
        let params = params
            .into_iter()
            .map(|p| p.map(|t| self.lower_type(t)).unwrap_or(Ty::Error))
            .collect();
        let ret = ret.map(|r| self.lower_type(r)).unwrap_or(Ty::Unit);
        Ty::Fn {
            params,
            ret: Box::new(ret),
        }
    }

    // -- items ---------------------------------------------------------------

    fn check_item(&mut self, item: ItemId) {
        if self.ast.items[item].origin.is_recovered() {
            return;
        }
        match &self.ast.items[item].kind {
            ItemKind::Fn(f) => {
                let name = self.ast.text(f.name).to_string();
                let body = f.body;
                let signature = self.fn_signature(item);
                self.item_types.insert(item.raw(), signature);
                let ret_ty = f.return_type;
                let ret_span = ret_ty.map(|r| self.ast.types[r].span);
                let ret = ret_ty.map(|r| self.lower_type(r)).unwrap_or(Ty::Unit);
                let Some(body) = body else { return };
                self.return_types
                    .push((ret.clone(), name.clone(), ret_span));
                let actual = self.infer(body);
                let span = self.tail_span(body);
                if ret_ty.is_some() {
                    let mut blame = Blame::new(span, Reason::Return { function: name });
                    if let Some(ret_span) = ret_span {
                        blame = blame.against(ret_span, "the declared result type");
                    }
                    self.require(&actual, &ret, &blame);
                }
                self.return_types.pop();
            }
            ItemKind::Let(binding) => {
                let (annotation, init, name) = (binding.ty, binding.init, binding.name);
                let ty = self.check_binding(annotation, init, name);
                self.item_types.insert(item.raw(), ty);
            }
            ItemKind::TypeAlias(alias) => {
                if let Some(ty) = alias.ty {
                    let expansion = self.lower_type(ty);
                    self.item_types.insert(item.raw(), expansion);
                }
            }
            ItemKind::Space(_) | ItemKind::Role(_) | ItemKind::Import(_) | ItemKind::Error => {}
        }
    }

    fn check_binding(
        &mut self,
        annotation: Option<TypeExprId>,
        init: Option<ExprId>,
        name: Ident,
    ) -> Ty {
        let declared = annotation.map(|t| self.lower_type(t));
        let Some(init) = init else {
            return declared.unwrap_or(Ty::Error);
        };
        let actual = self.infer(init);
        match declared {
            Some(declared) => {
                let mut blame = Blame::new(
                    self.ast.exprs[init].span,
                    Reason::LetAnnotation {
                        name: self.ast.text(name).to_string(),
                    },
                );
                if let Some(annotation) = annotation {
                    blame = blame.against(self.ast.types[annotation].span, "declared here");
                }
                self.require(&actual, &declared, &blame);
                declared
            }
            None => actual,
        }
    }

    /// The span to blame for a function's result: the tail expression if there
    /// is one, else the whole body.
    fn tail_span(&self, body: ExprId) -> Span {
        if let ExprKind::Block {
            tail: Some(tail), ..
        } = &self.ast.exprs[body].kind
        {
            return self.ast.exprs[*tail].span;
        }
        self.ast.exprs[body].span
    }

    // -- expressions ---------------------------------------------------------

    fn infer(&mut self, id: ExprId) -> Ty {
        let ty = self.infer_uncached(id);
        self.expr_types.insert(id.raw(), ty.clone());
        ty
    }

    fn infer_uncached(&mut self, id: ExprId) -> Ty {
        let node = &self.ast.exprs[id];
        let span = node.span;
        if node.origin.is_recovered() {
            return Ty::Error;
        }
        match &node.kind {
            ExprKind::Error => Ty::Error,
            ExprKind::Literal(lit) => match lit {
                Literal::Int(_) => Ty::Int,
                Literal::Float(_) => Ty::Float,
                Literal::Str(_) => Ty::Str,
                Literal::Bool(_) => Ty::Bool,
            },
            ExprKind::Path(_) => match self.resolved.expr_ref(id) {
                Some(def) => self.def_type(def),
                None => Ty::Error,
            },
            ExprKind::Group(inner) => {
                let inner = *inner;
                self.infer(inner)
            }
            ExprKind::Unary { op, operand, .. } => {
                let (op, operand) = (*op, *operand);
                let ty = self.infer(operand);
                if op == UnOp::Neg && ty == Ty::Float {
                    return Ty::Float;
                }
                let expected = match op {
                    UnOp::Neg => Ty::Int,
                    UnOp::Not => Ty::Bool,
                };
                let blame = Blame::new(
                    self.ast.exprs[operand].span,
                    Reason::Arithmetic { op: op.spelling() },
                );
                self.require(&ty, &expected, &blame);
                expected
            }
            ExprKind::Binary { op, lhs, rhs, .. } => {
                let (op, lhs, rhs) = (*op, *lhs, *rhs);
                self.infer_binary(op, lhs, rhs)
            }
            ExprKind::Tuple(elems) => {
                let elems = elems.clone();
                if elems.is_empty() {
                    return Ty::Unit;
                }
                Ty::Tuple(elems.into_iter().map(|e| self.infer(e)).collect())
            }
            ExprKind::List(elems) => {
                let elems = elems.clone();
                let Some(&first) = elems.first() else {
                    return Ty::List(Box::new(Ty::Error));
                };
                let mut head = self.infer(first);
                for &elem in &elems[1..] {
                    let ty = self.infer(elem);
                    let blame = Blame::new(self.ast.exprs[elem].span, Reason::ListElement)
                        .against(self.ast.exprs[first].span, "the first element is here");
                    head = self.join(&head, &ty, &blame);
                }
                Ty::List(Box::new(head))
            }
            ExprKind::Block { stmts, tail } => {
                let (stmts, tail) = (stmts.clone(), *tail);
                self.check_block(&stmts, tail)
            }
            ExprKind::If {
                cond,
                then_block,
                else_branch,
            } => {
                let (cond, then_block, else_branch) = (*cond, *then_block, *else_branch);
                let cond_ty = self.infer(cond);
                let blame = Blame::new(self.ast.exprs[cond].span, Reason::Condition);
                self.require(&cond_ty, &Ty::Bool, &blame);
                let then_ty = self.infer(then_block);
                match else_branch {
                    Some(branch) => {
                        let else_ty = self.infer(branch);
                        let blame = Blame::new(self.ast.exprs[branch].span, Reason::Branches)
                            .against(self.ast.exprs[then_block].span, "the other arm is here");
                        self.require(&else_ty, &then_ty, &blame);
                        then_ty
                    }
                    None => Ty::Unit,
                }
            }
            ExprKind::Field { base, .. } => {
                let base = *base;
                let _ = self.infer(base);
                Ty::Error
            }
            ExprKind::Call { callee, args } => {
                let (callee, args) = (*callee, args.clone());
                self.check_call(callee, &args, span)
            }
            ExprKind::Vsa(_) => {
                let call = self.vsa_snapshot(id);
                let args = call.args.clone();
                self.check_vsa(&call, &args, span)
            }
            ExprKind::Pipeline { value, stage, .. } => {
                let (value, stage) = (*value, *stage);
                self.check_pipeline(value, stage, span)
            }
        }
    }

    /// The least type both operands fit, for contexts with no annotation to
    /// check against — today, list literals.
    ///
    /// This is a *join*, not a coercion: an atom is already a vector of load
    /// one, so a list mixing `Sym[S]` and `Vec[S]` is a list of vectors whose
    /// load interval covers both. Anything wider than that is a mismatch,
    /// reported against the first element, which is what fixed the type.
    fn join(&mut self, left: &Ty, right: &Ty, blame: &Blame) -> Ty {
        if left == right || right.is_error() {
            return left.clone();
        }
        if left.is_error() {
            return right.clone();
        }
        let (Some(a), Some(b)) = (left.as_vector(), right.as_vector()) else {
            self.report_plain_mismatch(right, left, blame);
            return Ty::Error;
        };
        self.require_space(b.space, a.space, blame);
        Ty::vector(VecTy {
            space: a.space.or(b.space),
            load: Load {
                low: a.load.low.min(b.load.low),
                high: a.load.high.max(b.load.high),
            },
            roles: {
                let mut row = a.roles.union(&b.roles);
                row.open = true;
                row
            },
            clean: if a.clean == b.clean { a.clean } else { None },
            depth: a.depth.max(b.depth),
        })
    }

    fn infer_binary(&mut self, op: BinOp, lhs: ExprId, rhs: ExprId) -> Ty {
        let left = self.infer(lhs);
        let right = self.infer(rhs);
        let spelling = op.spelling();
        if op == BinOp::Eq {
            let blame = Blame::new(
                self.ast.exprs[rhs].span,
                Reason::Arithmetic { op: spelling },
            )
            .against(self.ast.exprs[lhs].span, "compared with this");
            self.require(&right, &left, &blame);
            return Ty::Bool;
        }
        let numeric = matches!(op, BinOp::Add | BinOp::Sub | BinOp::Mul | BinOp::Div);
        let expected = if left == Ty::Float || right == Ty::Float {
            Ty::Float
        } else {
            Ty::Int
        };
        for (expr, ty) in [(lhs, &left), (rhs, &right)] {
            let blame = Blame::new(
                self.ast.exprs[expr].span,
                Reason::Arithmetic { op: spelling },
            );
            self.require(ty, &expected, &blame);
        }
        if numeric {
            expected
        } else {
            Ty::Bool
        }
    }

    fn check_block(&mut self, stmts: &[StmtId], tail: Option<ExprId>) -> Ty {
        for &stmt in stmts {
            self.check_stmt(stmt);
        }
        match tail {
            Some(tail) => self.infer(tail),
            None if stmts
                .iter()
                .any(|stmt| matches!(&self.ast.stmts[*stmt].kind, StmtKind::Return(_))) =>
            {
                self.return_types
                    .last()
                    .map(|(ty, _, _)| ty.clone())
                    .unwrap_or(Ty::Error)
            }
            None => Ty::Unit,
        }
    }

    fn check_stmt(&mut self, id: StmtId) {
        let stmt_span = self.ast.stmts[id].span;
        match &self.ast.stmts[id].kind {
            StmtKind::Error => {}
            StmtKind::Item(item) => {
                let item = *item;
                self.check_item(item);
            }
            StmtKind::Expr(expr) => {
                let expr = *expr;
                let _ = self.infer(expr);
            }
            StmtKind::Let(binding) => {
                let (annotation, init, name) = (binding.ty, binding.init, binding.name);
                let ty = self.check_binding(annotation, init, name);
                if let Some(def) = self.local_def(name) {
                    self.def_types.insert(def, ty);
                }
            }
            StmtKind::Return(value) => {
                let value = *value;
                let expected = self.return_types.last().cloned();
                let actual = match value {
                    Some(expr) => self.infer(expr),
                    None => Ty::Unit,
                };
                if let Some((expected, function, ret_span)) = expected {
                    let span = value.map(|e| self.ast.exprs[e].span).unwrap_or(stmt_span);
                    let mut blame = Blame::new(span, Reason::Return { function });
                    if let Some(ret_span) = ret_span {
                        blame = blame.against(ret_span, "the declared result type");
                    }
                    self.require(&actual, &expected, &blame);
                }
            }
        }
    }

    /// The `DefId` the resolver allocated for a local `let`, found by its
    /// declaration span, which is unique to it.
    fn local_def(&self, name: Ident) -> Option<DefId> {
        self.resolved
            .defs
            .iter()
            .position(|d| d.span == Some(name.span) && matches!(d.kind, DefKind::Let { .. }))
            .map(|i| DefId(i as u32))
    }

    fn check_call(&mut self, callee: ExprId, args: &[ExprId], span: Span) -> Ty {
        let callee_ty = self.infer(callee);
        let name = self.callee_name(callee);
        let Ty::Fn { params, ret } = callee_ty else {
            if !callee_ty.is_error() {
                let found = self.show(&callee_ty);
                self.diagnostics.push(
                    Diagnostic::error(
                        codes::NOT_CALLABLE,
                        format!("`{name}` is not something you can call"),
                    )
                    .with_primary(self.ast.exprs[callee].span, format!("this is `{found}`"))
                    .with_help("only functions and function-typed parameters can be called"),
                );
            }
            for &arg in args {
                let _ = self.infer(arg);
            }
            return Ty::Error;
        };
        if params.len() != args.len() {
            self.diagnostics.push(
                Diagnostic::error(
                    codes::BAD_ARGUMENT_COUNT,
                    format!(
                        "`{name}` takes {} but {} {} given",
                        plural(params.len(), "argument"),
                        args.len(),
                        if args.len() == 1 { "was" } else { "were" }
                    ),
                )
                .with_primary(span, format!("{} here", plural(args.len(), "argument")))
                .with_help("check the call against the signature"),
            );
        }
        for (index, &arg) in args.iter().enumerate() {
            let actual = self.infer(arg);
            if let Some(expected) = params.get(index).cloned() {
                let blame = Blame::new(
                    self.ast.exprs[arg].span,
                    Reason::Argument {
                        callee: name.clone(),
                        index,
                    },
                );
                self.require(&actual, &expected, &blame);
            }
        }
        *ret
    }

    fn callee_name(&self, callee: ExprId) -> String {
        match &self.ast.exprs[callee].kind {
            ExprKind::Path(segments) => segments
                .iter()
                .map(|s| self.ast.text(*s))
                .collect::<Vec<_>>()
                .join("::"),
            _ => "this expression".to_string(),
        }
    }

    /// `value |> stage` threads `value` into the stage's *first* operand.
    fn check_pipeline(&mut self, value: ExprId, stage: ExprId, span: Span) -> Ty {
        let ty = match &self.ast.exprs[stage].kind {
            ExprKind::Vsa(_) => {
                let call = self.vsa_snapshot(stage);
                let mut args = vec![value];
                args.extend(call.args.iter().copied());
                self.check_vsa(&call, &args, span)
            }
            ExprKind::Call { callee, args } => {
                let (callee, rest) = (*callee, args.clone());
                let mut args = vec![value];
                args.extend(rest);
                self.check_call(callee, &args, span)
            }
            _ => self.check_call(stage, &[value], span),
        };
        self.expr_types.insert(stage.raw(), ty.clone());
        ty
    }

    /// The parts of a `VsaCall` this phase needs, copied out of the arena so
    /// the tree is not borrowed while diagnostics are pushed.
    fn vsa_snapshot(&self, id: ExprId) -> VsaSnapshot {
        match &self.ast.exprs[id].kind {
            ExprKind::Vsa(call) => VsaSnapshot::of(call),
            _ => VsaSnapshot {
                op: VsaOp::Bundle,
                op_span: self.ast.exprs[id].span,
                variant: None,
                args: Vec::new(),
            },
        }
    }

    // -- the VSA algebra -----------------------------------------------------

    fn check_vsa(&mut self, call: &VsaSnapshot, args: &[ExprId], span: Span) -> Ty {
        let types: Vec<Ty> = args.iter().map(|&a| self.infer(a)).collect();
        match call.op {
            VsaOp::Bind => self.check_bind(call, args, &types),
            VsaOp::Bundle => self.check_bundle(call, args, &types, span),
            VsaOp::Permute => self.check_permute(args, &types),
            VsaOp::Unbind => self.check_unbind(call, args, &types),
            VsaOp::Cleanup => self.check_cleanup(args, &types),
            VsaOp::Broadcast => self.check_broadcast(args, &types),
        }
    }

    /// Every operand must be a vector in one space; returns that space plus
    /// the operands' vector views. Operands that are not vectors are reported
    /// and dropped.
    ///
    /// `elementwise` carries the operation keyword's span for the operations
    /// that combine their operands position by position — `bind` and `bundle`.
    /// Those are the ones a tensor library would silently broadcast, so a
    /// space mismatch between two of their operands is reported as
    /// [`codes::SILENT_BROADCAST`] rather than as a plain space mismatch. See
    /// GRAMMAR.md §7.3.
    fn vector_operands(
        &mut self,
        op: &'static str,
        elementwise: Option<Span>,
        args: &[ExprId],
        types: &[Ty],
    ) -> (Option<SpaceId>, Vec<VecTy>) {
        let mut space: Option<SpaceId> = None;
        let mut anchor: Option<Span> = None;
        let mut out = Vec::new();
        for (index, (&arg, ty)) in args.iter().zip(types).enumerate() {
            if ty.is_error() {
                continue;
            }
            let Some(vector) = ty.as_vector() else {
                let found = self.show(ty);
                self.diagnostics.push(
                    Diagnostic::error(codes::TYPE_MISMATCH, format!("`{op}` operates on vectors"))
                        .with_primary(
                            self.ast.exprs[arg].span,
                            format!("this is `{found}`, not a vector"),
                        )
                        .with_note(Reason::Operand { op, index }.context()),
                );
                continue;
            };
            if let Some(id) = vector.space {
                match space {
                    None => {
                        space = Some(id);
                        anchor = Some(self.ast.exprs[arg].span);
                    }
                    Some(first) if first != id => {
                        let shape = elementwise.zip(anchor).and_then(|(op_span, anchor)| {
                            self.broadcast_shape(first, id)
                                .map(|k| (op_span, anchor, k))
                        });
                        match shape {
                            Some((op_span, anchor, kind)) => self.report_silent_broadcast(
                                op,
                                op_span,
                                kind,
                                (anchor, first),
                                (self.ast.exprs[arg].span, id),
                            ),
                            None => {
                                let mut blame = Blame::new(
                                    self.ast.exprs[arg].span,
                                    Reason::Operand { op, index },
                                );
                                if let Some(anchor) = anchor {
                                    blame = blame.against(anchor, "the first operand is here");
                                }
                                self.report_space_mismatch(id, first, &blame);
                            }
                        }
                    }
                    Some(_) => {}
                }
            }
            out.push(vector);
        }
        (space, out)
    }

    fn check_bind(&mut self, call: &VsaSnapshot, args: &[ExprId], types: &[Ty]) -> Ty {
        let (space, operands) = self.vector_operands("bind", Some(call.op_span), args, types);
        if operands.is_empty() {
            return Ty::Error;
        }
        // Load multiplies: binding distributes over superposition, so binding
        // an m-item bundle with an n-item bundle yields m*n terms.
        let mut load = Load::exactly(1);
        let mut roles = Row::closed_empty();
        let mut clean = Some(true);
        let mut depth = 0;
        for vector in &operands {
            load = load.multiply(&vector.load);
            roles = roles.union(&vector.roles);
            if vector.clean == Some(false) {
                clean = Some(false);
            }
            depth = depth.max(vector.depth);
        }
        // A role operand is what makes a binding *keyed*: that is the label
        // the row gains, and the one `unbind` will later ask for.
        for ty in types {
            if let Ty::Sym {
                role: Some(def), ..
            } = ty
            {
                roles.extend(*def);
            }
        }
        Ty::vector(VecTy {
            space,
            load,
            roles,
            clean,
            depth,
        })
    }

    fn check_bundle(
        &mut self,
        call: &VsaSnapshot,
        args: &[ExprId],
        types: &[Ty],
        span: Span,
    ) -> Ty {
        // `bundle()` has already been reported by the parser (RALY2003):
        // superposition has no identity element in any discretised family, so
        // an empty bundle denotes no vector. Nothing to add here.
        if args.is_empty() {
            return Ty::Error;
        }
        let (space, operands) = self.vector_operands("bundle", Some(call.op_span), args, types);
        if operands.is_empty() {
            return Ty::Error;
        }
        let mut load = Load::exactly(0);
        let mut roles = Row::closed_empty();
        let mut clean = Some(true);
        let mut depth = 0;
        for vector in &operands {
            load = load.add(&vector.load);
            roles = roles.union(&vector.roles);
            if vector.clean == Some(false) {
                clean = Some(false);
            }
            depth = depth.max(vector.depth);
        }
        if call.variant == Some(VsaVariant::Left) && args.len() >= 3 {
            self.diagnostics.push(
                Diagnostic::warning(
                    codes::LOSSY_FOLD,
                    format!(
                        "`bundle.left` folds {} operands pairwise, which is not the vector \
                         `bundle` would produce",
                        args.len()
                    ),
                )
                .with_primary(call.op_span, "the left-nested fold")
                .with_note(
                    "normalised bundling is not associative in any VSA family, so the fold \
                     renormalises after each pair and gives the earlier operands less weight",
                )
                .with_help("use the n-ary `bundle(a, b, c)` unless the nesting is deliberate"),
            );
        }
        if let Some(space) = space {
            self.check_capacity(space, load.minimum(), span, CapacitySite::Bundle);
        }
        Ty::vector(VecTy {
            space,
            load,
            roles,
            clean,
            depth,
        })
    }

    fn check_permute(&mut self, args: &[ExprId], types: &[Ty]) -> Ty {
        let head = args.len().min(1);
        let (space, operands) =
            self.vector_operands("permute", None, &args[..head], &types[..head]);
        if let (Some(&shift), Some(ty)) = (args.get(1), types.get(1)) {
            let blame = Blame::new(
                self.ast.exprs[shift].span,
                Reason::Operand {
                    op: "permute",
                    index: 1,
                },
            );
            self.require(ty, &Ty::Int, &blame);
        }
        let Some(vector) = operands.into_iter().next() else {
            return Ty::Error;
        };
        // Permutation is a bijection: it preserves load, roles and cleanliness.
        Ty::vector(VecTy {
            space,
            load: vector.load,
            roles: vector.roles,
            clean: vector.clean,
            depth: vector.depth,
        })
    }

    fn check_unbind(&mut self, call: &VsaSnapshot, args: &[ExprId], types: &[Ty]) -> Ty {
        let (Some(&target), Some(target_ty)) = (args.first(), types.first()) else {
            return Ty::Error;
        };
        if target_ty.is_error() {
            return Ty::Error;
        }
        let target_ty = target_ty.clone();
        let Some(vector) = target_ty.as_vector() else {
            let found = self.show(&target_ty);
            self.diagnostics.push(
                Diagnostic::error(codes::TYPE_MISMATCH, "`unbind` operates on vectors")
                    .with_primary(
                        self.ast.exprs[target].span,
                        format!("this is `{found}`, not a vector"),
                    )
                    .with_note(
                        Reason::Operand {
                            op: "unbind",
                            index: 0,
                        }
                        .context(),
                    ),
            );
            return Ty::Error;
        };

        let mut roles = vector.roles.clone();
        if let (Some(&key), Some(key_ty)) = (args.get(1), types.get(1)) {
            let key_span = self.ast.exprs[key].span;
            let key_ty = key_ty.clone();
            match &key_ty {
                Ty::Error => {}
                Ty::Sym {
                    role: Some(def), ..
                } => {
                    let blame = Blame::new(key_span, Reason::UnbindKey);
                    self.require_space(key_ty.space(), vector.space, &blame);
                    if !roles.restrict(*def) && !roles.open {
                        self.report_role_not_bound(*def, &vector.roles, key_span, target);
                    }
                }
                other => {
                    let found = self.show(other);
                    self.diagnostics.push(
                        Diagnostic::error(
                            codes::NOT_A_ROLE,
                            "the key of an `unbind` must be a declared role",
                        )
                        .with_primary(key_span, format!("this is `{found}`"))
                        .with_note(Reason::UnbindKey.context())
                        .with_note(
                            "roles are static: the compiler tracks which roles a vector \
                             carries, and only a declared role can be looked up",
                        )
                        .with_help("declare it with `role <name> in <space>`"),
                    );
                }
            }
        }

        let depth = vector.depth + 1;
        if depth >= 2 {
            let inner = self.ast.exprs[target].span;
            self.report_nesting(depth, call.op_span, inner);
        }
        // What comes back is *one* item's worth of signal plus the residue of
        // everything else bundled at this level: load 1, and noisy until a
        // `cleanup` projects it back onto the codebook.
        Ty::vector(VecTy {
            space: vector.space,
            load: Load::exactly(1),
            roles,
            clean: Some(false),
            depth,
        })
    }

    fn check_cleanup(&mut self, args: &[ExprId], types: &[Ty]) -> Ty {
        let (Some(&target), Some(target_ty)) = (args.first(), types.first()) else {
            return Ty::Error;
        };
        let target_ty = target_ty.clone();
        let space = target_ty.space();
        if !target_ty.is_error() && target_ty.as_vector().is_none() {
            let found = self.show(&target_ty);
            self.diagnostics.push(
                Diagnostic::error(codes::TYPE_MISMATCH, "`cleanup` operates on vectors")
                    .with_primary(
                        self.ast.exprs[target].span,
                        format!("this is `{found}`, not a vector"),
                    )
                    .with_note(
                        Reason::Operand {
                            op: "cleanup",
                            index: 0,
                        }
                        .context(),
                    ),
            );
            return Ty::Error;
        }
        if let (Some(&codebook), Some(ty)) = (args.get(1), types.get(1)) {
            let codebook_span = self.ast.exprs[codebook].span;
            let ty = ty.clone();
            match ty {
                Ty::Error => {}
                Ty::Space(named) => {
                    let blame = Blame::new(codebook_span, Reason::CleanupCodebook);
                    self.require_space(Some(named), space, &blame);
                }
                other => {
                    let found = self.show(&other);
                    self.diagnostics.push(
                        Diagnostic::error(codes::TYPE_MISMATCH, "expected a space")
                            .with_primary(codebook_span, format!("this is `{found}`, not a space"))
                            .with_note(Reason::CleanupCodebook.context())
                            .with_help("name a `space` declaration, or drop the second operand"),
                    );
                }
            }
        }
        // Projection onto the codebook is what makes a value an atom again:
        // load collapses to one, the nesting counter resets, and the result is
        // clean by construction.
        Ty::Sym { space, role: None }
    }

    /// `broadcast(v, S)` — the explicit opt-in.
    ///
    /// GRAMMAR.md §7.3: elementwise operations require identical operand
    /// types, so the intent "combine these two anyway" needs somewhere to
    /// live. It lives here, as one keyword the reader cannot miss. The result
    /// is deliberately **noisy**: re-expressing a vector in a space with a
    /// different width or a different family is not information-preserving,
    /// and pretending otherwise would give back exactly the silence this whole
    /// feature exists to remove.
    fn check_broadcast(&mut self, args: &[ExprId], types: &[Ty]) -> Ty {
        let (Some(&target), Some(target_ty)) = (args.first(), types.first()) else {
            return Ty::Error;
        };
        let target_ty = target_ty.clone();
        if target_ty.is_error() {
            return Ty::Error;
        }
        let Some(vector) = target_ty.as_vector() else {
            let found = self.show(&target_ty);
            self.diagnostics.push(
                Diagnostic::error(codes::TYPE_MISMATCH, "`broadcast` operates on vectors")
                    .with_primary(
                        self.ast.exprs[target].span,
                        format!("this is `{found}`, not a vector"),
                    )
                    .with_note(
                        Reason::Operand {
                            op: "broadcast",
                            index: 0,
                        }
                        .context(),
                    ),
            );
            return Ty::Error;
        };
        let mut into = None;
        if let (Some(&arg), Some(ty)) = (args.get(1), types.get(1)) {
            let span = self.ast.exprs[arg].span;
            match ty {
                Ty::Error => {}
                Ty::Space(id) => into = Some(*id),
                other => {
                    let found = self.show(other);
                    self.diagnostics.push(
                        Diagnostic::error(codes::TYPE_MISMATCH, "expected a space")
                            .with_primary(span, format!("this is `{found}`, not a space"))
                            .with_note(
                                "`broadcast`'s second operand names the space to re-express the first one in",
                            )
                            .with_help("name a `space` declaration here"),
                    );
                }
            }
        }
        Ty::vector(VecTy {
            space: into.or(vector.space),
            load: vector.load,
            roles: vector.roles,
            clean: Some(false),
            depth: vector.depth,
        })
    }

    // -- the four properties, as checks --------------------------------------

    fn require(&mut self, actual: &Ty, expected: &Ty, blame: &Blame) {
        if actual.is_error() || expected.is_error() {
            return;
        }
        match expected {
            Ty::Sym { space, .. } => match actual {
                Ty::Sym {
                    space: actual_space,
                    ..
                } => {
                    let actual_space = *actual_space;
                    self.require_space(actual_space, *space, blame);
                }
                Ty::Vec(_) => {
                    // A vector is not an atom until it has been projected onto
                    // a codebook. Naming the operation that does that is more
                    // useful than saying the types differ.
                    let found = self.show(actual);
                    let want = self.show(expected);
                    let diag = self
                        .mismatch(blame, &want, &found)
                        .with_note(
                            "a bundled or unbound vector is not a codebook atom; only \
                             `cleanup` projects one back onto the codebook",
                        )
                        .with_help("wrap it in `cleanup(..)`");
                    self.diagnostics.push(diag);
                }
                _ => self.report_plain_mismatch(actual, expected, blame),
            },
            Ty::Vec(want) => {
                let want = (**want).clone();
                let Some(found) = actual.as_vector() else {
                    self.report_plain_mismatch(actual, expected, blame);
                    return;
                };
                self.require_space(found.space, want.space, blame);
                self.require_load(&found, &want, blame);
                self.require_roles(&found, &want, blame);
                self.require_clean(&found, &want, blame);
            }
            Ty::Fn { params, ret } => {
                let (params, ret) = (params.clone(), (**ret).clone());
                let Ty::Fn {
                    params: actual_params,
                    ret: actual_ret,
                } = actual.clone()
                else {
                    self.report_plain_mismatch(actual, expected, blame);
                    return;
                };
                if actual_params.len() != params.len() {
                    self.report_plain_mismatch(actual, expected, blame);
                    return;
                }
                for (a, b) in actual_params.iter().zip(&params) {
                    self.require(a, b, blame);
                }
                self.require(&actual_ret, &ret, blame);
            }
            Ty::Tuple(want) => {
                let want = want.clone();
                let Ty::Tuple(found) = actual.clone() else {
                    self.report_plain_mismatch(actual, expected, blame);
                    return;
                };
                if found.len() != want.len() {
                    self.report_plain_mismatch(actual, expected, blame);
                    return;
                }
                for (a, b) in found.iter().zip(&want) {
                    self.require(a, b, blame);
                }
            }
            Ty::List(want) => {
                let want = (**want).clone();
                match actual.clone() {
                    Ty::List(found) => self.require(&found, &want, blame),
                    _ => self.report_plain_mismatch(actual, expected, blame),
                }
            }
            _ => {
                if actual != expected {
                    self.report_plain_mismatch(actual, expected, blame);
                }
            }
        }
    }

    /// The **family**, **dimension** and **codebook** checks, in that order.
    ///
    /// The order is what makes the message right: two spaces that differ in
    /// family differ in what `bind` even computes, so reporting a dimension
    /// mismatch about them would be true and useless.
    fn require_space(&mut self, actual: Option<SpaceId>, expected: Option<SpaceId>, blame: &Blame) {
        let (Some(actual), Some(expected)) = (actual, expected) else {
            return;
        };
        if actual == expected {
            return;
        }
        self.report_space_mismatch(actual, expected, blame);
    }

    fn report_space_mismatch(&mut self, actual: SpaceId, expected: SpaceId, blame: &Blame) {
        let (Some(left), Some(right)) = (
            self.space_info(actual).cloned(),
            self.space_info(expected).cloned(),
        ) else {
            return;
        };
        let (mut diag, help) = match (left.family, right.family) {
            (Some(a), Some(b)) if a != b => family_mismatch(&left, &right, a, b, blame),
            _ => match left.dim.unify(&right.dim) {
                Err(residual) => dimension_mismatch(&left, &right, &residual, blame),
                Ok(()) => codebook_mismatch(&left, &right, blame),
            },
        };
        if let Some((span, message)) = &blame.secondary {
            diag = diag.with_secondary(*span, message.clone());
        }
        // The blame note goes before the help, so the reader learns *why* the
        // constraint existed before being told what to do about it.
        self.diagnostics
            .push(diag.with_note(blame.reason.context()).with_help(help));
    }

    fn require_load(&mut self, found: &VecTy, want: &VecTy, blame: &Blame) {
        if found.load.intersects(&want.load) {
            return;
        }
        let mut diag = Diagnostic::error(
            codes::LOAD_MISMATCH,
            format!(
                "this superposes {} items, but the type says {}",
                found.load, want.load
            ),
        )
        .with_primary(blame.span, format!("load here is {}", found.load));
        if let Some((span, message)) = &blame.secondary {
            diag = diag.with_secondary(*span, message.clone());
        }
        if let Some(space) = want.space.and_then(|s| self.space_info(s)) {
            diag = diag.with_note(space.capacity_provenance());
        }
        self.diagnostics.push(
            diag.with_note(blame.reason.context())
                .with_note(
                    "load is tracked as an interval, so an annotation only has to name a \
                     value the expression could actually have",
                )
                .with_help("change the annotation, or change how many items are bundled"),
        );
    }

    fn require_roles(&mut self, found: &VecTy, want: &VecTy, blame: &Blame) {
        if want.roles.open {
            return;
        }
        let missing = want.roles.missing_from(&found.roles);
        let extra = if found.roles.open {
            Vec::new()
        } else {
            found.roles.missing_from(&want.roles)
        };
        if missing.is_empty() && extra.is_empty() {
            return;
        }
        let carried = self.role_list(&found.roles);
        let mut diag = Diagnostic::error(
            codes::ROLE_NOT_BOUND,
            "this vector does not carry the roles its type says it does",
        )
        .with_primary(blame.span, format!("this carries {carried}"));
        if let Some((span, message)) = &blame.secondary {
            diag = diag.with_secondary(*span, message.clone());
        }
        if !missing.is_empty() {
            let names = self.name_list(&missing);
            diag = diag.with_note(format!("declared but never bound: {names}"));
        }
        if !extra.is_empty() {
            let names = self.name_list(&extra);
            diag = diag.with_note(format!("bound but not declared: {names}"));
        }
        self.diagnostics.push(
            diag.with_note(
                "a role schema is static: which roles are bound is a compile-time fact, even \
                 though the values bound to them are not",
            )
            .with_help("bind the missing roles, or widen the schema in the annotation"),
        );
    }

    fn require_clean(&mut self, found: &VecTy, want: &VecTy, blame: &Blame) {
        if want.clean != Some(true) || found.clean != Some(false) {
            return;
        }
        let mut diag = Diagnostic::error(
            codes::TYPE_MISMATCH,
            "this vector is noisy, and a clean one is wanted",
        )
        .with_primary(blame.span, "the residue of an `unbind`, never cleaned up");
        if let Some((span, message)) = &blame.secondary {
            diag = diag.with_secondary(*span, message.clone());
        }
        self.diagnostics.push(
            diag.with_note(
                "unbinding out of a superposition returns the target plus the crosstalk of \
                 everything else bundled with it",
            )
            .with_note(blame.reason.context())
            .with_help("project it onto the codebook with `cleanup(..)`"),
        );
    }

    // -- silent broadcasting -------------------------------------------------

    /// Which of the two shape properties makes these spaces different, if
    /// either does.
    ///
    /// Deliberately scoped to **dimension and family**. A space also fixes a
    /// codebook, and two spaces that agree on family and width but not on
    /// codebook are still an error — but not a *broadcast* error, because no
    /// tensor library has a notion of a codebook to paper over. That case
    /// keeps `RALY4003`. Superposition load and role schema are not shape
    /// either: `bundle` adds loads and unions role schemas by design, so
    /// requiring those to be identical would break the algebra rather than
    /// protect it. See GRAMMAR.md §7.3.
    fn broadcast_shape(&self, left: SpaceId, right: SpaceId) -> Option<BroadcastShape> {
        let (left, right) = (self.space_info(left)?, self.space_info(right)?);
        if let (Some(a), Some(b)) = (left.family, right.family) {
            if a != b {
                return Some(BroadcastShape::Family(a, b));
            }
        }
        match left.dim.unify(&right.dim) {
            Err(residual) => Some(BroadcastShape::Width(residual)),
            Ok(()) => None,
        }
    }

    /// The diagnostic this whole feature exists for.
    ///
    /// It names what would have happened silently somewhere else, because
    /// that is the part a reader cannot look up: the mistake in a tensor
    /// library is invisible at the line that makes it, and only surfaces as a
    /// loss curve that never comes down.
    fn report_silent_broadcast(
        &mut self,
        op: &'static str,
        op_span: Span,
        shape: BroadcastShape,
        left: (Span, SpaceId),
        right: (Span, SpaceId),
    ) {
        let (Some(a), Some(b)) = (
            self.space_info(left.1).cloned(),
            self.space_info(right.1).cloned(),
        ) else {
            return;
        };
        let names = Names {
            spaces: &self.spaces,
            defs: &self.resolved.defs,
        };
        let (shown_a, shown_b) = (names.describe_space(left.1), names.describe_space(right.1));
        let mut diag = Diagnostic::error(
            codes::SILENT_BROADCAST,
            format!(
                "`{op}` combines its operands position by position, and these two do not have the same type"
            ),
        )
        .with_primary(op_span, "both operands of this must have identical types")
        .with_secondary(left.0, format!("this one is `{shown_a}`, in `{}`", a.name))
        .with_secondary(right.0, format!("this one is `{shown_b}`, in `{}`", b.name));

        match &shape {
            BroadcastShape::Family(fa, fb) => {
                diag = diag
                    .with_note(format!(
                        "`{}` is {} and `{}` is {}",
                        a.name,
                        fa.describe(),
                        b.name,
                        fb.describe()
                    ))
                    .with_note(format!(
                        "a tensor library would not stop here: both sides are the same length, so it would add them position by position without a word and hand back a vector belonging to neither {} nor {}",
                        fa.name(),
                        fb.name()
                    ));
            }
            BroadcastShape::Width(residual) => {
                diag = diag
                    .with_note(format!(
                        "dimensions form an abelian group, and these do not cancel: the residual is {residual}"
                    ))
                    .with_note(silent_broadcast_note(&a, &b));
            }
        }
        self.diagnostics.push(
            diag.with_note(
                "Raly requires identical types here on purpose. Every property this message names is in the type, so the mistake is a compile error rather than a shape that happens to work",
            )
            .with_help(format!(
                "if combining them is genuinely what you meant, say so: `{op}(.., broadcast(<the second one>, {}))` re-expresses it in `{}`, and the result is `noisy`, because that reinterpretation throws information away",
                a.name, a.name
            ))
            .with_help("otherwise the two values belong in one space; change a declaration"),
        );
    }

    // -- capacity ------------------------------------------------------------

    fn check_capacity(&mut self, space: SpaceId, items: u32, span: Span, site: CapacitySite) {
        let Some(info) = self.space_info(space).cloned() else {
            return;
        };
        let Some(capacity_limit) = info.capacity else {
            return;
        };
        if items <= capacity_limit {
            return;
        }
        let needed = capacity::dimension_for(items);
        let power = capacity::round_up_pow2(needed);
        let basis = match info.capacity_basis {
            CapacityBasis::Effective => format!(
                " (from its measured effective dimension {}, not its nominal one)",
                info.capacity_dim.unwrap_or_default()
            ),
            CapacityBasis::Nominal => String::new(),
        };
        let power_hint = if power != needed {
            format!(", or {power} for a power of two")
        } else {
            String::new()
        };
        let (message, label) = match site {
            CapacitySite::Bundle => (
                format!("this bundles {items} items into a space that holds {capacity_limit}"),
                format!("{items} items superposed here"),
            ),
            CapacitySite::Annotation => (
                format!(
                    "this type declares a load of {items} in a space that holds {capacity_limit}"
                ),
                format!("a load of {items} declared here"),
            ),
        };
        self.diagnostics.push(
            Diagnostic::error(codes::CAPACITY_EXCEEDED, message)
                .with_primary(span, label)
                .with_secondary(
                    info.decl_span,
                    format!("`{}` holds {capacity_limit} items{basis}", info.name),
                )
                .with_note(info.capacity_provenance())
                .with_note(
                    "past capacity, cleanup returns the wrong atom and accuracy degrades towards \
                 chance without anything failing at run time",
                )
                .with_help(format!(
                    "superpose fewer items, or declare `{}` at dimension {needed}{power_hint}",
                    info.name
                )),
        );
    }

    fn report_nesting(&mut self, depth: u32, op_span: Span, inner: Span) {
        let message = format!("this is {depth} `unbind`s deep with no `cleanup` in between");
        let diag = if depth >= 3 {
            Diagnostic::error(codes::UNCLEANED_NESTING, message)
        } else {
            Diagnostic::warning(codes::UNCLEANED_NESTING, message)
        };
        self.diagnostics.push(
            diag.with_primary(op_span, "this unbind is nested")
                .with_secondary(
                    inner,
                    "and this is what it reads from, itself an unbind result",
                )
                .with_note(
                    "noise is not additive across levels of nesting, it is multiplicative in \
                     SNR: each unbind carries forward the residue of everything bundled at \
                     that level",
                )
                .with_note(
                    "measured usable depth without cleanup is about 2 at D=1000 (semantics \
                     §3), so depth 3 retrieves at close to chance",
                )
                .with_help("insert `|> cleanup(<space>)` between the unbinds"),
        );
    }

    fn report_role_not_bound(&mut self, role: DefId, row: &Row, span: Span, target: ExprId) {
        let name = self.resolved.def(role).name.clone();
        let carried = self.role_list(row);
        let declared_at = self.resolved.def(role).span;
        let mut diag = Diagnostic::error(
            codes::ROLE_NOT_BOUND,
            format!("`{name}` is not bound into this vector"),
        )
        .with_primary(span, "this role is not in the vector's schema")
        .with_secondary(
            self.ast.exprs[target].span,
            format!("this carries {carried}"),
        );
        if let Some(decl) = declared_at {
            diag = diag.with_secondary(decl, format!("`{name}` declared here"));
        }
        let help = if row.is_empty() {
            format!("bind it first: `bind({name}, <filler>)`")
        } else {
            format!("bind `{name}` first, or unbind one of {carried}")
        };
        self.diagnostics.push(
            diag.with_note(
                "unbinding a role that was never bound returns pure crosstalk, and `cleanup` \
                 will happily project that onto some arbitrary atom",
            )
            .with_help(help),
        );
    }

    fn report_non_constant_dimension(&mut self, expr: ExprId, name: &str) {
        self.diagnostics.push(
            Diagnostic::error(
                codes::NON_CONSTANT_DIMENSION,
                format!("the dimension of `{name}` is not a compile-time constant"),
            )
            .with_primary(self.ast.exprs[expr].span, "this does not fold to a number")
            .with_note(
                "capacity is derived from the dimension, so a dimension the compiler cannot \
                 evaluate leaves every bundle in this space unchecked",
            )
            .with_help("write a literal, or a top-level `let` of literals"),
        );
    }

    fn report_plain_mismatch(&mut self, actual: &Ty, expected: &Ty, blame: &Blame) {
        let found = self.show(actual);
        let want = self.show(expected);
        let diag = self.mismatch(blame, &want, &found);
        self.diagnostics.push(diag);
    }

    /// The common shape of a mismatch, returned so callers can add advice.
    fn mismatch(&self, blame: &Blame, want: &str, found: &str) -> Diagnostic {
        let mut diag = Diagnostic::error(codes::TYPE_MISMATCH, "mismatched types")
            .with_primary(blame.span, format!("expected `{want}`, found `{found}`"));
        if let Some((span, message)) = &blame.secondary {
            diag = diag.with_secondary(*span, message.clone());
        }
        diag.with_note(blame.reason.context())
    }

    // -- rendering helpers ---------------------------------------------------

    fn show(&self, ty: &Ty) -> String {
        Names {
            spaces: &self.spaces,
            defs: &self.resolved.defs,
        }
        .show(ty)
    }

    fn role_list(&self, row: &Row) -> String {
        if row.is_empty() {
            return if row.open {
                "no roles the compiler can see".to_string()
            } else {
                "no roles".to_string()
            };
        }
        let mut names = Vec::new();
        for (label, count) in row.labels() {
            for _ in 0..count {
                names.push(self.resolved.def(label).name.clone());
            }
        }
        if row.open {
            names.push("..".to_string());
        }
        format!("roles {{{}}}", names.join(", "))
    }

    fn name_list(&self, defs: &[DefId]) -> String {
        defs.iter()
            .map(|d| format!("`{}`", self.resolved.def(*d).name))
            .collect::<Vec<_>>()
            .join(", ")
    }
}

// -- diagnostics that need no checker state ----------------------------------

fn family_mismatch(
    left: &SpaceInfo,
    right: &SpaceInfo,
    a: Family,
    b: Family,
    blame: &Blame,
) -> (Diagnostic, &'static str) {
    let diag = Diagnostic::error(
        codes::FAMILY_MISMATCH,
        format!(
            "`{}` is a {} space and `{}` is a {} space",
            left.name,
            a.name(),
            right.name,
            b.name()
        ),
    )
    .with_primary(
        blame.span,
        format!("this is in `{}`, but `{}` is wanted", left.name, right.name),
    )
    .with_secondary(right.decl_span, format!("`{}` declared here", right.name))
    .with_note(format!("{} is {}", a.name(), a.describe()))
    .with_note(format!("{} is {}", b.name(), b.describe()));
    (
        diag,
        "families have different binding operations and different vector alphabets; there is \
         no conversion between them",
    )
}

fn dimension_mismatch(
    left: &SpaceInfo,
    right: &SpaceInfo,
    residual: &Dim,
    blame: &Blame,
) -> (Diagnostic, &'static str) {
    let family = left.family.map(|f| f.name()).unwrap_or("?");
    let mut diag = Diagnostic::error(
        codes::DIMENSION_MISMATCH,
        format!(
            "`{}` has dimension {} and `{}` has dimension {}",
            left.name, left.dim, right.name, right.dim
        ),
    )
    .with_primary(blame.span, format!("this is `{family}[{}]`", left.dim));
    diag = match right.dim_span {
        Some(span) => diag.with_secondary(span, format!("`{}` is this wide", right.name)),
        None => diag.with_secondary(right.decl_span, format!("`{}` declared here", right.name)),
    };
    let diag = diag.with_note(format!(
        "dimensions form an abelian group, and these do not cancel: the residual is {residual}"
    ));
    (
        diag,
        "bind, bundle and unbind are all elementwise; two widths cannot mix",
    )
}

fn codebook_mismatch(
    left: &SpaceInfo,
    right: &SpaceInfo,
    blame: &Blame,
) -> (Diagnostic, &'static str) {
    let diag = Diagnostic::error(
        codes::SPACE_MISMATCH,
        format!("`{}` and `{}` are different spaces", left.name, right.name),
    )
    .with_primary(blame.span, format!("this is in `{}`", left.name))
    .with_secondary(right.decl_span, format!("`{}` declared here", right.name))
    .with_note(
        "they agree on family and dimension, but a space also fixes the codebook, and atoms \
         of one codebook are noise to the other",
    );
    (
        diag,
        "use one space, or project across with an explicit `cleanup`",
    )
}

// -- small helpers -----------------------------------------------------------

/// A `VsaCall` with the arena borrow dropped.
#[derive(Clone, Debug)]
struct VsaSnapshot {
    op: VsaOp,
    op_span: Span,
    variant: Option<VsaVariant>,
    args: Vec<ExprId>,
}

impl VsaSnapshot {
    fn of(call: &VsaCall) -> VsaSnapshot {
        VsaSnapshot {
            op: call.op,
            op_span: call.op_span,
            variant: call.variant_kind,
            // Source order, because that is what diagnostics point at. The
            // commutative operations are order-insensitive by construction:
            // every rule below folds over the operands with an associative,
            // commutative combiner, so the canonical order would give the same
            // answer.
            args: call.args.clone(),
        }
    }
}

/// Which property makes two spaces different shapes, for `RALY4012`.
#[derive(Clone, Debug)]
enum BroadcastShape {
    /// Same width, different VSA family — the genuinely silent case: a tensor
    /// library has no notion of family and combines them without complaint.
    Family(Family, Family),
    /// Different widths, carrying the abelian-group residual.
    Width(Dim),
}

/// The `note:` that names what a tensor library would have done instead.
///
/// This is the sentence the feature exists for. PyTorch and NumPy broadcast:
/// a length-1 axis on either operand — which is what every `unsqueeze`, every
/// batch, head or beam dimension adds — turns a pair of mismatched widths into
/// an outer product instead of an error. Nothing warns, nothing fails, and the
/// first sign is a loss curve that never comes down.
fn silent_broadcast_note(left: &SpaceInfo, right: &SpaceInfo) -> String {
    match (left.dim.as_constant(), right.dim.as_constant()) {
        (Some(m), Some(n)) => format!(
            "a tensor library would not stop here: in NumPy or PyTorch, one length-1 axis on either side -- which is what every unsqueeze, batch, head or beam dimension adds -- makes ({m}, 1) and (1, {n}) broadcast to a matrix of shape ({m}, {n}), silently, and the first thing that looks wrong is a loss curve days later"
        ),
        _ => "a tensor library would not stop here: in NumPy or PyTorch, one length-1 axis on either side -- which is what every unsqueeze, batch, head or beam dimension adds -- makes two mismatched widths broadcast into an outer product instead of failing, silently, and the first thing that looks wrong is a loss curve days later"
            .to_string(),
    }
}

/// Where a capacity check fired, which decides how it reads.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum CapacitySite {
    /// A `bundle(..)` expression superposing more than the space holds.
    Bundle,
    /// A `load` qualifier over capacity, with no bundle in sight.
    Annotation,
}

/// The parts of a `TypeQual` the checker needs, without the arena borrow.
#[derive(Clone, Copy, Debug)]
enum QualInfo {
    Load { count: Option<ExprId>, span: Span },
    Roles { count: usize },
    Clean,
    Noisy,
    Other,
}

fn describe_quals(quals: &[TypeQual]) -> Vec<QualInfo> {
    quals
        .iter()
        .map(|q| match q {
            TypeQual::Load { count, span, .. } => QualInfo::Load {
                count: *count,
                span: *span,
            },
            TypeQual::Roles { names, .. } => QualInfo::Roles { count: names.len() },
            TypeQual::Clean(_) => QualInfo::Clean,
            TypeQual::Noisy(_) => QualInfo::Noisy,
            TypeQual::Error(_) => QualInfo::Other,
        })
        .collect()
}

fn plural(n: usize, noun: &str) -> String {
    if n == 1 {
        format!("{n} {noun}")
    } else {
        format!("{n} {noun}s")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plurals_read_correctly() {
        assert_eq!(plural(1, "argument"), "1 argument");
        assert_eq!(plural(3, "argument"), "3 arguments");
    }
}
