# OpenRouter tournament postmortem — 2026-08-27

Status: complete through the final board. Reviewer patch checks were skipped by
explicit user direction. No commit or push was made.

## Timeline

- Read `PROJECT_GUIDE.md` and `HANDOFF.md`; preserved the pre-existing dirty tree.
- Detected that the prepared packet represented older Experiment 11 files and
  preserved the original packet/manifest under `pre-refresh/`; refreshed the
  current 145-file packet.
- Initial preflight refused the original $0.85 tournament ceiling because the
  conservative forecast was $1.0909. The user authorized a nominal $1.09 cap;
  the harness used $1.091 so the exact forecast was not rejected by rounding.
- First paid attempt: Luna used 32,000 reasoning tokens, returned no visible
  report, and cost $0.2034137. DeepSeek was interrupted; its final server-side
  cost is unknown. The attempt is preserved under
  `attempt-1-luna-empty-deepseek-interrupted/`.
- Added report-safe effort, pricing-tier-aware forecasting, model-supported
  completion fields, fail-closed response handling, resume support, and local
  self-tests.
- Second attempt: Luna produced a report; DeepSeek exhausted its budget with no
  visible report. Preserved under `attempt-2-luna-good-deepseek-empty/`.
- Resumed without retrying processed reviewers. Nemotron was interrupted during
  a long request; its final server-side cost is unknown. Preserved under
  `attempt-3-luna-good-deepseek-empty-nemotron-interrupted/`.
- Added tiny canaries. Nemotron and Gemini both returned `CANARY_OK`.
- Completed Nemotron and Gemini. The current tournament ledger reached
  $1.005065805.
- Sol Pro investment committee returned a real memo at $1.6142342, exceeding
  its $1.50 stage ceiling. No additional committee or reviewer calls were made.
- Independently reproduced the committee-selected findings locally, added six
  narrow compiler fixes plus focused regression tests, and corrected the
  Experiment 11 protocol/claims wording.
- Ran the complete compiler gate. Python source checks passed. A model run was
  not launched because the host reported active desktop GPU consumers.
- Sent one compact, guarded final-board packet to Sol Pro. It returned a real
  memo at $0.0342707. No retry occurred.

## Snapshot and exact prompts

- Tournament snapshot: 145 files, 1,000,488 packet characters;
  SHA-256 `ce13e3cfe32045ecca4eaac8963ece4243546a5d1943d0492d069e7f8173d145`.
- Exact blind prompts: `prompt-luna.json`, `prompt-deepseek.json`,
  `prompt-nemotron.json`, and `prompt-gemini.json`.
- Exact committee prompt: `prompt-committee-sol-pro.json`.
- Exact final-board prompt: `prompt-final-board-sol-pro.json`.
- Final-board packet SHA-256:
  `49fd7f863909e1164913e400912a07ad56f6161a9a30d82e8dfe33e112ff1d96`.
- Raw responses, visible reports, failures, preflights, ledgers, and interrupted
  attempt archives are retained beside these files.

## Blind verdicts

- Reviewer A / Luna: high-confidence compiler soundness issues in qualified
  paths, return flow, role multiplicity, ignored type applications, Unicode
  escapes, and diagnostic locator ordering; continue after front-end fixes.
- Reviewer B / DeepSeek: no usable visible verdict; 22,394 reasoning tokens,
  length termination, zero report characters.
- Reviewer C / Nemotron: acknowledged absence of executable IR/backend/runtime
  and the disconnect between the Python DSL and Raly; recommended a minimal
  execution milestone after correctness fixes.
- Reviewer D / Gemini: identified train/evaluation contamination, threshold
  candidate leakage, provenance leakage, sampler seed reuse, and an integer
  intervention no-op; recommended correcting controls and claims.

## Disagreement matrix

| Topic | Luna | Nemotron | Gemini | Committee/board disposition |
|---|---|---|---|---|
| Front-end compiler escapes | Confirmed | Not primary focus | Not primary focus | Reproduced, patched, gated |
| No executable IR/runtime | Sequencing concern | Blocking gap | DSL/compiler disconnect | Acknowledged gap, pause backend expansion |
| Experiment 11 validity | Not primary focus | Disconnected toy | Multiple confounds | Correct protocol/claims; rerun later |
| Kill typed mediation entirely | Continue | Continue after prerequisites | Pivot current experiment | Rejected general kill overclaim |
| Corrected model result | Not available | Not available | Not available | Unknown until safe GPU run |

## Complete finding classification

The investment committee classified every submitted finding as follows. These
classifications were then checked against the current checkout where stated.

### Confirmed defects / claim or instrumentation defects

- A-C1 qualified paths silently skipped: confirmed and patched with an explicit
  unresolved/unsupported diagnostic.
- A-C2 return-flow inference: confirmed and patched for return-only blocks.
- A-C3 role multiplicity: confirmed and patched with count-aware row comparison.
- A-C4 ignored type applications, narrowed to surplus arguments/qualifiers:
  confirmed and patched with arity/qualifier diagnostics.
- A-C5 malformed Unicode scalar escapes: confirmed and patched with validation.
- A-C6 diagnostic arrow insertion-order bug: confirmed and patched to follow the
  primary label.
- B7 “compiler constraint” wording: confirmed instrumentation/claim defect;
  the Python candidate filter is not Raly compilation and remains described as
  such.
- C1 train/evaluation identity overlap: confirmed and corrected with a
  disjoint split assertion; historical numbers remain pre-correction.
- C2 sole threshold candidate: confirmed confound, narrowed because the
  threshold is visible in the request; left as an explicit limitation rather
  than misdescribed as private-threshold generalization.
- C3 model-visible provenance leakage: confirmed and corrected by making
  provenance opt-in.
- C5 hardcoded optimizer sampler seed: confirmed and corrected by threading the
  run seed.
- C7 integer relevant corruption no-op: confirmed and corrected to mutate the
  integer value.

### Strong inferences / acknowledged sequencing limitations

- B1 no IR/backend/runtime: strong inference and documented sequencing gap, not
  a regression.
- B2 Experiment 11 is disconnected from Raly: strong inference and scope limit.
- B8 learned-codebook provenance/coherence gap: strong inference and future
  design constraint.

### Hypotheses not patched

- A-S1 effective-dimension domain policy.
- C4 whether the empty prefix-token callback is invoked after EOS by the pinned
  Transformers version.

### Duplicates

- C6 duplicates B2.
- B3/B4/B6 are consequences of B1, not separate defects.

### Rejected findings or overclaims

- A-S2 upper load bounds are not a defect under the documented interval and
  minimum-only semantics.
- B5 mandatory runtime capacity failure is not evidenced and would change the
  stated semantics.
- “Held-out failure falsifies typed mediation” is an overclaim; it only rejects
  the present controller/state representation on that smoke.
- Specific MIR/kernel/runtime API proposals are design suggestions, not findings.
- `Vec[S; load 40]` is not evidence that vector qualifiers are ignored; the
  valid narrowed C4 cases were surplus constructor/scalar/alias applications.

## Reproduction attempts and patches

The exact minimal programs and result summaries are under `reproduction/`.

- `qualified-path.raly`: now exits 1 with RALY3001 for `missing::name`.
- `return-flow.raly`: now exits 0 for an explicit return-only `Int` function.
- `role-multiplicity.raly`: now exits 1 with RALY4007 for the duplicate role.
- `ignored-applications.raly`: now exits 1 with three RALY4009 arity errors and
  one RALY2008 qualifier error.
- `unicode-escape.raly`: now exits 1 with RALY1003 for `\u{110000}`.
- Deterministic DSL checks show the original `train=26`, `eval=16` split had
  16 identical task objects; corrected relevant integer intervention is 42 →
  43; default serialization has no `from`, while explicit provenance mode does.
- Python AST parsing passes for `dsl.py`, `smoke.py`, and `next_smoke.py`.

Source changes retained:

- `compiler/crates/raly-resolve/src/lib.rs`: diagnose unsupported qualified
  value/type paths and preserve error mappings.
- `compiler/crates/raly-types/src/lib.rs`: validate type applications and infer
  return-only blocks from the declared return type.
- `compiler/crates/raly-types/src/ty.rs`: compare role rows by multiplicity.
- `compiler/crates/raly-lexer/src/lib.rs`: validate Unicode scalar escapes.
- `compiler/crates/raly-diag/src/render.rs`: locate the primary label explicitly.
- `experiments/11_typed_state_mediation/{dsl.py,smoke.py,next_smoke.py}`:
  correct provenance exposure, integer intervention, split, and seed plumbing.
- Focused tests were added for Unicode scalar validation, multiset rows, and
  primary-label rendering.

No backend, IR, runtime-capacity, effective-dimension, or EOS hypothesis patch
was made. No paid reviewer patch checks were run.

## Verification results

- `cargo build --workspace`: passed.
- `cargo test --workspace`: passed; all unit, integration, UI, golden,
  recovery, grammar, diagnostic, and doctest suites passed.
- `cargo clippy --workspace --all-targets -- -D warnings`: passed with zero
  warnings.
- `cargo fmt --all --check`: passed.
- Python AST parsing: passed for all three Experiment 11 Python files.
- GPU-sensitive model run: intentionally not run; `nvidia-smi` reported active
  desktop GPU consumers and no process was interrupted.

## Cost after every recorded call

| Call | Status | Cost | Recorded cumulative |
|---|---|---:|---:|
| Luna, first attempt | empty/length | $0.203413700 | $0.203413700 |
| DeepSeek, first attempt | interrupted; unknown final charge | unknown | $0.203413700 + unknown |
| Luna, resumed | completed | $0.172229400 | $0.375643100 |
| DeepSeek, resumed | empty/length | $0.459457680 | $0.835100780 |
| Nemotron canary | passed | $0.000157800 | $0.835258580 |
| Gemini canary | passed | $0.000219750 | $0.835478330 |
| Nemotron, interrupted attempt | interrupted; unknown final charge | unknown | $0.835478330 + unknown |
| Nemotron, resumed | completed | $0.217567800 | $1.053046130 |
| Gemini, resumed | completed | $0.155433375 | $1.208479505 |
| Sol Pro committee | completed; over committee cap | $1.614234200 | $2.822713705 |
| Sol Pro final board | completed | $0.034270700 | **$2.856984405** |

The known total is deduplicated across preserved ledgers. The two interrupted
requests have no usable response ledger; their conservative prepared forecasts
were approximately $0.4505 and $0.2805, or about $0.731 combined. The final
board preflight reserved $0.75 for them and forecast the board at $0.0329; the
actual board cost was $0.0343. No known or conservatively reserved total crossed
the $4.50 global ceiling. The committee did exceed its separate $1.50 ceiling
by $0.1142342; work stopped immediately afterward.

## Committee decision

The committee required local reproduction and decision impact. It recommended
the six compiler fixes, the five Experiment 11 protocol/reporting corrections,
no backend patch, and a pause on backend expansion until corrected experiment
evidence exists.

## Final board verdict

Sol Pro independently approved retaining all six compiler patches because each
has a local reproducer and the complete gate passes. It recommended pausing IR
and backend investment until the corrected model-dependent smoke is run. It
allowed claims about reproduced compiler defects/fixes and deterministic control
checks, while prohibiting corrected model-performance claims, typed-mediation
capability gains, causal interpretability, general coding improvement,
private-threshold generalization, learned-codebook conclusions, and a claimed
DSL/Raly execution path. It named one smallest next action: run the corrected
Experiment 11 smoke once at a safe idle-GPU window, preserving seed, assertions,
outputs, and exit status.

## What the exercise changed

- Closed six concrete compiler soundness/diagnostic escapes and added focused
  regressions.
- Repaired the Experiment 11 split, provenance exposure, seed plumbing, and
  integer intervention, while downgrading historical model numbers to
  pre-correction results.
- Made the tournament harness fail closed on blank/length responses, choose
  provider-supported token fields, record raw evidence and token accounting,
  use canaries, resume without automatic retries, and guard a compact final
  board packet.
- Established that model agreement is not evidence: all accepted changes were
  reproduced locally before implementation.
- Confirmed that the Python DSL and the Raly compiler remain separate; no
  executable IR/backend claim is currently justified.

## Remaining uncertainty and next smallest action

Remaining uncertainty is the final server-side charge for the two interrupted
requests, Sol Pro's provider-specific completion-cap behavior, and all
model-dependent outcomes under the corrected Experiment 11 protocol.

The next smallest action is free and operationally gated: at the first safe
idle-GPU window, run the existing corrected Experiment 11 smoke once, preserve
its seed, split assertion, artifacts, and exit status, and use that result only
to decide whether an IR/backend milestone has decision value. Do not make
another paid review call, commit, or push as part of this tournament.
