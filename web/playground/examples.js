// Preloaded programs for the Raly playground.
//
// These are real Raly programs. The playground runs the same front end the
// `raly` binary runs -- lexer, parser, name resolution, type checker -- so
// what you see here is what `raly check` prints on the command line.
//
// Most of them come straight from the compiler's own test suite
// (compiler/crates/raly/tests/ui/) and from compiler/examples/, so if the
// checker ever stops reporting what a blurb claims, a UI test fails first.

window.RALY_EXAMPLES = [
  {
    id: 'capacity',
    name: 'Capacity',
    blurb: 'RALY5001: four items into a space measurement says holds three.',
    source: `// The error the language exists for.
//
// MiniLM hands you 384 numbers per sentence. Measurement says only about 111
// of those dimensions carry usable variance, and a space can say so. The
// capacity bound is then computed from the measured number rather than the
// flattering one.

space Sentences = MAP[384] where effective = 111

role Subject, Verb, Object in Sentences

// Fine: three items in a space that holds three.
fn scene(s: Sym[Sentences], v: Sym[Sentences], o: Sym[Sentences]) -> Vec[Sentences; load 3] {
    bundle(bind(Subject, s), bind(Verb, v), bind(Object, o))
}

// Not fine. Every vector here is the right length and every operation is
// defined, so a tensor library would run this and hand back a number. What it
// would not tell you is that cleanup on the result comes back with the wrong
// atom often enough to matter, and accuracy just quietly sags.
fn quad(
    a: Sym[Sentences],
    b: Sym[Sentences],
    c: Sym[Sentences],
    d: Sym[Sentences],
) -> Vec[Sentences] {
    bundle(a, b, c, d)
}
`
  },
  {
    id: 'capacity-nominal',
    name: 'Capacity, 40 into 31',
    blurb: 'The same error at the nominal dimension, with the fix in the help line.',
    source: `// RALY5001 without a measured effective dimension: the bound comes from the
// declared width. Forty items superposed into a space that measurement says
// holds thirty-one.

space Small = MAP[1000]

fn overload(
    a: Sym[Small], b: Sym[Small], c: Sym[Small], d: Sym[Small],
    e: Sym[Small], f: Sym[Small], g: Sym[Small], h: Sym[Small],
) -> Vec[Small] {
    bundle(
        a, b, c, d, e, f, g, h,
        a, b, c, d, e, f, g, h,
        a, b, c, d, e, f, g, h,
        a, b, c, d, e, f, g, h,
        a, b, c, d, e, f, g, h,
    )
}
`
  },
  {
    id: 'wrong-role',
    name: 'Wrong role',
    blurb: 'RALY4007: unbinding a role that was never bound in, plus a nesting warning.',
    source: `// wrong-role.raly -- asking a record for a field it does not have.
//
// A scene is built by binding three roles and superposing them. Reading it
// back means unbinding one of those three. Unbinding a *fourth* role is not a
// runtime error and not a shape error: the arithmetic is identical, the result
// is the right length, and it is pure crosstalk. \`cleanup\` will then project
// that noise onto whichever codebook atom it happens to lie nearest.

space Concepts = MAP[4096]

role Subject, Verb, Object in Concepts
role Place in Concepts

type Scene = Vec[Concepts; load 3; roles {Subject, Verb, Object}]

fn encode(s: Sym[Concepts], v: Sym[Concepts], o: Sym[Concepts]) -> Scene {
    bundle(bind(Subject, s), bind(Verb, v), bind(Object, o))
}

// Fine: \`Subject\` is in the schema.
fn subject_of(scene: Scene) -> Sym[Concepts] {
    scene |> unbind(Subject) |> cleanup(Concepts)
}

// Not fine: \`Place\` was never bound into a \`Scene\`.
fn place_of(scene: Scene) -> Sym[Concepts] {
    scene |> unbind(Place) |> cleanup(Concepts)
}

// Also not fine: two unbinds with no cleanup between them. Retrieval degrades
// multiplicatively with nesting depth, and the checker counts.
fn nested(scene: Scene) -> Sym[Concepts] {
    unbind(unbind(scene, Subject), Verb) |> cleanup(Concepts)
}
`
  },
  {
    id: 'dimension',
    name: 'Dimension mismatch',
    blurb: 'RALY4002: two MAP spaces of different width, with the residual.',
    source: `// The message prints the residual of the abelian-group unification, not
// "cannot unify". Dimensions cancel or they do not, and it says which.

space Wide = MAP[8192]
space Narrow = MAP[1024]

fn f(a: Sym[Wide], b: Sym[Narrow]) -> Vec[Wide; load 2] {
    bundle(a, b)
}
`
  },
  {
    id: 'clean',
    name: 'Clean',
    blurb: 'A role schema built, read back and projected. No diagnostics at all.',
    source: `// No diagnostics. A role schema built by \`bind\`, read back by \`unbind\`, and
// projected by \`cleanup\` -- every one of the four properties satisfied.

space Concepts = MAP[2048]
role Subject, Verb, Object in Concepts

type Scene = Vec[Concepts; load 3; roles {Subject, Verb, Object}]

fn encode(s: Sym[Concepts], v: Sym[Concepts], o: Sym[Concepts]) -> Scene {
    bundle(bind(Subject, s), bind(Verb, v), bind(Object, o))
}

fn subject_of(scene: Scene) -> Sym[Concepts] {
    scene |> unbind(Subject) |> cleanup(Concepts)
}
`
  },
  {
    id: 'all-phases',
    name: 'Every phase',
    blurb: 'A lexical, a resolution and a type error, all reported in one run.',
    source: `// Every phase reports in one pass. A lexical error does not silence the
// parser, a syntax error does not silence name resolution, and an unresolved
// name does not silence the type checker.

space Concepts = MAP[2048]

fn broken(x: Sym[Concepts]) -> Sym[Concepts] {
    let caption = "the quick brown fox
    let echo = missing_name
    let flag: Int = true
    x
}
`
  },
  {
    id: 'homoglyphs',
    name: 'Homoglyphs',
    blurb: 'Lookalike characters pasted out of a document, named one by one.',
    source: `// Pasted out of a document, which is where these always come from. The lexer
// names each lookalike and says which ASCII character was meant. The parser
// and the type checker keep going anyway: six errors, one run.

space Concepts = MAP[1024]

fn scale(v: Sym[Concepts], k: Int) -> Int {
    let factor = 2 \u{d7} k
    let name = \u{201c}weighted\u{201d}
    factor
}
`
  },
  {
    id: 'tour',
    name: 'Tour',
    blurb: 'Every token class the lexer recognises, in a program that checks clean.',
    source: `// A tour of the surface syntax: every token class the lexer recognises, in a
// program the parser, the resolver and the type checker all accept.

import std::codebook

space Concepts = MAP[2048] where seed = 20260826, codebook = fixed

role Subject, Verb, Object in Concepts

type Scene = Vec[Concepts; load 3; roles {Subject, Verb, Object}]

let default_shift: Int = 1

fn encode(s: Sym[Concepts], v: Sym[Concepts], o: Sym[Concepts]) -> Scene {
    bundle(bind(Subject, s), bind(Verb, v), bind(Object, o))
}

fn subject_of(scene: Scene) -> Sym[Concepts] {
    scene |> unbind(Subject) |> cleanup(Concepts)
}

fn ordered_pair(a: Sym[Concepts], b: Sym[Concepts]) -> Vec[Concepts; load 2] {
    bundle(a, permute(b, default_shift))
}

fn numbers() -> Int {
    let big = 1_000_000
    let hex = 0xDEAD_BEEF
    let bin = 0b1010_1010
    let ratio = 0.75
    let sci = 6.022e23
    big
}

fn describe(scene: Scene, verbose: Bool) -> Str {
    if verbose {
        return "a three-role scene\\tin Concepts"
    }
    "scene"
}
`
  },
  {
    id: 'empty',
    name: 'Empty',
    blurb: 'The front end is total: empty input is fine.',
    source: ''
  }
];
