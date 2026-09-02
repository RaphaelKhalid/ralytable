# Findings — Experiment 34

**The recursive leakage audit accepted both clean prompts, including ordinary
“solution” prose, and rejected all three contaminated records, including nested
answer keys and a base64-encoded payload; the earlier shallow scanner was
insufficient.**

## Evidence

Two clean synthetic records were accepted. Three attacks were rejected: a
nested `answer` key, a nested base64 string encoding `solution`, and a nested
`oracle` key.

## Decision

Keep recursive forbidden-key checks and conservative encoded-value checks in
the training-data boundary. Extend future audits to other encodings and
corpus-specific provenance/fingerprint checks; this small attack set is not a
complete contamination guarantee.

## Limitations

- The encoded attack set is small and only covers simple base64.
- Real provenance and benchmark contamination require corpus-specific checks.
- No model, coding benchmark, or Qwen comparison is run.
