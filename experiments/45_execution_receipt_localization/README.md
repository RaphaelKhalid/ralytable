# Loop 26: execution receipt localization

This bounded CPU probe compares final-only receipts, hash-chain receipts, and
stepwise replay receipts. The endpoint is first-divergence localization under
an altered output digest, a changed operation argument, and a dropped receipt.

Run:

```text
python experiments/45_execution_receipt_localization/receipt_probe.py
```
