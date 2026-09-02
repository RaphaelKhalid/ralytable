# Findings — Experiment 33

**The preregistered schema accepted all 100 clean synthetic records and rejected
all four deliberate answer/test/solution leakage records; it validates the
data-boundary contract but says nothing about whether the proposed loss trains
a parser.**

## Evidence

The clean record family contained only prompt, graph, public examples, and
counterfactual fields. Deliberate contamination used top-level `answer`,
`hidden_test`, nested `expected_output`, and `solution` fields. All clean rows
were accepted and all contaminated rows were rejected.

## Decision

Keep the separated graph, replay, counterfactual, and unused-field loss terms
and the hard leakage contract. Before model training, extend the audit to
encoded/nested strings and benchmark provenance; a top-level key filter is not
enough for real corpora.

## Limitations

- No loss is optimized and no parser is trained.
- Synthetic records do not establish contamination-free real data.
- No coding benchmark or Qwen comparison is run.
