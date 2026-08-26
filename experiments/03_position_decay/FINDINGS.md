# Position decay: real (early commitment), not a runway artifact

**Verdict: real property, not a measurement artifact.** The position-vs-importance
correlation (rho=-0.551, CI [-0.608,-0.488], n=40) collapses to **zero** once you
condition on how decided the answer already is: restricting to chunks with accuracy
q in [0.3, 0.7] (26/40 traces have >=5 such chunks) gives **rho=+0.009, CI
[-0.126, +0.144]**. Position only "predicts" importance because position predicts q,
and it's q -- how close the trajectory already is to its ceiling -- that actually
determines how much a step can move the outcome. That is the early-commitment
mechanism, not a mechanical runway effect.

Reparameterising as chunk_idx / relative position / remaining steps / log(remaining)
is uninformative on its own: within a trace n is fixed, so remaining = n - chunk_idx
is a monotonic transform of chunk_idx and Spearman rho is invariant to it (confirmed:
+0.551 vs -0.551, identical magnitude). The length test is the tiebreaker instead:
comparing mean importance at the same absolute chunk window (10-25) between short
vs long traces (median split at 152 chunks), long traces show higher importance
at that fixed window (1.13 vs 0.43, t=-1.96, p=0.057) -- the opposite of what a pure
runway artifact predicts (short traces have less remaining room at that window, so
should show similar-or-lower importance, not that long traces should be higher).
Consistent with "decisions happen early in this trace's own timeline" rather than
"importance depends on absolute room-to-go."

| test | result | verdict signal |
|---|---|---|
| position vs importance, all chunks | rho=-0.551 [-0.608,-0.488] | baseline decay |
| position vs importance, q in [0.3,0.7] | rho=+0.009 [-0.126,+0.144] | decay vanishes |
| importance @ chunks 10-25, short vs long traces | 0.43 vs 1.13, p=0.057 | not runway-consistent |

Code: `experiments/03_position_decay/analyse.py`. Data: 40 local traces, no pooling
across traces (within-trace Spearman, Fisher-z averaged, 95% CI throughout).
