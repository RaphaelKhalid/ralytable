# Preregistration — typed state-dependent bounded repair

Status: written before implementation and smoke testing.

## Question

Can a small controller over a corrupted executable sketch use typed state to
rank a bounded repair, rather than emitting a complete program and relying on
broad search to repair around it?

## Frozen protocol

Each task is generated from the existing restricted-Python integer-list
surface. One operation is removed from a target sketch at a deterministic
random gap; the model receives the request, the corrupted sketch, and the gap
but never the hidden input or expected output. It predicts the missing action.
Public examples select a candidate for the full-system arm; hidden execution
is used only for final scoring. Training templates and held-out templates are
fixed in `repair_policy.py`; evaluation uses 48 tasks, RNG 130000, and seeds
11, 23, and 37.

Compare raw top-1 repair, typed top-1 repair, public-example bounded repair,
and a target-independent fixed-order null. Report raw and full-system pass,
Python compile rate, repair expansions, latency, VRAM, parameter count, and
state relevant-change/placebo-preservation rates. The learned gate is 9M.

## Hypothesis and promotion

Typed executable state at the repair gap will improve repair ranking and make
the selected edit causally sensitive to state while an unused noise feature is
not. Retain only as an exploratory lead if the beam/full-system pass is at
least the recurrent-beam reference and relevant-change exceeds 10% with
placebo preservation above 95%. Otherwise record a negative result and do not
promote it.
