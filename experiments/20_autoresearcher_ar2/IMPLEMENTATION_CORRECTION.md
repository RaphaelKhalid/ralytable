# AR2 implementation correction

The first AR2 execution (`ar2-20260827T232315Z-c58342`) exposed a receipt
validation bug. Each trial correctly started an independent hash chain, but
the completion check incorrectly passed the concatenated multi-trial receipt
file to the single-chain validator. That made `receipt_chain_valid=false` and
correctly forced `G=0`; the run is retained as invalid evidence and is not
used for promotion.

The corrected implementation validates each trial stream independently using
the frozen policy, ablation, researcher seed, family, and instance identifiers
already present in every receipt. The score, landscapes, seeds, budgets,
trigger thresholds, and promotion rule are unchanged. A regression test
covers both valid multi-stream validation and tamper rejection. The corrected
AR2 run `ar2-20260827T234349Z-4c250f` completed as a fresh immutable artifact
run under the same preregistered protocol, with `G=1` and no promotion.
