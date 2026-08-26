//! A readable, deterministic dump of a parsed tree, for `raly parse <file>`.
//!
//! The format is stable enough to snapshot in tests: one node per line,
//! indented by depth, `kind @ start..end` with the interesting fields inline.
//! Recovered nodes are marked, because the first question about a dump of a
//! broken file is always "which of this is real?".

use std::fmt::Write as _;

use raly_ast::{
    Ast, ExprId, ExprKind, ItemId, ItemKind, LetBinding, Origin, StmtId, StmtKind, TypeExprId,
    TypeExprKind, TypeQual,
};

/// Render the whole tree.
pub fn dump(ast: &Ast) -> String {
    let mut out = String::new();
    if ast.root.is_empty() {
        out.push_str("(empty)\n");
        return out;
    }
    for &item in &ast.root {
        item_to(&mut out, ast, item, 0);
    }
    out
}

fn line(out: &mut String, depth: usize, origin: Origin, body: &str) {
    for _ in 0..depth {
        out.push_str("  ");
    }
    out.push_str(body);
    if let Some(reason) = origin.reason() {
        let _ = write!(out, "  [recovered: {}]", reason.describe());
    }
    out.push('\n');
}

fn item_to(out: &mut String, ast: &Ast, id: ItemId, depth: usize) {
    let item = &ast.items[id];
    let span = item.span;
    let head = |name: &str| format!("{name} @ {}..{}", span.start, span.end);

    match &item.kind {
        ItemKind::Import(decl) => {
            let path = decl
                .path
                .iter()
                .map(|s| ast.text(*s))
                .collect::<Vec<_>>()
                .join("::");
            line(out, depth, item.origin, &head(&format!("import `{path}`")));
        }
        ItemKind::Space(decl) => {
            let family = decl.family.map(|f| ast.text(f)).unwrap_or("<missing>");
            line(
                out,
                depth,
                item.origin,
                &head(&format!("space `{}` family={family}", ast.text(decl.name))),
            );
            if let Some(dim) = decl.dim {
                line(out, depth + 1, Origin::Source, "dim:");
                expr_to(out, ast, dim, depth + 2);
            }
            for attr in &decl.attrs {
                line(
                    out,
                    depth + 1,
                    Origin::Source,
                    &format!("attr `{}`", ast.text(attr.name)),
                );
                if let Some(value) = attr.value {
                    expr_to(out, ast, value, depth + 2);
                }
            }
        }
        ItemKind::Role(decl) => {
            let names = decl
                .names
                .iter()
                .map(|n| ast.text(*n))
                .collect::<Vec<_>>()
                .join(", ");
            let space = decl.space.map(|s| ast.text(s)).unwrap_or("<missing>");
            line(
                out,
                depth,
                item.origin,
                &head(&format!("role {names} in `{space}`")),
            );
        }
        ItemKind::TypeAlias(alias) => {
            line(
                out,
                depth,
                item.origin,
                &head(&format!("type `{}`", ast.text(alias.name))),
            );
            if let Some(ty) = alias.ty {
                type_to(out, ast, ty, depth + 1);
            }
        }
        ItemKind::Fn(def) => {
            line(
                out,
                depth,
                item.origin,
                &head(&format!("fn `{}`", ast.text(def.name))),
            );
            for param in &def.params {
                line(
                    out,
                    depth + 1,
                    Origin::Source,
                    &format!("param `{}`", ast.text(param.name)),
                );
                match param.ty {
                    Some(ty) => type_to(out, ast, ty, depth + 2),
                    None => line(out, depth + 2, Origin::Source, "<no type>"),
                }
            }
            if let Some(ret) = def.return_type {
                line(out, depth + 1, Origin::Source, "returns:");
                type_to(out, ast, ret, depth + 2);
            }
            for attr in &def.attrs {
                line(
                    out,
                    depth + 1,
                    Origin::Source,
                    &format!("attr `{}`", ast.text(attr.name)),
                );
                if let Some(value) = attr.value {
                    expr_to(out, ast, value, depth + 2);
                }
            }
            if let Some(body) = def.body {
                expr_to(out, ast, body, depth + 1);
            }
        }
        ItemKind::Let(binding) => let_to(out, ast, binding, item.origin, span, depth),
        ItemKind::Error => line(out, depth, item.origin, &head("<error>")),
    }
}

fn let_to(
    out: &mut String,
    ast: &Ast,
    binding: &LetBinding,
    origin: Origin,
    span: raly_diag::Span,
    depth: usize,
) {
    let m = if binding.mutable { "mut " } else { "" };
    line(
        out,
        depth,
        origin,
        &format!(
            "let {m}`{}` @ {}..{}",
            ast.text(binding.name),
            span.start,
            span.end
        ),
    );
    if let Some(ty) = binding.ty {
        type_to(out, ast, ty, depth + 1);
    }
    if let Some(init) = binding.init {
        expr_to(out, ast, init, depth + 1);
    }
}

fn stmt_to(out: &mut String, ast: &Ast, id: StmtId, depth: usize) {
    let stmt = &ast.stmts[id];
    let span = stmt.span;
    match &stmt.kind {
        StmtKind::Let(binding) => let_to(out, ast, binding, stmt.origin, span, depth),
        StmtKind::Return(value) => {
            line(
                out,
                depth,
                stmt.origin,
                &format!("return @ {}..{}", span.start, span.end),
            );
            if let Some(value) = value {
                expr_to(out, ast, *value, depth + 1);
            }
        }
        StmtKind::Expr(expr) => expr_to(out, ast, *expr, depth),
        StmtKind::Item(item) => item_to(out, ast, *item, depth),
        StmtKind::Error => line(
            out,
            depth,
            stmt.origin,
            &format!("<error stmt> @ {}..{}", span.start, span.end),
        ),
    }
}

fn expr_to(out: &mut String, ast: &Ast, id: ExprId, depth: usize) {
    let expr = &ast.exprs[id];
    let span = expr.span;
    let head = |name: String| format!("{name} @ {}..{}", span.start, span.end);

    match &expr.kind {
        ExprKind::Literal(lit) => {
            let text = match lit {
                raly_ast::Literal::Int(s) => format!("int {}", ast.names.resolve(*s)),
                raly_ast::Literal::Float(s) => format!("float {}", ast.names.resolve(*s)),
                raly_ast::Literal::Str(s) => format!("str \"{}\"", ast.names.resolve(*s)),
                raly_ast::Literal::Bool(b) => format!("bool {b}"),
            };
            line(out, depth, expr.origin, &head(text));
        }
        ExprKind::Path(segments) => {
            let path = segments
                .iter()
                .map(|s| ast.text(*s))
                .collect::<Vec<_>>()
                .join("::");
            line(out, depth, expr.origin, &head(format!("path `{path}`")));
        }
        ExprKind::Group(inner) => {
            line(out, depth, expr.origin, &head("group".into()));
            expr_to(out, ast, *inner, depth + 1);
        }
        ExprKind::Unary { op, operand, .. } => {
            line(
                out,
                depth,
                expr.origin,
                &head(format!("unary `{}`", op.spelling())),
            );
            expr_to(out, ast, *operand, depth + 1);
        }
        ExprKind::Binary { op, lhs, rhs, .. } => {
            line(
                out,
                depth,
                expr.origin,
                &head(format!("binary `{}`", op.spelling())),
            );
            expr_to(out, ast, *lhs, depth + 1);
            expr_to(out, ast, *rhs, depth + 1);
        }
        ExprKind::Pipeline { value, stage, .. } => {
            line(out, depth, expr.origin, &head("pipeline `|>`".into()));
            expr_to(out, ast, *value, depth + 1);
            expr_to(out, ast, *stage, depth + 1);
        }
        ExprKind::Call { callee, args } => {
            line(out, depth, expr.origin, &head("call".into()));
            expr_to(out, ast, *callee, depth + 1);
            for &arg in args {
                expr_to(out, ast, arg, depth + 1);
            }
        }
        ExprKind::Field { base, name } => {
            line(
                out,
                depth,
                expr.origin,
                &head(format!("field `{}`", ast.text(*name))),
            );
            expr_to(out, ast, *base, depth + 1);
        }
        ExprKind::Vsa(call) => {
            let name = match call.variant_kind {
                Some(v) => format!("{}.{}", call.op.name(), v.name()),
                None => call.op.name().to_string(),
            };
            let order = if call.is_order_insensitive() {
                " (multiset)"
            } else {
                ""
            };
            line(out, depth, expr.origin, &head(format!("{name}{order}")));
            for &arg in &call.args {
                expr_to(out, ast, arg, depth + 1);
            }
        }
        ExprKind::List(items) => {
            line(out, depth, expr.origin, &head("list".into()));
            for &item in items {
                expr_to(out, ast, item, depth + 1);
            }
        }
        ExprKind::Tuple(items) => {
            line(out, depth, expr.origin, &head("tuple".into()));
            for &item in items {
                expr_to(out, ast, item, depth + 1);
            }
        }
        ExprKind::Block { stmts, tail } => {
            line(out, depth, expr.origin, &head("block".into()));
            for &stmt in stmts {
                stmt_to(out, ast, stmt, depth + 1);
            }
            if let Some(tail) = tail {
                line(out, depth + 1, Origin::Source, "tail:");
                expr_to(out, ast, *tail, depth + 2);
            }
        }
        ExprKind::If {
            cond,
            then_block,
            else_branch,
        } => {
            line(out, depth, expr.origin, &head("if".into()));
            expr_to(out, ast, *cond, depth + 1);
            expr_to(out, ast, *then_block, depth + 1);
            if let Some(branch) = else_branch {
                expr_to(out, ast, *branch, depth + 1);
            }
        }
        ExprKind::Error => line(out, depth, expr.origin, &head("<error expr>".into())),
    }
}

fn type_to(out: &mut String, ast: &Ast, id: TypeExprId, depth: usize) {
    let ty = &ast.types[id];
    let span = ty.span;
    match &ty.kind {
        TypeExprKind::Named { path, args, quals } => {
            let name = path
                .iter()
                .map(|s| ast.text(*s))
                .collect::<Vec<_>>()
                .join("::");
            line(
                out,
                depth,
                ty.origin,
                &format!("type `{name}` @ {}..{}", span.start, span.end),
            );
            for &arg in args {
                type_to(out, ast, arg, depth + 1);
            }
            for qual in quals {
                qual_to(out, ast, qual, depth + 1);
            }
        }
        TypeExprKind::Fn { params, ret } => {
            line(
                out,
                depth,
                ty.origin,
                &format!("type fn @ {}..{}", span.start, span.end),
            );
            for &param in params {
                type_to(out, ast, param, depth + 1);
            }
            if let Some(ret) = ret {
                line(out, depth + 1, Origin::Source, "->");
                type_to(out, ast, *ret, depth + 2);
            }
        }
        TypeExprKind::Tuple(items) => {
            line(
                out,
                depth,
                ty.origin,
                &format!("type tuple @ {}..{}", span.start, span.end),
            );
            for &item in items {
                type_to(out, ast, item, depth + 1);
            }
        }
        TypeExprKind::Error => line(
            out,
            depth,
            ty.origin,
            &format!("<error type> @ {}..{}", span.start, span.end),
        ),
    }
}

fn qual_to(out: &mut String, ast: &Ast, qual: &TypeQual, depth: usize) {
    match qual {
        TypeQual::Load { count, .. } => {
            line(out, depth, Origin::Source, "qual load");
            if let Some(count) = count {
                expr_to(out, ast, *count, depth + 1);
            }
        }
        TypeQual::Roles { names, .. } => {
            let names = names
                .iter()
                .map(|n| ast.text(*n))
                .collect::<Vec<_>>()
                .join(", ");
            line(
                out,
                depth,
                Origin::Source,
                &format!("qual roles {{{names}}}"),
            );
        }
        TypeQual::Clean(_) => line(out, depth, Origin::Source, "qual clean"),
        TypeQual::Noisy(_) => line(out, depth, Origin::Source, "qual noisy"),
        TypeQual::Error(_) => line(out, depth, Origin::Source, "<error qual>"),
    }
}
