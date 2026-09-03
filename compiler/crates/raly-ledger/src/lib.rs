//! A typed, content-addressed sidecar over the Raly front end.
//!
//! The ledger does not replace the AST. It gives each expression a semantic
//! address derived from its operation, semantic parameters, ordered inputs,
//! and inferred type. Source spans and bound-name spellings are retained as
//! provenance but deliberately excluded from the address.
//!
//! This first runtime slice executes pure top-level constants made from
//! integers, booleans, strings, lists, tuples, unary operators, and integer
//! arithmetic/comparisons. Unsupported nodes remain inspectable and fail
//! explicitly if execution reaches them.

#![deny(missing_debug_implementations)]

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fmt;
use std::fmt::Write as _;

use raly_ast::{Ast, ExprId, ExprKind, ItemKind, Literal, Origin, StmtKind, VsaVariant};
use raly_diag::Span;
use raly_resolve::{DefId, Resolved};
use raly_types::{Checked, Ty};

const HASH_SEED: u64 = 0xcbf2_9ce4_8422_2325;
const HASH_PRIME: u64 = 0x0000_0100_0000_01b3;

/// A deterministic, collision-checked address for semantic ledger content.
///
/// This is an identity key, not a cryptographic commitment. The builder keeps
/// the canonical payload beside every key and rejects a collision rather than
/// silently merging distinct nodes.
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct SemanticId(pub u64);

impl fmt::Debug for SemanticId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "s{:016x}", self.0)
    }
}

impl fmt::Display for SemanticId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "s{:016x}", self.0)
    }
}

/// One source occurrence of a semantic node.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct SourceRef {
    pub expr: ExprId,
    pub span: Span,
    pub origin: Origin,
}

/// One unique semantic expression in the ledger.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct LedgerNode {
    pub id: SemanticId,
    pub operation: String,
    pub parameters: Vec<String>,
    pub inputs: Vec<SemanticId>,
    pub output_type: String,
    pub sources: Vec<SourceRef>,
}

/// A sidecar graph plus the mapping back to the parser's arena ids.
#[derive(Debug)]
pub struct Ledger {
    nodes: Vec<LedgerNode>,
    positions: BTreeMap<SemanticId, usize>,
    expr_ids: HashMap<u32, SemanticId>,
}

impl Ledger {
    /// Materialize every expression in a checked file without changing the
    /// AST, resolver, or type-checker outputs.
    pub fn build(ast: &Ast, resolved: &Resolved, checked: &Checked) -> Result<Self, BuildError> {
        let ids: Vec<ExprId> = ast.exprs.ids().collect();
        let mut builder = Builder {
            ast,
            resolved,
            checked,
            nodes: Vec::new(),
            positions: BTreeMap::new(),
            expr_ids: HashMap::new(),
            payloads: BTreeMap::new(),
            active: BTreeSet::new(),
        };
        for id in ids {
            builder.materialize(id)?;
        }
        Ok(Ledger {
            nodes: builder.nodes,
            positions: builder.positions,
            expr_ids: builder.expr_ids,
        })
    }

    pub fn nodes(&self) -> &[LedgerNode] {
        &self.nodes
    }

    pub fn id_for_expr(&self, expr: ExprId) -> Option<SemanticId> {
        self.expr_ids.get(&expr.raw()).copied()
    }

    pub fn node(&self, id: SemanticId) -> Option<&LedgerNode> {
        self.positions
            .get(&id)
            .and_then(|&index| self.nodes.get(index))
    }

    /// Execute all pure top-level constant bindings in source order.
    pub fn execute_constants(
        &self,
        ast: &Ast,
        resolved: &Resolved,
    ) -> Result<Execution, ExecError> {
        let mut interpreter = Interpreter::new(self);
        for &item in &ast.root {
            let ItemKind::Let(binding) = &ast.items[item].kind else {
                continue;
            };
            let Some(initializer) = binding.init else {
                continue;
            };
            let def = resolved.def_of_item(item).unwrap_or(DefId::ERROR);
            if def == DefId::ERROR {
                return Err(ExecError::UnresolvedBinding(def));
            }
            let root = self
                .id_for_expr(initializer)
                .ok_or(ExecError::MissingExpression(initializer.raw()))?;
            let value = interpreter.evaluate(root)?;
            interpreter.bindings.insert(def, value.clone());
            interpreter.constants.push(ConstantValue {
                def,
                name: ast.text(binding.name).to_string(),
                value,
                root,
            });
        }
        Ok(Execution {
            constants: interpreter.constants,
            receipts: interpreter.receipts,
        })
    }

    /// Re-execute a module and return the first receipt that differs.
    pub fn verify_replay(
        &self,
        ast: &Ast,
        resolved: &Resolved,
        expected: &[Receipt],
    ) -> Result<(), ReplayError> {
        let actual = self
            .execute_constants(ast, resolved)
            .map_err(ReplayError::Execution)?;
        for (index, (actual_receipt, expected_receipt)) in
            actual.receipts.iter().zip(expected).enumerate()
        {
            if actual_receipt != expected_receipt {
                return Err(ReplayError::Diverged {
                    index,
                    expected: expected_receipt.clone(),
                    actual: actual_receipt.clone(),
                });
            }
        }
        if actual.receipts.len() != expected.len() {
            return Err(ReplayError::Length {
                expected: expected.len(),
                actual: actual.receipts.len(),
            });
        }
        Ok(())
    }
}

/// A value supported by the first effect-free interpreter.
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum Value {
    Int(i64),
    Bool(bool),
    Str(String),
    List(Vec<Value>),
    Tuple(Vec<Value>),
}

impl fmt::Display for Value {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Value::Int(value) => write!(f, "{value}"),
            Value::Bool(value) => write!(f, "{value}"),
            Value::Str(value) => write!(f, "\"{value}\""),
            Value::List(items) => write_values(f, "[", "]", items),
            Value::Tuple(items) => write_values(f, "(", ")", items),
        }
    }
}

fn write_values(
    f: &mut fmt::Formatter<'_>,
    open: &str,
    close: &str,
    items: &[Value],
) -> fmt::Result {
    f.write_str(open)?;
    for (index, item) in items.iter().enumerate() {
        if index > 0 {
            f.write_str(", ")?;
        }
        write!(f, "{item}")?;
    }
    f.write_str(close)
}

#[derive(Clone, PartialEq, Eq, Debug)]
pub struct ConstantValue {
    pub def: DefId,
    pub name: String,
    pub value: Value,
    pub root: SemanticId,
}

#[derive(Clone, PartialEq, Eq, Debug)]
pub struct Execution {
    pub constants: Vec<ConstantValue>,
    pub receipts: Vec<Receipt>,
}

impl Execution {
    /// Render the execution and its receipts as deterministic, typed JSON.
    ///
    /// Hashes are strings rather than JSON numbers because their full 64-bit
    /// values cannot be represented exactly by JavaScript's number type.
    pub fn json(&self) -> String {
        let mut out = String::from("{\n  \"schema\": \"raly.execution.v1\",\n  \"constants\": [\n");
        for (index, constant) in self.constants.iter().enumerate() {
            let comma = if index + 1 < self.constants.len() {
                ","
            } else {
                ""
            };
            let _ = writeln!(
                out,
                "    {{\"name\": {}, \"root\": \"{}\", \"value\": {}}}{comma}",
                json_quote(&constant.name),
                constant.root,
                value_json(&constant.value)
            );
        }
        out.push_str("  ],\n  \"receipts\": [\n");
        for (index, receipt) in self.receipts.iter().enumerate() {
            let comma = if index + 1 < self.receipts.len() {
                ","
            } else {
                ""
            };
            let _ = writeln!(
                out,
                "    {{\"node\": \"{}\", \"before\": \"{:016x}\", \"after\": \"{:016x}\", \"value\": \"{:016x}\"}}{comma}",
                receipt.node, receipt.before, receipt.after, receipt.value
            );
        }
        out.push_str("  ]\n}\n");
        out
    }
}

/// A per-node execution receipt over ordered state before and after the step.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct Receipt {
    pub node: SemanticId,
    pub before: u64,
    pub after: u64,
    pub value: u64,
}

fn value_json(value: &Value) -> String {
    match value {
        Value::Int(value) => format!("{{\"kind\": \"int\", \"value\": {value}}}"),
        Value::Bool(value) => format!("{{\"kind\": \"bool\", \"value\": {value}}}"),
        Value::Str(value) => format!("{{\"kind\": \"string\", \"value\": {}}}", json_quote(value)),
        Value::List(items) => collection_json("list", items),
        Value::Tuple(items) => collection_json("tuple", items),
    }
}

fn collection_json(kind: &str, items: &[Value]) -> String {
    let items = items.iter().map(value_json).collect::<Vec<_>>().join(", ");
    format!("{{\"kind\": \"{kind}\", \"items\": [{items}]}}")
}

fn json_quote(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    out.push('"');
    for ch in text.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            ch if (ch as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", ch as u32);
            }
            ch => out.push(ch),
        }
    }
    out.push('"');
    out
}

#[derive(Clone, PartialEq, Eq, Debug)]
pub enum BuildError {
    Cycle(u32),
    AddressCollision(SemanticId),
}

impl fmt::Display for BuildError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            BuildError::Cycle(expr) => write!(f, "expression {expr} forms an AST cycle"),
            BuildError::AddressCollision(id) => {
                write!(f, "two different ledger nodes produced address {id}")
            }
        }
    }
}

impl std::error::Error for BuildError {}

#[derive(Clone, PartialEq, Eq, Debug)]
pub enum ExecError {
    MissingNode(SemanticId),
    MissingExpression(u32),
    UnresolvedBinding(DefId),
    Unbound(DefId),
    Unsupported {
        node: SemanticId,
        operation: String,
    },
    InvalidLiteral {
        node: SemanticId,
        text: String,
    },
    Type {
        node: SemanticId,
        message: &'static str,
    },
    Cycle(SemanticId),
}

impl fmt::Display for ExecError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ExecError::MissingNode(id) => write!(f, "ledger node {id} is missing"),
            ExecError::MissingExpression(id) => write!(f, "expression {id} is not in the ledger"),
            ExecError::UnresolvedBinding(id) => write!(f, "binding {id:?} did not resolve"),
            ExecError::Unbound(id) => write!(f, "binding {id:?} has no runtime value"),
            ExecError::Unsupported { node, operation } => {
                write!(
                    f,
                    "ledger node {node} uses unsupported operation `{operation}`"
                )
            }
            ExecError::InvalidLiteral { node, text } => {
                write!(f, "ledger node {node} has invalid literal `{text}`")
            }
            ExecError::Type { node, message } => write!(f, "ledger node {node}: {message}"),
            ExecError::Cycle(id) => write!(f, "ledger execution reached a cycle at {id}"),
        }
    }
}

impl std::error::Error for ExecError {}

#[derive(Clone, PartialEq, Eq, Debug)]
pub enum ReplayError {
    Execution(ExecError),
    Diverged {
        index: usize,
        expected: Receipt,
        actual: Receipt,
    },
    Length {
        expected: usize,
        actual: usize,
    },
}

impl fmt::Display for ReplayError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ReplayError::Execution(error) => write!(f, "replay could not execute: {error}"),
            ReplayError::Diverged { index, .. } => write!(f, "replay diverged at receipt {index}"),
            ReplayError::Length { expected, actual } => {
                write!(f, "replay produced {actual} receipts; expected {expected}")
            }
        }
    }
}

impl std::error::Error for ReplayError {}

struct Builder<'a> {
    ast: &'a Ast,
    resolved: &'a Resolved,
    checked: &'a Checked,
    nodes: Vec<LedgerNode>,
    positions: BTreeMap<SemanticId, usize>,
    expr_ids: HashMap<u32, SemanticId>,
    payloads: BTreeMap<SemanticId, String>,
    active: BTreeSet<u32>,
}

impl Builder<'_> {
    fn materialize(&mut self, expr_id: ExprId) -> Result<SemanticId, BuildError> {
        if let Some(id) = self.expr_ids.get(&expr_id.raw()) {
            return Ok(*id);
        }
        if !self.active.insert(expr_id.raw()) {
            return Err(BuildError::Cycle(expr_id.raw()));
        }
        let expr = &self.ast.exprs[expr_id];
        let (operation, parameters, child_exprs) = self.shape(expr_id);
        let mut inputs = Vec::with_capacity(child_exprs.len());
        for child in child_exprs {
            inputs.push(self.materialize(child)?);
        }
        if operation == "vsa.bind" || operation == "vsa.bundle" {
            inputs.sort_unstable();
        }
        let output_type = self
            .checked
            .type_of(expr_id)
            .map(type_key)
            .unwrap_or_else(|| "unknown".to_string());
        let payload = canonical_payload(&operation, &parameters, &inputs, &output_type);
        let semantic_id = SemanticId(stable_hash(payload.as_bytes()));
        if let Some(existing) = self.payloads.get(&semantic_id) {
            if existing != &payload {
                return Err(BuildError::AddressCollision(semantic_id));
            }
            let position = self.positions[&semantic_id];
            self.nodes[position].sources.push(SourceRef {
                expr: expr_id,
                span: expr.span,
                origin: expr.origin,
            });
        } else {
            let position = self.nodes.len();
            self.payloads.insert(semantic_id, payload);
            self.positions.insert(semantic_id, position);
            self.nodes.push(LedgerNode {
                id: semantic_id,
                operation,
                parameters,
                inputs,
                output_type,
                sources: vec![SourceRef {
                    expr: expr_id,
                    span: expr.span,
                    origin: expr.origin,
                }],
            });
        }
        self.active.remove(&expr_id.raw());
        self.expr_ids.insert(expr_id.raw(), semantic_id);
        Ok(semantic_id)
    }

    fn shape(&self, id: ExprId) -> (String, Vec<String>, Vec<ExprId>) {
        match &self.ast.exprs[id].kind {
            ExprKind::Literal(literal) => literal_shape(self.ast, *literal),
            ExprKind::Path(segments) => {
                let def = self.resolved.expr_ref(id).unwrap_or(DefId::ERROR);
                (
                    "path".to_string(),
                    vec![
                        format!("binder:{}", def.0),
                        format!("segments:{}", segments.len()),
                    ],
                    Vec::new(),
                )
            }
            ExprKind::Group(inner) => ("group".to_string(), Vec::new(), vec![*inner]),
            ExprKind::Unary { op, operand, .. } => (
                format!("unary.{}", op.spelling()),
                Vec::new(),
                vec![*operand],
            ),
            ExprKind::Binary { op, lhs, rhs, .. } => (
                format!("binary.{}", op.spelling()),
                Vec::new(),
                vec![*lhs, *rhs],
            ),
            ExprKind::Pipeline { value, stage, .. } => {
                ("pipeline".to_string(), Vec::new(), vec![*value, *stage])
            }
            ExprKind::Call { callee, args } => {
                let mut children = vec![*callee];
                children.extend(args.iter().copied());
                ("call".to_string(), Vec::new(), children)
            }
            ExprKind::Field { base, name } => (
                "field".to_string(),
                vec![self.ast.text(*name).to_string()],
                vec![*base],
            ),
            ExprKind::Vsa(call) => {
                let operation = match call.variant_kind {
                    Some(VsaVariant::Left) => format!("vsa.{}.left", call.op.name()),
                    None => format!("vsa.{}", call.op.name()),
                };
                (operation, Vec::new(), call.operands().to_vec())
            }
            ExprKind::List(items) => ("list".to_string(), Vec::new(), items.clone()),
            ExprKind::Tuple(items) => ("tuple".to_string(), Vec::new(), items.clone()),
            ExprKind::Block { stmts, tail } => {
                let mut parameters = Vec::new();
                let mut children = Vec::new();
                for stmt in stmts {
                    match &self.ast.stmts[*stmt].kind {
                        StmtKind::Let(binding) => {
                            parameters.push("let".to_string());
                            children.extend(binding.init);
                        }
                        StmtKind::Return(value) => {
                            parameters.push("return".to_string());
                            children.extend(*value);
                        }
                        StmtKind::Expr(value) => {
                            parameters.push("expr".to_string());
                            children.push(*value);
                        }
                        StmtKind::Item(_) => parameters.push("item".to_string()),
                        StmtKind::Error => parameters.push("error".to_string()),
                    }
                }
                if let Some(tail) = tail {
                    parameters.push("tail".to_string());
                    children.push(*tail);
                }
                ("block".to_string(), parameters, children)
            }
            ExprKind::If {
                cond,
                then_block,
                else_branch,
            } => {
                let mut children = vec![*cond, *then_block];
                children.extend(*else_branch);
                ("if".to_string(), Vec::new(), children)
            }
            ExprKind::Error => ("error".to_string(), Vec::new(), Vec::new()),
        }
    }
}

fn literal_shape(ast: &Ast, literal: Literal) -> (String, Vec<String>, Vec<ExprId>) {
    match literal {
        Literal::Int(symbol) => (
            "literal.int".to_string(),
            vec![ast.names.resolve(symbol).replace('_', "")],
            Vec::new(),
        ),
        Literal::Float(symbol) => (
            "literal.float".to_string(),
            vec![ast.names.resolve(symbol).replace('_', "")],
            Vec::new(),
        ),
        Literal::Str(symbol) => (
            "literal.str".to_string(),
            vec![ast.names.resolve(symbol).to_string()],
            Vec::new(),
        ),
        Literal::Bool(value) => (
            "literal.bool".to_string(),
            vec![value.to_string()],
            Vec::new(),
        ),
    }
}

struct Interpreter<'a> {
    ledger: &'a Ledger,
    bindings: BTreeMap<DefId, Value>,
    values: BTreeMap<SemanticId, Value>,
    active: BTreeSet<SemanticId>,
    constants: Vec<ConstantValue>,
    receipts: Vec<Receipt>,
}

impl<'a> Interpreter<'a> {
    fn new(ledger: &'a Ledger) -> Self {
        Self {
            ledger,
            bindings: BTreeMap::new(),
            values: BTreeMap::new(),
            active: BTreeSet::new(),
            constants: Vec::new(),
            receipts: Vec::new(),
        }
    }

    fn evaluate(&mut self, id: SemanticId) -> Result<Value, ExecError> {
        if let Some(value) = self.values.get(&id) {
            return Ok(value.clone());
        }
        if !self.active.insert(id) {
            return Err(ExecError::Cycle(id));
        }
        let node = self.ledger.node(id).ok_or(ExecError::MissingNode(id))?;
        let mut inputs = Vec::with_capacity(node.inputs.len());
        for input in &node.inputs {
            inputs.push(self.evaluate(*input)?);
        }
        let value = evaluate_node(node, &inputs, &self.bindings)?;
        let before = state_hash(&self.values);
        self.values.insert(id, value.clone());
        let after = state_hash(&self.values);
        self.receipts.push(Receipt {
            node: id,
            before,
            after,
            value: stable_hash(value_key(&value).as_bytes()),
        });
        self.active.remove(&id);
        Ok(value)
    }
}

fn evaluate_node(
    node: &LedgerNode,
    inputs: &[Value],
    bindings: &BTreeMap<DefId, Value>,
) -> Result<Value, ExecError> {
    let type_error = |message| ExecError::Type {
        node: node.id,
        message,
    };
    match node.operation.as_str() {
        "literal.int" => node.parameters[0]
            .parse::<i64>()
            .map(Value::Int)
            .map_err(|_| ExecError::InvalidLiteral {
                node: node.id,
                text: node.parameters[0].clone(),
            }),
        "literal.bool" => Ok(Value::Bool(node.parameters[0] == "true")),
        "literal.str" => Ok(Value::Str(node.parameters[0].clone())),
        "path" => {
            let raw = node.parameters[0]
                .strip_prefix("binder:")
                .and_then(|value| value.parse::<u32>().ok())
                .unwrap_or(DefId::ERROR.0);
            let def = DefId(raw);
            bindings.get(&def).cloned().ok_or(ExecError::Unbound(def))
        }
        "group" => inputs
            .first()
            .cloned()
            .ok_or_else(|| type_error("group has no value")),
        "unary.-" => match inputs {
            [Value::Int(value)] => value
                .checked_neg()
                .map(Value::Int)
                .ok_or_else(|| type_error("integer negation overflowed")),
            _ => Err(type_error("integer negation expected one integer")),
        },
        "unary.!" => match inputs {
            [Value::Bool(value)] => Ok(Value::Bool(!value)),
            _ => Err(type_error("boolean negation expected one boolean")),
        },
        "binary.+" | "binary.-" | "binary.*" | "binary./" => {
            let [Value::Int(left), Value::Int(right)] = inputs else {
                return Err(type_error("integer arithmetic expected two integers"));
            };
            let result = match node.operation.as_str() {
                "binary.+" => left.checked_add(*right),
                "binary.-" => left.checked_sub(*right),
                "binary.*" => left.checked_mul(*right),
                "binary./" => left.checked_div(*right),
                _ => unreachable!(),
            };
            result
                .map(Value::Int)
                .ok_or_else(|| type_error("integer arithmetic failed or overflowed"))
        }
        "binary.==" => match inputs {
            [left, right] => Ok(Value::Bool(left == right)),
            _ => Err(type_error("equality expected two values")),
        },
        "binary.<" | "binary.<=" | "binary.>" | "binary.>=" => {
            let [Value::Int(left), Value::Int(right)] = inputs else {
                return Err(type_error("comparison expected two integers"));
            };
            Ok(Value::Bool(match node.operation.as_str() {
                "binary.<" => left < right,
                "binary.<=" => left <= right,
                "binary.>" => left > right,
                "binary.>=" => left >= right,
                _ => unreachable!(),
            }))
        }
        "list" => Ok(Value::List(inputs.to_vec())),
        "tuple" => Ok(Value::Tuple(inputs.to_vec())),
        operation => Err(ExecError::Unsupported {
            node: node.id,
            operation: operation.to_string(),
        }),
    }
}

fn canonical_payload(
    operation: &str,
    parameters: &[String],
    inputs: &[SemanticId],
    output_type: &str,
) -> String {
    let mut out = String::new();
    push_field(&mut out, operation);
    push_field(&mut out, output_type);
    for parameter in parameters {
        push_field(&mut out, parameter);
    }
    out.push('|');
    for input in inputs {
        out.push_str(&format!("{:016x}", input.0));
    }
    out
}

fn push_field(out: &mut String, value: &str) {
    out.push_str(&value.len().to_string());
    out.push(':');
    out.push_str(value);
}

fn type_key(ty: &Ty) -> String {
    match ty {
        Ty::Error => "error".to_string(),
        Ty::Unit => "unit".to_string(),
        Ty::Int => "int".to_string(),
        Ty::Float => "float".to_string(),
        Ty::Bool => "bool".to_string(),
        Ty::Str => "str".to_string(),
        Ty::Space(space) => format!("space:{}", space.0),
        Ty::Sym { space, role } => format!(
            "sym:{}:{}",
            space
                .map(|id| id.0.to_string())
                .unwrap_or_else(|| "?".to_string()),
            role.map(|id| id.0.to_string())
                .unwrap_or_else(|| "?".to_string())
        ),
        Ty::Vec(vector) => {
            let roles = vector
                .roles
                .labels()
                .map(|(def, count)| format!("{}x{}", def.0, count))
                .collect::<Vec<_>>()
                .join(",");
            format!(
                "vec:{}:{}:{}:{}:{}:{}:{}",
                vector
                    .space
                    .map(|id| id.0.to_string())
                    .unwrap_or_else(|| "?".to_string()),
                vector.load.low,
                vector.load.high,
                roles,
                vector.roles.open,
                vector
                    .clean
                    .map(|value| value.to_string())
                    .unwrap_or_else(|| "?".to_string()),
                vector.depth
            )
        }
        Ty::Fn { params, ret } => format!(
            "fn:({})->{}",
            params.iter().map(type_key).collect::<Vec<_>>().join(","),
            type_key(ret)
        ),
        Ty::Tuple(items) => format!(
            "tuple:({})",
            items.iter().map(type_key).collect::<Vec<_>>().join(",")
        ),
        Ty::List(item) => format!("list:{}", type_key(item)),
    }
}

fn state_hash(values: &BTreeMap<SemanticId, Value>) -> u64 {
    let mut text = String::new();
    for (id, value) in values {
        text.push_str(&format!("{:016x}", id.0));
        push_field(&mut text, &value_key(value));
    }
    stable_hash(text.as_bytes())
}

fn value_key(value: &Value) -> String {
    match value {
        Value::Int(value) => format!("i:{value}"),
        Value::Bool(value) => format!("b:{value}"),
        Value::Str(value) => format!("s:{}:{value}", value.len()),
        Value::List(items) => format!(
            "l:[{}]",
            items.iter().map(value_key).collect::<Vec<_>>().join(",")
        ),
        Value::Tuple(items) => format!(
            "t:({})",
            items.iter().map(value_key).collect::<Vec<_>>().join(",")
        ),
    }
}

fn stable_hash(bytes: &[u8]) -> u64 {
    bytes.iter().fold(HASH_SEED, |hash, byte| {
        (hash ^ u64::from(*byte)).wrapping_mul(HASH_PRIME)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn compile(source: &str) -> (Ast, Resolved, Checked) {
        let file = raly_diag::FileId(0);
        let lexed = raly_lexer::lex(file, source);
        let parsed = raly_parse::parse(file, source, &lexed.tokens);
        let resolved = raly_resolve::resolve(&parsed.ast);
        let checked = raly_types::check(&parsed.ast, &resolved);
        assert!(!lexed.diagnostics.has_errors());
        assert!(!parsed.diagnostics.has_errors());
        assert!(!resolved.has_errors());
        assert!(!checked.has_errors());
        (parsed.ast, resolved, checked)
    }

    fn last_initializer(ast: &Ast) -> ExprId {
        let ItemKind::Let(binding) = &ast.items[*ast.root.last().unwrap()].kind else {
            panic!("expected a let")
        };
        binding.init.expect("let initializer")
    }

    #[test]
    fn executes_constants_and_replays_exactly() {
        let (ast, resolved, checked) =
            compile("let answer: Int = 1 + 2 * 3\nlet same: Bool = answer == 7\n");
        let ledger = Ledger::build(&ast, &resolved, &checked).unwrap();
        let execution = ledger.execute_constants(&ast, &resolved).unwrap();
        assert_eq!(execution.constants[0].value, Value::Int(7));
        assert_eq!(execution.constants[1].value, Value::Bool(true));
        assert!(ledger
            .verify_replay(&ast, &resolved, &execution.receipts)
            .is_ok());
    }

    #[test]
    fn execution_json_preserves_types_hashes_and_escaping() {
        let execution = Execution {
            constants: vec![ConstantValue {
                def: DefId(7),
                name: "a\"b".to_string(),
                value: Value::Tuple(vec![Value::Str("line\n".to_string()), Value::Bool(false)]),
                root: SemanticId(1),
            }],
            receipts: vec![Receipt {
                node: SemanticId(1),
                before: 2,
                after: 3,
                value: 4,
            }],
        };

        assert_eq!(
            execution.json(),
            concat!(
                "{\n",
                "  \"schema\": \"raly.execution.v1\",\n",
                "  \"constants\": [\n",
                "    {\"name\": \"a\\\"b\", \"root\": \"s0000000000000001\", ",
                "\"value\": {\"kind\": \"tuple\", \"items\": [",
                "{\"kind\": \"string\", \"value\": \"line\\n\"}, ",
                "{\"kind\": \"bool\", \"value\": false}]}}\n",
                "  ],\n",
                "  \"receipts\": [\n",
                "    {\"node\": \"s0000000000000001\", ",
                "\"before\": \"0000000000000002\", ",
                "\"after\": \"0000000000000003\", ",
                "\"value\": \"0000000000000004\"}\n",
                "  ]\n",
                "}\n"
            )
        );
    }

    #[test]
    fn replay_localizes_the_first_changed_receipt() {
        let (ast, resolved, checked) = compile("let answer = 40 + 2\n");
        let ledger = Ledger::build(&ast, &resolved, &checked).unwrap();
        let mut receipts = ledger.execute_constants(&ast, &resolved).unwrap().receipts;
        receipts[1].after ^= 1;
        let error = ledger
            .verify_replay(&ast, &resolved, &receipts)
            .unwrap_err();
        assert!(matches!(error, ReplayError::Diverged { index: 1, .. }));
    }

    #[test]
    fn alpha_renaming_does_not_change_path_identity() {
        let (a_ast, a_resolved, a_checked) = compile("let alpha = 1\nlet out = alpha + 2\n");
        let (b_ast, b_resolved, b_checked) = compile("let x = 1\nlet out = x + 2\n");
        let a = Ledger::build(&a_ast, &a_resolved, &a_checked).unwrap();
        let b = Ledger::build(&b_ast, &b_resolved, &b_checked).unwrap();
        assert_eq!(
            a.id_for_expr(last_initializer(&a_ast)),
            b.id_for_expr(last_initializer(&b_ast))
        );
        assert_eq!(
            a.nodes().iter().map(|node| node.id).collect::<Vec<_>>(),
            b.nodes().iter().map(|node| node.id).collect::<Vec<_>>()
        );
    }

    #[test]
    fn commutative_vsa_inputs_have_one_address() {
        let prefix = "space S = MAP[1024]\nrole A, B in S\n";
        let (a_ast, a_resolved, a_checked) = compile(&format!(
            "{prefix}fn f(a: Sym[S], b: Sym[S]) {{ bind(a, b) }}\n"
        ));
        let (b_ast, b_resolved, b_checked) = compile(&format!(
            "{prefix}fn f(a: Sym[S], b: Sym[S]) {{ bind(b, a) }}\n"
        ));
        let a = Ledger::build(&a_ast, &a_resolved, &a_checked).unwrap();
        let b = Ledger::build(&b_ast, &b_resolved, &b_checked).unwrap();
        let a_bind = a
            .nodes()
            .iter()
            .find(|node| node.operation == "vsa.bind")
            .unwrap();
        let b_bind = b
            .nodes()
            .iter()
            .find(|node| node.operation == "vsa.bind")
            .unwrap();
        assert_eq!(a_bind.id, b_bind.id);
        assert_eq!(a_bind.inputs, b_bind.inputs);
    }

    #[test]
    fn source_spans_are_provenance_not_identity() {
        let (a_ast, a_resolved, a_checked) = compile("let x = 1 + 2\n");
        let (b_ast, b_resolved, b_checked) = compile("\n\nlet x = 1 + 2\n");
        let a = Ledger::build(&a_ast, &a_resolved, &a_checked).unwrap();
        let b = Ledger::build(&b_ast, &b_resolved, &b_checked).unwrap();
        assert_eq!(
            a.nodes().iter().map(|node| node.id).collect::<Vec<_>>(),
            b.nodes().iter().map(|node| node.id).collect::<Vec<_>>()
        );
        assert_ne!(a.nodes()[0].sources[0].span, b.nodes()[0].sources[0].span);
    }
}
