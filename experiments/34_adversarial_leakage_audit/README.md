# Experiment 34 — adversarial leakage audit

Dependency-free follow-up to Experiment 33. It recursively scans structured
training records for forbidden answer/test keys and detects simple base64
encoding, while allowing ordinary prompt text to mention words such as
“solution.”

Run `python leakage_audit.py`.
