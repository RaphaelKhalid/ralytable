//! Turning compiler facts into ordinary English.
//!
//! Every phrase here is a promise: it may say only what the types prove. Where
//! a property is unknown or open, the wording says *unknown* rather than
//! picking the likely answer, because a confident guess in a document whose
//! whole claim is "derived entirely from the types" is a lie about the types.

use raly_resolve::Family;
use raly_types::{Load, SpaceInfo};

/// `a`, `a and b`, `a, b and c`.
pub fn and_list(items: &[String]) -> String {
    match items {
        [] => String::new(),
        [one] => one.clone(),
        [head @ .., last] => format!("{} and {last}", head.join(", ")),
    }
}

/// Small counts read better as words than as digits.
pub fn count(n: usize) -> String {
    const WORDS: [&str; 11] = [
        "no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    ];
    WORDS
        .get(n)
        .map(|w| (*w).to_string())
        .unwrap_or_else(|| n.to_string())
}

/// `1 item` / `3 items`.
pub fn items(n: u32) -> String {
    if n == 1 {
        "1 item".to_string()
    } else {
        format!("{n} items")
    }
}

/// What a VSA family *is*, without using the words "vector symbolic".
///
/// `raly-resolve`'s `Family::describe` is the one-clause version for a reader
/// who already knows; this is the version for a reader who does not.
pub fn family(family: Family) -> &'static str {
    match family {
        Family::Map => {
            "every position holds either +1 or -1, and two of them are combined by multiplying \
             position against position"
        }
        Family::Bsc => {
            "every position holds either 0 or 1, two of them are combined by exclusive-or, and \
             several are merged by taking a majority vote at each position"
        }
        Family::Hrr => {
            "every position holds an ordinary real number, and two of them are combined by a \
             wrap-around sliding sum called circular convolution"
        }
        Family::Fhrr => {
            "every position holds an angle, and two of them are combined by adding their angles"
        }
    }
}

/// How a load reads on its own: "3 items", "at least 2 items", "2 to 5 items".
pub fn load(load: Load) -> String {
    match (load.low, load.high) {
        (low, high) if low == high => items(low),
        (low, Load::UNBOUNDED) => format!("at least {}", items(low)),
        (low, high) => format!("between {low} and {high} items"),
    }
}

/// "3 of the 269 items `Sentences` can hold", when both numbers are known.
pub fn load_against_capacity(value: Load, space: Option<&SpaceInfo>) -> String {
    let phrase = load(value);
    match space.and_then(|s| s.capacity.map(|c| (s, c))) {
        Some((space, capacity)) if value.is_exact() => format!(
            "{} of the {capacity} items `{}` can hold",
            value.minimum(),
            space.name
        ),
        _ => phrase,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lists_read_as_english() {
        let three = ["a".to_string(), "b".to_string(), "c".to_string()];
        assert_eq!(and_list(&three), "a, b and c");
        assert_eq!(and_list(&three[..2]), "a and b");
        assert_eq!(and_list(&three[..1]), "a");
        assert_eq!(and_list(&[]), "");
    }

    #[test]
    fn counts_become_words_only_while_they_are_short() {
        assert_eq!(count(0), "no");
        assert_eq!(count(3), "three");
        assert_eq!(count(11), "11");
    }

    #[test]
    fn loads_say_what_they_know_and_no_more() {
        assert_eq!(load(Load::exactly(1)), "1 item");
        assert_eq!(load(Load::exactly(3)), "3 items");
        assert_eq!(load(Load::any()), "at least 1 item");
    }
}
