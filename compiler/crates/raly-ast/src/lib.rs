//! The arena-based syntax tree for the Raly language.
//!
//! The grammar this implements is written down in `compiler/GRAMMAR.md`, which
//! is normative: where the two disagree, one of them is a bug.
//!
//! # Shape
//!
//! An [`Ast`] owns flat [`arena`]s of nodes and hands out 32-bit [`Id`]
//! handles instead of boxes. That is not a micro-optimisation: it makes side
//! tables (types, resolutions) trivial to hang off the same indices, keeps the
//! tree serialisable, and sidesteps the lifetime problems that make
//! `&'ast Node` trees painful to build *during error recovery* — which the
//! parser does constantly.
//!
//! # Two invariants worth knowing
//!
//! **The tree is total.** Parsing never fails and never returns `Result`. Text
//! that could not be understood becomes an `Error` node whose span covers the
//! tokens involved, so every significant token in the source lies inside some
//! node. Downstream phases can always walk a whole file.
//!
//! **Every node knows why it exists.** [`Origin`] distinguishes a node the
//! user wrote from one recovery synthesised, and in the latter case names the
//! [`Reason`]. A checker can then refuse to blame an expression that is not
//! really there — the difference between good and bad error messages is
//! mostly this kind of provenance, and it is far cheaper to carry from the
//! start than to retrofit.
//!
//! # Canonical operand order
//!
//! Binding and n-ary bundling are commutative. [`VsaCall`] therefore stores
//! its operands twice: once in source order, for diagnostics and formatting,
//! and once in a canonical order derived from [`Ast::structural_key`]. That
//! makes commutativity structurally true instead of a law each later pass has
//! to remember. The `bundle.left` fold deliberately gets no canonical order,
//! because superposition is not associative and the fold is a genuinely
//! different function.

#![deny(missing_debug_implementations)]

pub mod arena;
pub mod node;
pub mod visit;

pub use arena::{Arena, Id, Interner, Symbol};
pub use node::{
    Ast, Attr, BinOp, Expr, ExprId, ExprKind, FnDef, Ident, ImportDecl, Item, ItemId, ItemKind,
    LetBinding, Literal, Origin, Param, Reason, RoleDecl, SpaceDecl, Stmt, StmtId, StmtKind,
    TypeAlias, TypeExpr, TypeExprId, TypeExprKind, TypeQual, UnOp, VsaCall, VsaOp, VsaVariant,
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

    /// Builds, in shape only:
    ///
    /// ```text
    /// fn double(x: Vec[S]) { let y = 2; bundle(x, y) }
    /// ```
    fn sample() -> Ast {
        let mut ast = Ast::new();

        let two = ast.names.intern("2");
        let two_expr = ast.expr(ExprKind::Literal(Literal::Int(two)), span(30, 31));
        let y = ast.ident("y", span(26, 27));
        let let_stmt = ast.stmt(
            StmtKind::Let(LetBinding {
                mutable: false,
                name: y,
                ty: None,
                init: Some(two_expr),
            }),
            span(22, 32),
        );

        let x_use = ast.ident("x", span(41, 42));
        let x_expr = ast.expr(ExprKind::Path(vec![x_use]), span(41, 42));
        let y_use = ast.ident("y", span(44, 45));
        let y_expr = ast.expr(ExprKind::Path(vec![y_use]), span(44, 45));
        let args = vec![x_expr, y_expr];
        let canonical = ast.canonical_order(&args);
        let tail = ast.expr(
            ExprKind::Vsa(VsaCall {
                op: VsaOp::Bundle,
                op_span: span(34, 40),
                variant: None,
                variant_kind: None,
                args,
                canonical,
            }),
            span(34, 46),
        );

        let body = ast.expr(
            ExprKind::Block {
                stmts: vec![let_stmt],
                tail: Some(tail),
            },
            span(20, 48),
        );

        let s = ast.ident("S", span(17, 18));
        let s_ty = ast.type_expr(
            TypeExprKind::Named {
                path: vec![s],
                args: Vec::new(),
                quals: Vec::new(),
            },
            span(17, 18),
        );
        let vec_name = ast.ident("Vec", span(13, 16));
        let param_ty = ast.type_expr(
            TypeExprKind::Named {
                path: vec![vec_name],
                args: vec![s_ty],
                quals: Vec::new(),
            },
            span(13, 19),
        );

        let x_param = ast.ident("x", span(10, 11));
        let name = ast.ident("double", span(3, 9));
        let f = ast.item(
            ItemKind::Fn(FnDef {
                name,
                params: vec![Param {
                    name: x_param,
                    ty: Some(param_ty),
                    span: span(10, 19),
                }],
                return_type: None,
                attrs: Vec::new(),
                body: Some(body),
            }),
            span(0, 48),
        );
        ast.root.push(f);
        ast
    }

    #[test]
    fn arena_ids_round_trip() {
        let ast = sample();
        assert_eq!(ast.items.len(), 1);
        assert_eq!(ast.stmts.len(), 1);
        assert_eq!(ast.exprs.len(), 5);
        for id in ast.exprs.ids() {
            assert!(ast.exprs.get(id).is_some());
        }
        for id in ast.types.ids() {
            assert!(ast.types.get(id).is_some());
        }
    }

    #[test]
    fn interner_deduplicates() {
        let ast = sample();
        // "x" and "y" each appear twice in the source but are interned once.
        assert_eq!(ast.names.len(), 6, "expected 2, y, x, S, Vec, double");
    }

    #[test]
    fn every_node_defaults_to_source_provenance() {
        let ast = sample();
        assert!(ast.exprs.iter().all(|e| e.origin == Origin::Source));
        assert!(ast.items.iter().all(|i| i.origin == Origin::Source));
    }

    #[test]
    fn recovered_nodes_carry_their_reason() {
        let mut ast = Ast::new();
        let id = ast.expr_from(
            ExprKind::Error,
            span(0, 3),
            Origin::Recovered(Reason::MissingExpr),
        );
        let origin = ast.exprs[id].origin;
        assert!(origin.is_recovered());
        assert_eq!(origin.reason(), Some(Reason::MissingExpr));
        assert_eq!(Reason::MissingExpr.describe(), "a missing expression");
    }

    #[test]
    fn commutative_operands_have_a_canonical_order() {
        // `bundle(a, b)` and `bundle(b, a)` must produce the same canonical
        // sequence of structural keys, and the same key for the whole call.
        fn build(first: &str, second: &str) -> (Ast, ExprId) {
            let mut ast = Ast::new();
            let a = ast.ident(first, span(0, 1));
            let a_expr = ast.expr(ExprKind::Path(vec![a]), span(0, 1));
            let b = ast.ident(second, span(2, 3));
            let b_expr = ast.expr(ExprKind::Path(vec![b]), span(2, 3));
            let args = vec![a_expr, b_expr];
            let canonical = ast.canonical_order(&args);
            let call = ast.expr(
                ExprKind::Vsa(VsaCall {
                    op: VsaOp::Bundle,
                    op_span: span(0, 6),
                    variant: None,
                    variant_kind: None,
                    args,
                    canonical,
                }),
                span(0, 10),
            );
            (ast, call)
        }

        let (ab, ab_id) = build("alpha", "beta");
        let (ba, ba_id) = build("beta", "alpha");

        assert_eq!(ab.structural_key(ab_id), ba.structural_key(ba_id));

        let keys = |ast: &Ast, id: ExprId| -> Vec<u64> {
            let ExprKind::Vsa(call) = &ast.exprs[id].kind else {
                unreachable!()
            };
            call.operands()
                .iter()
                .map(|&o| ast.structural_key(o))
                .collect()
        };
        assert_eq!(keys(&ab, ab_id), keys(&ba, ba_id));
    }

    #[test]
    fn the_fold_is_order_sensitive() {
        let mut ast = Ast::new();
        let a = ast.ident("a", span(0, 1));
        let a_expr = ast.expr(ExprKind::Path(vec![a]), span(0, 1));
        let b = ast.ident("b", span(2, 3));
        let b_expr = ast.expr(ExprKind::Path(vec![b]), span(2, 3));
        let variant = ast.ident("left", span(7, 11));
        let call = VsaCall {
            op: VsaOp::Bundle,
            op_span: span(0, 6),
            variant: Some(variant),
            variant_kind: Some(VsaVariant::Left),
            args: vec![a_expr, b_expr],
            canonical: Vec::new(),
        };
        assert!(!call.is_order_insensitive());
        // With no canonical order recorded, `operands()` falls back to source
        // order, which is exactly what a fold must respect.
        assert_eq!(call.operands(), &[a_expr, b_expr]);
    }

    #[test]
    fn arities_match_the_grammar() {
        assert_eq!(VsaOp::Bind.arity(None), (2, None));
        assert_eq!(VsaOp::Bundle.arity(None), (1, None));
        assert_eq!(VsaOp::Bundle.arity(Some(VsaVariant::Left)), (2, None));
        assert_eq!(VsaOp::Unbind.arity(None), (2, Some(2)));
        assert_eq!(VsaOp::Cleanup.arity(None), (1, Some(2)));
        assert_eq!(VsaOp::Permute.arity(None), (1, Some(2)));
        assert_eq!(VsaOp::Bundle.variants(), &["left"]);
        assert!(VsaOp::Permute.variants().is_empty());
    }

    #[test]
    fn visitor_reaches_every_node() {
        #[derive(Default)]
        struct Count {
            exprs: usize,
            items: usize,
            stmts: usize,
            types: usize,
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
            fn visit_stmt(&mut self, ast: &Ast, id: StmtId) {
                self.stmts += 1;
                visit::walk_stmt(self, ast, id);
            }
            fn visit_type(&mut self, ast: &Ast, id: TypeExprId) {
                self.types += 1;
                visit::walk_type(self, ast, id);
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
        assert_eq!(count.items, 1);
        assert_eq!(count.stmts, 1);
        assert_eq!(count.exprs, 5);
        assert_eq!(count.types, 2);
        assert_eq!(count.literals, 1);
        // `double`, the parameter `x`, `Vec`, `S`, `y`, and the uses of `x`
        // and `y`.
        assert_eq!(count.idents, 7);
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
