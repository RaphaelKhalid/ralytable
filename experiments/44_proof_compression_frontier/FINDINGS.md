# Loop 25 findings

Status: executed after tightening the rule-label audit.

Reusable proof subgraphs reduced certificate cost by 13.33% for two branches,
33.33% for eight depth-4 branches, 36.67% for sixteen depth-4 branches, and
38.71% for eight depth-8 branches. Under a 64-token budget, the shared DAG
covered six of eight depth-4 obligations versus four for flat paths; at
sixteen branches it covered six versus four. The hash-only lower bound was
cheaper but is rejected as non-interpretable. The tightened audit accepted the
valid 36-node graph and rejected a forged shared rule.

Decision: keep reusable proof DAGs and expose their local premises and rules;
sharing is a useful way to spend a small model's output budget without
removing auditability. This calculation is not coder-model evidence.
