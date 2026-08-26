//! A generic, non-consuming visitor.
//!
//! Every method has a default that walks children, so an implementor overrides
//! only what it cares about and calls the matching `walk_*` free function to
//! continue downwards (or does not, to prune the subtree).
//!
//! ```
//! use raly_ast::{visit, Ast, ExprId, Visitor};
//!
//! /// Counts every expression node reachable from the root.
//! struct CountExprs(usize);
//!
//! impl Visitor for CountExprs {
//!     fn visit_expr(&mut self, ast: &Ast, id: ExprId) {
//!         self.0 += 1;
//!         visit::walk_expr(self, ast, id);
//!     }
//! }
//! ```
//!
//! Adding an [`crate::ExprKind`] variant means adding a match arm in the
//! matching `walk_*` function and nothing else; every existing implementor
//! keeps compiling and automatically traverses the new nodes.
//!
//! Note that [`walk_expr`] walks a VSA call's operands in **source** order.
//! The canonical order is a property of the node
//! ([`crate::VsaCall::operands`]) and is not what a syntactic traversal
//! should impose on a consumer that is, say, rendering the source back out.

use crate::node::{
    Ast, Attr, Expr, ExprId, ExprKind, FnDef, Ident, ImportDecl, Item, ItemId, ItemKind,
    LetBinding, Literal, Param, RoleDecl, SpaceDecl, Stmt, StmtId, StmtKind, TypeAlias, TypeExpr,
    TypeExprId, TypeExprKind, TypeQual, VsaCall,
};

/// Read-only traversal of an [`Ast`].
pub trait Visitor: Sized {
    fn visit_ast(&mut self, ast: &Ast) {
        walk_ast(self, ast);
    }
    fn visit_item(&mut self, ast: &Ast, id: ItemId) {
        walk_item(self, ast, id);
    }
    fn visit_import(&mut self, ast: &Ast, decl: &ImportDecl) {
        walk_import(self, ast, decl);
    }
    fn visit_space(&mut self, ast: &Ast, decl: &SpaceDecl) {
        walk_space(self, ast, decl);
    }
    fn visit_role(&mut self, ast: &Ast, decl: &RoleDecl) {
        walk_role(self, ast, decl);
    }
    fn visit_type_alias(&mut self, ast: &Ast, alias: &TypeAlias) {
        walk_type_alias(self, ast, alias);
    }
    fn visit_fn_def(&mut self, ast: &Ast, def: &FnDef) {
        walk_fn_def(self, ast, def);
    }
    fn visit_param(&mut self, ast: &Ast, param: &Param) {
        walk_param(self, ast, param);
    }
    fn visit_attr(&mut self, ast: &Ast, attr: &Attr) {
        walk_attr(self, ast, attr);
    }
    fn visit_let(&mut self, ast: &Ast, binding: &LetBinding) {
        walk_let(self, ast, binding);
    }
    fn visit_stmt(&mut self, ast: &Ast, id: StmtId) {
        walk_stmt(self, ast, id);
    }
    fn visit_expr(&mut self, ast: &Ast, id: ExprId) {
        walk_expr(self, ast, id);
    }
    fn visit_vsa(&mut self, ast: &Ast, call: &VsaCall) {
        walk_vsa(self, ast, call);
    }
    fn visit_type(&mut self, ast: &Ast, id: TypeExprId) {
        walk_type(self, ast, id);
    }
    fn visit_type_qual(&mut self, ast: &Ast, qual: &TypeQual) {
        walk_type_qual(self, ast, qual);
    }
    /// Leaves. Default is to do nothing.
    fn visit_ident(&mut self, _ast: &Ast, _ident: &Ident) {}
    fn visit_literal(&mut self, _ast: &Ast, _literal: &Literal) {}
}

pub fn walk_ast<V: Visitor>(v: &mut V, ast: &Ast) {
    for &item in &ast.root {
        v.visit_item(ast, item);
    }
}

pub fn walk_item<V: Visitor>(v: &mut V, ast: &Ast, id: ItemId) {
    let Item { kind, .. } = &ast.items[id];
    match kind {
        ItemKind::Import(decl) => v.visit_import(ast, decl),
        ItemKind::Space(decl) => v.visit_space(ast, decl),
        ItemKind::Role(decl) => v.visit_role(ast, decl),
        ItemKind::TypeAlias(alias) => v.visit_type_alias(ast, alias),
        ItemKind::Fn(def) => v.visit_fn_def(ast, def),
        ItemKind::Let(binding) => v.visit_let(ast, binding),
        ItemKind::Error => {}
    }
}

pub fn walk_import<V: Visitor>(v: &mut V, ast: &Ast, decl: &ImportDecl) {
    for segment in &decl.path {
        v.visit_ident(ast, segment);
    }
}

pub fn walk_space<V: Visitor>(v: &mut V, ast: &Ast, decl: &SpaceDecl) {
    v.visit_ident(ast, &decl.name);
    if let Some(family) = &decl.family {
        v.visit_ident(ast, family);
    }
    if let Some(dim) = decl.dim {
        v.visit_expr(ast, dim);
    }
    for attr in &decl.attrs {
        v.visit_attr(ast, attr);
    }
}

pub fn walk_role<V: Visitor>(v: &mut V, ast: &Ast, decl: &RoleDecl) {
    for name in &decl.names {
        v.visit_ident(ast, name);
    }
    if let Some(space) = &decl.space {
        v.visit_ident(ast, space);
    }
}

pub fn walk_type_alias<V: Visitor>(v: &mut V, ast: &Ast, alias: &TypeAlias) {
    v.visit_ident(ast, &alias.name);
    if let Some(ty) = alias.ty {
        v.visit_type(ast, ty);
    }
}

pub fn walk_fn_def<V: Visitor>(v: &mut V, ast: &Ast, def: &FnDef) {
    v.visit_ident(ast, &def.name);
    for param in &def.params {
        v.visit_param(ast, param);
    }
    if let Some(ty) = def.return_type {
        v.visit_type(ast, ty);
    }
    for attr in &def.attrs {
        v.visit_attr(ast, attr);
    }
    if let Some(body) = def.body {
        v.visit_expr(ast, body);
    }
}

pub fn walk_param<V: Visitor>(v: &mut V, ast: &Ast, param: &Param) {
    v.visit_ident(ast, &param.name);
    if let Some(ty) = param.ty {
        v.visit_type(ast, ty);
    }
}

pub fn walk_attr<V: Visitor>(v: &mut V, ast: &Ast, attr: &Attr) {
    v.visit_ident(ast, &attr.name);
    if let Some(value) = attr.value {
        v.visit_expr(ast, value);
    }
}

pub fn walk_let<V: Visitor>(v: &mut V, ast: &Ast, binding: &LetBinding) {
    v.visit_ident(ast, &binding.name);
    if let Some(ty) = binding.ty {
        v.visit_type(ast, ty);
    }
    if let Some(init) = binding.init {
        v.visit_expr(ast, init);
    }
}

pub fn walk_stmt<V: Visitor>(v: &mut V, ast: &Ast, id: StmtId) {
    let Stmt { kind, .. } = &ast.stmts[id];
    match kind {
        StmtKind::Let(binding) => v.visit_let(ast, binding),
        StmtKind::Return(value) => {
            if let Some(value) = value {
                v.visit_expr(ast, *value);
            }
        }
        StmtKind::Expr(expr) => v.visit_expr(ast, *expr),
        StmtKind::Item(item) => v.visit_item(ast, *item),
        StmtKind::Error => {}
    }
}

pub fn walk_expr<V: Visitor>(v: &mut V, ast: &Ast, id: ExprId) {
    let Expr { kind, .. } = &ast.exprs[id];
    match kind {
        ExprKind::Literal(lit) => v.visit_literal(ast, lit),
        ExprKind::Path(segments) => {
            for segment in segments {
                v.visit_ident(ast, segment);
            }
        }
        ExprKind::Group(inner) => v.visit_expr(ast, *inner),
        ExprKind::Unary { operand, .. } => v.visit_expr(ast, *operand),
        ExprKind::Binary { lhs, rhs, .. } => {
            v.visit_expr(ast, *lhs);
            v.visit_expr(ast, *rhs);
        }
        ExprKind::Pipeline { value, stage, .. } => {
            v.visit_expr(ast, *value);
            v.visit_expr(ast, *stage);
        }
        ExprKind::Call { callee, args } => {
            v.visit_expr(ast, *callee);
            for &arg in args {
                v.visit_expr(ast, arg);
            }
        }
        ExprKind::Field { base, name } => {
            v.visit_expr(ast, *base);
            v.visit_ident(ast, name);
        }
        ExprKind::Vsa(call) => v.visit_vsa(ast, call),
        ExprKind::List(items) | ExprKind::Tuple(items) => {
            for &item in items {
                v.visit_expr(ast, item);
            }
        }
        ExprKind::Block { stmts, tail } => {
            for &stmt in stmts {
                v.visit_stmt(ast, stmt);
            }
            if let Some(tail) = tail {
                v.visit_expr(ast, *tail);
            }
        }
        ExprKind::If {
            cond,
            then_block,
            else_branch,
        } => {
            v.visit_expr(ast, *cond);
            v.visit_expr(ast, *then_block);
            if let Some(branch) = else_branch {
                v.visit_expr(ast, *branch);
            }
        }
        ExprKind::Error => {}
    }
}

pub fn walk_vsa<V: Visitor>(v: &mut V, ast: &Ast, call: &VsaCall) {
    if let Some(variant) = &call.variant {
        v.visit_ident(ast, variant);
    }
    for &arg in &call.args {
        v.visit_expr(ast, arg);
    }
}

pub fn walk_type<V: Visitor>(v: &mut V, ast: &Ast, id: TypeExprId) {
    let TypeExpr { kind, .. } = &ast.types[id];
    match kind {
        TypeExprKind::Named { path, args, quals } => {
            for segment in path {
                v.visit_ident(ast, segment);
            }
            for &arg in args {
                v.visit_type(ast, arg);
            }
            for qual in quals {
                v.visit_type_qual(ast, qual);
            }
        }
        TypeExprKind::Fn { params, ret } => {
            for &param in params {
                v.visit_type(ast, param);
            }
            if let Some(ret) = ret {
                v.visit_type(ast, *ret);
            }
        }
        TypeExprKind::Tuple(items) => {
            for &item in items {
                v.visit_type(ast, item);
            }
        }
        TypeExprKind::Error => {}
    }
}

pub fn walk_type_qual<V: Visitor>(v: &mut V, ast: &Ast, qual: &TypeQual) {
    match qual {
        TypeQual::Load { count, .. } => {
            if let Some(count) = count {
                v.visit_expr(ast, *count);
            }
        }
        TypeQual::Roles { written, .. } => {
            for name in written {
                v.visit_ident(ast, name);
            }
        }
        TypeQual::Clean(_) | TypeQual::Noisy(_) | TypeQual::Error(_) => {}
    }
}
