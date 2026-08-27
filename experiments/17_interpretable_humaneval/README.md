# Experiment 17 — interpretable HumanEval+ architecture smoke

This directory contains the first trainable candidate and a dependency-free
code-validation proxy. The candidate is a nine-parameter named typed-state
monotonic gate trained from source/request/execution-derived features. It does
not emit HumanEval Python completions, so its proxy scores are not HumanEval+
scores and no official hidden tests are loaded here.

The immutable trust kernel and append-only ledger live under
`tools/autoresearch_next/`. Candidate configuration may evolve; evaluator,
partitions, hidden-score storage, ledger, and trust code may not.

Example, with artifacts outside Git:

```text
python -m tools.autoresearch_next init --profile rtx4060-8gb --root C:\temp\ralytable-autoresearch-next
python -m tools.autoresearch_next run --arm both --experiments 10 --seconds 300 --root C:\temp\ralytable-autoresearch-next
python -m tools.autoresearch_next report --root C:\temp\ralytable-autoresearch-next
python -m tools.autoresearch_next dashboard --root C:\temp\ralytable-autoresearch-next --port 8787
```

The requested 300-second budget is a ceiling. The dependency-free fallback
finishes earlier on CPU and records that deviation. An approved WSL/PyTorch
environment can replace the training implementation without changing the
trust boundary.

