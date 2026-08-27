# Codex entry point

Codex reads `AGENTS.md` at the repo root automatically. It is identical to
`CLAUDE.md`, so both tools start from the same rules.

Read in this order:

1. `AGENTS.md` — methodology rules and the claims that are not allowed. Binding.
   Every rule was written after a result here turned out wrong in that exact way.
2. `HANDOFF.md` — what exists, what was found, what was already tried and failed,
   and the ranked open directions. Start here if you are picking this up cold.
3. `ROADMAP.md` — the plan and the honest risks.
4. `experiments/*/FINDINGS.md` — nine experiments, verdict in the first sentence
   of each.

Plans written to be picked up cold, with no prior context:

- `docs/plan-controlled-language.md`
- `docs/arena-prior-art.md` (what exists and why trojan competitions died)
- `docs/small-model-baseline.md` (what is achievable at each parameter count)
