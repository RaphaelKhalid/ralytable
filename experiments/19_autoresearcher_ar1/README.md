# Autoresearcher AR1

AR1 evaluates researcher policies with a preregistered cost-normalized score,
larger deterministic landscapes, multiple instances, paired seeds, exhaustive
optimum/QD checks, a blind family, and explicit credit/QD falsifications.

Run the frozen protocol in the repaired WSL environment:

```text
wsl.exe -d Ubuntu -- env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/mnt/c/Users/rapha/.codex/worktrees/8bdb/mechinterp /home/rapha/ralytable-autoresearch-next/.venv/bin/python -m tools.autoresearch_next ar1 --root /home/rapha/ralytable-autoresearch-next --environment wsl
```

Start the loopback dashboard with:

```text
wsl.exe -d Ubuntu -- env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/mnt/c/Users/rapha/.codex/worktrees/8bdb/mechinterp /home/rapha/ralytable-autoresearch-next/.venv/bin/python -m tools.autoresearch_next ar1-dashboard --root /home/rapha/ralytable-autoresearch-next --port 8791
```

AR1 writes only to `/home/rapha/ralytable-autoresearch-next/ar1` and never
invokes official HumanEval+.
