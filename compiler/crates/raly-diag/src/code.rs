//! Stable diagnostic codes.
//!
//! Every user-visible diagnostic carries a code such as `RALY1002`. Codes are
//! *stable*: once published, a code's meaning never changes and the code is
//! never reused for something else. Wording may be improved freely; the code is
//! the thing users search for, pin in `#[allow]`-style attributes, and grep for
//! in CI logs.
//!
//! Number ranges are reserved per compiler phase so that later phases can be
//! added without renumbering:
//!
//! | Range      | Phase                                    |
//! |------------|------------------------------------------|
//! | `0000-0999`| driver, CLI and I/O                      |
//! | `1000-1999`| lexical analysis                         |
//! | `2000-2999`| parsing / syntax                         |
//! | `3000-3999`| name resolution                          |
//! | `4000-4999`| type checking                            |
//! | `5000-5999`| capacity and space checking              |

use std::fmt;

/// A stable, greppable diagnostic identifier.
///
/// Construct these only through the constants in this module so the registry
/// below stays the single source of truth.
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Code(&'static str);

impl Code {
    /// The code as it appears in output, e.g. `"RALY1002"`.
    pub const fn as_str(&self) -> &'static str {
        self.0
    }

    /// One-line explanation, for `raly explain <code>` once that exists.
    pub fn description(&self) -> &'static str {
        REGISTRY
            .iter()
            .find(|(c, _)| c.0 == self.0)
            .map(|(_, d)| *d)
            .unwrap_or("no description registered")
    }
}

impl fmt::Display for Code {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.0)
    }
}

impl fmt::Debug for Code {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.0)
    }
}

macro_rules! codes {
    ($($konst:ident => $lit:literal, $desc:literal;)*) => {
        $(
            #[doc = $desc]
            pub const $konst: Code = Code($lit);
        )*
        /// Every registered code, paired with its description.
        pub static REGISTRY: &[(Code, &str)] = &[$(($konst, $desc)),*];
    };
}

codes! {
    // ---- driver -----------------------------------------------------------
    IO_ERROR          => "RALY0001", "a source file could not be read";
    BAD_EXTENSION     => "RALY0002", "a source file does not use the `.raly` extension";

    // ---- lexical ----------------------------------------------------------
    UNKNOWN_CHARACTER => "RALY1001", "a character that is not part of Raly's syntax";
    UNTERMINATED_STRING => "RALY1002", "a string literal reaches end of line or end of file without a closing quote";
    INVALID_ESCAPE    => "RALY1003", "an unrecognised escape sequence inside a string literal";
    MALFORMED_NUMBER  => "RALY1004", "a numeric literal that cannot be interpreted";

    // ---- syntax -----------------------------------------------------------
    UNEXPECTED_TOKEN  => "RALY2001", "a token that cannot appear where it was written";
    UNCLOSED_DELIMITER => "RALY2002", "an opening bracket with no matching close";
    EMPTY_BUNDLE      => "RALY2003", "`bundle()` with no operands; superposition has no identity element";
    BAD_OP_ARITY      => "RALY2004", "a VSA operation applied to the wrong number of operands";
    UNKNOWN_OP_VARIANT => "RALY2005", "an operation variant that does not exist";
    MISSING_PARAM_TYPE => "RALY2006", "a function parameter written without a type annotation";
    UNIMPLEMENTED_CONSTRUCT => "RALY2007", "a reserved construct the parser recognises but does not implement yet";
    UNKNOWN_TYPE_QUALIFIER => "RALY2008", "an unrecognised qualifier after `;` in a type argument list";
    DUPLICATE_ROLE    => "RALY2009", "the same role named twice in one role schema";
    BAD_SPACE_DECL    => "RALY2010", "a `space` declaration missing its family or its dimension";
    EXPECTED_ITEM     => "RALY2011", "text at the top level that does not begin a declaration";

    // ---- name resolution --------------------------------------------------
    UNRESOLVED_NAME   => "RALY3001", "a name with no definition in scope";
    UNRESOLVED_TYPE   => "RALY3002", "a type name with no definition in scope";
    DUPLICATE_DEFINITION => "RALY3003", "two definitions of the same name in one scope";
    USE_BEFORE_DEFINITION => "RALY3004", "a local binding used above the `let` that defines it";
    UNKNOWN_FAMILY    => "RALY3005", "a `space` declared with a VSA family that does not exist";
    ROLE_NOT_IN_SPACE => "RALY3006", "a `role` declared in something that is not a space";
    SHADOWS_DECLARATION => "RALY3007", "a local binding that hides a `role` or `space` declaration";

    // ---- types ------------------------------------------------------------
    FAMILY_MISMATCH   => "RALY4001", "two vectors from different VSA families combined";
    DIMENSION_MISMATCH => "RALY4002", "two vectors of different dimension combined";
    SPACE_MISMATCH    => "RALY4003", "two vectors from different codebooks combined";
    NON_CONSTANT_DIMENSION => "RALY4004", "a `space` dimension that is not a compile-time constant";
    LOAD_MISMATCH     => "RALY4005", "a declared superposition load the expression cannot have";
    TYPE_MISMATCH     => "RALY4006", "an expression whose type is not the one required here";
    ROLE_NOT_BOUND    => "RALY4007", "unbinding a role the vector does not carry";
    NOT_A_ROLE        => "RALY4008", "a binding key that is not a declared role";
    BAD_ARGUMENT_COUNT => "RALY4009", "a call with the wrong number of arguments";
    RECURSIVE_TYPE    => "RALY4010", "a type alias defined in terms of itself";
    NOT_CALLABLE      => "RALY4011", "a call or pipeline stage that is not a function";

    // ---- capacity ---------------------------------------------------------
    CAPACITY_EXCEEDED => "RALY5001", "a bundle of more items than its space can hold";
    UNCLEANED_NESTING => "RALY5002", "nested `unbind` with no `cleanup` in between";
    LOSSY_FOLD        => "RALY5003", "a left-nested bundle fold, which is not the n-ary primitive";
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;

    #[test]
    fn codes_are_unique() {
        let mut seen = HashSet::new();
        for (code, _) in REGISTRY {
            assert!(seen.insert(code.as_str()), "duplicate code {code}");
        }
    }

    #[test]
    fn codes_are_well_formed() {
        for (code, _) in REGISTRY {
            let s = code.as_str();
            assert!(s.starts_with("RALY"), "{s} lacks the RALY prefix");
            assert_eq!(s.len(), 8, "{s} is not RALY + 4 digits");
            assert!(s[4..].chars().all(|c| c.is_ascii_digit()), "{s}");
        }
    }

    #[test]
    fn descriptions_resolve() {
        assert_eq!(
            UNTERMINATED_STRING.description(),
            "a string literal reaches end of line or end of file without a closing quote"
        );
    }
}
