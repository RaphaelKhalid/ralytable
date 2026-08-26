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
//! When the real grammar lands and [`crate::ExprKind`] grows variants, the
//! only edits needed here are new match arms in the `walk_*` functions; every
//! existing implementor keeps compiling and automatically traverses the new
//! nodes.

use crate::node::{
    Ast, Expr, ExprId, ExprKind, FnDef, Ident, Item, ItemId, ItemKind, LetBinding, Literal, Param,
    TypeExpr, TypeExprId,
};

/// Read-only traversal of an [`Ast`].
pub trait Visitor: Sized {
    fn visit_ast(&mut self, ast: &Ast) {
        walk_ast(self, ast);
    }
    fn visit_item(&mut self, ast: &Ast, id: ItemId) {
        walk_item(self, ast, id);
    }
    fn visit_fn_def(&mut self, ast: &Ast, def: &FnDef) {
        walk_fn_def(self, ast, def);
    }
    fn visit_param(&mut self, ast: &Ast, param: &Param) {
        walk_param(self, ast, param);
    }
    fn visit_let(&mut self, ast: &Ast, binding: &LetBinding) {
        walk_let(self, ast, binding);
    }
    fn visit_expr(&mut self, ast: &Ast, id: ExprId) {
        walk_expr(self, ast, id);
    }
    fn visit_type(&mut self, ast: &Ast, id: TypeExprId) {
        walk_type(self, ast, id);
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
        ItemKind::Fn(def) => v.visit_fn_def(ast, def),
        ItemKind::Let(binding) => v.visit_let(ast, binding),
        ItemKind::Error => {}
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

pub fn walk_let<V: Visitor>(v: &mut V, ast: &Ast, binding: &LetBinding) {
    v.visit_ident(ast, &binding.name);
    if let Some(ty) = binding.ty {
        v.visit_type(ast, ty);
    }
    if let Some(init) = binding.init {
        v.visit_expr(ast, init);
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
        ExprKind::Op { operands, .. } => {
            for &operand in operands {
                v.visit_expr(ast, operand);
            }
        }
        ExprKind::Call { callee, args } => {
            v.visit_expr(ast, *callee);
            for &arg in args {
                v.visit_expr(ast, arg);
            }
        }
        ExprKind::Block { items, tail } => {
            for &item in items {
                v.visit_item(ast, item);
            }
            if let Some(tail) = tail {
                v.visit_expr(ast, *tail);
            }
        }
        ExprKind::Error => {}
    }
}

pub fn walk_type<V: Visitor>(_v: &mut V, ast: &Ast, id: TypeExprId) {
    // Annotations are opaque for now, so there is nothing below them. This
    // function exists so that implementors already call through it and keep
    // working once type syntax gains structure.
    let TypeExpr { .. } = &ast.types[id];
}
