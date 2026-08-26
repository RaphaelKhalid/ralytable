//! Top-level declarations: GRAMMAR.md §2, §3, §4, §6.

use raly_ast::{
    Attr, FnDef, Ident, ImportDecl, ItemId, ItemKind, LetBinding, Param, Reason, RoleDecl,
    SpaceDecl, TypeAlias,
};
use raly_diag::{codes, Diagnostic};
use raly_lexer::TokenKind;

use crate::cursor::{Parser, ITEM_STARTS, PARAM_STOPS};

impl Parser<'_> {
    /// `Program = { Item } EOF`
    pub(crate) fn parse_program(&mut self) {
        while !self.at_eof() {
            let before = self.position();
            let item = self.parse_item();
            self.ast.root.push(item);
            if self.position() == before {
                // Defensive: no production may fail to consume a token, or
                // this loop would not terminate.
                let span = self.span();
                self.bump();
                let id = self.ast.item_from(
                    ItemKind::Error,
                    span,
                    Parser::recovered(Reason::SkippedTokens),
                );
                self.ast.root.push(id);
            }
        }
    }

    pub(crate) fn parse_item(&mut self) -> ItemId {
        match self.peek() {
            TokenKind::Import => self.parse_import(),
            TokenKind::Space => self.parse_space(),
            TokenKind::Role => self.parse_role(),
            TokenKind::Type => self.parse_type_alias(),
            TokenKind::Fn => self.parse_fn(),
            TokenKind::Let => self.parse_let_item(),
            TokenKind::Struct | TokenKind::Enum | TokenKind::Match | TokenKind::For => {
                self.parse_unimplemented_item()
            }
            _ => {
                let start = self.span();
                self.report_expected_item();
                let skipped = self.sync(ITEM_STARTS);
                self.ast.item_from(
                    ItemKind::Error,
                    start.merge(skipped),
                    Parser::recovered(Reason::UnexpectedToken),
                )
            }
        }
    }

    fn report_expected_item(&mut self) {
        if self.is_silenced() {
            return;
        }
        let found = self.peek();
        let mut diag = Diagnostic::error(
            codes::EXPECTED_ITEM,
            format!("expected a declaration, found {}", found.describe()),
        )
        .with_primary(self.span(), "not the start of a declaration")
        .with_note(
            "a Raly file is a sequence of `import`, `space`, `role`, `type`, `fn` and `let` \
             declarations",
        );
        if found == TokenKind::Ident {
            let text = self.text(self.span()).to_string();
            diag = diag.with_help(format!(
                "if `{text}` is meant to be a definition, it needs a keyword, e.g. `fn {text}(..)` \
                 or `let {text} = ..`"
            ));
        }
        self.push_silencing(diag);
    }

    /// A keyword that is reserved but whose construct is not implemented.
    fn parse_unimplemented_item(&mut self) -> ItemId {
        let token = self.bump();
        let word = self.text(token.span).to_string();
        let diag = Diagnostic::error(
            codes::UNIMPLEMENTED_CONSTRUCT,
            format!("`{word}` is reserved but not implemented yet"),
        )
        .with_primary(token.span, format!("`{word}` cannot be used yet"))
        .with_note(unimplemented_note(token.kind))
        .with_help("remove it for now; the keyword is reserved so that adding it later is not a breaking change");
        self.push_silencing(diag);
        let skipped = self.sync(ITEM_STARTS);
        self.ast.item_from(
            ItemKind::Error,
            token.span.merge(skipped),
            Parser::recovered(Reason::Unimplemented),
        )
    }

    /// `Import = "import" Path`
    fn parse_import(&mut self) -> ItemId {
        let start = self.span();
        self.bump();
        let path = self.parse_path_segments("after `import`");
        let span = self.span_from(start);
        self.ast.item(ItemKind::Import(ImportDecl { path }), span)
    }

    fn parse_path_segments(&mut self, purpose: &str) -> Vec<Ident> {
        let mut path = Vec::new();
        match self.expect(TokenKind::Ident, purpose) {
            Some(token) => path.push(self.ident_of(token)),
            None => return path,
        }
        while self.eat(TokenKind::ColonColon) {
            match self.expect(TokenKind::Ident, "after `::`") {
                Some(token) => path.push(self.ident_of(token)),
                None => break,
            }
        }
        path
    }

    /// `SpaceDecl = "space" IDENT "=" Family "[" Expr "]" [ WhereClause ]`
    fn parse_space(&mut self) -> ItemId {
        let start = self.span();
        self.bump();

        let name = match self.expect(TokenKind::Ident, "after `space`") {
            Some(token) => self.ident_of(token),
            None => {
                let at = self.after_prev();
                self.missing_ident(at)
            }
        };
        self.expect(TokenKind::Eq, "after the space name");

        let (family, dim) = self.parse_space_body(name);
        let attrs = self.parse_where_clause();

        let span = self.span_from(start);
        let origin = if family.is_some() && dim.is_some() {
            raly_ast::Origin::Source
        } else {
            Parser::recovered(Reason::MissingName)
        };
        self.ast.item_from(
            ItemKind::Space(SpaceDecl {
                name,
                family,
                dim,
                attrs,
            }),
            span,
            origin,
        )
    }

    /// The `MAP[8192]` half of a space declaration.
    ///
    /// The common mistake here is writing just the dimension, which is what
    /// the pre-grammar examples did. That gets its own diagnostic rather than
    /// a generic one, because the fix is not obvious from "expected an
    /// identifier".
    fn parse_space_body(&mut self, name: Ident) -> (Option<Ident>, Option<raly_ast::ExprId>) {
        if matches!(
            self.peek(),
            TokenKind::Int | TokenKind::Float | TokenKind::MalformedNumber
        ) {
            let dim_span = self.span();
            let dim_text = self.text(dim_span).to_string();
            let name_text = self.ast.text(name).to_string();
            let diag = Diagnostic::error(
                codes::BAD_SPACE_DECL,
                "a space needs a VSA family, not just a dimension",
            )
            .with_primary(dim_span, "this is the dimension; the family is missing")
            .with_secondary(name.span, format!("`{name_text}` is declared here"))
            .with_note(
                "`MAP<1024>` and `FHRR<1024>` are both 1024 numbers, and mixing them silently \
                 produces garbage; the family is part of a vector's identity",
            )
            .with_help(format!(
                "write `space {name_text} = MAP[{dim_text}]`, or one of `BSC`, `HRR`, `FHRR`"
            ));
            self.push_silencing(diag);
            let dim = self.parse_expr();
            return (None, Some(dim));
        }

        let family = match self.expect(TokenKind::Ident, "for the VSA family") {
            Some(token) => self.ident_of(token),
            None => return (None, None),
        };

        // Checked by hand rather than with `expect`, so that the specific
        // diagnostic below is the only one reported.
        let open = if self.at(TokenKind::LBracket) {
            Some(self.bump())
        } else {
            None
        };
        let Some(open) = open else {
            let name_text = self.ast.text(family).to_string();
            let diag = Diagnostic::error(
                codes::BAD_SPACE_DECL,
                format!("space family `{name_text}` is missing its dimension"),
            )
            .with_primary(self.after_prev(), "expected `[` and a dimension here")
            .with_note("capacity is derived from the dimension, so the dimension is mandatory")
            .with_help(format!("write `{name_text}[1024]`"));
            self.push_silencing(diag);
            return (Some(family), None);
        };

        let dim = self.parse_expr();
        self.expect_close(TokenKind::RBracket, open.span);
        (Some(family), Some(dim))
    }

    /// `RoleDecl = "role" IDENT%"," "in" IDENT`
    fn parse_role(&mut self) -> ItemId {
        let start = self.span();
        self.bump();

        let mut names = Vec::new();
        while let Some(token) = self.expect(TokenKind::Ident, "for a role name") {
            names.push(self.ident_of(token));
            if !self.eat(TokenKind::Comma) {
                break;
            }
        }

        let space = if self.eat(TokenKind::In) {
            self.expect(TokenKind::Ident, "for the space these roles belong to")
                .map(|token| self.ident_of(token))
        } else {
            let list = names
                .iter()
                .map(|n| self.ast.text(*n).to_string())
                .collect::<Vec<_>>()
                .join(", ");
            let diag = Diagnostic::error(
                codes::UNEXPECTED_TOKEN,
                format!("expected `in`, found {}", self.peek().describe()),
            )
            .with_primary(self.span(), "expected `in` and a space name")
            .with_note(
                "a role is an atom drawn from one space's codebook; the same name against a \
                 different codebook is a different, incomparable vector",
            )
            .with_help(if list.is_empty() {
                "write `role Name in SomeSpace`".to_string()
            } else {
                format!("write `role {list} in SomeSpace`")
            });
            self.push_silencing(diag);
            None
        };

        let span = self.span_from(start);
        let origin = if space.is_some() && !names.is_empty() {
            raly_ast::Origin::Source
        } else {
            Parser::recovered(Reason::MissingName)
        };
        self.ast
            .item_from(ItemKind::Role(RoleDecl { names, space }), span, origin)
    }

    /// `TypeAlias = "type" IDENT "=" Type`
    fn parse_type_alias(&mut self) -> ItemId {
        let start = self.span();
        self.bump();
        let name = match self.expect(TokenKind::Ident, "after `type`") {
            Some(token) => self.ident_of(token),
            None => {
                let at = self.after_prev();
                self.missing_ident(at)
            }
        };
        let ty = if self.expect(TokenKind::Eq, "after the type name").is_some() {
            Some(self.parse_type())
        } else {
            None
        };
        let span = self.span_from(start);
        self.ast
            .item(ItemKind::TypeAlias(TypeAlias { name, ty }), span)
    }

    /// `FnDef = "fn" IDENT "(" [ Param%"," ] ")" [ "->" Type ] [ WhereClause ] Block`
    fn parse_fn(&mut self) -> ItemId {
        let start = self.span();
        self.bump();

        let name = match self.expect(TokenKind::Ident, "after `fn`") {
            Some(token) => self.ident_of(token),
            None => {
                let at = self.after_prev();
                self.missing_ident(at)
            }
        };

        let params = self.parse_params();

        let return_type = if self.eat(TokenKind::Arrow) {
            Some(self.parse_type())
        } else {
            None
        };

        let attrs = self.parse_where_clause();

        let body = if self.at(TokenKind::LBrace) {
            Some(self.parse_block())
        } else {
            let name_text = self.ast.text(name).to_string();
            let diag = Diagnostic::error(
                codes::UNEXPECTED_TOKEN,
                format!(
                    "expected a body for `{name_text}`, found {}",
                    self.peek().describe()
                ),
            )
            .with_primary(self.after_prev(), "expected `{` here")
            .with_secondary(name.span, format!("`{name_text}` is declared here"))
            .with_help("every Raly function has a body; write `{ .. }`");
            self.push_silencing(diag);
            self.sync(ITEM_STARTS);
            None
        };

        let span = self.span_from(start);
        let origin = if body.is_some() {
            raly_ast::Origin::Source
        } else {
            Parser::recovered(Reason::MissingBody)
        };
        self.ast.item_from(
            ItemKind::Fn(FnDef {
                name,
                params,
                return_type,
                attrs,
                body,
            }),
            span,
            origin,
        )
    }

    fn parse_params(&mut self) -> Vec<Param> {
        let mut params = Vec::new();
        let Some(open) = self.expect(TokenKind::LParen, "to start the parameter list") else {
            return params;
        };

        loop {
            // `{` and `->` end the list whether or not a `)` was written: the
            // body is far more valuable to recover than the parameter is.
            if self.at(TokenKind::RParen)
                || self.at(TokenKind::LBrace)
                || self.at(TokenKind::Arrow)
                || self.at_eof()
            {
                break;
            }
            let before = self.position();
            params.push(self.parse_param());
            if !self.eat(TokenKind::Comma) {
                break;
            }
            if self.position() == before {
                break;
            }
        }
        self.expect_close(TokenKind::RParen, open.span);
        params
    }

    fn parse_param(&mut self) -> Param {
        let start = self.span();
        let name = match self.expect(TokenKind::Ident, "for a parameter name") {
            Some(token) => self.ident_of(token),
            None => {
                let at = self.after_prev();
                let ident = self.missing_ident(at);
                self.sync(PARAM_STOPS);
                return Param {
                    name: ident,
                    ty: None,
                    span: at,
                };
            }
        };

        let ty = if self.eat(TokenKind::Colon) {
            Some(self.parse_type())
        } else {
            let name_text = self.ast.text(name).to_string();
            let diag = Diagnostic::error(
                codes::MISSING_PARAM_TYPE,
                format!("parameter `{name_text}` has no type annotation"),
            )
            .with_primary(name.span, "expected `:` and a type after this")
            .with_note(
                "Raly does not infer parameter types: a vector's space, load and role schema are \
                 part of its type, and inferring them would move every error to the call site",
            )
            .with_help(format!(
                "annotate it, e.g. `{name_text}: Vec[Concepts]` or `{name_text}: Int`"
            ));
            self.push_silencing(diag);
            None
        };

        Param {
            name,
            ty,
            span: self.span_from(start),
        }
    }

    /// `LetItem = "let" [ "mut" ] IDENT [ ":" Type ] "=" Expr`
    fn parse_let_item(&mut self) -> ItemId {
        let start = self.span();
        let binding = self.parse_let_binding();
        let span = self.span_from(start);
        self.ast.item(ItemKind::Let(binding), span)
    }

    pub(crate) fn parse_let_binding(&mut self) -> LetBinding {
        self.bump(); // `let`
        let mutable = self.eat(TokenKind::Mut);

        let name = match self.expect(TokenKind::Ident, "after `let`") {
            Some(token) => self.ident_of(token),
            None => {
                let at = self.after_prev();
                self.missing_ident(at)
            }
        };

        let ty = if self.eat(TokenKind::Colon) {
            Some(self.parse_type())
        } else {
            None
        };

        let init = if self
            .expect(TokenKind::Eq, "to give the bound value")
            .is_some()
        {
            Some(self.parse_expr())
        } else {
            None
        };

        LetBinding {
            mutable,
            name,
            ty,
            init,
        }
    }

    /// `WhereClause = "where" Attr%","`
    pub(crate) fn parse_where_clause(&mut self) -> Vec<Attr> {
        let mut attrs = Vec::new();
        if !self.eat(TokenKind::Where) {
            return attrs;
        }
        loop {
            let start = self.span();
            let Some(token) = self.expect(TokenKind::Ident, "for an attribute name") else {
                break;
            };
            let name = self.ident_of(token);
            let value = if self
                .expect(TokenKind::Eq, "after the attribute name")
                .is_some()
            {
                Some(self.parse_expr())
            } else {
                None
            };
            let span = self.span_from(start);
            attrs.push(Attr { name, value, span });
            if !self.eat(TokenKind::Comma) {
                break;
            }
        }
        attrs
    }
}

fn unimplemented_note(kind: TokenKind) -> &'static str {
    match kind {
        TokenKind::For => {
            "a `for` loop that bundles one item per iteration is the canonical way to blow past a \
             space's capacity, so it stays out until the checker can count the iterations"
        }
        TokenKind::Match => "pattern syntax has not been designed yet",
        _ => "aggregate types have not been designed yet",
    }
}
