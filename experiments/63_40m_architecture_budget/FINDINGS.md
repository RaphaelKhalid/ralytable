# Loop 44 findings

Status: executed.

All three role-constrained configurations fit below 40M learned parameters
with zero opaque residual bypass: lean parser 23,700,480, verifier-heavy
27,922,240, and balanced ledger 38,265,728. The balanced design leaves
1,734,272 parameters of headroom; the other two leave 16,299,520 and
12,077,760. Every counted parameter belongs to byte parsing, typed routing,
module/retrieval interfaces, verifier heads, or explicit copy identity.

Decision: the architectural budget is arithmetically feasible without an
opaque residual. This is only a budget gate; capability, calibration, and
coding-distribution parity remain unmeasured.
