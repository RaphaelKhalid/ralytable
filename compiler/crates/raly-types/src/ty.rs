//! The type language: spaces, loads, role rows, and the types built from them.

use std::collections::BTreeMap;
use std::fmt::Write as _;

use raly_diag::Span;
use raly_resolve::{DefId, Family};

use crate::capacity;
use crate::dim::Dim;

/// A handle to a [`SpaceInfo`] in [`crate::Checked::spaces`].
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Debug)]
pub struct SpaceId(pub u32);

impl SpaceId {
    pub fn index(self) -> usize {
        self.0 as usize
    }
}

/// Which dimension a space's capacity was computed from.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum CapacityBasis {
    /// The dimension written in the declaration.
    Nominal,
    /// A measured effective dimension from `where effective = ...`, which is
    /// what `experiments/05_real_embeddings` says a real embedding space
    /// actually has.
    Effective,
}

/// Everything a `space` declaration fixes.
#[derive(Clone, Debug)]
pub struct SpaceInfo {
    pub def: DefId,
    pub name: String,
    /// The whole declaration, for the secondary label of a capacity error.
    pub decl_span: Span,
    /// The dimension expression's own span, for pointing at the number.
    pub dim_span: Option<Span>,
    pub family: Option<Family>,
    pub dim: Dim,
    /// The dimension capacity was computed from, when it is a known number.
    pub capacity_dim: Option<u64>,
    pub capacity_basis: CapacityBasis,
    /// How many items a bundle in this space may hold. `None` when the
    /// dimension did not fold to a number, in which case capacity is not
    /// checked rather than guessed.
    pub capacity: Option<u32>,
}

impl SpaceInfo {
    /// The `note:` line explaining where a capacity number came from.
    pub fn capacity_provenance(&self) -> String {
        let Some(capacity) = self.capacity else {
            return "this space's dimension is not a compile-time constant, so its capacity \
                    is unknown"
                .to_string();
        };
        let dimension = self.capacity_dim.unwrap_or_default();
        let basis = match self.capacity_basis {
            CapacityBasis::Nominal => format!("dimension {dimension}"),
            CapacityBasis::Effective => {
                format!("measured effective dimension {dimension}, not the nominal one")
            }
        };
        format!(
            "{capacity} is the capacity of `{}` at {basis}, measured at 95% retrieval in \
             experiments/04_capacity",
            self.name
        )
    }
}

/// A closed interval of natural numbers, saturating at [`Load::UNBOUNDED`].
///
/// Decision 4 asks for "a natural-number term with `+` and constants plus
/// interval bounds — a tiny abstract-interpretation lattice, not an arithmetic
/// theory", and this is it. `bundle` adds intervals, `bind` multiplies them,
/// `cleanup` collapses to exactly one.
///
/// A `Vec[S]` written with no `load` qualifier is `[1, unbounded]`: the type
/// says a vector is there, not how loaded it is. Compatibility is therefore
/// **interval intersection**, not equality — an annotation narrows what the
/// checker knows rather than asserting something it must prove.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Load {
    pub low: u32,
    pub high: u32,
}

impl Load {
    pub const UNBOUNDED: u32 = u32::MAX;

    pub fn exactly(n: u32) -> Load {
        Load { low: n, high: n }
    }

    /// At least one item, with no upper bound known.
    pub fn any() -> Load {
        Load {
            low: 1,
            high: Load::UNBOUNDED,
        }
    }

    pub fn is_exact(&self) -> bool {
        self.low == self.high
    }

    pub fn add(&self, other: &Load) -> Load {
        Load {
            low: self.low.saturating_add(other.low),
            high: self.high.saturating_add(other.high),
        }
    }

    pub fn multiply(&self, other: &Load) -> Load {
        Load {
            low: self.low.saturating_mul(other.low),
            high: self.high.saturating_mul(other.high),
        }
    }

    /// Whether the two intervals have a value in common.
    pub fn intersects(&self, other: &Load) -> bool {
        self.low <= other.high && other.low <= self.high
    }

    /// How much of a space this load is known to consume, at minimum.
    pub fn minimum(&self) -> u32 {
        self.low
    }
}

impl std::fmt::Display for Load {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match (self.low, self.high) {
            (low, high) if low == high => write!(f, "{low}"),
            (low, Load::UNBOUNDED) => write!(f, "at least {low}"),
            (low, high) => write!(f, "{low} to {high}"),
        }
    }
}

/// The set of roles bound into a vector.
///
/// Leijen's scoped labels, as decision 4 asks: a row is a *multiset* of labels
/// plus a tail. Duplicates are permitted rather than an error, because binding
/// one role twice is a meaningful VSA operation, and permitting them is what
/// makes scoped labels simpler than other record systems rather than harder.
///
/// `open` is the row variable. A `Vec[S]` written with no `roles {...}`
/// qualifier is open — "at least these roles, possibly more" — so a function
/// can accept any vector carrying `Subject` without naming the rest. Only an
/// explicit `roles {...}` closes a row, and only a closed row can prove that a
/// role is *absent*.
#[derive(Clone, PartialEq, Eq, Default, Debug)]
pub struct Row {
    labels: BTreeMap<DefId, u32>,
    pub open: bool,
}

impl Row {
    /// The empty closed row: this vector carries no roles at all.
    pub fn closed_empty() -> Row {
        Row {
            labels: BTreeMap::new(),
            open: false,
        }
    }

    /// The empty open row: nothing is known about which roles are bound.
    pub fn unknown() -> Row {
        Row {
            labels: BTreeMap::new(),
            open: true,
        }
    }

    pub fn is_empty(&self) -> bool {
        self.labels.is_empty()
    }

    pub fn labels(&self) -> impl Iterator<Item = (DefId, u32)> + '_ {
        self.labels.iter().map(|(&d, &n)| (d, n))
    }

    pub fn contains(&self, label: DefId) -> bool {
        self.labels.contains_key(&label)
    }

    /// `bind` extends a row.
    pub fn extend(&mut self, label: DefId) {
        *self.labels.entry(label).or_insert(0) += 1;
    }

    /// `unbind` restricts one. Returns false when the label is not there,
    /// which is exactly the wrong-role error.
    pub fn restrict(&mut self, label: DefId) -> bool {
        match self.labels.get_mut(&label) {
            Some(count) if *count > 1 => {
                *count -= 1;
                true
            }
            Some(_) => {
                self.labels.remove(&label);
                true
            }
            None => false,
        }
    }

    /// The union used by `bundle` and `bind`: label counts add, and the result
    /// is open if either operand was.
    pub fn union(&self, other: &Row) -> Row {
        let mut labels = self.labels.clone();
        for (&label, &count) in &other.labels {
            *labels.entry(label).or_insert(0) += count;
        }
        Row {
            labels,
            open: self.open || other.open,
        }
    }

    /// Whether every label of `self` also appears in `other`, at least as often.
    pub fn subsumed_by(&self, other: &Row) -> bool {
        self.labels
            .iter()
            .all(|(label, count)| other.labels.get(label).is_some_and(|n| n >= count))
    }

    /// The labels of `self` that `other` lacks.
    pub fn missing_from(&self, other: &Row) -> Vec<DefId> {
        self.labels
            .keys()
            .copied()
            .filter(|label| !other.contains(*label))
            .collect()
    }
}

/// A vector's type: which space, how loaded, which roles, how clean.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct VecTy {
    /// `None` only when an earlier error made the space unknowable.
    pub space: Option<SpaceId>,
    pub load: Load,
    pub roles: Row,
    /// `Some(true)` after a `cleanup`, `Some(false)` after an `unbind`, `None`
    /// when the source did not say and nothing forced it.
    pub clean: Option<bool>,
    /// How many `unbind`s deep this value is with no `cleanup` in between.
    ///
    /// Retrieval degrades roughly multiplicatively with nesting depth
    /// (semantics §3), so this is tracked rather than inferred later.
    pub depth: u32,
}

impl VecTy {
    pub fn atom(space: Option<SpaceId>) -> VecTy {
        VecTy {
            space,
            load: Load::exactly(1),
            roles: Row::closed_empty(),
            clean: Some(true),
            depth: 0,
        }
    }
}

/// A Raly type.
///
/// There are no unification variables. Annotations are mandatory at function
/// boundaries (GRAMMAR.md §5.6) and locals are checked against their
/// initialiser, so every type is ground when it is compared — which is the
/// Swift lesson from decision 5 taken seriously: no implicit conversions, no
/// whole-program inference, and therefore no search.
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum Ty {
    /// Compatible with everything and reports nothing. This is the cascade
    /// suppression decision 5 asks for: one mistake, one message.
    Error,
    Unit,
    Int,
    Float,
    Bool,
    Str,
    /// A space used as a value, as in `cleanup(v, Concepts)`.
    Space(SpaceId),
    /// A single codebook atom. `role` is set when the atom *is* a declared
    /// role, which is what lets `bind` extend a row and `unbind` name a label.
    Sym {
        space: Option<SpaceId>,
        role: Option<DefId>,
    },
    Vec(Box<VecTy>),
    Fn {
        params: Vec<Ty>,
        ret: Box<Ty>,
    },
    Tuple(Vec<Ty>),
    List(Box<Ty>),
}

impl Ty {
    pub fn vector(v: VecTy) -> Ty {
        Ty::Vec(Box::new(v))
    }

    pub fn is_error(&self) -> bool {
        matches!(self, Ty::Error)
    }

    /// The vector view of a value, if it has one. An atom is a vector of load
    /// one; this is an inclusion, not a conversion, so no coercion syntax is
    /// implied.
    pub fn as_vector(&self) -> Option<VecTy> {
        match self {
            Ty::Vec(v) => Some((**v).clone()),
            Ty::Sym { space, .. } => Some(VecTy::atom(*space)),
            _ => None,
        }
    }

    pub fn space(&self) -> Option<SpaceId> {
        match self {
            Ty::Vec(v) => v.space,
            Ty::Sym { space, .. } => *space,
            Ty::Space(space) => Some(*space),
            _ => None,
        }
    }
}

/// Everything needed to render a type back into something a user recognises.
#[derive(Clone, Copy, Debug)]
pub struct Names<'a> {
    pub spaces: &'a [SpaceInfo],
    pub defs: &'a [raly_resolve::Def],
}

impl<'a> Names<'a> {
    pub fn space(&self, id: SpaceId) -> &'a str {
        self.spaces
            .get(id.index())
            .map(|s| s.name.as_str())
            .unwrap_or("?")
    }

    pub fn def(&self, id: DefId) -> &'a str {
        self.defs
            .get(id.index())
            .map(|d| d.name.as_str())
            .unwrap_or("?")
    }

    /// A type as Raly source, as close to what the user would have written as
    /// the information allows.
    pub fn show(&self, ty: &Ty) -> String {
        match ty {
            Ty::Error => "<unknown>".to_string(),
            Ty::Unit => "()".to_string(),
            Ty::Int => "Int".to_string(),
            Ty::Float => "Float".to_string(),
            Ty::Bool => "Bool".to_string(),
            Ty::Str => "Str".to_string(),
            Ty::Space(id) => format!("space {}", self.space(*id)),
            Ty::Sym { space, .. } => match space {
                Some(id) => format!("Sym[{}]", self.space(*id)),
                None => "Sym[?]".to_string(),
            },
            Ty::Vec(v) => self.show_vec(v),
            Ty::Fn { params, ret } => {
                let params: Vec<String> = params.iter().map(|p| self.show(p)).collect();
                format!("({}) -> {}", params.join(", "), self.show(ret))
            }
            Ty::Tuple(elems) => {
                let elems: Vec<String> = elems.iter().map(|e| self.show(e)).collect();
                format!("({})", elems.join(", "))
            }
            Ty::List(elem) => format!("[{}]", self.show(elem)),
        }
    }

    fn show_vec(&self, v: &VecTy) -> String {
        let space = v
            .space
            .map(|id| self.space(id).to_string())
            .unwrap_or_else(|| "?".to_string());
        let mut out = format!("Vec[{space}");
        if !(v.load == Load::any()) {
            let _ = write!(out, "; load {}", v.load);
        }
        if !v.roles.open || !v.roles.is_empty() {
            let mut names = Vec::new();
            for (label, count) in v.roles.labels() {
                for _ in 0..count {
                    names.push(self.def(label).to_string());
                }
            }
            if v.roles.open {
                names.push("..".to_string());
            }
            let _ = write!(out, "; roles {{{}}}", names.join(", "));
        }
        match v.clean {
            Some(true) => out.push_str("; clean"),
            Some(false) => out.push_str("; noisy"),
            None => {}
        }
        out.push(']');
        out
    }

    /// A short phrase naming a space's family and dimension, for mismatch notes.
    pub fn describe_space(&self, id: SpaceId) -> String {
        let Some(info) = self.spaces.get(id.index()) else {
            return "?".to_string();
        };
        let family = info.family.map(|f| f.name()).unwrap_or("?");
        format!("{}[{}]", family, info.dim)
    }
}

/// The capacity of a dimension, re-exported so callers need one import.
pub fn capacity_of(dimension: u64) -> u32 {
    capacity::capacity(dimension)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loads_add_and_multiply_with_saturation() {
        assert_eq!(Load::exactly(3).add(&Load::exactly(2)), Load::exactly(5));
        assert_eq!(
            Load::exactly(3).multiply(&Load::exactly(2)),
            Load::exactly(6)
        );
        let unbounded = Load::any().add(&Load::any());
        assert_eq!(unbounded.high, Load::UNBOUNDED);
        assert_eq!(unbounded.low, 2);
    }

    #[test]
    fn intervals_intersect_rather_than_match() {
        assert!(Load::exactly(3).intersects(&Load::any()));
        assert!(!Load::exactly(5).intersects(&Load::exactly(3)));
        assert!(Load::any().intersects(&Load::exactly(40)));
    }

    #[test]
    fn rows_extend_and_restrict() {
        let mut row = Row::closed_empty();
        row.extend(DefId(4));
        row.extend(DefId(4));
        assert!(row.contains(DefId(4)));
        assert!(row.restrict(DefId(4)));
        assert!(row.contains(DefId(4)), "the duplicate binding survives");
        assert!(row.restrict(DefId(4)));
        assert!(!row.contains(DefId(4)));
        assert!(!row.restrict(DefId(4)), "restricting an absent label fails");
    }

    #[test]
    fn row_union_is_open_if_either_side_is() {
        let mut closed = Row::closed_empty();
        closed.extend(DefId(1));
        let union = closed.union(&Row::unknown());
        assert!(union.open);
        assert!(union.contains(DefId(1)));
    }
}
