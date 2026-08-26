//! Expressions, statements and blocks: GRAMMAR.md §7 and §8.
//!
//! Precedence climbing (Pratt). Binding powers are the only place precedence
//! is written down, and they are laid out in one table so that reading the
//! grammar and reading the code agree.

use raly_ast::{
    BinOp, ExprId, ExprKind, Literal, Reason, StmtId, StmtKind, UnOp, VsaCall, VsaOp, VsaVariant,
};
use raly_diag::{codes, Diagnostic, Span};
use raly_lexer::TokenKind;

use crate::cursor::{Parser, STMT_STARTS};

/// Left and right binding powers for infix operators.
///
/// `right = left + 1` makes an operator left-associative; the only levels here
/// are left-associative. See GRAMMAR.md §8.1.
fn infix_power(kind: TokenKind) -> Option<(u8, u8)> {
    Some(match kind {
        TokenKind::Pipeline => (1, 2),
        TokenKind::EqEq | TokenKind::Lt | TokenKind::LtEq | TokenKind::Gt | TokenKind::GtEq => {
            (3, 4)
        }
        TokenKind::Plus | TokenKind::Minus => (5, 6),
        TokenKind::Star | TokenKind::Slash => (7, 8),
        _ => return None,
    })
}

/// Binding power of a prefix operator: binds tighter than every infix level.
const PREFIX_POWER: u8 = 9;

fn binop_of(kind: TokenKind) -> Option<BinOp> {
    Some(match kind {
        TokenKind::Plus => BinOp::Add,
        TokenKind::Minus => BinOp::Sub,
        TokenKind::Star => BinOp::Mul,
        TokenKind::Slash => BinOp::Div,
        TokenKind::EqEq => BinOp::Eq,
        TokenKind::Lt => BinOp::Lt,
        TokenKind::LtEq => BinOp::LtEq,
        TokenKind::Gt => BinOp::Gt,
        TokenKind::GtEq => BinOp::GtEq,
        _ => return None,
    })
}

fn vsa_op_of(kind: TokenKind) -> Option<VsaOp> {
    Some(match kind {
        TokenKind::Bind => VsaOp::Bind,
        TokenKind::Bundle => VsaOp::Bundle,
        TokenKind::Permute => VsaOp::Permute,
        TokenKind::Unbind => VsaOp::Unbind,
        TokenKind::Cleanup => VsaOp::Cleanup,
        TokenKind::Broadcast => VsaOp::Broadcast,
        _ => return None,
    })
}

impl Parser<'_> {
    pub(crate) fn parse_expr(&mut self) -> ExprId {
        self.parse_expr_bp(0)
    }

    fn parse_expr_bp(&mut self, min_bp: u8) -> ExprId {
        let mut lhs = self.parse_prefix();

        loop {
            let kind = self.peek();
            let Some((left_bp, right_bp)) = infix_power(kind) else {
                break;
            };
            if left_bp < min_bp {
                break;
            }
            let op_token = self.bump();

            if kind == TokenKind::Pipeline {
                let stage = self.parse_pipeline_stage(right_bp);
                let span = self.ast.exprs[lhs].span.merge(self.ast.exprs[stage].span);
                lhs = self.ast.expr(
                    ExprKind::Pipeline {
                        value: lhs,
                        op_span: op_token.span,
                        stage,
                    },
                    span,
                );
                continue;
            }

            let op = binop_of(kind).expect("infix_power and binop_of must agree");
            let rhs = self.parse_expr_bp(right_bp);
            let span = self.ast.exprs[lhs].span.merge(self.ast.exprs[rhs].span);
            lhs = self.ast.expr(
                ExprKind::Binary {
                    op,
                    op_span: op_token.span,
                    lhs,
                    rhs,
                },
                span,
            );
        }

        lhs
    }

    fn parse_prefix(&mut self) -> ExprId {
        let kind = self.peek();
        let op = match kind {
            TokenKind::Minus => Some(UnOp::Neg),
            TokenKind::Bang => Some(UnOp::Not),
            _ => None,
        };
        let Some(op) = op else {
            return self.parse_postfix();
        };
        let op_token = self.bump();
        let operand = self.parse_expr_bp(PREFIX_POWER);
        let span = op_token.span.merge(self.ast.exprs[operand].span);
        self.ast.expr(
            ExprKind::Unary {
                op,
                op_span: op_token.span,
                operand,
            },
            span,
        )
    }

    fn parse_postfix(&mut self) -> ExprId {
        let mut expr = self.parse_primary();
        loop {
            match self.peek() {
                TokenKind::LParen => {
                    let open = self.bump();
                    let args = self.parse_call_args(open.span);
                    let span = self.ast.exprs[expr].span.merge(self.prev_span());
                    expr = self.ast.expr(ExprKind::Call { callee: expr, args }, span);
                }
                TokenKind::Dot => {
                    self.bump();
                    let Some(token) = self.expect(TokenKind::Ident, "for a field name") else {
                        break;
                    };
                    let name = self.ident_of(token);
                    let span = self.ast.exprs[expr].span.merge(token.span);
                    expr = self.ast.expr(ExprKind::Field { base: expr, name }, span);
                }
                _ => break,
            }
        }
        expr
    }

    /// The right-hand side of `|>`.
    ///
    /// A bare operation keyword is allowed here — `v |> cleanup` — because the
    /// piped value supplies the first operand. Arity is checked against the
    /// *effective* count, so `v |> unbind()` still reports that `unbind` wants
    /// two operands.
    fn parse_pipeline_stage(&mut self, bp: u8) -> ExprId {
        if let Some(op) = vsa_op_of(self.peek()) {
            return self.parse_vsa_call(op, 1);
        }
        self.parse_expr_bp(bp)
    }

    fn parse_primary(&mut self) -> ExprId {
        let kind = self.peek();

        if let Some(op) = vsa_op_of(kind) {
            return self.parse_vsa_call(op, 0);
        }

        match kind {
            TokenKind::Int => self.literal_expr(Literal::Int),
            TokenKind::Float => self.literal_expr(Literal::Float),
            TokenKind::Str => self.string_expr(),
            TokenKind::True => {
                let token = self.bump();
                self.ast
                    .expr(ExprKind::Literal(Literal::Bool(true)), token.span)
            }
            TokenKind::False => {
                let token = self.bump();
                self.ast
                    .expr(ExprKind::Literal(Literal::Bool(false)), token.span)
            }
            TokenKind::Ident => {
                let start = self.span();
                let token = self.bump();
                let mut path = vec![self.ident_of(token)];
                while self.eat(TokenKind::ColonColon) {
                    match self.expect(TokenKind::Ident, "after `::`") {
                        Some(t) => path.push(self.ident_of(t)),
                        None => break,
                    }
                }
                let span = self.span_from(start);
                self.ast.expr(ExprKind::Path(path), span)
            }
            TokenKind::LParen => self.parse_paren_expr(),
            TokenKind::LBracket => self.parse_list_expr(),
            TokenKind::LBrace => self.parse_block(),
            TokenKind::If => self.parse_if(),
            TokenKind::Match | TokenKind::For => self.parse_unimplemented_expr(),
            // Malformed numbers and unterminated strings have already been
            // reported by the lexer. Accept them as literals so that one
            // lexical mistake does not also produce a syntax error.
            TokenKind::MalformedNumber => self.literal_expr(Literal::Int),
            TokenKind::UnterminatedStr => self.string_expr(),
            _ => {
                self.unexpected("expected an expression");
                let span = self.span();
                let skipped = self.sync(STMT_STARTS);
                self.ast.expr_from(
                    ExprKind::Error,
                    span.merge(skipped),
                    Parser::recovered(Reason::MissingExpr),
                )
            }
        }
    }

    fn literal_expr(&mut self, make: fn(raly_ast::Symbol) -> Literal) -> ExprId {
        let token = self.bump();
        let text = self.text(token.span);
        let symbol = self.ast.names.intern(text);
        self.ast.expr(ExprKind::Literal(make(symbol)), token.span)
    }

    /// Strings are interned without their quotes; escapes stay unexpanded,
    /// because how `\u{...}` becomes a value is a semantic question.
    fn string_expr(&mut self) -> ExprId {
        let token = self.bump();
        let raw = self.text(token.span);
        let body = raw
            .strip_prefix('"')
            .map(|s| s.strip_suffix('"').unwrap_or(s))
            .unwrap_or(raw);
        let symbol = self.ast.names.intern(body);
        self.ast
            .expr(ExprKind::Literal(Literal::Str(symbol)), token.span)
    }

    fn parse_paren_expr(&mut self) -> ExprId {
        let open = self.bump();
        let mut elems = Vec::new();
        let mut trailing_comma = false;

        while !self.at(TokenKind::RParen) && !self.at_eof() {
            let before = self.position();
            elems.push(self.parse_expr());
            trailing_comma = false;
            if self.eat(TokenKind::Comma) {
                trailing_comma = true;
            } else {
                break;
            }
            if self.position() == before {
                break;
            }
        }
        self.expect_close(TokenKind::RParen, open.span);
        let span = self.span_from(open.span);

        if elems.len() == 1 && !trailing_comma {
            let inner = elems[0];
            return self.ast.expr(ExprKind::Group(inner), span);
        }
        self.ast.expr(ExprKind::Tuple(elems), span)
    }

    fn parse_list_expr(&mut self) -> ExprId {
        let open = self.bump();
        let mut elems = Vec::new();
        while !self.at(TokenKind::RBracket) && !self.at_eof() {
            let before = self.position();
            elems.push(self.parse_expr());
            if !self.eat(TokenKind::Comma) {
                break;
            }
            if self.position() == before {
                break;
            }
        }
        self.expect_close(TokenKind::RBracket, open.span);
        let span = self.span_from(open.span);
        self.ast.expr(ExprKind::List(elems), span)
    }

    fn parse_if(&mut self) -> ExprId {
        let start = self.span();
        self.bump();
        let cond = self.parse_expr();
        let then_block = if self.at(TokenKind::LBrace) {
            self.parse_block()
        } else {
            self.unexpected("expected `{` to start the `if` body");
            let span = self.after_prev();
            self.ast.expr_from(
                ExprKind::Error,
                span,
                Parser::recovered(Reason::MissingBody),
            )
        };
        let else_branch = if self.eat(TokenKind::Else) {
            Some(if self.at(TokenKind::If) {
                self.parse_if()
            } else if self.at(TokenKind::LBrace) {
                self.parse_block()
            } else {
                self.unexpected("expected `{` or `if` after `else`");
                let span = self.after_prev();
                self.ast.expr_from(
                    ExprKind::Error,
                    span,
                    Parser::recovered(Reason::MissingBody),
                )
            })
        } else {
            None
        };
        let span = self.span_from(start);
        self.ast.expr(
            ExprKind::If {
                cond,
                then_block,
                else_branch,
            },
            span,
        )
    }

    fn parse_unimplemented_expr(&mut self) -> ExprId {
        let token = self.bump();
        let word = self.text(token.span).to_string();
        let diag = Diagnostic::error(
            codes::UNIMPLEMENTED_CONSTRUCT,
            format!("`{word}` is reserved but not implemented yet"),
        )
        .with_primary(token.span, format!("`{word}` cannot be used yet"))
        .with_help("the keyword is reserved so that adding it later is not a breaking change");
        self.push_silencing(diag);
        let skipped = self.sync(STMT_STARTS);
        self.ast.expr_from(
            ExprKind::Error,
            token.span.merge(skipped),
            Parser::recovered(Reason::Unimplemented),
        )
    }

    // -- the VSA operations -------------------------------------------------

    /// `VsaExpr = VsaOp [ "." IDENT ] "(" [ Expr%"," ] ")"`
    ///
    /// `implicit` is the number of operands supplied from outside the
    /// parentheses — 1 when this call is a pipeline stage, 0 otherwise.
    fn parse_vsa_call(&mut self, op: VsaOp, implicit: usize) -> ExprId {
        let op_token = self.bump();

        let (variant, variant_kind) = self.parse_vsa_variant(op);

        // A bare operation keyword is legal only as a pipeline stage, where
        // the piped value is the sole operand.
        if implicit > 0 && !self.at(TokenKind::LParen) {
            let call = VsaCall {
                op,
                op_span: op_token.span,
                variant,
                variant_kind,
                args: Vec::new(),
                canonical: Vec::new(),
            };
            let span = self.span_from(op_token.span);
            self.check_arity(&call, implicit, span);
            return self.ast.expr(ExprKind::Vsa(call), span);
        }

        let args = match self.expect(TokenKind::LParen, "to give the operands") {
            Some(open) => self.parse_call_args(open.span),
            None => Vec::new(),
        };

        let canonical = if op.is_commutative() && variant_kind.is_none() {
            self.ast.canonical_order(&args)
        } else {
            Vec::new()
        };

        let call = VsaCall {
            op,
            op_span: op_token.span,
            variant,
            variant_kind,
            args,
            canonical,
        };
        let span = self.span_from(op_token.span);
        let ok = self.check_arity(&call, implicit, span);
        let origin = if ok {
            raly_ast::Origin::Source
        } else {
            Parser::recovered(Reason::BadArity)
        };
        self.ast.expr_from(ExprKind::Vsa(call), span, origin)
    }

    fn parse_vsa_variant(&mut self, op: VsaOp) -> (Option<raly_ast::Ident>, Option<VsaVariant>) {
        if !(self.at(TokenKind::Dot) && self.peek_at(1) == TokenKind::Ident) {
            return (None, None);
        }
        self.bump(); // `.`
        let token = self.bump();
        let ident = self.ident_of(token);
        let text = self.text(token.span).to_string();

        let kind = match (op, text.as_str()) {
            (VsaOp::Bundle, "left") => Some(VsaVariant::Left),
            _ => None,
        };

        if kind.is_none() {
            let valid = op.variants();
            let mut diag = Diagnostic::error(
                codes::UNKNOWN_OP_VARIANT,
                format!("`{}` has no variant `{text}`", op.name()),
            )
            .with_primary(token.span, "unknown variant");
            if valid.is_empty() {
                diag = diag
                    .with_note(format!("`{}` has no variants", op.name()))
                    .with_help(format!("write `{}(..)`", op.name()));
            } else {
                diag = diag
                    .with_note(format!(
                        "the variants of `{}` are {}",
                        op.name(),
                        valid
                            .iter()
                            .map(|v| format!("`{v}`"))
                            .collect::<Vec<_>>()
                            .join(", ")
                    ))
                    .with_help(
                        "`bundle.left` is the left-nested binary fold; it is a different function \
                         from n-ary `bundle`, not a spelling of it",
                    );
            }
            self.push(diag);
        }

        (Some(ident), kind)
    }

    /// Enforce GRAMMAR.md §7.1. Returns whether the arity was acceptable.
    fn check_arity(&mut self, call: &VsaCall, implicit: usize, span: Span) -> bool {
        let count = call.args.len() + implicit;
        let (min, max) = call.op.arity(call.variant_kind);

        if call.op == VsaOp::Bundle && call.variant_kind.is_none() && count == 0 {
            // The one case that gets its own code: an empty superposition is
            // not a zero vector, because no discretized VSA family has a
            // bundle identity at all.
            let diag = Diagnostic::error(
                codes::EMPTY_BUNDLE,
                "`bundle()` needs at least one operand",
            )
            .with_primary(span, "this bundle superposes nothing")
            .with_note(
                "superposition has no identity element in any VSA family, so an empty bundle \
                 denotes no vector — it is not a zero vector",
            )
            .with_help("pass the operands directly, as in `bundle(a, b, c)`");
            self.push(diag);
            return false;
        }

        if count >= min && max.is_none_or(|max| count <= max) {
            return true;
        }

        let wanted = match (min, max) {
            (min, None) => format!("at least {min}"),
            (min, Some(max)) if min == max => format!("exactly {min}"),
            (min, Some(max)) => format!("between {min} and {max}"),
        };
        let name = match call.variant_kind {
            Some(v) => format!("{}.{}", call.op.name(), v.name()),
            None => call.op.name().to_string(),
        };
        let plural = |n: usize| if n == 1 { "operand" } else { "operands" };
        let mut diag = Diagnostic::error(
            codes::BAD_OP_ARITY,
            format!(
                "`{name}` takes {wanted} {}, but {count} {} given",
                plural(max.unwrap_or(min)),
                if count == 1 { "was" } else { "were" }
            ),
        )
        .with_primary(span, format!("{count} {} here", plural(count)));

        // The secondary label earns its place only when it points somewhere
        // the primary does not already cover.
        if call.op_span.start > span.start || call.op_span.end < span.end {
            let covered = call.op_span.start >= span.start && call.op_span.end <= span.end;
            if !covered {
                diag = diag.with_secondary(call.op_span, format!("`{name}` is applied here"));
            }
        }

        if implicit > 0 {
            diag = diag.with_note(format!(
                "the piped value counts as the first operand, so `{name}` sees {count} in total"
            ));
        }
        diag = diag.with_note(arity_rationale(call.op, call.variant_kind));
        self.push(diag);
        false
    }

    pub(crate) fn parse_call_args(&mut self, open: Span) -> Vec<ExprId> {
        let mut args = Vec::new();
        while !self.at(TokenKind::RParen) && !self.at_eof() {
            let before = self.position();
            args.push(self.parse_expr());
            if !self.eat(TokenKind::Comma) {
                break;
            }
            if self.position() == before {
                break;
            }
        }
        self.expect_close(TokenKind::RParen, open);
        args
    }

    // -- blocks and statements ----------------------------------------------

    /// `Block = "{" { Stmt } [ Expr ] "}"`
    pub(crate) fn parse_block(&mut self) -> ExprId {
        let open = self.bump();
        let mut stmts: Vec<StmtId> = Vec::new();
        let mut tail: Option<ExprId> = None;

        while !self.at(TokenKind::RBrace) && !self.at_eof() {
            let before = self.position();

            match self.peek() {
                TokenKind::Let => {
                    let start = self.span();
                    let binding = self.parse_let_binding();
                    self.eat(TokenKind::Semi);
                    let span = self.span_from(start);
                    let id = self.ast.stmt(StmtKind::Let(binding), span);
                    stmts.push(id);
                }
                TokenKind::Return => {
                    let start = self.span();
                    self.bump();
                    let value = if self.at(TokenKind::Semi) || self.at(TokenKind::RBrace) {
                        None
                    } else {
                        Some(self.parse_expr())
                    };
                    self.eat(TokenKind::Semi);
                    let span = self.span_from(start);
                    let id = self.ast.stmt(StmtKind::Return(value), span);
                    stmts.push(id);
                }
                TokenKind::Fn
                | TokenKind::Space
                | TokenKind::Role
                | TokenKind::Type
                | TokenKind::Import
                | TokenKind::Struct
                | TokenKind::Enum => {
                    let start = self.span();
                    let item = self.parse_item();
                    let span = self.span_from(start);
                    let id = self.ast.stmt(StmtKind::Item(item), span);
                    stmts.push(id);
                }
                _ => {
                    let start = self.span();
                    let expr = self.parse_expr();
                    if self.at(TokenKind::RBrace) {
                        tail = Some(expr);
                        break;
                    }
                    self.eat(TokenKind::Semi);
                    let span = self.span_from(start);
                    let id = self.ast.stmt(StmtKind::Expr(expr), span);
                    stmts.push(id);
                }
            }

            if self.position() == before {
                // Nothing consumed: force progress so recovery terminates.
                let span = self.span();
                self.bump();
                let id = self.ast.stmt_from(
                    StmtKind::Error,
                    span,
                    Parser::recovered(Reason::SkippedTokens),
                );
                stmts.push(id);
            }
        }

        self.expect_close(TokenKind::RBrace, open.span);
        let span = self.span_from(open.span);
        self.ast.expr(ExprKind::Block { stmts, tail }, span)
    }
}

/// The reason an operation has the arity it has. These are the facts from the
/// semantics note, and they belong in the error rather than in a manual.
fn arity_rationale(op: VsaOp, variant: Option<VsaVariant>) -> &'static str {
    match (op, variant) {
        (VsaOp::Bind, _) => {
            "binding combines two or more vectors; with one operand there is nothing to bind it to"
        }
        (VsaOp::Bundle, Some(VsaVariant::Left)) => {
            "`bundle.left` folds pairwise from the left, so it needs at least two operands"
        }
        (VsaOp::Bundle, None) => "n-ary `bundle` superposes all its operands at once",
        (VsaOp::Permute, _) => "`permute(v)` shifts by one; `permute(v, k)` shifts by `k`",
        (VsaOp::Unbind, _) => "`unbind(v, key)` takes the vector and the key it was bound with",
        (VsaOp::Cleanup, _) => {
            "`cleanup(v)` projects onto the value's own space; `cleanup(v, S)` names the codebook \
             explicitly"
        }
        (VsaOp::Broadcast, _) => {
            "`broadcast(v, S)` takes the vector and the space to re-express it in"
        }
    }
}
