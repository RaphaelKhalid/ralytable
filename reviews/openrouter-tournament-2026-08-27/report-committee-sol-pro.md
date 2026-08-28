# Committee memo — packet `ce13e3cf…d145`

## 1. Five-line bottom line

1. **Patch required:** source-level proof confirms six front-end defects, led by silent qualified paths, broken return flow, and ignored type applications.  
2. **Experiment 11’s original 15/16 smoke result is invalid as held-out evidence:** its evaluation tasks are the same objects used for training.  
3. **Hard mediation is also confounded:** serialized provenance exposes operation history, and constrained decoding supplies the sole threshold candidate rather than testing argument generation.  
4. **No IR/runtime is an acknowledged project gap, not a newly discovered defect; do not begin backend expansion until the P1 front-end escapes and Experiment 11 claims are corrected.**  
5. **Continue the research direction, but patch correctness and reporting now; the bundle does not justify killing typed mediation or prescribing a particular MIR/runtime design.**

## 2. Decision table

“Direct proof” means the cited control flow is sufficient; commands below are still required before merging because the committee did not execute the snapshot.

| Reviewer finding | Classification | Evidence and reproducer/command | Decision impact | Required follow-up |
|---|---|---|---|---|
| **A-C1: qualified paths silently fail** | **Confirmed defect** | Resolver skips every multi-segment expression/type path (`raly-resolve:508-521,586-612`); checker turns absent mapping into `Ty::Error` without a diagnostic (`raly-types:720-723`). Run `raly check` on `fn f()->Int { missing::name }`. | Silent acceptance violates resolver totality and compiler correctness. | Emit an unsupported/unresolved-qualified-path diagnostic and add expression/type negative tests. |
| **A-C2: return-flow checking** | **Confirmed defect** | `return` is checked against the result type, but `check_block` still returns `Unit` without a tail and `check_item` compares that with the annotation (`615-641,884-929`). Run the two functions in A-C2. | Rejects a valid explicit return and silently records an unannotated value-returning function as `()`. | Define omitted-return semantics and add return-only, branch-return, reachable-tail, and unannotated-tail tests. |
| **A-C3: role multiplicity ignored** | **Confirmed defect** | Rows count duplicates (`ty.rs:200-203`), while `missing_from` compares only key presence (`241-247`); closed-role checking uses it both ways (`lib.rs:1600-1610`). Run A-C3’s `{A,A}` → `{A}` example. | Breaks the documented multiset role invariant. | Make closed-row comparison count-aware; retain duplicate runtime bindings unless policy changes. |
| **A-C4: ignored type applications** | **Confirmed defect, narrowed** | `Vec`/`Sym` inspect only the first argument; scalars ignore all applications; alias application ignores site arguments and qualifiers (`366-469`). Test `Vec[S,Int]`, `Int[S]`, and `type B=Vec[S]; type X=B[Int; load 40]`. | Source annotations can contain semantically discarded material. | Validate arity and legal qualifiers for every type head. **Reject A’s `type AlsoBad = Vec[S; load 40]` as an ignored-qualifier example:** `Vec` does process `load`. |
| **A-C5: malformed `\u{…}` accepted** | **Confirmed defect** | The lexer only scans to `}` and validates neither content, closure, scalar range, nor surrogates (`raly-lexer:234-243`). Run lexer/check on empty, non-hex, out-of-range, surrogate, and unclosed escapes. | Malformed literals escape lexical diagnostics. | Add targeted lexer tests and validation. |
| **A-C6: locator arrow follows insertion order** | **Confirmed defect** | Renderer chooses `-->` using `i == 0`, independent of `LabelStyle` (`render.rs:179-182`), while underline style uses severity at `206-209`. | Can visually identify a secondary span as the fault site; material to diagnostic correctness. | Add secondary-before-primary renderer test and normalize locator selection. |
| **A-S1: invalid effective dimensions** | **Hypothesis** | Source proves zero and oversized folded integers are accepted as capacity inputs (`184-205`), but the bundle provides no normative range or relationship to nominal dimension. | Potential capacity-policy hole, not yet a proven language defect. | Specify the domain first; then test zero and effective-greater-than-nominal. No patch before that decision. |
| **A-S2: upper load bounds ignored** | **Rejected as a current defect** | Intersection compatibility and minimum-only capacity are explicit semantics (`ty.rs:89-92,132-139`; `lib.rs:1572-1597`). | The proposed “annotation is a guarantee” invariant contradicts current documented behavior. It may still be a design risk. | Open a separate semantics decision if guarantees are desired; do not silently change compatibility. |
| **B1: no IR/backend/runtime** | **Strong inference — acknowledged sequencing gap** | Directly documented in `PROJECT_GUIDE:222-225`, `HANDOFF:26`, `README:33`, and `ROADMAP:76,151`. | Raly cannot presently validate execution, gradients, or runtime intervention claims. | After correctness fixes, scope the smallest executable VSA subset; do not treat the missing planned phase as a regression. |
| **B2: Experiment 11 is disconnected from Raly** | **Strong inference** | `dsl.py` is a standalone regex/string interpreter with list operations; it imports no compiler component. Project guide explicitly permits Python before Raly executes (`252-257`). | Experiment 11 may test a toy typed-state idea, but it is not evidence for Raly’s parser, VSA types, or compiler semantics. | Correct scope language; require a Raly-backed experiment before making Raly-specific claims. |
| **C6: same DSL/compiler disconnect** | **Duplicate of B2** | Same source proof and impact. | No additional finding. | No separate reproduction. |
| **B3/B4/B6: no runtime intervention, VSA kernel, or AD path** | **Duplicates of B1** | All are immediate consequences of the acknowledged absence of executable IR/runtime. | They help define future scope but are not three independent defects. | Address through one executable-subset milestone; do not accept the reviewers’ specific architecture as evidence. |
| **B5: runtime capacity should fail** | **Rejected** | There is no runtime, and existing semantics explicitly say over-capacity cleanup degrades “without anything failing at run time” (`README:76-77`; `lib.rs:1804-1807`). | A mandatory runtime panic would change semantics, not repair a demonstrated defect. | None unless runtime capacity policy is separately redesigned. |
| **B7: “compiler constraint” is a string candidate filter** | **Confirmed claim/instrumentation defect** | `valid_candidates` constructs DSL strings from Python slot tags; `prefix_allowed_tokens_fn` restricts generation to those tokenizations (`smoke.py:163-185,216-237`). No Raly checker is called. `FINDINGS:73` calls it a compiler constraint. | The result demonstrates candidate filtering/type-tag enforcement, not Raly compilation or type-driven AST decoding. | Rename the instrument and revise claims, or actually route candidates through Raly once a mapping exists. |
| **B8: learned codebook provenance absent** | **Strong inference — acknowledged limitation** | README and roadmap explicitly state learned codebooks invalidate current capacity assumptions (`README:113`; `ROADMAP:149,162`); attributes other than `effective` are not interpreted. | Gates learned-codebook capacity claims, but is not a surprise regression in the present fixed-space checker. | Specify provenance/coherence semantics before implementing learned codebooks. |
| **C1: train-on-test contamination** | **Confirmed defect** | Training uses `examples(tasks[:26])`; evaluation uses the identical `tasks[:16]` objects (`smoke.py:313-328`). | Invalidates the original 15/16 result as held-out learning evidence, although it can remain a pipeline/memorization smoke. | Create explicit disjoint splits, assert identity/content disjointness, and correct `FINDINGS.md` wording. Do not merely use `tasks[26:]` without ensuring enough evaluation tasks. |
| **C2: threshold supplied by candidate generator** | **Confirmed experimental confound, narrowed** | Every generated `filter_gt` candidate uses `task.threshold`, with no competing integer (`smoke.py:174-182`). The threshold is normally visible in `task.request`, so it is not a private hidden label. | Constrained accuracy does not test extracting/generating the numeric argument; it tests operation/slot selection under a privileged candidate set. | Either declare argument generation out of scope or ablate with competing thresholds/open integer generation. |
| **C3: provenance leaks operation history** | **Confirmed defect** | Every operation appends its name to `Slot.provenance`; `serialize_state` emits it as `"from"` (`dsl.py:138-188,219-228`); mediated prompts include that JSON (`smoke.py:199-205`). | Confounds transcript versus “hard-mediated” comparisons. | Strip provenance from model-visible state and rerun the held-out comparison; provenance may remain internal. |
| **C4: empty prefix-token set at completed candidate** | **Hypothesis** | Source-level helper returns `[]` when `generated` equals a complete candidate (`smoke.py:225-235`), but the bundle does not show that Transformers invokes the callback after EOS rather than terminating first. | Runtime consequence and effect on reported runs remain unproven. | Add a focused callback/generation test against the pinned Transformers version before patching. |
| **C5: hardcoded optimizer sampler seed** | **Confirmed defect, limited impact** | `train_smoke` always uses `random.Random(11)` despite outer seeds (`smoke.py:137-142`; `next_smoke.py:74-104`). | Multi-seed runs reuse the same record-index schedule. Tasks and model initialization still differ, so “complete pseudoreplication” is overstated. | Thread the outer seed/RNG into training and record it. |
| **C7: relevant corruption is a no-op for integers** | **Confirmed defect, limited scope** | Relevant corruption mutates lists only (`dsl.py:231-235`). A counting-task `s3: Int` remains unchanged. | Makes the generic intervention sanity check invalid for integer outputs; default original smoke used a list-output first task, so this does not by itself overturn its reported list control. | Add primitive-type intervention tests and require mutation to be asserted. |
| **C bottom line: held-out failure falsifies the core premise** | **Rejected overclaim** | `FINDINGS:38-57` confirms failure of the current controller but explicitly says it does not show hard mediation is intrinsically worse. Raw artifacts were not supplied here. | Supports stopping or redesigning the current representation, not killing typed mediation as a general research hypothesis. | Preserve the negative current-system result; do not generalize beyond it. |

### Canonical compiler reproduction form

For each compiler case above:

```bash
cd compiler
cat > /tmp/repro.raly <<'EOF'
# replace with the listed Raly source
EOF
cargo run -q -p raly -- check /tmp/repro.raly
echo "exit=$?"
```

A silent zero exit for A-C1, A-C3, or the narrowed A-C4 cases confirms the escape. A-C2 should demonstrate both the erroneous rejection and the missing check.

## 3. Ranked findings to reproduce first

1. **C1 — train/evaluation identity overlap:** CPU-only, seconds, and directly changes the interpretation of Experiment 11’s headline 15/16 result.
2. **A-C1 — silent qualified paths:** smallest high-severity compiler escape; confirms invalid input can pass with no diagnostic.
3. **A-C2 — return flow:** affects both valid and invalid functions and must be settled before lowering functions to an IR.
4. **A-C4 — ignored type applications:** tests whether source-visible types can misrepresent what the checker enforced.
5. **C3 — model-visible provenance history:** cheap CPU reproduction that decides whether the mediated/transcript comparison is properly isolated.
6. **C2 — sole threshold candidate:** inspect the generated action set and quantify exactly what constrained accuracy did not test.
7. **A-C3 — role multiplicity:** directly tests one of Raly’s four advertised semantic properties.
8. **A-C5/A-C6, then C5/C7:** confirmed but lower sequencing impact.
9. **C4 prefix callback:** reproduce only after the direct defects; its actual HuggingFace runtime effect is uncertain.

## 4. Explicit rejects

- **Reject “runtime capacity must panic.”** It contradicts the supplied semantics and is not a repair for an observed runtime.
- **Reject A-S2 as a compiler bug under current semantics.** Interval intersection and minimum-only checking are deliberate; changing them requires a language decision.
- **Reject `Vec[S; load 40]` as proof that `Vec` ignores qualifiers.** `build_vec` handles `load`; the valid C4 reproducers are surplus applications to constructors/scalars/aliases.
- **Reject “Experiment 11 must already be written in Raly.”** The project guide explicitly permits Python while Raly cannot execute. The surviving conclusion is narrower: Experiment 11 cannot validate Raly-specific claims.
- **Reject “held-out failure falsifies the core premise.”** It falsifies the present controller/state representation on the reported held-out template, not typed mediation generally.
- **Reject the reviewers’ proposed `Mir` enum, kernel trait, panic policy, estimator tags, and runtime APIs as committee conclusions.** They are design suggestions, not results established by the bundle.
- **Do not patch effective-dimension bounds or the EOS callback yet.** Their intended semantics/runtime effect remain hypotheses requiring one focused decision or reproduction.

## 5. Patch/no-patch recommendation

**PATCH, in two narrow tracks; no backend patch yet.**

1. **Compiler correctness patch set:** A-C1, A-C2, A-C3, and narrowed A-C4 first; then A-C5 and A-C6. Each requires a failing regression test before implementation and the full compiler gate afterward:
   ```bash
   cargo build
   cargo test --workspace
   cargo clippy --workspace --all-targets
   cargo fmt --all --check
   ```
2. **Experiment/reporting patch set:** enforce disjoint smoke splits, remove model-visible provenance, accurately name the Python candidate constraint, control the training sampler seed, and repair integer intervention checks. Rerun only cheap deterministic checks before authorizing another model run.
3. **No patch yet:** A-S1, A-S2, C4, runtime capacity behavior, learned-codebook representation, or any prescribed IR architecture.
4. **Sequencing:** do not expand IR/backend work until the P1 front-end escapes are closed. Afterward, the next compiler milestone may be a minimal executable subset, consistent with the existing roadmap.

## 6. Limits and exact next smallest action

This decision is based on the supplied snapshot excerpts, not a checked-out repository. No command was run; parser acceptance, CLI exit behavior, generated artifacts, pinned Transformers behavior, and the reported held-out percentages were not independently recomputed. Some files cited by reviewers were absent or only partially supplied. The committee therefore confirms source-level control-flow defects, not the state of any later commit.

**Exact next smallest action — verify Experiment 11 overlap without loading a model:**

```bash
cd experiments/11_typed_state_mediation
python - <<'PY'
import random
from dsl import make_task

rng = random.Random(20260827)
tasks = [make_task(rng) for _ in range(32)]
train = tasks[:26]
evaluation = tasks[:16]

overlap = {id(t) for t in train} & {id(t) for t in evaluation}
print(f"train={len(train)} eval={len(evaluation)} identical_objects={len(overlap)}")
assert len(overlap) == 16
PY
```

Expected result: `identical_objects=16`. Record that output before editing code or claims.