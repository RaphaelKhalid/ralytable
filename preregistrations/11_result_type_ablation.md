# Experiment 11 result-type constraint ablation

## Question

Does a typed task contract help the controller finish a program by preventing
returns from slots with the wrong type?

## Design

- Use the same three seeds, training templates, held-out template, and update
  budget as `11_typed_state_next_smoke.md`.
- Both transcript and hard-mediated arms receive the same declared result type.
- Typed condition: the compiler-constrained decoder allows `return` only from a
  slot whose type matches the declared result type.
- Untyped condition: the compiler-constrained decoder allows `return` from any
  existing slot, regardless of type.
- The trained model is held fixed while the two decoding conditions are run on
  the same tasks.
- Raw unconstrained output remains a separate descriptive condition.

## Primary endpoint

For each controller arm, report hidden-task pass rate under typed and untyped
decoding on the held-out template. The primary effect is the paired per-seed
difference `typed - untyped`, calculated before averaging across seeds.

## Hypotheses

H0 for a future confirmatory run: result-type enforcement does not improve
held-out hidden-task accuracy, meaning the typed-minus-untyped effect is at most
zero.

H1: result-type enforcement improves held-out hidden-task accuracy, meaning the
effect is greater than zero.

The future confirmatory test will use alpha = 0.05, one-sided, with tasks as the
unit and seed-aware paired aggregation. This smoke is not large enough for a
valid inferential claim; it reports the predefined effect descriptively.

## Interpretation

An improvement would show that a compiler constraint prevents a specific class
of planning errors. It would not show that the model understands arbitrary
programs, reasons generally, or is superior to a normal language model.

Malformed raw outputs, executor errors, and failed checkpoints are outcomes or
infrastructure failures respectively, never silently excluded.
