# Loop 29: semantic ID normalization and collision audit

This bounded CPU probe tests canonical semantic IDs. It compares raw
serialization hashes, unchecked truncated hashes, collision-checked truncated
hashes, and full hashes. The endpoint is equivalence under metadata ordering,
decorative metadata invariance, structural sensitivity, and collision safety.

Run:

```text
python experiments/48_semantic_id_collision_audit/id_probe.py
```
