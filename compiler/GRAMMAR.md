# The Raly grammar

Status: **first concrete grammar.** This document is normative for
`raly-parse`; where the parser and this file disagree, one of them is a bug.

Raly describes models whose primitives are Vector Symbolic Architecture
operations. The grammar's job is to make the things the type system must track
— dimension, family, superposition load, and role schema — *visible in the
source*, and to make the algebra's sharp edges (non-associative bundling,
approximate unbinding, no bundle identity) impossible to write down by
accident.

Everything below is justified against
[`docs/semantics/vsa-and-discrete-ops.md`](../docs/semantics/vsa-and-discrete-ops.md),
cited as §n.

---

## 1. Notation

EBNF, with:

| Form | Meaning |
| --- | --- |
| `"x"` | the literal token `x` |
| `A B` | `A` followed by `B` |
| `A \| B` | `A` or `B` |
| `[ A ]` | zero or one `A` |
| `{ A }` | zero or more `A` |
| `( A )` | grouping |
| `A%","` | one or more `A` separated by `,`, with an optional trailing `,` |

Terminals in `UPPER_SNAKE` are lexer token classes (`IDENT`, `INT`, `FLOAT`,
`STR`). Comments (`// ...`) are trivia and may appear between any two tokens.

Raly is **not** whitespace sensitive. Statements inside a block are separated
by an optional `;`; see §8.

---

## 2. Compilation unit

```ebnf
Program   = { Item } EOF ;

Item      = Import
          | SpaceDecl
          | RoleDecl
          | TypeAlias
          | FnDef
          | LetItem ;
```

There is no visibility modifier and no module body. `import` names a path and
nothing resolves it yet, exactly as before.

```ebnf
Import    = "import" Path ;
Path      = IDENT { "::" IDENT } ;
```

---

## 3. Spaces

A **space** is the unit that fixes everything a vector's identity depends on:
the VSA family, the dimension, and (once codebooks exist) the codebook the
atoms are drawn from. §7.1 and §7.2 say family+dimension and codebook
provenance must be part of a vector's type; making the space a *named
declaration* rather than an inline type means a program can say `Concepts` in
fifty places and the compiler still knows all fifty are the same codebook.

```ebnf
SpaceDecl = "space" IDENT "=" Family "[" Expr "]" [ WhereClause ] ;
Family    = IDENT ;
```

```raly
space Concepts = MAP[8192]
space Phases   = FHRR[1024] where seed = 20260826, codebook = fixed
```

**Decisions.**

- **Family is a bare identifier, not a keyword.** `MAP`, `BSC`, `HRR`, `FHRR`
  are resolved by the checker against a builtin table. New families (matrix
  binding, VDTB — the non-commutative binds §1 says ordered structure requires)
  can then be added without a lexer change or a new reserved word.
- **The dimension slot is a full `Expr`, not an `INT`.** It must be a
  compile-time constant, but *constant folding is the checker's job*. Writing
  `MAP[2 * BASE_D]` should be a resolution question, not a parse error.
- **Capacity is never written.** There is no syntax for it anywhere in the
  language. §3 gives `M* = Θ(D / ln N)`; it is derived from the space, and a
  hand-written capacity would be a number that silently drifts out of agreement
  with the dimension sitting next to it.
- **`where` carries attributes, not constraints.** `where seed = 42` is a
  comma-separated list of `name = expr`. This is the extension point for
  codebook provenance and the `coherence: unknown` marking §7.2 asks for on
  learned codebooks, without committing to their spelling now.

```ebnf
WhereClause = "where" Attr%"," ;
Attr        = IDENT "=" Expr ;
```

---

## 4. Roles

Roles are the symbols used as binding keys. They are declared, not conjured
from strings, because §7.4 requires the compiler to know a vector's role schema
statically — and a role schema is only checkable if roles are a closed, named
set.

```ebnf
RoleDecl  = "role" IDENT%"," "in" IDENT ;
```

```raly
role Subject, Verb, Object in Concepts
```

**Decisions.**

- **A role belongs to a space.** A role is an atom drawn from that space's
  codebook; a `Concepts` role is meaningless against a `Phases` cleanup memory
  (§7.2). Making `in Space` mandatory means that mistake cannot be spelled.
- **One declaration, many names.** A realistic model declares eight or twelve
  roles in the same space. `role A, B, C in S` keeps that to one line and one
  AST node without inventing a block form.
- **`role` is a real keyword**, added to the lexer alongside `space`. A
  contextual keyword would let `role` also be a variable name, at the price of
  "expected an item, found an identifier" wherever the user typo'd a role
  declaration. Roles are core enough to spend a word on.

---

## 5. Types

This is the centre of the design. A Raly type annotation must be able to say:
*which space* (hence dimension, family, codebook), *how loaded* the
superposition is, and *which roles* are bound inside.

```ebnf
Type      = FnType | AppType ;

FnType    = "(" [ Type%"," ] ")" "->" Type ;

AppType   = Path [ "[" TypeArgs "]" ] ;

TypeArgs  = [ Type { "," Type } ] [ ";" TypeQual { ";" TypeQual } ] ;

TypeQual  = "load" Expr
          | "roles" "{" [ IDENT%"," ] "}"
          | "clean"
          | "noisy" ;
```

```raly
Sym[Concepts]                                    // one codebook atom
Vec[Concepts]                                    // a vector in Concepts
Vec[Concepts; load 3]                            // superposition of 3 items
Vec[Concepts; roles {Subject, Verb, Object}]     // a bound record
Vec[Concepts; load 3; roles {Subject, Verb, Object}; noisy]
(Sym[Concepts], Int) -> Vec[Concepts; load 1]
```

`load`, `roles`, `clean` and `noisy` are **contextual** — they are ordinary
identifiers everywhere except immediately after a `;` inside a type argument
list. They cost no reserved words and cannot be confused with anything, since
that position admits nothing else.

### 5.1 Why `[ ]` and not `< >`

The semantics doc writes `MAP<1024>`. The language does not, and the divergence
is deliberate: `<` and `>` are already comparison operators, and every language
that overloads them for type arguments pays for it — C++ with `>>`, Rust with
the turbofish, Java with a hand-written disambiguator. Raly is new enough to
simply not have the problem. `[ ]` is never an expression operator in Raly
(there is no indexing syntax), so a `[` in type position is unambiguous with
one token of lookahead and needs no backtracking.

### 5.2 Why `;` separates arguments from qualifiers

`Vec[Concepts, load 3]` reads as *two type arguments*. `Vec[Concepts; load 3]`
reads as *one type argument, then a qualification of it* — which is exactly
what it is. The precedent is Rust's `[T; N]`, where a semicolon separates two
different kinds of thing inside one bracket. Qualifiers are then `;`-separated
among themselves, so adding one never changes how the ones before it parse.

### 5.3 Why `load n` and not `load n of m`

§3: capacity is `Θ(D / ln N)`, a function of the space. The *n* is a fact about
this value; the *m* is a fact about its space, and the checker already knows the
space from the same annotation. `load 3 of 91` invites the `91` to drift. The
AST node reserves the capacity slot (`TypeQual::Load { count, capacity: None }`)
so the checker can fill it in and diagnostics can still render the familiar
`3 of 91`.

### 5.4 Why role schemas are brace-delimited sets

`roles {Subject, Verb, Object}` uses braces because it denotes a **set**, and
because §7.4 is emphatic that bind is commutative and therefore the keys of a
binding form a multiset in which *order carries no information*. Parentheses or
square brackets would suggest a sequence and invite users to believe the order
means something. It does not. The parser sorts the names into a canonical order
in the AST and reports duplicates (`RALY2009`).

### 5.5 `clean` / `noisy`

§7.6 wants cleanliness in the type: a value that has been unbound is noisy until
projected onto a codebook, and nested access without an intervening `cleanup` is
the documented footgun. The qualifier exists so the checker has somewhere to put
that; the grammar takes no position on the default.

### 5.6 Parameters must be annotated

```ebnf
Param     = IDENT ":" Type ;
```

There is no inference at a function boundary. A parameter with no annotation is
`RALY2006`, with a `help` naming the shape it wants. Whole-program inference for
a type carrying load and role schema would produce unexplainable errors at the
*use* site rather than at the definition, which is precisely the failure mode
Raly exists to avoid.

---

## 6. Functions and bindings

```ebnf
FnDef     = "fn" IDENT "(" [ Param%"," ] ")" [ "->" Type ] [ WhereClause ] Block ;

LetItem   = "let" [ "mut" ] IDENT [ ":" Type ] "=" Expr ;

TypeAlias = "type" IDENT "=" Type ;
```

`let` is both an item and a statement, with identical syntax. A top-level `let`
is a module constant.

---

## 7. The VSA operations

```ebnf
VsaExpr   = VsaOp [ "." IDENT ] "(" [ Expr%"," ] ")" ;
VsaOp     = "bind" | "bundle" | "permute" | "unbind" | "cleanup" ;
```

The five operations are **keywords with call syntax** — not identifiers, and not
infix operators. Three consequences, all wanted:

1. They cannot be shadowed, so `bundle` in a Raly program always means bundling.
2. The parser knows the arity rules and enforces them (below) with a dedicated
   diagnostic instead of a generic arity error much later.
3. **They are never infix.** This is the load-bearing decision. §2 shows
   normalized bundling is non-associative in *every* family and has no identity,
   and that bind is commutative in all four. An infix spelling would silently
   invite users to re-associate, re-order, and factor out identities the algebra
   does not have. Prefix n-ary call syntax has no associativity to assume.

### 7.1 Arity and variants

| Written | Arity | Rule |
| --- | --- | --- |
| `bind(a, b, ...)` | n ≥ 2 | associative and commutative (§2), so n-ary is well defined |
| `bundle(a, b, ...)` | n ≥ 1 | the **primitive**; `bundle()` is `RALY2003` |
| `bundle.left(a, b, ...)` | n ≥ 2 | the left-nested binary fold — a *different function* |
| `permute(v)` / `permute(v, k)` | 1 or 2 | `k` defaults to 1 |
| `unbind(v, k)` | 2 | |
| `cleanup(v)` / `cleanup(v, S)` | 1 or 2 | `S` names the codebook to project onto |

**`bundle()` is a parse error, not a zero vector.** §7.10: no bundle identity
exists in any discretized family, so an empty bundle has no value to denote. The
diagnostic says exactly that.

**`bundle.left` is the fold.** §2 and §7.8 require that if a binary fold is
offered at all, it be a *distinct, named, non-associative operator*, because
`bundle(bundle(a,b),c) ≠ bundle(a,b,c)` and in BSC it is measurably worse.
Spelling it as a variant of `bundle` rather than an unrelated word keeps the
relationship visible while making the difference unmissable at every call site,
and gives one obvious place to hang the warning the checker will want. Any other
variant — `bundle.foo`, `bind.left` — is `RALY2005`, listing the valid ones.

### 7.2 Canonical operand order

`bind` and `bundle` are commutative (§2). The AST therefore stores, alongside
the source-order operand list, a **canonical permutation** of the same operand
ids, sorted by a structural key of each operand subtree. Commutativity is then
structurally true rather than a law some later pass has to remember to apply,
and `bundle(a, b)` and `bundle(b, a)` compare equal without any pass doing work.
Source order is retained separately because diagnostics and any future formatter
need to point at what the user actually wrote.

`bundle.left` gets **no** canonical order — it is order-dependent by
construction. That asymmetry in the AST is the point.

---

## 8. Statements and expressions

```ebnf
Block     = "{" { Stmt } [ Expr ] "}" ;

Stmt      = LetItem [ ";" ]
          | "return" [ Expr ] [ ";" ]
          | Item
          | Expr [ ";" ] ;
```

### 8.1 Precedence

Pratt / precedence climbing, lowest binding first:

| Level | Operators | Associativity |
| --- | --- | --- |
| 1 | `\|>` | left |
| 2 | `==` `<` `<=` `>` `>=` | left |
| 3 | `+` `-` | left |
| 4 | `*` `/` | left |
| 5 | unary `-` `!` | prefix |
| 6 | `f(..)` `x.field` | postfix |

`^ ~ @ & \|` are lexed but are **not expression operators**. They are held in
reserve; using one is `RALY2001` with a note saying so. They are conspicuously
*not* aliases for the VSA operations, for the reason in §7.

### 8.2 The pipeline

```ebnf
Pipeline  = Expr "|>" Stage ;
```

`x |> f` means `f(x)`; `x |> f(a, b)` means `f(x, a, b)`; `x |> cleanup` means
`cleanup(x)`. The pipeline threads into the **first** argument, which is the
receiver position for every operation in §7 — so
`v |> unbind(Subject) |> cleanup` reads in the order the data moves, and is
exactly the shape §3 says nested access must have.

The pipeline is **kept as its own AST node** rather than desugared at parse
time. A desugared tree reports `unbind` arity errors against a call the user
never wrote.

### 8.3 Primary expressions

```ebnf
Primary   = INT | FLOAT | STR | "true" | "false"
          | Path
          | VsaExpr
          | "(" [ Expr%"," ] ")"        (* unit, group, or tuple *)
          | "[" [ Expr%"," ] "]"        (* list *)
          | Block
          | IfExpr ;

IfExpr    = "if" Expr Block [ "else" ( Block | IfExpr ) ] ;
```

Lists exist so that a *collection* of vectors is a different thing from a
superposition of them. §7.10's ill-typed `bundle([])` should be a type error
about lists, and it can only be one if lists are writable.

---

## 9. Reserved but unimplemented

`struct`, `enum`, `match` and `for` lex as keywords and parse to a dedicated
"recognised but not yet implemented" error (`RALY2007`) naming the construct,
rather than falling out as a confusing "expected an item". `for` in particular
is §3's canonical broken program — a loop that bundles one item per timestep
past capacity — and will not be added until the checker can count.

---

## 10. Error recovery

The parser **always returns a tree**. There is no `Result`. Recovery is:

- **Panic-mode with synchronisation sets.** On an unexpected token the parser
  emits one diagnostic, then skips tokens until it reaches a token that can
  start the enclosing construct's next element (`fn`, `let`, `space`, `role`,
  `type`, `import`, `}`, `;`) or EOF.
- **Bracket-aware skipping.** Skipping tracks `(`/`[`/`{` depth, so a stray
  token inside a nested call does not abandon the whole item.
- **Error nodes, spanned.** Every skipped region becomes an `Error` node
  covering exactly the tokens skipped. The tree is *total* over the input: every
  significant token lies inside some node's span.
- **Provenance.** Every node records an `Origin` — either `Source`, or
  `Recovered(reason)` naming the recovery decision that produced it. The checker
  uses this to avoid blaming a node the user never wrote.
- **One diagnostic per cause.** After an error the parser suppresses further
  "unexpected token" reports until it has consumed at least one token
  successfully, so a single mistake cannot cascade into ten messages.

### Diagnostic codes

| Code | Meaning |
| --- | --- |
| `RALY2001` | unexpected token |
| `RALY2002` | unclosed delimiter |
| `RALY2003` | `bundle()` with no operands |
| `RALY2004` | a VSA operation given the wrong number of operands |
| `RALY2005` | unknown operation variant |
| `RALY2006` | a parameter with no type annotation |
| `RALY2007` | a reserved construct that is not implemented yet |
| `RALY2008` | unknown type qualifier |
| `RALY2009` | a role repeated in one role schema |
| `RALY2010` | a `space` declaration missing its family or dimension |
| `RALY2011` | expected an item at the top level |

---

## 11. A whole program

```raly
// A three-role scene encoder, and the query that reads it back.

space Concepts = MAP[8192] where seed = 20260826

role Subject, Verb, Object in Concepts

type Scene = Vec[Concepts; load 3; roles {Subject, Verb, Object}]

fn encode(s: Sym[Concepts], v: Sym[Concepts], o: Sym[Concepts]) -> Scene {
    bundle(
        bind(Subject, s),
        bind(Verb, v),
        bind(Object, o),
    )
}

fn subject_of(scene: Scene) -> Sym[Concepts] {
    scene |> unbind(Subject) |> cleanup(Concepts)
}

fn ordered_pair(a: Sym[Concepts], b: Sym[Concepts]) -> Vec[Concepts; load 2] {
    // bind is commutative, so order must come from permute -- see §1 of the
    // semantics note. bind(a, b) and bind(b, a) are the same vector.
    bundle(a, permute(b, 1))
}
```
