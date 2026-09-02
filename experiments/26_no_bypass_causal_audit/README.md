# Experiment 26 — no-bypass causal audit

Dependency-free test of the causal gate proposed for a typed-ledger coder. The
synthetic renderers deliberately include a raw-prompt shortcut, a decorative
trace, a mixed path, and a ledger-only path. We intervene on the typed state,
the raw prompt, and an irrelevant placebo independently.

The required pattern is: relevant state changes output, raw-prompt distractor
does not, and irrelevant state does not. This is an audit methodology result,
not evidence of coding ability.

Run `python causal_audit.py`.
