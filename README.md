# legible-reasoning

Interpretability for reasoning models: is the structure of a chain of thought the
structure of the computation?

**Status:** scoping. Nothing here is a result yet.

## The question

Reasoning models do their work across thousands of forward passes, with the visible
text acting as the wire between them. [Thought Anchors](https://arxiv.org/abs/2506.19143)
(Bogdan et al., 2025) proposed the first paradigm for this: treat a *sentence* as the
unit of computation, and measure its importance by resampling it ~100 times and watching
the final-answer distribution move.

That instrument is expensive (~100 API calls per sentence) and has known confounds
(overdetermination, sentence position). This repo asks whether the dependency structure
of a reasoning trace can be read off *directly* instead of estimated by ablation --
and whether the structure you read off is the one that is causally real.

## Planned work

1. **Baseline.** Reproduce sentence-level resampling importance on a cheap
   open reasoning model via OpenRouter. Small: a handful of problems, capped resamples.
2. **Instrument audit.** Quantify the position confound and the overdetermination
   blind spot in that baseline.
3. **Substrate experiment.** Have the model reason in a formally-structured substrate
   where step dependencies are explicit, and test whether the read-off dependency graph
   predicts the resampling-measured causal importance.

Outcomes are informative in both directions: agreement gives a much cheaper
interpretability instrument, disagreement is a faithfulness result about what
natural-language CoT is doing.

## Conventions

- Every experiment lands via a PR. Claims are preregistered in `preregistrations/`
  before the run, not after.
- Negative and null results are kept, not deleted.
- `RESEARCH_LOG.md` is append-only and includes dead ends.

## License

MIT
