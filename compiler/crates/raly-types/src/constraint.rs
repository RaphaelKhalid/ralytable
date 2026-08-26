//! Blame provenance: why the checker required what it required.
//!
//! Decision 5 of `docs/compiler-architecture.md` is emphatic that this is the
//! single most expensive thing to retrofit and the cheapest to carry from the
//! start: *every* constraint gets a `Span + Reason` at the moment it is
//! generated, so a failure can be reported against the expression that caused
//! it rather than against wherever the solver happened to notice.
//!
//! Helium's lesson is the split — generate, then solve — and the payoff is
//! that a mismatch message can say "the return type of `encode` says `Scene`"
//! instead of "cannot unify". Raly has no unification variables to search over
//! (annotations are mandatory at function boundaries), so the *ordering* half
//! of the Helium design is not needed yet. The provenance half is, and it is
//! here from the first commit.

use raly_diag::Span;

/// Why a type was required at a particular place.
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum Reason {
    /// The tail expression or a `return` of a function with a declared result.
    Return { function: String },
    /// The initialiser of an annotated `let`.
    LetAnnotation { name: String },
    /// The `index`th argument of a call.
    Argument { callee: String, index: usize },
    /// The `index`th operand of a VSA operation.
    Operand { op: &'static str, index: usize },
    /// The key of an `unbind`.
    UnbindKey,
    /// The codebook argument of a `cleanup`.
    CleanupCodebook,
    /// The condition of an `if`.
    Condition,
    /// The two arms of an `if` must agree.
    Branches,
    /// An operand of an arithmetic or comparison operator.
    Arithmetic { op: &'static str },
    /// An element of a list literal, which must match the first element.
    ListElement,
    /// The space argument of `Vec[..]` or `Sym[..]`.
    SpaceArgument { constructor: &'static str },
    /// The declared `load` of a type annotation.
    LoadAnnotation,
}

impl Reason {
    /// A clause for the `note:` line: "... because <this>".
    pub fn context(&self) -> String {
        match self {
            Reason::Return { function } => {
                format!("this is the result of `{function}`, whose signature fixes its type")
            }
            Reason::LetAnnotation { name } => {
                format!("`{name}` was annotated, and the initialiser has to match")
            }
            Reason::Argument { callee, index } => {
                format!("this is argument {} of `{callee}`", index + 1)
            }
            Reason::Operand { op, index } => {
                format!("this is operand {} of `{op}`", index + 1)
            }
            Reason::UnbindKey => {
                "`unbind` takes the vector first and the role it was bound with second".to_string()
            }
            Reason::CleanupCodebook => {
                "`cleanup`'s second operand names the space to project onto".to_string()
            }
            Reason::Condition => "an `if` condition is a `Bool`".to_string(),
            Reason::Branches => "both arms of an `if` produce the same type".to_string(),
            Reason::Arithmetic { op } => format!("`{op}` works on numbers"),
            Reason::ListElement => {
                "a list holds one type of element; the first one fixed it".to_string()
            }
            Reason::SpaceArgument { constructor } => {
                format!("`{constructor}[..]` takes a space as its argument")
            }
            Reason::LoadAnnotation => {
                "a `load` qualifier states how many items are superposed".to_string()
            }
        }
    }
}

/// One constraint's provenance: where it came from and why.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct Blame {
    /// The expression that must satisfy the constraint.
    pub span: Span,
    pub reason: Reason,
    /// The declaration that imposed it, when there is one to point at.
    pub secondary: Option<(Span, String)>,
}

impl Blame {
    pub fn new(span: Span, reason: Reason) -> Blame {
        Blame {
            span,
            reason,
            secondary: None,
        }
    }

    pub fn against(mut self, span: Span, message: impl Into<String>) -> Blame {
        self.secondary = Some((span, message.into()));
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reasons_read_as_english() {
        assert_eq!(
            Reason::Argument {
                callee: "encode".into(),
                index: 1
            }
            .context(),
            "this is argument 2 of `encode`"
        );
        assert_eq!(
            Reason::Operand {
                op: "bundle",
                index: 0
            }
            .context(),
            "this is operand 1 of `bundle`"
        );
    }
}
