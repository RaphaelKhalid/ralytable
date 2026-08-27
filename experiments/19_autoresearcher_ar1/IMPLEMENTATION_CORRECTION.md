# AR1 implementation correction

The first AR1 execution used the preregistered researcher score and paired
bootstrap for visible challenger deltas, but its promotion predicate compared
the blind-family point estimate directly with the non-inferiority margin. The
protocol requires the blind-family paired-bootstrap lower 95% bound instead.

This is a decision-layer correction only. The protocol, policies, seeds,
landscapes, costs, raw trial records, and score weights are unchanged. The
corrected implementation computes a separate 10,000-resample blind delta
interval and requires its lower bound to be at least -1.0. The earlier run is
preserved for audit; it is not used for the final AR1 decision.
