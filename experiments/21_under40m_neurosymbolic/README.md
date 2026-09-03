# Experiment 21 — under-40M neurosymbolic Python synthesis

**Status: blocked at the learned-parser gate.** Experiment 66 failed the
preregistered compositional replay and causal-intervention thresholds. The
commands below document the prepared pipeline, but training must not start
until a revised parser clears that gate.

This is the first real HumanEval+ pipeline in the repository. It trains a
roughly 30M-parameter transformer to classify an explicit typed state into a
named algorithm family, then emits Python from a constrained symbolic backend.
The state is parsed from the task prompt and contains the function name,
argument/type slots, return type, normalized keywords, feature bits, and
docstring. The backend never receives the raw prompt.

HumanEval+ is a benchmark-guided, disclosed discovery score. It is not held-out
evidence, and all optimized results must be called HumanEval+-tuned. Training
examples are private synthetic descriptions; the prompt manifest contains only
task IDs, entry points, and prompts. Solutions, tests, and expected outputs stay
inside the isolated official EvalPlus environment.

## Reproduction in WSL

```text
TRAIN=/home/rapha/ralytable-autoresearch-next/.venv/bin/python
EVAL=/home/rapha/.venvs/ralytable-evalplus-0.3.1/bin/python
ROOT=/home/rapha/ralytable-under40m
cd /mnt/c/Users/rapha/OneDrive/Desktop/Claude/mechinterp
$EVAL experiments/21_under40m_neurosymbolic/pipeline.py export-prompts --output $ROOT/humaneval-plus-prompts.json
$TRAIN experiments/21_under40m_neurosymbolic/pipeline.py parameter-count
$TRAIN experiments/21_under40m_neurosymbolic/pipeline.py train --output $ROOT/checkpoints/smoke.pt --seed 11 --examples 512 --epochs 1
$TRAIN experiments/21_under40m_neurosymbolic/pipeline.py generate --manifest $ROOT/humaneval-plus-prompts.json --checkpoint $ROOT/checkpoints/smoke.pt --output $ROOT/samples/smoke.jsonl --metadata $ROOT/metadata/smoke.json
$EVAL experiments/21_under40m_neurosymbolic/pipeline.py evaluate --samples $ROOT/samples/smoke.jsonl --parallel 1
```

The detached tournament runs candidates until its time budget or a stop file:

```text
$TRAIN experiments/21_under40m_neurosymbolic/tournament.py --train-python $TRAIN --eval-python $EVAL --root $ROOT --hours 8 --parallel 8 --stop-file $ROOT/STOP
```

If a WSL VHD becomes read-only, use a new root under `/mnt/c` and continue
without repeating already recorded candidate indices:

```text
$TRAIN experiments/21_under40m_neurosymbolic/tournament.py --train-python $TRAIN --eval-python $EVAL --root /mnt/c/Users/$USER/AppData/Local/Temp/ralytable-under40m/resume --start-index 10 --max-candidates 90 --hours 8 --parallel 8
```

The result record is append-only JSONL. Each row records configuration, seed,
parameter count, model training metrics, generation artifact paths, official
evaluator output, and failures. The causal state audit is separate from the
HumanEval+ outcome: an evaluation run must report how often erasing relevant
state changes the selected strategy and how often an irrelevant state placebo
preserves it.
