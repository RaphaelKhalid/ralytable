# Autoresearcher AR0

AR0 evaluates search policies before they are applied to any Python coder. It
uses small deterministic bit-vector landscapes with exhaustively enumerable
optima, paired seeds, an unseen constraint-heavy family, and the existing
typed-state candidate only as a CUDA/orchestration proxy.

Run from the repository root with the repaired WSL environment:

```text
wsl.exe -d Ubuntu -- env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/mnt/c/Users/rapha/.codex/worktrees/8bdb/mechinterp /home/rapha/ralytable-autoresearch-next/.venv/bin/python -m tools.autoresearch_next ar0 --root /home/rapha/ralytable-autoresearch-next --seeds 11,23,37 --budget 64 --environment wsl
```

The run writes only to `/home/rapha/ralytable-autoresearch-next/ar0` and does
not invoke official HumanEval+.
