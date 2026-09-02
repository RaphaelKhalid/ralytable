# Loop 31: deterministic parallel scheduler

This bounded CPU probe schedules independent ledger branches with explicit
ordering constraints. It compares input-order FIFO, randomized ready-queue
selection, and semantic-key topological scheduling.

Run:

```text
python experiments/50_deterministic_parallel_scheduler/scheduler_probe.py
```
