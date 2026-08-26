//! Type syntax: GRAMMAR.md §5.
//!
//! The whole point of Raly's types is that they carry more than a shape — a
//! space (hence family and dimension), a superposition load, and a role
//! schema. That makes this the most important production in the grammar, and
//! the one whose diagnostics are worth the most effort.

use raly_ast::{Ident, TypeExprId, TypeExprKind, TypeQual};
use raly_diag::{codes, Diagnostic, Span};
use raly_lexer::TokenKind;

use crate::cursor::Parser;

impl Parser<'_> {
    /// `Type = FnType | AppType`
    pub(crate) fn parse_type(&mut self) -> TypeExprId {
        if self.at(TokenKind::LParen) {
            return self.parse_paren_type();
        }
        self.parse_app_type()
    }

    /// `( )`, `( T )`, `( T, U )` and `( T, U ) -> V`.
    fn parse_paren_type(&mut self) -> TypeExprId {
        let open = self.bump();
        let mut elems = Vec::new();
        let mut trailing_comma = false;

        while !self.at(TokenKind::RParen) && !self.at_eof() {
            let before = self.position();
            elems.push(self.parse_type());
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

        if self.eat(TokenKind::Arrow) {
            let ret = self.parse_type();
            let span = self.span_from(open.span);
            return self.ast.type_expr(
                TypeExprKind::Fn {
                    params: elems,
                    ret: Some(ret),
                },
                span,
            );
        }

        // `(T)` is just `T`; only `()` and `(T, U)` are tuples.
        if elems.len() == 1 && !trailing_comma {
            return elems[0];
        }
        let span = self.span_from(open.span);
        self.ast.type_expr(TypeExprKind::Tuple(elems), span)
    }

    /// `AppType = Path [ "[" TypeArgs "]" ]`
    fn parse_app_type(&mut self) -> TypeExprId {
        let start = self.span();
        let Some(first) = self.expect(TokenKind::Ident, "for a type name") else {
            let span = self.after_prev();
            return self.ast.type_expr_from(
                TypeExprKind::Error,
                span,
                Parser::recovered(raly_ast::Reason::MissingType),
            );
        };

        let mut path = vec![self.ident_of(first)];
        while self.eat(TokenKind::ColonColon) {
            match self.expect(TokenKind::Ident, "after `::`") {
                Some(token) => path.push(self.ident_of(token)),
                None => break,
            }
        }

        let (args, quals) = if self.at(TokenKind::LBracket) {
            self.parse_type_args()
        } else {
            (Vec::new(), Vec::new())
        };

        let span = self.span_from(start);
        self.ast
            .type_expr(TypeExprKind::Named { path, args, quals }, span)
    }

    /// `TypeArgs = [ Type { "," Type } ] [ ";" TypeQual { ";" TypeQual } ]`
    fn parse_type_args(&mut self) -> (Vec<TypeExprId>, Vec<TypeQual>) {
        let open = self.bump();
        let mut args = Vec::new();
        let mut quals = Vec::new();

        while !self.at(TokenKind::RBracket) && !self.at(TokenKind::Semi) && !self.at_eof() {
            let before = self.position();
            args.push(self.parse_type());
            if !self.eat(TokenKind::Comma) {
                break;
            }
            if self.position() == before {
                break;
            }
        }

        while self.eat(TokenKind::Semi) {
            let before = self.position();
            quals.push(self.parse_type_qual());
            if self.position() == before {
                break;
            }
        }

        self.expect_close(TokenKind::RBracket, open.span);
        (args, quals)
    }

    /// `TypeQual = "load" Expr | "roles" "{" [ IDENT%"," ] "}" | "clean" | "noisy"`
    ///
    /// The qualifier names are contextual: they are ordinary identifiers
    /// anywhere else, and cost no reserved words, because nothing else may
    /// appear in this position.
    fn parse_type_qual(&mut self) -> TypeQual {
        let start = self.span();
        let Some(token) = self.expect(TokenKind::Ident, "for a type qualifier") else {
            return TypeQual::Error(self.after_prev());
        };

        match self.text(token.span) {
            "load" => {
                let count = self.parse_expr();
                TypeQual::Load {
                    count: Some(count),
                    // Never written by hand: capacity is a function of the
                    // space's dimension and is filled in by the checker.
                    capacity: None,
                    span: self.span_from(start),
                }
            }
            "roles" => self.parse_role_schema(start),
            "clean" => TypeQual::Clean(token.span),
            "noisy" => TypeQual::Noisy(token.span),
            other => {
                let other = other.to_string();
                let mut diag = Diagnostic::error(
                    codes::UNKNOWN_TYPE_QUALIFIER,
                    format!("unknown type qualifier `{other}`"),
                )
                .with_primary(token.span, "not a recognised qualifier")
                .with_note(format!(
                    "the qualifiers are {}",
                    TypeQual::KEYWORDS
                        .iter()
                        .map(|k| format!("`{k}`"))
                        .collect::<Vec<_>>()
                        .join(", ")
                ));
                if let Some(suggestion) = nearest(&other, TypeQual::KEYWORDS) {
                    diag = diag.with_help(format!("did you mean `{suggestion}`?"));
                } else {
                    diag = diag.with_help(
                        "write the load as `load 3` and the role schema as `roles {A, B}`",
                    );
                }
                self.push_silencing(diag);
                self.sync(&[TokenKind::Semi, TokenKind::RBracket]);
                TypeQual::Error(self.span_from(start))
            }
        }
    }

    /// `roles {Subject, Verb, Object}`
    ///
    /// Braces because this is a *set*: binding is commutative, so the order
    /// of the keys carries no information (GRAMMAR.md §5.4). The parser sorts
    /// the names, keeps the source order alongside, and reports repeats.
    fn parse_role_schema(&mut self, start: Span) -> TypeQual {
        let Some(open) = self.expect(TokenKind::LBrace, "to start the role schema") else {
            return TypeQual::Error(self.span_from(start));
        };

        let mut written: Vec<Ident> = Vec::new();
        while !self.at(TokenKind::RBrace) && !self.at_eof() {
            let Some(token) = self.expect(TokenKind::Ident, "for a role name") else {
                break;
            };
            let ident = self.ident_of(token);
            if let Some(first) = written.iter().find(|w| w.symbol == ident.symbol) {
                let name = self.ast.text(ident).to_string();
                let diag = Diagnostic::error(
                    codes::DUPLICATE_ROLE,
                    format!("role `{name}` appears twice in this schema"),
                )
                .with_primary(ident.span, "repeated here")
                .with_secondary(first.span, "first named here")
                .with_note(
                    "a role schema is a set: binding is commutative, so a role is either present \
                     or absent and cannot be present twice",
                )
                .with_help(format!("remove one of the two `{name}`s"));
                self.push(diag);
            } else {
                written.push(ident);
            }
            if !self.eat(TokenKind::Comma) {
                break;
            }
        }
        self.expect_close(TokenKind::RBrace, open.span);

        let mut names = written.clone();
        names.sort_by_key(|n| n.symbol);
        TypeQual::Roles {
            names,
            written,
            span: self.span_from(start),
        }
    }
}

/// The closest candidate within edit distance 2, for "did you mean".
fn nearest<'k>(word: &str, candidates: &[&'k str]) -> Option<&'k str> {
    candidates
        .iter()
        .map(|c| (edit_distance(word, c), *c))
        .filter(|(d, _)| *d <= 2)
        .min_by_key(|(d, _)| *d)
        .map(|(_, c)| c)
}

/// Levenshtein distance, two rows at a time.
fn edit_distance(a: &str, b: &str) -> usize {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    let mut prev: Vec<usize> = (0..=b.len()).collect();
    let mut curr = vec![0usize; b.len() + 1];
    for (i, ca) in a.iter().enumerate() {
        curr[0] = i + 1;
        for (j, cb) in b.iter().enumerate() {
            let cost = usize::from(ca != cb);
            curr[j + 1] = (prev[j + 1] + 1).min(curr[j] + 1).min(prev[j] + cost);
        }
        std::mem::swap(&mut prev, &mut curr);
    }
    prev[b.len()]
}
