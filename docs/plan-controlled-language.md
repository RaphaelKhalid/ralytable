# Plan: does constraining the output language make reasoning verifiable, and what does it cost?

Status: **not started.** Written to be picked up cold, by a later session or by
Codex. Nothing here has been run. Every number below is a target, not a result.

## The question

Not "can we compress language". The question is:

> **If a model must express its reasoning in a restricted language, how much more
> of that reasoning can a machine check, and how much accuracy does it lose?**

The output is one number pair: **verifiability gained, accuracy lost.** If
verifiability rises a lot and accuracy falls a little, that is the legibility
trade in a form that pays for itself.

## Why this is worth doing

Controlled natural languages already work in industries where ambiguity is
expensive. ASD Simplified Technical English is mandatory in aerospace maintenance
manuals: restricted vocabulary, one meaning per word, prescribed sentence shapes.
Attempto Controlled English is an English subset that maps deterministically onto
first-order logic, so a machine can prove things about what was written. Basic
English ran on 850 words.

None of those were built for brevity. They were built so that what was written
could be **checked**. That is the same reason this project wants them.

It also connects the two halves of the project for the first time. A constraint
on an output language is a thing a type system can enforce, which is what Raly is
for.

## How it relates to the arena

They are the independent and dependent variable of one experiment.

- The **arena** (`experiments/10_auditing_baseline` and whatever follows it)
  measures whether a hidden property inside a model can be found.
- **Controlled language** is a mechanism that should make hiding harder. A hidden
  objective has to make the model's stated reasoning diverge from its behaviour.
  In free English nothing checks the words against anything. In a language where
  each step is verifiable, a lie is a step that fails verification rather than
  text nobody examined.

The claim they jointly support, and neither supports alone:

> Models that reason in a verifiable language are N times easier to audit, at M%
> capability cost.

Arena supplies N. This pilot supplies M.

**They do not compete for resources.** The arena is GPU and local model weights.
This pilot is API only and costs cents. Run them at the same time.

## Do this first, before building anything

**Can a frontier model even stay inside the constraint?** If DeepSeek cannot hold
the format without falling apart, a 29M model certainly cannot, and that is worth
knowing for a dollar rather than a week. This is a kill-switch, not a warm-up.

## Design

### The two conditions

Same problems, same model, same temperature, two output formats.

**A. Free** — ordinary chain of thought, no constraint.

**B. Controlled** — a restricted language. Start strict and relax only if
condition A's accuracy proves unreachable:
- a fixed vocabulary of relation and operation words, published in the prompt
- one assertion per line, no subordinate clauses
- every quantity introduced must be named once and referred to by that name after
- every derived line names the lines it uses, in the `[3] from [1],[2]:` shape
  already used in `experiments/06_discrete_core`
- a final answer line in a fixed format

Design the grammar so a parser either accepts a line or rejects it. Ambiguity
that a human would resolve is a failure of the grammar, not of the model.

### The task

Needs a checkable ground truth and reasoning worth verifying. GSM8K is the
obvious choice: real, published, unambiguous numeric answers. Use a fixed random
sample, at least 200 problems, drawn once and reused across conditions so the
comparison is paired.

### The two measurements

**Accuracy.** Fraction of final answers correct. Paired across conditions on the
same problems, so report the paired difference with a confidence interval, not
two independent means.

**Verifiability — the hard part, and the part to get right.** Not "does it look
structured". A step counts as verified only if a **program** confirms it:
- parse each line against the controlled grammar; unparseable lines are
  unverifiable by definition
- for arithmetic lines, recompute and compare
- for lines that cite earlier lines, confirm the cited lines exist, precede it,
  and actually supply the named quantities
- report the fraction of steps verified, and separately the fraction of problems
  where *every* step verified

Run the same checker against condition A. Free-form English will mostly fail to
parse, and **that gap is the result.** If it does not fail, the constraint is
buying nothing and the pilot has answered its question.

### Controls, all of which have caught something in this repo already

- **Baseline for verifiability.** What fraction of free-text steps does the
  checker verify? Without it, "88% verified" means nothing.
- **A checker that can fail.** Feed it deliberately wrong reasoning: correct
  format, false arithmetic, citations to lines that do not exist. If it verifies
  those, it is a formatter not a checker, and every other number is void.
- **Answer-only control.** Ask for the answer with no reasoning at all. If
  accuracy is unchanged, the reasoning is decorative in both conditions and the
  comparison is measuring formatting.
- **Length confound.** Controlled output will differ in length. Report token
  counts; if condition B is much shorter, some accuracy difference is a
  compute-per-problem difference and must be said so.
- Confidence intervals throughout. Multiple samples per problem where budget
  allows.

## What would make this fail, stated in advance

- The model cannot hold the format, and violation rate stays high however the
  prompt is written. Then controlled reasoning is not viable at this scale, and
  say so in the first sentence.
- The constraint costs a large amount of accuracy (say more than 10 points on
  GSM8K). Then legibility is expensive here too, which matters and echoes
  `experiments/09_story_quality`.
- Free text turns out to be nearly as verifiable as controlled text. Then the
  constraint is buying nothing.

Any of those is a publishable negative and should be reported as the headline.

## Steps

1. Write the controlled grammar down, with a parser that accepts or rejects. The
   grammar is the contribution; write it before any prompting.
2. Build the checker. Test it against deliberately wrong reasoning FIRST and
   confirm it rejects. A checker that never fails is worthless.
3. Kill-switch run: 20 problems, condition B only. Measure format violation rate.
   If the model cannot stay inside the grammar, stop and report.
4. Full run: 200+ problems, both conditions, fixed sample, paired.
5. Analyse: paired accuracy difference with CI, verified-step fraction in both
   conditions, fully-verified-problem fraction, token counts.
6. Write `experiments/NN_controlled_language/FINDINGS.md`, verdict first
   sentence, limitations section naming what was not tested.

## Cost and time

API only, DeepSeek V4 Flash at roughly $0.03 / $0.075 per million tokens. 200
problems across two conditions with a few samples each is well under a dollar.
Half a day of work, most of it in the grammar and the checker rather than the
runs.

## Afterwards

If the constraint holds and buys real verifiability, the next question is whether
Raly's type system can *enforce* the grammar rather than a prompt asking for it,
which is the first time the language and the model would be doing the same job.

And the arena version: audit a model that reasons in controlled language against
one that does not, at matched capability. That chart is the whole pitch.
