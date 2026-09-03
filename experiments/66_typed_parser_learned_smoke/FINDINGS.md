# Findings — learned typed-parser smoke

The structured parser objective failed the preregistered gate, so the
under-40M coding-model run must not start.

Across seeds 11, 23, and 37, the structured arm improved exact held-out graph
recovery over the matched graph-cross-entropy null (11.5% versus 0.0%). That
did not translate into the behavior the ledger needs: execution-equivalent
replay was 25.5% for the structured arm versus 29.3% for the null, and changing
a relevant requirement changed the structured prediction only 12.2% of the
time versus 17.2% for the null. The preregistered relevant-intervention target
was 80%.

Unused-field invariance averaged 95.7% for the structured arm, but one seed was
93.2%, below the 95% per-seed floor. Both arms reached 100% train-set exact
graph and replay accuracy, making the held-out failure a compositional
generalization failure rather than simple underfitting.

The first smoke instrument was invalidated before reporting: its supposed
placebo pair also resampled semantic phrases, and its evaluation demanded
wholly unseen synonyms from a tiny byte-level model. The instrument was fixed
to hold all semantic wording constant within intervention pairs and to use
unseen paraphrases with shared semantic anchors. Only the corrected run is in
`summary.json`.

This is a three-seed synthetic smoke test over two-node list-operation graphs.
It supplies no confidence interval and says nothing directly about Python code
generation, HumanEval+, a 40M model, or comparison with Qwen. It does show that
the current structured loss is not a sufficient reason to pay for the larger
run.

Reproduce with the PyTorch environment described in `README.md`:

```text
python experiments/66_typed_parser_learned_smoke/run.py
```

The recorded run used PyTorch 2.13.0+cu130 on CUDA. Full per-seed metrics and
the exact environment facts are in `summary.json`.
