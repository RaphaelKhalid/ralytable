# Autoresearcher AR2

AR2 tests whether a frozen stagnation-aware MAP-Elites/emitter portfolio
improves the autoresearcher on fresh deterministic landscapes. It is a
researcher meta-evaluation, not a Python-coder, HumanEval+, or interpretability
result.

The frozen protocol is in `PROTOCOL.md`. The implementation is in
`tools/autoresearch_next/ar2.py`; all run data, receipts, certificates,
checkpoints, ledgers, and reports are kept outside Git under
`/home/rapha/ralytable-autoresearch-next/ar2`.

The corrected run was resumed from preserved artifacts rather than restarting
completed trials. The first run is retained as invalid audit evidence because
its multi-trial receipt checker was wrong; see `IMPLEMENTATION_CORRECTION.md`.
