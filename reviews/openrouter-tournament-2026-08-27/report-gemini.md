### Five-Line Bottom-Line Verdict

1. Experiment 11's reported learning success is an artifact of 100% train-on-test data contamination (`tasks[:16]` evaluated after training on `tasks[:26]`).
2. Constrained decoding operates as an information oracle by injecting ground-truth task arguments (`task.threshold`) directly into candidate strings.
3. The supposedly "transcript-free" mediated state leaks the full operation history inside the serialized JSON slot provenance metadata (`from`).
4. The Python DSL shares zero syntax, semantics, AST structures, or type checking with the Raly compiler front end in `compiler/`.
5. On held-out templates, hard mediation collapses (6.25% accuracy vs 60.42% for transcript, and 0% unconstrained); the core premise is falsified.

---

### Material Findings

#### Finding 1 (P0): Direct Train-on-Test Contamination in Experiment 11 Baseline Smoke
- **Verdict:** The headline smoke evaluation pass rate (15/16) was measured on the exact task instances used during training.
- **File and line(s):** `experiments/11_typed_state_mediation/smoke.py:313, 327-328`
- **Invariant allegedly violated:** Evaluation sets must be strictly disjoint from training sets; smoke learning gates must test generalization or explicitly label training-set memorization.
- **Minimal reproducer:**
  ```python
  # smoke.py:313
  pairs = examples(tasks[:26], mode)
  losses = train_smoke(model, tokenizer, device, pairs, args.updates)
  # smoke.py:327
  eval_rows = [run_controller(model, tokenizer, device, t, mode) for t in tasks[:16]]
  ```
  `tasks[:16]` is a proper prefix of `tasks[:26]`. All 16 evaluation tasks were seen multiple times across the 100 training updates.
- **Expected versus actual result:** Expected evaluation on held-out tasks (`tasks[26:]`); actual evaluation evaluated on `tasks[:16]`, making the 15/16 result pure memorization of a 5-line static template.
- **Regression test:** Partition `tasks` into `tasks[:train_count]` and `tasks[train_count:]` with an explicit assertion `assert len(set(eval_tasks).intersection(set(train_tasks))) == 0`.
- **Smallest safe fix:** In `smoke.py:327`, slice `tasks[26:]` instead of `tasks[:16]`.
- **Confidence and falsification:** Confirmed defect. Falsified only if `tasks[:16]` and `tasks[:26]` do not reference the same list instances.

---

#### Finding 2 (P0): Ground-Truth Parameter Leakage via Constrained Decoding Action Space
- **Verdict:** The constrained decoding grammar leaks the private ground-truth threshold argument directly into the model's candidate set.
- **File and line(s):** `experiments/11_typed_state_mediation/smoke.py:163-185`, `experiments/11_typed_state_mediation/dsl.py:63`
- **Invariant allegedly violated:** Constrained decoding must enforce structural/syntactic validity, not inject hidden target parameters into the candidate set.
- **Minimal reproducer:**
  ```python
  # smoke.py:178
  candidates.extend([
      f"filter_gt {source} {task.threshold} -> {target}",
      f"sort_asc {source} -> {target}",
      f"unique {source} -> {target}",
      f"count {source} -> {target}",
  ])
  ```
  `task.threshold` is read from the private `Task` struct. The model is never offered any other integer argument (e.g. `filter_gt s0 0 -> s1`), eliminating the need to extract or predict numerical parameters from `task.request`.
- **Expected versus actual result:** Expected candidate generation parameterized over integers present in the prompt/domain or an open grammar; actual candidate generator spoon-feeds the ground-truth integer.
- **Regression test:** Replace `task.threshold` in `valid_candidates` with candidate integers drawn from `[-20, 20]`. Measure model accuracy when selecting among 40 threshold variants.
- **Smallest safe fix:** Parameterize `valid_candidates` over all integer literals present in `task.request` or require unconstrained parameter token generation.
- **Confidence and falsification:** Confirmed defect. Falsified only if `valid_candidates` generates competing threshold values.

---

#### Finding 3 (P1): Full History Transcript Leakage Inside the Serialized "Mediated" State
- **Verdict:** The hard-mediated state representation explicitly includes the complete sequential execution history via slot provenance metadata.
- **File and line(s):** `experiments/11_typed_state_mediation/dsl.py:22-25, 138, 151, 163, 177, 225`, `experiments/11_typed_state_mediation/smoke.py:73`
- **Invariant allegedly violated:** Hard mediation requires that the controller acts purely on current typed state without access to the execution transcript.
- **Minimal reproducer:**
  ```python
  # dsl.py:223-225
  slots[name] = {
      "type": slot.type_name if include_types else "Value",
      "value": slot.value,
      "from": list(slot.provenance),
  }
  ```
  `Slot.provenance` accumulates every preceding operation (`("input", "filter_gt", "sort_asc", "unique")`). When serialized to JSON, `Current typed state:` contains the chronological operation sequence.
- **Expected versus actual result:** Expected state representation to contain only current value and type assertions; actual state contains a reconstructed operation transcript.
- **Regression test:** Strip `"from"` from `serialize_state()` and evaluate whether mediated accuracy drops on multi-step tasks.
- **Smallest safe fix:** In `serialize_state()`, omit `"from"` or sanitize provenance to a static space identifier.
- **Confidence and falsification:** Confirmed defect. Falsified if `"from"` is stripped before passing the prompt to the model.

---

#### Finding 4 (P1): Unconstrained Generation Collapse and Degenerate Prefix-Allowed Token Mask
- **Verdict:** The controller achieves 0% pass rate without constrained decoding, while the constrained token mask returns empty candidate sets upon string completion.
- **File and line(s):** `experiments/11_typed_state_mediation/smoke.py:225-237`, `experiments/11_typed_state_mediation/FINDINGS.md:48, 78`
- **Invariant allegedly violated:** Constrained generation must handle terminal sequence states gracefully, and architecture claims must not obscure 0% base model fidelity.
- **Minimal reproducer:**
  ```python
  # smoke.py:228-235
  matching = [ids for ids in candidate_ids if ids[:len(generated)] == generated]
  if not matching:
      return list(range(tokenizer.vocab_size))
  return sorted({ids[len(generated)] for ids in matching if len(generated) < len(ids)})
  ```
  When `generated` matches a candidate including its EOS token, `len(generated) < len(ids)` is false for all `ids` in `matching`. The comprehension evaluates to `set()`, returning `[]`.
- **Expected versus actual result:** Expected explicit EOS return or fallback; actual returns empty list, forcing `-inf` logits across the entire vocabulary in HuggingFace `generate`.
- **Regression test:** Call `allowed_tokens(0, torch.tensor([...prefix_ids, ...candidate_ids[0]]))` and assert return value is non-empty.
- **Smallest safe fix:** When `any(len(generated) == len(ids) for ids in matching)`, return `[tokenizer.eos_token_id]` or allow termination.
- **Confidence and falsification:** Confirmed defect. Falsified if HuggingFace `generate` intercepts empty token lists without setting all logits to `-inf`.

---

#### Finding 5 (P1): Hardcoded Optimizer RNG and Seed Pseudoreplication in Multi-Seed Runs
- **Verdict:** Multi-seed training runs in `next_smoke.py` use identical optimizer batch sampling sequences due to an internal hardcoded RNG seed.
- **File and line(s):** `experiments/11_typed_state_mediation/smoke.py:137-142`, `experiments/11_typed_state_mediation/next_smoke.py:62, 74-104`
- **Invariant allegedly violated:** Multi-seed evaluations must randomize both task generation and mini-batch optimization trajectories.
- **Minimal reproducer:**
  ```python
  # smoke.py:137
  def train_smoke(..., updates: int, ...):
      ...
      rng = random.Random(11)  # Hardcoded seed 11 ignored outer seed loop!
      for step in range(updates):
          batch = [records[rng.randrange(len(records))] for _ in range(batch_size)]
  ```
- **Expected versus actual result:** Expected each seed in `next_smoke.py` (`11, 23, 37`) to control `train_smoke` batch indexing; actual executed identical mini-batch update orders across all runs.
- **Regression test:** Pass an explicit `seed` parameter to `train_smoke` and verify distinct loss trajectories on identical task sets.
- **Smallest safe fix:** Pass `rng: random.Random` or `seed: int` into `train_smoke`.
- **Confidence and falsification:** Confirmed defect. Falsified if `train_smoke` derives its RNG from the outer environment.

---

#### Finding 6 (P1): Complete Disconnect Between Experiment 11 DSL and the Raly Compiler
- **Verdict:** Experiment 11 tests an ad-hoc Python string-regex interpreter that shares zero AST nodes, type rules, or execution semantics with the Raly compiler front end.
- **File and line(s):** `experiments/11_typed_state_mediation/dsl.py:17-203`, `compiler/crates/raly-types/src/lib.rs:1-110`, `compiler/GRAMMAR.md:1-120`
- **Invariant allegedly violated:** Experiments evaluating Raly's typed intermediate representation must compile or check against Raly's actual semantic definitions.
- **Minimal reproducer:**
  Compare `dsl.py` operations (`filter_gt`, `sort_asc`, `unique`, `count`) with Raly primitives in `GRAMMAR.md` (`bind`, `bundle`, `permute`, `unbind`, `cleanup`, `broadcast`). The Python code never imports, links to, or calls `raly` / `raly-wasm` / `raly-types`.
- **Expected versus actual result:** Expected state mediation to test Raly's abelian dimensions (`MAP[8192]`), role schemas (`roles {Subject, Verb}`), load intervals (`load 3 of 31`), and cleanliness; actual evaluated integer list sorting.
- **Regression test:** Attempt to parse any `dsl.py` program with `cargo run -p raly -- parse`; it will fail with parse error `RALY2011`.
- **Smallest safe fix:** Build an execution runtime for Raly AST nodes before asserting that "typed state mediation" validates Raly language design.
- **Confidence and falsification:** Confirmed defect / Strong inference. Falsified only if `dsl.py` is an intentional non-Raly toy baseline and explicitly documented as unrelated to the Raly type checker.

---

#### Finding 7 (P2): Intervention Sanity Check Silently Fails on Non-List Slot Types
- **Verdict:** `corrupt_state(state, "relevant")` is a no-op when the target slot contains an integer, causing the oracle intervention check to fail on counting tasks.
- **File and line(s):** `experiments/11_typed_state_mediation/dsl.py:231-250`, `experiments/11_typed_state_mediation/smoke.py:44-54`
- **Invariant allegedly violated:** Causal intervention controls must mutate state across all supported primitive types, not silently pass through non-list values.
- **Minimal reproducer:**
  ```python
  from dsl import Task, State, Slot, corrupt_state
  state = State(slots={"s3": Slot("Int", 42, ("count",))})
  corrupted = corrupt_state(state, "relevant", relevant="s3")
  assert corrupted.slots["s3"].value != state.slots["s3"].value  # FAILS (value is still 42)
  ```
  `isinstance(out.slots[relevant].value, list)` evaluates to `False`. The integer is not corrupted.
- **Expected versus actual result:** Expected integer values to be modified (e.g. `value ^ 1` or `value + 1`); actual returns unchanged state, causing `check_interpreter` to raise `RuntimeError` if `tasks[0]` is a counting task.
- **Regression test:** Run `check_interpreter([make_task(random.Random(0), template="filter_unique_count")])`.
- **Smallest safe fix:** Add `elif isinstance(out.slots[relevant].value, int): out.slots[relevant].value += 1` to `corrupt_state`.
- **Confidence and falsification:** Confirmed defect. Falsified if `relevant` is guaranteed to point exclusively to `List[Int]` slots.

---

### Classification of Findings

- **Confirmed Defects:** Findings 1, 2, 3, 4, 5, 7.
- **Strong Inferences:** Finding 6 (Experiment 11 provides no evidence for Raly's actual type system).
- **Hypotheses:** None required; all material issues are grounded in source code reproduction paths.

---

### Ranked Top Three Findings

1. **Finding 1 (P0) — Direct Train-on-Test Evaluation Contamination:** Invalidates all reported smoke pass rates (15/16) in `FINDINGS.md`.
2. **Finding 2 (P0) — Ground-Truth Parameter Leakage in Constrained Decoder:** Invalidates the model's apparent execution capability by feeding the exact target threshold into the generation candidate set.
3. **Finding 6 (P1) — Complete Semantic Disconnect from Raly Compiler:** Falsifies the claim that Experiment 11 evaluates Raly's typed state representation or compiler architecture.

---

### Direction Decision: KILL Current Experiment 11 Direction / PIVOT to Compiler Runtime

- **Decision:** **KILL** the prompt-based Python DSL typed-state mediation direction.
- **Justification:**
  1. The Python DSL is a disconnected toy that does not test Raly's actual VSA types, abelian dimensions, role schemas, or capacity bounds.
  2. Hard mediation failed its generalization gate (6.25% vs 60.42%) on held-out templates, while unconstrained generation is 0%.
  3. The project roadmap explicitly prioritizes Direction 1 (Auditing baseline extension), Direction 4 (Embedding diagnostic product), and Direction 6 (Raly IR and execution backend). Effort spent building prompt-mediated Python list transformers distracts from making Raly itself executable.