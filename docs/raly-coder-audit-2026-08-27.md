# Raly Coder takeover audit

Date: 2026-08-27

## Verdict

Ralytable has a credible compiler and a disciplined record of negative model
results, but it does not yet have evidence for Raly Coder. The next experiment
must measure executable coding success and causal dependence on named typed
states. The existing typed-state controller is a useful plumbing prototype, not
the coding benchmark or the 9M-parameter comparison.

## Repository and Git state

- Current branch: `codex/result-type-ablation` at `03da4f4`.
- One open PR: [#30](https://github.com/RaphaelKhalid/ralytable/pull/30),
  `Add typed-state mediation smoke and return-type ablation`, targeting `main`.
- PR checks observed: Vercel deployment and preview comments passed.
- The worktree is dirty. Uncommitted tracked edits touch `AGENTS.md`,
  `CLAUDE.md`, `HANDOFF.md`, `README.md`, `ROADMAP.md`, and `tools/watch.py`.
  Untracked work includes experiment-11 outputs, review notes, the OpenRouter
  tournament artifacts, and project-guide material. These are preserved and are
  not part of this audit change.
- No merge, benchmark submission, or paid external call was made during this
  audit.

## What the experiments establish

- Experiments 00-03 show that self-reported dependency graphs and committor
  trajectories do not provide a clean causal importance signal. Position and
  decision confidence explain much of the apparent structure.
- Experiments 04-07 establish real VSA/embedding capacity risks and a potentially
  useful embedding-aggregation diagnostic. They do not establish a coding
  architecture.
- Experiments 08-09 show a matched 29.5M, 512-code midpoint model losing to a
  dense control on TinyStories cross-entropy, accuracy, and blind story quality.
  The failure is especially referential identity, not merely grammar.
- Experiment 10 shows that the taboo-organism audit is at ceiling under a cheap
  semantic attack. It is not a useful public benchmark as currently designed.
- Experiment 11 shows that the deterministic toy interpreter and intervention
  plumbing work, while the held-out-template smoke fails badly for the current
  mediated controller. The result-type ablation changes legal returns but gives
  no total accuracy improvement. Raw unconstrained pass rate is zero in the
  recorded smoke, so constrained decoding is currently doing substantive work.

## Open questions that matter for Raly Coder

1. Does typed executable structure improve hidden-test pass rate at matched
   parameter count, or only improve syntax validity?
2. Does the improvement, if any, survive held-out repositories, bug patterns,
   operation order, and unseen symbol names?
3. Does the model use the declared intermediate state? A relevant state
   intervention must change the result more than an irrelevant intervention,
   with a placebo and residual-off control.
4. How much of any result is caused by the agent scaffold: constrained decoding,
   retries, tool affordances, prompt length, or test feedback?
5. Can a 9M Raly model retain useful code identity and test feedback, and does a
   matched 28M Raly control change the answer through capacity alone?
6. Does the selected Python API vocabulary cover the operations required by the
   private benchmark without becoming a disguised general shell interface?

## Immediate decision

Build the smallest deterministic Python coding sandbox and a private held-out
benchmark before changing the neural architecture. The first confirmatory
comparison should hold the sandbox, task order, action budget, retries,
temperature, prompts, tokenizer, optimizer, data budget, and evaluator fixed
across dense, free-text-CoT, and Raly arms. The smoke test is only a pipeline
gate. A pretty trace without more passing tests or selective intervention is a
failure for this project.

