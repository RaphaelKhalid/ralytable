# Experiment 66 — learned typed-parser smoke

This is the first optimization run for the objective preregistered in
`preregistrations/33_typed_parser_objective.md`. It is deliberately small and
synthetic: a byte-level parser maps two ordered requirements into a typed
two-node list-operation graph.

The comparison holds architecture, parameters, examples, batches, and seeds
fixed. The null optimizes graph-token cross-entropy only. The structured arm
adds deterministic replay-signature classification, a paired counterfactual
margin, and prediction invariance to a declared-unused note using the
preregistered weights `1.0 / 0.5 / 0.5 / 0.25`.

Evaluation compositions are held out as whole semantic groups. Prompts use
unseen paraphrases, renamed identifiers, and changed unused notes. No benchmark
prompts, solutions, tests, expected outputs, or answer-bearing metadata are
used. The renderer consumes only the predicted graph.

Run in the existing PyTorch environment:

```text
python experiments/66_typed_parser_learned_smoke/run.py
```

This is a smoke test of the learned-parser gate, not evidence about Python
coding, HumanEval+, a 40M model, or Qwen parity.

## Result

The structured arm failed the preregistered compositional and causal gate, so
the under-40M run remains blocked. See [FINDINGS.md](FINDINGS.md) for the
verdict and limitations and `summary.json` for every per-seed measurement.
