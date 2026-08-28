# Experiment 13 — typed sketch and recurrent state search

Status: exploratory smoke harness. No claim about general Python capability is
made by this experiment.

The architectural bet is that a small learned controller should not have to
learn syntax, type safety, or all search. It emits a short, inspectable
operation sketch. A Raly-style typed sketch harness masks impossible transitions and
bounded search verifies candidates on public examples before hidden execution.
The hidden input/output is never shown to the controller or verifier.

Three directions are logged separately:

- raw-controller: greedy learned sketch with no type mask or search.
- typed-greedy: same sketch with type masks but no public-example repair.
- typed-local-repair: typed public-example repair restricted to edit distance two.
- typed-sketch: same learned weights, typed legality and public-example search.
- deterministic-null: no model; bounded typed enumeration.

The current exploratory branch also logs `state-raw`,
`state-typed-greedy`, `state-typed-beam`, and `state-null`. These use a small
recurrent controller conditioned on typed executable state over a harder
four-operation held-out family. The corrected three-seed result is recorded in
FINDINGS.md: the learned beam leads the null on hidden pass, but its exposed
state has not passed the causal intervention gate.

The state-gated margin branch logs `state-gated-raw`,
`state-gated-greedy`, and `state-gated-beam`. It adds an explicit state-to-action
gate and counterfactual margin; the beam branch was rejected because its
three-seed pass and compile rates were below the ungated recurrent beam, even
though raw generation improved.

The state-dependent repair branch logs `repair-raw`, `repair-typed`,
`repair-public`, and `repair-null`. It predicts one missing operation in a
corrupted executable sketch. The learned public-search arm is currently the
best efficiency lead, but its state intervention remains below the causal
promotion threshold.

The abstract-value branch logs `value-raw`, `value-public`, `value-null`,
`value-state-only`, and `value-state-only-public`. The state-only controller
removes the request-text pathway and is the clearest candidate for a state that
is causally load-bearing in a synthetic control, but its task family is
intentionally synthetic and the null matches its full-system accuracy.

The executable-Python port logs `py-state-null`, `py-state-only`, and
`py-state-only-public`. It renders candidate actions as Python functions and
validates them through parse, compile, public execution, and hidden execution.
It preserves the state-only raw causal signal, but remains a generated
microtask benchmark rather than general repository coding.

The important null is the deterministic enumerator. If it solves the tasks
within budget, the learned model is not needed for correctness and its value is
only search efficiency. If the typed system wins only after seeing hidden
answers, the result is invalid; the harness never does that.

The two-parameter predicate-gate lineage is a supplied-bit identity/routing
control, not semantic inference. In particular, the `semantic_rule_gate` and
`repository_bundle_gate` nuisance placebos are tautological because nuisance is
absent from the gate; their causal rates are historical and not promotion
evidence. All task families remain synthetic or generated, and the actual Raly
compiler/runtime is not in the execution path.

Run a short smoke from the repository root:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/run.py --device cpu --updates 120 --seeds 11,23,37 --fresh-log

For local live monitoring, in another terminal:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/dashboard_server.py --port 8767

Then open http://127.0.0.1:8767/dashboard.html. The dashboard polls the
append-only research_log.jsonl every three seconds.

The learned parameter gate is checked in code and the raw and full-system
metrics are never merged. Causal evidence is limited to interventions whose
interface is not tautological: swapping a relevant step must alter the
selected program, while an irrelevant perturbation should preserve it. This is
causal dependence in a synthetic control, not parameter-level understanding.

Historical `latency_ms` fields begin after model inference and include old-loop
evaluation work. New runs of `run.py` emit separate inference, selection,
hidden-scoring, and end-to-end-through-selection timings. The append-only log
and the preserved invalid oracle log are not recomputed by the audit.

The Python-surface replication is run with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/python_surface.py --device cuda --updates 181 --train-count 96 --eval-count 48 --seeds 11,23,37

It lowers the same typed IR to restricted Python, then parses, compiles, and
executes the generated function for public and hidden cases.

The recurrent state branch is reproduced with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/state_policy.py --device cuda --updates 181 --train-count 96 --eval-count 48 --seeds 11,23,37

To rerun only the gated branch:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/state_policy.py --device cuda --updates 181 --train-count 96 --eval-count 48 --seeds 11,23,37 --directions state-gated-raw,state-gated-greedy,state-gated-beam

To rerun the repair branch:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/repair_policy.py --device cuda --updates 181 --train-count 96 --eval-count 48 --seeds 11,23,37

To rerun the abstract-value branch:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/abstract_value_state.py --device cuda --updates 181 --train-count 96 --eval-count 48 --seeds 11,23,37

To rerun the executable-Python state-only port:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/python_state_only.py --device cuda --updates 181 --train-count 96 --eval-count 48 --seeds 11,23,37

The full-system beam state audit is included in that same command's
`state-typed-beam` rows. It is recorded separately from the preregistered
greedy intervention because it measures causal dependence at the point where
the reported beam capability is actually selected.

The larger executable-Python repair suite is run with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/python_repair_suite.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37

It reports raw controller performance separately from public-verifier
performance, checks the 9M learned-parameter gate, and records the
relevant-state versus irrelevant-placebo intervention rates.

The text/state recombination falsification is run with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/python_recombination.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37

Its `recomb-hybrid` direction receives both an intent-first request token and
the executable abstract state; the state-only and text-only rows are
one-factor controls.

The explicit cross-product follow-up can be isolated with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/python_recombination.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37 --directions recomb-cross,recomb-cross-public

The held-out factor-combination stress test is run with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/python_recombination_ood.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37

The additive-rule diagnostic can be isolated with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/python_recombination_ood.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37 --directions ood-additive

The cyclic-factor diagnostic can be isolated with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/python_recombination_ood.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37 --directions ood-cyclic

The natural-language conditional repair proxy is run with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/python_semantic_repair.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37

The typed semantic-parser/controller split is run with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/semantic_parser_controller.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37

The explicit typed predicate-slot follow-up is run with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/semantic_predicate_slots.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37

The two-parameter learned predicate-gate follow-up is run with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/semantic_rule_gate.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37

The held-out request-paraphrase gate test is run with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/semantic_paraphrase_gate.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37

The ordinary Python source-repair gate test is run with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/python_source_repair_gate.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37

The varied executable-prefix typed-state test is run with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/python_source_prefix_gate.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37

The two-hole ordinary Python repair test is run with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/python_source_two_hole_gate.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37

The multi-file repository bundle gate test is run with:

    C:\Users\rapha\AppData\Local\Programs\Python\Python312\python.exe experiments/13_autoresearch_raly_coder/repository_bundle_gate.py --device cuda --updates 181 --train-count 512 --eval-count 256 --seeds 11,23,37
