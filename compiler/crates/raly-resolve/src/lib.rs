//! Name resolution for Raly.
//!
//! `resolve(&Ast) -> Resolved` is a pure function of the tree: no ambient
//! mutable state, no interning into the AST, nothing written back. That is
//! decision 1 of `docs/compiler-architecture.md` — every phase a
//! `fn(&Db, Input) -> Output` — and it is what makes a later port to a query
//! engine mechanical rather than a rewrite.
//!
//! # It never fails
//!
//! Like the parser, this phase returns a value plus diagnostics, never a
//! `Result`. **Every reference resolves**: a name with no definition still
//! gets a [`DefId`], namely [`DefId::ERROR`], so the type checker can keep
//! walking and report everything else that is wrong in the same run. The error
//! binding is typed `Error`, which is compatible with everything and reports
//! nothing further — the cascade suppression that decision 5 asks for.
//!
//! # Scopes
//!
//! Two namespaces, `Value` and `Type`, because `Vec` the type constructor and
//! a hypothetical `Vec` the local are not the same name. A `space` goes into
//! *both*: it is a type (`Vec[Concepts]`) and it is also a value in the one
//! position that needs it (`cleanup(v, Concepts)` names a codebook to project
//! onto).
//!
//! Items are **hoisted**: every item in a scope is visible throughout it, so
//! functions may be mutually recursive and a `space` may be used above its
//! declaration. `let` bindings are **sequential**: a local is visible only
//! after its `let`, so `let x = x` refers to the outer `x`. Using a local
//! above its `let` is [`raly_diag::codes::USE_BEFORE_DEFINITION`] rather than
//! "unknown name", because the resolver can see the definition sitting below
//! and saying so is the whole difference between a useful message and a
//! useless one.
//!
//! Shadowing an outer *local* is allowed and silent. Shadowing a `role` or a
//! `space` is a warning: roles are codebook atoms, and a local that hides one
//! makes `bind(Subject, x)` silently mean something else.

#![deny(missing_debug_implementations)]

mod def;

pub use def::{Builtin, Def, DefId, DefKind, Family};

use std::collections::HashMap;

use raly_ast::{
    Ast, ExprId, ExprKind, Ident, ItemId, ItemKind, LetBinding, Stmt, StmtId, StmtKind, Symbol,
    TypeExprId, TypeExprKind, TypeQual,
};
use raly_diag::{codes, Diagnostic, Diagnostics, Span};

/// Which of the two namespaces a name lives in.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum Ns {
    /// Functions, parameters, `let` bindings, roles, and spaces.
    Value,
    /// Type aliases, spaces, and the builtin type constructors.
    Type,
}

/// Everything resolution learned about one file.
#[derive(Debug)]
pub struct Resolved {
    /// Index 0 is always the error binding.
    pub defs: Vec<Def>,
    /// `ExprKind::Path` node id -> what it names.
    pub expr_refs: HashMap<u32, DefId>,
    /// `TypeExprKind::Named` node id -> what its head path names.
    pub type_refs: HashMap<u32, DefId>,
    /// `(type node id, index within the schema)` -> the role named there.
    pub role_refs: HashMap<(u32, u32), DefId>,
    /// `space` item id -> the family it declared, when that family exists.
    pub families: HashMap<u32, Family>,
    /// Definitions keyed by the item that introduced them, so the checker can
    /// go from an `ItemId` back to its `DefId`.
    pub item_defs: HashMap<u32, DefId>,
    pub diagnostics: Diagnostics,
}

impl Resolved {
    pub fn def(&self, id: DefId) -> &Def {
        &self.defs[id.index()]
    }

    /// What an expression path refers to. Unresolved references are recorded
    /// as [`DefId::ERROR`], so this is `None` only for nodes that are not
    /// single-segment paths at all.
    pub fn expr_ref(&self, id: ExprId) -> Option<DefId> {
        self.expr_refs.get(&id.raw()).copied()
    }

    pub fn type_ref(&self, id: TypeExprId) -> Option<DefId> {
        self.type_refs.get(&id.raw()).copied()
    }

    pub fn role_ref(&self, ty: TypeExprId, index: usize) -> Option<DefId> {
        self.role_refs.get(&(ty.raw(), index as u32)).copied()
    }

    pub fn family_of(&self, item: ItemId) -> Option<Family> {
        self.families.get(&item.raw()).copied()
    }

    pub fn def_of_item(&self, item: ItemId) -> Option<DefId> {
        self.item_defs.get(&item.raw()).copied()
    }

    pub fn has_errors(&self) -> bool {
        self.diagnostics.has_errors()
    }
}

/// Resolve every name in `ast`.
///
/// Never panics, never bails out early, and always returns a total mapping for
/// the references it saw.
pub fn resolve(ast: &Ast) -> Resolved {
    let mut resolver = Resolver::new(ast);
    resolver.run();
    resolver.finish()
}

// -- the resolver ------------------------------------------------------------

#[derive(Debug)]
struct Scope {
    names: HashMap<(Ns, Symbol), DefId>,
    /// `let` names declared later in this scope, with the span of the `let`.
    /// Drained as the resolver walks past each one, so a lookup failure can
    /// tell "not defined" from "not defined *yet*".
    pending: HashMap<Symbol, Span>,
}

impl Scope {
    fn new() -> Self {
        Scope {
            names: HashMap::new(),
            pending: HashMap::new(),
        }
    }
}

#[derive(Debug)]
struct Resolver<'a> {
    ast: &'a Ast,
    defs: Vec<Def>,
    scopes: Vec<Scope>,
    expr_refs: HashMap<u32, DefId>,
    type_refs: HashMap<u32, DefId>,
    role_refs: HashMap<(u32, u32), DefId>,
    families: HashMap<u32, Family>,
    item_defs: HashMap<u32, DefId>,
    diagnostics: Diagnostics,
}

impl<'a> Resolver<'a> {
    fn new(ast: &'a Ast) -> Self {
        Resolver {
            ast,
            defs: vec![Def {
                name: "<error>".to_string(),
                span: None,
                kind: DefKind::Error,
            }],
            scopes: vec![Scope::new()],
            expr_refs: HashMap::new(),
            type_refs: HashMap::new(),
            role_refs: HashMap::new(),
            families: HashMap::new(),
            item_defs: HashMap::new(),
            diagnostics: Diagnostics::new(),
        }
    }

    fn finish(mut self) -> Resolved {
        self.diagnostics.sort_by_position();
        Resolved {
            defs: self.defs,
            expr_refs: self.expr_refs,
            type_refs: self.type_refs,
            role_refs: self.role_refs,
            families: self.families,
            item_defs: self.item_defs,
            diagnostics: self.diagnostics,
        }
    }

    fn run(&mut self) {
        let root = self.ast.root.clone();
        self.declare_items(&root);
        for &item in &root {
            self.resolve_item_body(item);
        }
    }

    // -- scope plumbing ------------------------------------------------------

    fn push_scope(&mut self) {
        self.scopes.push(Scope::new());
    }

    fn pop_scope(&mut self) {
        self.scopes.pop();
    }

    fn alloc(&mut self, name: &str, span: Span, kind: DefKind) -> DefId {
        let id = DefId(self.defs.len() as u32);
        self.defs.push(Def {
            name: name.to_string(),
            span: Some(span),
            kind,
        });
        id
    }

    /// Bind `sym` in the innermost scope, reporting duplicates and shadowing.
    fn bind(&mut self, ns: Ns, sym: Symbol, span: Span, def: DefId) {
        let key = (ns, sym);
        let existing = self.scopes.last().and_then(|s| s.names.get(&key).copied());
        if let Some(previous) = existing {
            self.report_duplicate(previous, span, def);
            return;
        }
        if let Some(outer) = self.lookup(ns, sym) {
            self.report_shadowing(outer, span, def);
        }
        if let Some(scope) = self.scopes.last_mut() {
            scope.names.insert(key, def);
        }
    }

    fn lookup(&self, ns: Ns, sym: Symbol) -> Option<DefId> {
        self.scopes
            .iter()
            .rev()
            .find_map(|s| s.names.get(&(ns, sym)).copied())
    }

    fn pending(&self, sym: Symbol) -> Option<Span> {
        self.scopes
            .iter()
            .rev()
            .find_map(|s| s.pending.get(&sym).copied())
    }

    // -- declarations --------------------------------------------------------

    /// Hoist every item of one scope, so order does not matter between them.
    fn declare_items(&mut self, items: &[ItemId]) {
        for &item in items {
            self.declare_item(item);
        }
    }

    fn declare_item(&mut self, item: ItemId) {
        let node = &self.ast.items[item];
        if node.origin.is_recovered() {
            return;
        }
        match &node.kind {
            ItemKind::Space(space) => {
                let name = space.name;
                let def = self.alloc(self.ast.text(name), name.span, DefKind::Space(item));
                self.item_defs.insert(item.raw(), def);
                self.bind(Ns::Type, name.symbol, name.span, def);
                self.bind(Ns::Value, name.symbol, name.span, def);
                self.resolve_family(item);
            }
            ItemKind::Role(role) => {
                // The space is resolved once, before the names, so that every
                // role of one declaration shares the same answer.
                let space_ident = role.space;
                let names = role.names.clone();
                let space = space_ident.map(|s| self.resolve_role_space(s));
                for name in names {
                    let def = self.alloc(
                        self.ast.text(name),
                        name.span,
                        DefKind::Role { item, space },
                    );
                    self.item_defs.entry(item.raw()).or_insert(def);
                    self.bind(Ns::Value, name.symbol, name.span, def);
                }
            }
            ItemKind::TypeAlias(alias) => {
                let name = alias.name;
                let def = self.alloc(self.ast.text(name), name.span, DefKind::TypeAlias(item));
                self.item_defs.insert(item.raw(), def);
                self.bind(Ns::Type, name.symbol, name.span, def);
            }
            ItemKind::Fn(f) => {
                let name = f.name;
                let def = self.alloc(self.ast.text(name), name.span, DefKind::Fn(item));
                self.item_defs.insert(item.raw(), def);
                self.bind(Ns::Value, name.symbol, name.span, def);
            }
            ItemKind::Let(binding) => {
                let name = binding.name;
                let def = self.alloc(
                    self.ast.text(name),
                    name.span,
                    DefKind::Let { local: false },
                );
                self.item_defs.insert(item.raw(), def);
                self.bind(Ns::Value, name.symbol, name.span, def);
            }
            ItemKind::Import(_) | ItemKind::Error => {}
        }
    }

    /// Resolve the `in <Space>` of a `role` declaration.
    fn resolve_role_space(&mut self, ident: Ident) -> DefId {
        let def = self.lookup_type_or_error(ident.symbol, ident.span);
        if matches!(
            self.defs[def.index()].kind,
            DefKind::Space(_) | DefKind::Error
        ) {
            return def;
        }
        let kind = self.defs[def.index()].kind.describe();
        let decl = self.defs[def.index()].span;
        let mut diag = Diagnostic::error(
            codes::ROLE_NOT_IN_SPACE,
            format!("`{}` is not a space", self.ast.text(ident)),
        )
        .with_primary(
            ident.span,
            format!("a role must be declared in a space, but this is {kind}"),
        );
        if let Some(decl) = decl {
            diag = diag.with_secondary(decl, "declared here");
        }
        self.diagnostics.push(diag.with_note(
            "a role is an atom drawn from a space's codebook, so the space fixes its \
             family, dimension and provenance",
        ));
        DefId::ERROR
    }

    fn resolve_family(&mut self, item: ItemId) {
        let ItemKind::Space(space) = &self.ast.items[item].kind else {
            return;
        };
        let Some(family) = space.family else { return };
        let text = self.ast.text(family);
        match Family::from_name(text) {
            Some(f) => {
                self.families.insert(item.raw(), f);
            }
            None => {
                let known: Vec<&str> = Family::ALL.iter().map(|f| f.name()).collect();
                let mut diag = Diagnostic::error(
                    codes::UNKNOWN_FAMILY,
                    format!("`{text}` is not a VSA family"),
                )
                .with_primary(family.span, "no family by this name")
                .with_note(format!("the families Raly knows are {}", known.join(", ")));
                diag = match closest(text, &known) {
                    Some(best) => diag.with_help(format!("did you mean `{best}`?")),
                    None => diag.with_help(
                        "a space's family fixes what `bind` and `bundle` compute, so it cannot \
                         be inferred",
                    ),
                };
                self.diagnostics.push(diag);
            }
        }
    }

    // -- bodies --------------------------------------------------------------

    fn resolve_item_body(&mut self, item: ItemId) {
        let node = &self.ast.items[item];
        if node.origin.is_recovered() {
            return;
        }
        match &node.kind {
            ItemKind::Space(space) => {
                // Only the dimension is resolved. GRAMMAR.md §3 makes `where`
                // an *extension point* carrying attributes whose meaning is
                // not fixed yet, so `codebook = fixed` names a mode, not a
                // binding; resolving it would invent an error the language
                // does not have.
                if let Some(dim) = space.dim {
                    self.resolve_expr(dim);
                }
            }
            ItemKind::TypeAlias(alias) => {
                if let Some(ty) = alias.ty {
                    self.resolve_type(ty);
                }
            }
            ItemKind::Let(binding) => {
                let (ty, init) = (binding.ty, binding.init);
                if let Some(ty) = ty {
                    self.resolve_type(ty);
                }
                if let Some(init) = init {
                    self.resolve_expr(init);
                }
            }
            ItemKind::Fn(f) => {
                let params: Vec<(usize, Ident, Option<TypeExprId>)> = f
                    .params
                    .iter()
                    .enumerate()
                    .map(|(i, p)| (i, p.name, p.ty))
                    .collect();
                let ret = f.return_type;
                let body = f.body;
                self.push_scope();
                for (index, name, ty) in params {
                    if let Some(ty) = ty {
                        self.resolve_type(ty);
                    }
                    let def = self.alloc(
                        self.ast.text(name),
                        name.span,
                        DefKind::Param { item, index },
                    );
                    self.bind(Ns::Value, name.symbol, name.span, def);
                }
                if let Some(ret) = ret {
                    self.resolve_type(ret);
                }
                if let Some(body) = body {
                    self.resolve_expr(body);
                }
                self.pop_scope();
            }
            ItemKind::Import(_) | ItemKind::Role(_) | ItemKind::Error => {}
        }
    }

    fn resolve_local_let(&mut self, binding: &LetBinding) {
        let (ty, init, name) = (binding.ty, binding.init, binding.name);
        if let Some(ty) = ty {
            self.resolve_type(ty);
        }
        if let Some(init) = init {
            self.resolve_expr(init);
        }
        if let Some(scope) = self.scopes.last_mut() {
            scope.pending.remove(&name.symbol);
        }
        let def = self.alloc(self.ast.text(name), name.span, DefKind::Let { local: true });
        self.bind(Ns::Value, name.symbol, name.span, def);
    }

    fn resolve_block(&mut self, stmts: &[StmtId], tail: Option<ExprId>) {
        self.push_scope();
        // Items are visible throughout the block; locals are not.
        let items: Vec<ItemId> = stmts
            .iter()
            .filter_map(|&s| match &self.ast.stmts[s].kind {
                StmtKind::Item(item) => Some(*item),
                _ => None,
            })
            .collect();
        self.declare_items(&items);
        let lets: Vec<(Symbol, Span)> = stmts
            .iter()
            .filter_map(|&s| match &self.ast.stmts[s].kind {
                StmtKind::Let(binding) => Some((binding.name.symbol, self.ast.stmts[s].span)),
                _ => None,
            })
            .collect();
        if let Some(scope) = self.scopes.last_mut() {
            for (sym, span) in lets {
                scope.pending.entry(sym).or_insert(span);
            }
        }
        for &s in stmts {
            self.resolve_stmt(s);
        }
        if let Some(tail) = tail {
            self.resolve_expr(tail);
        }
        self.pop_scope();
    }

    fn resolve_stmt(&mut self, id: StmtId) {
        let stmt: &Stmt = &self.ast.stmts[id];
        match &stmt.kind {
            StmtKind::Let(binding) => {
                // Cloned out of the arena so the borrow ends before recursing.
                let binding = LetBinding {
                    mutable: binding.mutable,
                    name: binding.name,
                    ty: binding.ty,
                    init: binding.init,
                };
                self.resolve_local_let(&binding);
            }
            StmtKind::Return(Some(expr)) => self.resolve_expr(*expr),
            StmtKind::Return(None) => {}
            StmtKind::Expr(expr) => self.resolve_expr(*expr),
            StmtKind::Item(item) => self.resolve_item_body(*item),
            StmtKind::Error => {}
        }
    }

    fn resolve_expr(&mut self, id: ExprId) {
        let expr = &self.ast.exprs[id];
        let recovered = expr.origin.is_recovered();
        match &expr.kind {
            ExprKind::Path(segments) => {
                if recovered {
                    return;
                }
                if segments.len() == 1 {
                    let name = segments[0];
                    let def = self.lookup_value_or_error(name.symbol, name.span);
                    self.expr_refs.insert(id.raw(), def);
                } else if let (Some(first), Some(last)) = (segments.first(), segments.last()) {
                    let path = segments
                        .iter()
                        .map(|segment| self.ast.text(*segment))
                        .collect::<Vec<_>>()
                        .join("::");
                    self.diagnostics.push(
                        Diagnostic::error(
                            codes::UNRESOLVED_NAME,
                            format!("qualified path `{path}` is not supported yet"),
                        )
                        .with_primary(
                            first.span.merge(last.span),
                            "qualified path cannot be resolved",
                        )
                        .with_help("use a name in the current scope until modules are implemented"),
                    );
                    self.expr_refs.insert(id.raw(), DefId::ERROR);
                }
            }
            ExprKind::Group(inner) => {
                let inner = *inner;
                self.resolve_expr(inner);
            }
            ExprKind::Unary { operand, .. } => {
                let operand = *operand;
                self.resolve_expr(operand);
            }
            ExprKind::Binary { lhs, rhs, .. } => {
                let (lhs, rhs) = (*lhs, *rhs);
                self.resolve_expr(lhs);
                self.resolve_expr(rhs);
            }
            ExprKind::Pipeline { value, stage, .. } => {
                let (value, stage) = (*value, *stage);
                self.resolve_expr(value);
                self.resolve_expr(stage);
            }
            ExprKind::Call { callee, args } => {
                let (callee, args) = (*callee, args.clone());
                self.resolve_expr(callee);
                for arg in args {
                    self.resolve_expr(arg);
                }
            }
            ExprKind::Field { base, .. } => {
                let base = *base;
                self.resolve_expr(base);
            }
            ExprKind::Vsa(call) => {
                for arg in call.args.clone() {
                    self.resolve_expr(arg);
                }
            }
            ExprKind::List(items) | ExprKind::Tuple(items) => {
                for item in items.clone() {
                    self.resolve_expr(item);
                }
            }
            ExprKind::Block { stmts, tail } => {
                let (stmts, tail) = (stmts.clone(), *tail);
                self.resolve_block(&stmts, tail);
            }
            ExprKind::If {
                cond,
                then_block,
                else_branch,
            } => {
                let (cond, then_block, else_branch) = (*cond, *then_block, *else_branch);
                self.resolve_expr(cond);
                self.resolve_expr(then_block);
                if let Some(branch) = else_branch {
                    self.resolve_expr(branch);
                }
            }
            ExprKind::Literal(_) | ExprKind::Error => {}
        }
    }

    fn resolve_type(&mut self, id: TypeExprId) {
        let ty = &self.ast.types[id];
        let recovered = ty.origin.is_recovered();
        match &ty.kind {
            TypeExprKind::Named { path, args, quals } => {
                let head = if path.len() == 1 {
                    path.first().copied()
                } else {
                    None
                };
                let args = args.clone();
                let counts: Vec<ExprId> = quals
                    .iter()
                    .filter_map(|q| match q {
                        TypeQual::Load { count, .. } => *count,
                        _ => None,
                    })
                    .collect();
                let roles: Vec<Ident> = quals
                    .iter()
                    .flat_map(|q| match q {
                        TypeQual::Roles { names, .. } => names.clone(),
                        _ => Vec::new(),
                    })
                    .collect();
                if recovered {
                    return;
                }
                if let Some(head) = head {
                    let def = self.lookup_type_or_error(head.symbol, head.span);
                    self.type_refs.insert(id.raw(), def);
                } else if let (Some(first), Some(last)) = (path.first(), path.last()) {
                    let path = path
                        .iter()
                        .map(|segment| self.ast.text(*segment))
                        .collect::<Vec<_>>()
                        .join("::");
                    self.diagnostics.push(
                        Diagnostic::error(
                            codes::UNRESOLVED_TYPE,
                            format!("qualified type path `{path}` is not supported yet"),
                        )
                        .with_primary(
                            first.span.merge(last.span),
                            "qualified type path cannot be resolved",
                        )
                        .with_help(
                            "use a type name in the current scope until modules are implemented",
                        ),
                    );
                    self.type_refs.insert(id.raw(), DefId::ERROR);
                }
                for arg in args {
                    self.resolve_type(arg);
                }
                for count in counts {
                    self.resolve_expr(count);
                }
                for (index, name) in roles.into_iter().enumerate() {
                    let def = self.lookup_value_or_error(name.symbol, name.span);
                    if !matches!(
                        self.defs[def.index()].kind,
                        DefKind::Role { .. } | DefKind::Error
                    ) {
                        let kind = self.defs[def.index()].kind.describe();
                        self.diagnostics.push(
                            Diagnostic::error(
                                codes::NOT_A_ROLE,
                                format!("`{}` is not a role", self.ast.text(name)),
                            )
                            .with_primary(
                                name.span,
                                format!("a role schema may only list roles; this is {kind}"),
                            )
                            .with_help("declare it with `role <name> in <space>`"),
                        );
                    }
                    self.role_refs.insert((id.raw(), index as u32), def);
                }
            }
            TypeExprKind::Fn { params, ret } => {
                let (params, ret) = (params.clone(), *ret);
                for param in params {
                    self.resolve_type(param);
                }
                if let Some(ret) = ret {
                    self.resolve_type(ret);
                }
            }
            TypeExprKind::Tuple(elems) => {
                for elem in elems.clone() {
                    self.resolve_type(elem);
                }
            }
            TypeExprKind::Error => {}
        }
    }

    // -- lookups and their diagnostics ---------------------------------------

    fn lookup_value_or_error(&mut self, sym: Symbol, span: Span) -> DefId {
        if let Some(def) = self.lookup(Ns::Value, sym) {
            return def;
        }
        let text = self.ast.names.resolve(sym);
        if let Some(later) = self.pending(sym) {
            self.diagnostics.push(
                Diagnostic::error(
                    codes::USE_BEFORE_DEFINITION,
                    format!("`{text}` is used before it is defined"),
                )
                .with_primary(span, "used here")
                .with_secondary(later, "but defined here, further down")
                .with_note(
                    "a `let` comes into scope after its own statement, so that `let x = x` \
                     can refer to an outer `x`",
                )
                .with_help("move the `let` above this use"),
            );
            return DefId::ERROR;
        }
        self.report_unresolved(codes::UNRESOLVED_NAME, "name", text, span, Ns::Value);
        DefId::ERROR
    }

    fn lookup_type_or_error(&mut self, sym: Symbol, span: Span) -> DefId {
        if let Some(def) = self.lookup(Ns::Type, sym) {
            return def;
        }
        let text = self.ast.names.resolve(sym);
        if let Some(builtin) = Builtin::from_name(text) {
            let id = DefId(self.defs.len() as u32);
            self.defs.push(Def {
                name: text.to_string(),
                span: None,
                kind: DefKind::Builtin(builtin),
            });
            return id;
        }
        self.report_unresolved(codes::UNRESOLVED_TYPE, "type", text, span, Ns::Type);
        DefId::ERROR
    }

    fn report_unresolved(
        &mut self,
        code: raly_diag::Code,
        what: &str,
        text: &str,
        span: Span,
        ns: Ns,
    ) {
        let mut candidates: Vec<String> = Vec::new();
        for scope in &self.scopes {
            for &(scope_ns, sym) in scope.names.keys() {
                if scope_ns == ns {
                    candidates.push(self.ast.names.resolve(sym).to_string());
                }
            }
        }
        if ns == Ns::Type {
            candidates.extend(Builtin::ALL.iter().map(|b| b.name().to_string()));
        }
        candidates.sort();
        let borrowed: Vec<&str> = candidates.iter().map(|s| s.as_str()).collect();
        let mut diag =
            Diagnostic::error(code, format!("cannot find {what} `{text}` in this scope"))
                .with_primary(span, "not found in this scope");
        diag = match closest(text, &borrowed) {
            Some(best) => diag.with_help(format!("did you mean `{best}`?")),
            None if ns == Ns::Type => diag.with_help(
                "declare it with `space <name> = <FAMILY>[<dim>]`, or `type <name> = ...`",
            ),
            None => diag.with_help("declare it with `let`, `fn` or `role`"),
        };
        self.diagnostics.push(diag);
    }

    fn report_duplicate(&mut self, previous: DefId, span: Span, def: DefId) {
        let name = self.defs[def.index()].name.clone();
        let kind = self.defs[def.index()].kind.describe();
        let previous_kind = self.defs[previous.index()].kind.describe();
        let mut diag = Diagnostic::error(
            codes::DUPLICATE_DEFINITION,
            format!("`{name}` is defined twice in this scope"),
        )
        .with_primary(span, format!("redefined here as {kind}"));
        if let Some(first) = self.defs[previous.index()].span {
            diag = diag.with_secondary(first, format!("first defined here as {previous_kind}"));
        }
        self.diagnostics.push(
            diag.with_note("two definitions of one name in one scope leave every use ambiguous")
                .with_help("rename one of them"),
        );
    }

    fn report_shadowing(&mut self, outer: DefId, span: Span, def: DefId) {
        let outer_kind = self.defs[outer.index()].kind;
        if !matches!(outer_kind, DefKind::Role { .. } | DefKind::Space(_)) {
            return;
        }
        let name = self.defs[def.index()].name.clone();
        let noun = outer_kind.describe();
        let mut diag = Diagnostic::warning(
            codes::SHADOWS_DECLARATION,
            format!("`{name}` shadows {noun}"),
        )
        .with_primary(span, format!("this binding hides {noun} of the same name"));
        if let Some(first) = self.defs[outer.index()].span {
            diag = diag.with_secondary(first, "declared here");
        }
        self.diagnostics.push(
            diag.with_note(
                "a role is a codebook atom, so hiding one silently changes what every `bind` \
                 and `unbind` naming it computes",
            )
            .with_help("rename the local binding"),
        );
    }
}

/// The closest candidate within a small edit distance, if there is one.
///
/// The threshold scales with the length of what the user typed: one edit for
/// short names, up to three for long ones. A suggestion that is wrong is worse
/// than no suggestion, so this errs towards silence.
fn closest<'b>(needle: &str, candidates: &[&'b str]) -> Option<&'b str> {
    let limit = match needle.chars().count() {
        0..=3 => 1,
        4..=8 => 2,
        _ => 3,
    };
    let mut best: Option<(usize, &'b str)> = None;
    for &candidate in candidates {
        if candidate == needle {
            continue;
        }
        let distance = edit_distance(needle, candidate);
        if distance <= limit && best.map(|(d, _)| distance < d).unwrap_or(true) {
            best = Some((distance, candidate));
        }
    }
    best.map(|(_, candidate)| candidate)
}

/// Levenshtein distance, case-insensitively, over `char`s.
fn edit_distance(a: &str, b: &str) -> usize {
    let a: Vec<char> = a.to_lowercase().chars().collect();
    let b: Vec<char> = b.to_lowercase().chars().collect();
    let mut previous: Vec<usize> = (0..=b.len()).collect();
    let mut current = vec![0usize; b.len() + 1];
    for (i, &ca) in a.iter().enumerate() {
        current[0] = i + 1;
        for (j, &cb) in b.iter().enumerate() {
            let cost = usize::from(ca != cb);
            current[j + 1] = (previous[j] + cost)
                .min(previous[j + 1] + 1)
                .min(current[j] + 1);
        }
        std::mem::swap(&mut previous, &mut current);
    }
    previous[b.len()]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn edit_distance_basics() {
        assert_eq!(edit_distance("", ""), 0);
        assert_eq!(edit_distance("abc", "abc"), 0);
        assert_eq!(edit_distance("Subject", "subjekt"), 1);
        assert_eq!(edit_distance("kitten", "sitting"), 3);
    }

    #[test]
    fn closest_prefers_near_misses_and_stays_silent_otherwise() {
        assert_eq!(closest("Subjct", &["Subject", "Verb"]), Some("Subject"));
        assert_eq!(closest("zzzzzz", &["Subject", "Verb"]), None);
    }

    #[test]
    fn families_round_trip() {
        for family in Family::ALL {
            assert_eq!(Family::from_name(family.name()), Some(*family));
        }
        assert_eq!(Family::from_name("MAPP"), None);
    }
}
