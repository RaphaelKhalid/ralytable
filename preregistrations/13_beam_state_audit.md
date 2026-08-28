# Post-hoc audit — full-system beam state dependence

Status: measurement addendum written before the audit run. This does not
change the frozen benchmark, scorer, search budget, or promotion criteria.

The recurrent branch's primary capability result comes from `state-typed-beam`,
but its original causal intervention was measured only on greedy decoding.
This audit repeats the same second-transition intervention at the beam level:
erase the typed current-type bits, then set only the reserved placebo noise bit.

For each held-out task, compare the selected verified program to the baseline.
Report relevant-change rate, placebo-preservation rate, and their conjunction.
The audit is descriptive and cannot promote the branch. A zero result would
mean that the reported beam capability is not causally dependent on the
exposed typed state under this intervention.
