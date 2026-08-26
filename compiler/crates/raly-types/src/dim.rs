//! Dimensions as elements of a free abelian group.
//!
//! This is Kennedy's units-of-measure treatment, shipped in F# 2.0 and
//! recommended by decision 4 of `docs/compiler-architecture.md`. A dimension is
//! a formal product of *atoms* — integer constants and named constants the
//! checker could not fold — raised to integer powers:
//!
//! ```text
//! 8192          =>  8192^1
//! 2 * BASE_D    =>  2^1 · BASE_D^1
//! ```
//!
//! Multiplication adds exponents, division subtracts them, and the identity is
//! the empty product. Two dimensions are equal exactly when their **residual**
//! `a / b` is the identity — and that residual is the thing worth printing.
//! "unification failed" tells a user nothing; `8192 / 1024` tells them the
//! factor of 8 they are missing.
//!
//! Note what is *not* here: no solving for unknowns, because Raly has no
//! dimension variables to solve for. Annotations are mandatory at function
//! boundaries (GRAMMAR.md §5.6) and a space's dimension is a constant, so every
//! dimension is ground by the time it is compared. The group structure earns
//! its place for the *residual*, which is a diagnostic feature, and for
//! surviving unfolded constants without lying about them.

use std::collections::BTreeMap;
use std::fmt;

/// One irreducible factor of a dimension.
#[derive(Clone, PartialEq, Eq, PartialOrd, Ord, Debug)]
pub enum Atom {
    /// A literal, or something folded to one.
    Const(u64),
    /// A named constant the checker could not fold to a number.
    Var(String),
}

impl fmt::Display for Atom {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Atom::Const(n) => write!(f, "{n}"),
            Atom::Var(name) => f.write_str(name),
        }
    }
}

/// A formal product of [`Atom`]s with integer exponents.
///
/// Atoms with exponent zero are dropped on construction, so equality is
/// structural and the identity has exactly one representation.
#[derive(Clone, PartialEq, Eq, Default, Debug)]
pub struct Dim {
    factors: BTreeMap<Atom, i32>,
}

impl Dim {
    /// The identity of the group: the empty product, which is 1.
    pub fn one() -> Dim {
        Dim::default()
    }

    pub fn constant(value: u64) -> Dim {
        if value == 1 {
            return Dim::one();
        }
        Dim {
            factors: BTreeMap::from([(Atom::Const(value), 1)]),
        }
    }

    pub fn variable(name: impl Into<String>) -> Dim {
        Dim {
            factors: BTreeMap::from([(Atom::Var(name.into()), 1)]),
        }
    }

    pub fn is_one(&self) -> bool {
        self.factors.is_empty()
    }

    /// The dimension as a plain number, when every factor is a constant with a
    /// positive exponent. Capacity needs this; equality does not.
    pub fn as_constant(&self) -> Option<u64> {
        let mut product: u64 = 1;
        for (atom, &power) in &self.factors {
            let Atom::Const(value) = atom else {
                return None;
            };
            if power <= 0 {
                return None;
            }
            for _ in 0..power {
                product = product.checked_mul(*value)?;
            }
        }
        Some(product)
    }

    pub fn multiply(&self, other: &Dim) -> Dim {
        let mut factors = self.factors.clone();
        for (atom, power) in &other.factors {
            *factors.entry(atom.clone()).or_insert(0) += power;
        }
        factors.retain(|_, power| *power != 0);
        Dim { factors }
    }

    pub fn divide(&self, other: &Dim) -> Dim {
        let mut factors = self.factors.clone();
        for (atom, power) in &other.factors {
            *factors.entry(atom.clone()).or_insert(0) -= power;
        }
        factors.retain(|_, power| *power != 0);
        Dim { factors }
    }

    /// Abelian-group unification of two ground dimensions.
    ///
    /// `Ok(())` when they are equal; `Err(residual)` with the concrete
    /// non-identity quotient `self / other` otherwise. The residual is the
    /// whole point: it is what the diagnostic prints instead of "mismatch".
    pub fn unify(&self, other: &Dim) -> Result<(), Dim> {
        let residual = self.divide(other);
        if residual.is_one() {
            Ok(())
        } else {
            Err(residual)
        }
    }
}

impl fmt::Display for Dim {
    /// Renders as `a · b / c`, with negative exponents moved below the line so
    /// that a residual reads as the ratio it is.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.factors.is_empty() {
            return f.write_str("1");
        }
        let mut numerator = Vec::new();
        let mut denominator = Vec::new();
        for (atom, &power) in &self.factors {
            let (target, power) = if power > 0 {
                (&mut numerator, power)
            } else {
                (&mut denominator, -power)
            };
            target.push(if power == 1 {
                atom.to_string()
            } else {
                format!("{atom}^{power}")
            });
        }
        if numerator.is_empty() {
            numerator.push("1".to_string());
        }
        f.write_str(&numerator.join(" * "))?;
        if !denominator.is_empty() {
            write!(f, " / {}", denominator.join(" * "))?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identity_and_constants() {
        assert!(Dim::one().is_one());
        assert!(Dim::constant(1).is_one());
        assert_eq!(Dim::constant(1024).as_constant(), Some(1024));
        assert_eq!(Dim::variable("D").as_constant(), None);
    }

    #[test]
    fn multiplication_is_abelian_and_cancels() {
        let a = Dim::constant(2).multiply(&Dim::variable("D"));
        let b = Dim::variable("D").multiply(&Dim::constant(2));
        assert_eq!(a, b);
        assert!(a.divide(&b).is_one());
        assert_eq!(a.as_constant(), None);
    }

    #[test]
    fn unify_reports_a_concrete_residual() {
        let ok = Dim::constant(1024).unify(&Dim::constant(1024));
        assert!(ok.is_ok());
        let residual = Dim::constant(8192)
            .unify(&Dim::constant(1024))
            .expect_err("8192 and 1024 differ");
        assert_eq!(residual.to_string(), "8192 / 1024");
    }

    #[test]
    fn residual_keeps_unfolded_names() {
        let residual = Dim::variable("BASE_D")
            .unify(&Dim::constant(512))
            .expect_err("a name and a number are not known to be equal");
        assert_eq!(residual.to_string(), "BASE_D / 512");
    }

    #[test]
    fn powers_render() {
        let squared = Dim::variable("D").multiply(&Dim::variable("D"));
        assert_eq!(squared.to_string(), "D^2");
    }
}
