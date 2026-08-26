//! Provisional arena-based syntax tree for the Raly language.
//!
//! # What this crate is
//!
//! The *shape* a Raly front end needs: an [`Ast`] that owns flat [`arena`]s of
//! nodes, 32-bit [`Id`] handles instead of boxes, a [`Symbol`] interner for
//! names, a [`Span`](raly_diag::Span) on every node, and a [`Visitor`] whose
//! traversal is derived from the node definitions.
//!
//! # What this crate is not
//!
//! **It is not Raly's grammar.** The grammar and the semantics are being
//! designed separately and will land later. The node definitions in [`node`]
//! are placeholders, marked as such, chosen to be the smallest set that
//! exercises the infrastructure. They encode no precedence, no evaluation
//! order and no meaning for any keyword; type annotations are stored as opaque
//! source text for exactly that reason. Expect [`ExprKind`], [`ItemKind`] and
//! [`TypeExprKind`] to be replaced rather than extended.
//!
//! There is also no parser here, in this crate or any other. Nothing yet
//! *produces* an `Ast` except tests and callers building one by hand.

#![deny(missing_debug_implementations)]

pub mod arena;
pub mod node;
pub mod visit;

pub use arena::{Arena, Id, Interner, Symbol};
pub use node::{
    Ast, Expr, ExprId, ExprKind, FnDef, Ident, Item, ItemId, ItemKind, LetBinding, Literal, Param,
    TypeExpr, TypeExprId, TypeExprKind,
};
pub use visit::Visitor;

#[cfg(test)]
mod tests {
    use super::*;
    use raly_diag::{FileId, Span};

    const F: FileId = FileId(0);

    fn span(a: u32, b: u32) -> Span {
        Span::new(F, a, b)
    }

    /// Builds `fn double(x) { let y = 2; x }` in shape only.
    fn sample() -> Ast {
        let mut ast = Ast::new();

        let two = ast.names.intern("2");
        let two_expr = ast.expr(ExprKind::Literal(Literal::Int(two)), span(30, 31));
        let y = ast.ident("y", span(26, 27));
        let let_item = ast.item(
            ItemKind::Let(LetBinding {
                mutable: false,
                name: y,
                ty: None,
                init: Some(two_expr),
            }),
            span(22, 32),
        );

        let x_use = ast.ident("x", span(34, 35));
        let tail = ast.expr(ExprKind::Path(vec![x_use]), span(34, 35));
        let body = ast.expr(
            ExprKind::Block {
                items: vec![let_item],
                tail: Some(tail),
            },
            span(20, 37),
        );

        let x_param = ast.ident("x", span(14, 15));
        let name = ast.ident("double", span(3, 9));
        let f = ast.item(
            ItemKind::Fn(FnDef {
                name,
                params: vec![Param {
                    name: x_param,
                    ty: None,
                    span: span(14, 15),
                }],
                return_type: None,
                body: Some(body),
            }),
            span(0, 37),
        );
        ast.root.push(f);
        ast
    }

    #[test]
    fn arena_ids_round_trip() {
        let ast = sample();
        assert_eq!(ast.items.len(), 2);
        assert_eq!(ast.exprs.len(), 3);
        for id in ast.exprs.ids() {
            assert!(ast.exprs.get(id).is_some());
        }
    }

    #[test]
    fn interner_deduplicates() {
        let ast = sample();
        // "x" appears twice in the source but is interned once.
        assert_eq!(ast.names.len(), 4, "expected 2, y, x, double");
    }

    #[test]
    fn visitor_reaches_every_node() {
        #[derive(Default)]
        struct Count {
            exprs: usize,
            items: usize,
            idents: usize,
            literals: usize,
        }
        impl Visitor for Count {
            fn visit_expr(&mut self, ast: &Ast, id: ExprId) {
                self.exprs += 1;
                visit::walk_expr(self, ast, id);
            }
            fn visit_item(&mut self, ast: &Ast, id: ItemId) {
                self.items += 1;
                visit::walk_item(self, ast, id);
            }
            fn visit_ident(&mut self, _ast: &Ast, _i: &Ident) {
                self.idents += 1;
            }
            fn visit_literal(&mut self, _ast: &Ast, _l: &Literal) {
                self.literals += 1;
            }
        }

        let ast = sample();
        let mut count = Count::default();
        count.visit_ast(&ast);
        assert_eq!(count.items, 2);
        assert_eq!(count.exprs, 3);
        assert_eq!(count.literals, 1);
        // `double`, its parameter `x`, `y`, and the use of `x`.
        assert_eq!(count.idents, 4);
    }

    #[test]
    fn visitor_can_prune() {
        struct StopAtBlocks(usize);
        impl Visitor for StopAtBlocks {
            fn visit_expr(&mut self, ast: &Ast, id: ExprId) {
                self.0 += 1;
                if matches!(ast.exprs[id].kind, ExprKind::Block { .. }) {
                    return; // do not walk children
                }
                visit::walk_expr(self, ast, id);
            }
        }
        let ast = sample();
        let mut v = StopAtBlocks(0);
        v.visit_ast(&ast);
        assert_eq!(v.0, 1, "the block should have been pruned");
    }
}
