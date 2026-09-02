# Loop 35: calibration drift and distribution shift

This bounded CPU probe learns a confidence threshold on a source batch and
applies it to a shifted batch. It compares confidence-only selection with a
proof-plus-verifier gate that is explicitly treated as a separate signal.

Run:

```text
python experiments/54_calibration_shift_probe/calibration_probe.py
```
