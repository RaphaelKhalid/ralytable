// Preloaded programs for the Raly playground.
//
// These are not valid *programs* — Raly has no grammar yet, and saying
// otherwise would be a lie. They are inputs chosen to show what the lexer and
// the diagnostic renderer actually do.

window.RALY_EXAMPLES = [
  {
    id: 'tour',
    name: 'Tour',
    blurb: 'Every token class the lexer recognises.',
    source: `// A tour of everything the Raly lexer currently recognises.
// The grammar is not designed yet, so this file is not a valid program --
// it exists to exercise the tokeniser.

import std::space

space Concepts = 1024

fn describe(subject: Symbol, mut depth: Int) -> Str where depth >= 0 {
    let role = bind(subject, ROLE)
    let scene = bundle(role, permute(subject, 1))
    let recovered = unbind(scene, ROLE) |> cleanup
    let ratio = 0.75
    let mask = 0xFF ^ 0b1010
    match recovered {
        _ => "unknown\tsubject"
    }
}
`
  },
  {
    id: 'clean',
    name: 'Clean',
    blurb: 'Lexes with zero diagnostics.',
    source: `// Nothing here troubles the lexer: no diagnostics at all.

space Roles = 2048

fn encode(name: Str, slot: Int) -> Symbol {
    let atom = permute(seed(name), slot)
    let tagged = bind(atom, ROLE_NAME)
    return bundle(tagged, atom) |> cleanup
}

fn main() {
    let people = ["ada", "grace", "alan"]
    for who in people {
        let sym = encode(who, 0)
        if sym == UNKNOWN { return }
    }
}
`
  },
  {
    id: 'broken',
    name: 'Broken',
    blurb: 'One of every recoverable lexical error.',
    source: `fn main() {
    let greeting = "hello
    let n = 123abc
    let bad = "escape \\q here"
    let x = 5 × 3
}
`
  },
  {
    id: 'unterminated',
    name: 'Unterminated string',
    blurb: 'The two-span error: where it opened, where the line ran out.',
    source: `space Words = 512

fn caption(subject: Symbol) -> Str {
    let label = "the quick brown fox
    return label
}
`
  },
  {
    id: 'homoglyphs',
    name: 'Homoglyphs',
    blurb: 'Smart quotes and lookalike operators, with targeted hints.',
    source: `// Pasted out of a document, which is where these always come from.

fn scale(v: Symbol, k: Int) -> Symbol {
    let factor = 2 × k
    let limit  = k ≤ 64
    let name   = “weighted”
    let flow   = v → cleanup
    return permute(v, factor)
}
`
  },
  {
    id: 'numbers',
    name: 'Numbers',
    blurb: 'Good literals next to malformed ones.',
    source: `fn constants() {
    let ok_dec = 1_000_000
    let ok_hex = 0xDEAD_BEEF
    let ok_bin = 0b1010_1010
    let ok_flt = 6.022e23

    let no_digits = 0x
    let no_exp    = 1e
    let trailing  = 123abc
    let mixed     = 0b1012
}
`
  },
  {
    id: 'escapes',
    name: 'Escapes',
    blurb: 'One diagnostic per bad escape, spanning just two characters.',
    source: `fn strings() {
    let fine   = "tab\\there, newline\\nthere, quote \\" there"
    let broken = "\\q and \\z and \\8 are not escapes"
    let mixed  = "half ok \\n then \\y then ok \\\\"
}
`
  },
  {
    id: 'empty',
    name: 'Empty',
    blurb: 'The lexer is total: empty input is fine.',
    source: ''
  }
];
