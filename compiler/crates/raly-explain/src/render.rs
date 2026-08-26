//! Two renderings of an [`Explanation`]: plain English, and JSON.

use std::fmt::Write as _;

use crate::model::{Described, Explanation, Fact};

/// The reading rendering.
///
/// Deliberately narrow — about 78 columns — because this is prose, and prose
/// set to the width of a terminal is prose nobody finishes.
pub fn plain(explanation: &Explanation) -> String {
    let mut out = String::new();
    let _ = writeln!(out, "{}", explanation.file);
    let _ = writeln!(out, "{}", explanation.headline);
    for item in &explanation.items {
        out.push('\n');
        let _ = writeln!(out, "{}", item.signature);
        for sentence in &item.summary {
            out.push_str(&wrap(sentence, "  "));
        }
        for flag in &item.notable {
            out.push_str(&wrap(flag, "  ! "));
        }
    }
    out
}

/// Hard-wrap one sentence under a prefix, continuation lines aligned under the
/// first. The prefix's width, not its text, is what the continuation reuses,
/// so `! ` marks the flag once instead of every line.
fn wrap(sentence: &str, prefix: &str) -> String {
    const WIDTH: usize = 78;
    let hanging = " ".repeat(prefix.chars().count());
    let mut out = String::new();
    let mut line = prefix.to_string();
    let mut empty = true;
    for word in sentence.split_whitespace() {
        if !empty && line.chars().count() + 1 + word.chars().count() > WIDTH {
            out.push_str(line.trim_end());
            out.push('\n');
            line = hanging.clone();
            empty = true;
        }
        if !empty {
            line.push(' ');
        }
        line.push_str(word);
        empty = false;
    }
    if !empty {
        out.push_str(line.trim_end());
        out.push('\n');
    }
    out
}

/// The machine rendering.
///
/// Hand-written, for the same reason `raly-diag`'s renderer is: this crate
/// has no dependencies outside the workspace, the output is asserted on
/// character for character in tests, and a serialiser for five value shapes is
/// shorter than the review of adding one.
pub fn json(explanation: &Explanation) -> String {
    let mut out = String::from("{\n");
    let _ = writeln!(out, "  \"file\": {},", quote(&explanation.file));
    let _ = writeln!(out, "  \"headline\": {},", quote(&explanation.headline));
    out.push_str("  \"items\": [\n");
    for (index, item) in explanation.items.iter().enumerate() {
        out.push_str(&json_item(item));
        if index + 1 < explanation.items.len() {
            out.push(',');
        }
        out.push('\n');
    }
    out.push_str("  ]\n}\n");
    out
}

fn json_item(item: &Described) -> String {
    let mut out = String::from("    {\n");
    let _ = writeln!(out, "      \"kind\": {},", quote(item.kind));
    let _ = writeln!(out, "      \"name\": {},", quote(&item.name));
    let _ = writeln!(out, "      \"signature\": {},", quote(&item.signature));
    let _ = writeln!(out, "      \"summary\": {},", string_array(&item.summary));
    let _ = writeln!(out, "      \"notable\": {},", string_array(&item.notable));
    out.push_str("      \"facts\": {");
    if item.facts.is_empty() {
        out.push('}');
    } else {
        out.push('\n');
        for (index, (key, value)) in item.facts.iter().enumerate() {
            let comma = if index + 1 < item.facts.len() {
                ","
            } else {
                ""
            };
            let _ = writeln!(out, "        {}: {}{comma}", quote(key), json_fact(value));
        }
        out.push_str("      }");
    }
    out.push_str("\n    }");
    out
}

fn json_fact(fact: &Fact) -> String {
    match fact {
        Fact::Text(text) => quote(text),
        Fact::Number(n) => n.to_string(),
        Fact::Bool(b) => b.to_string(),
        Fact::List(items) => string_array(items),
        Fact::Unknown => "null".to_string(),
    }
}

fn string_array(items: &[String]) -> String {
    let items: Vec<String> = items.iter().map(|s| quote(s)).collect();
    format!("[{}]", items.join(", "))
}

fn quote(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    out.push('"');
    for ch in text.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wrapping_hangs_under_the_prefix() {
        let text = wrap(&"word ".repeat(30), "  ! ");
        let lines: Vec<&str> = text.lines().collect();
        assert!(lines.len() > 1);
        assert!(lines[0].starts_with("  ! word"));
        assert!(lines[1].starts_with("    word"));
        assert!(lines.iter().all(|l| l.chars().count() <= 78));
    }

    #[test]
    fn json_escapes_quotes_and_controls() {
        assert_eq!(quote("a\"b\\c\nd"), "\"a\\\"b\\\\c\\nd\"");
        assert_eq!(quote("tab\there"), "\"tab\\there\"");
    }
}
