# Experiment 22 — typed program ledger architecture probe

This is a CPU-only, dependency-free architecture study. It does **not** train
an LLM and does not report HumanEval+, pass@1, or Qwen comparisons.

## Question

Under a fixed small intermediate-state budget, which representation preserves
the information needed for inspectable code generation: a flat sketch,
entity slots, a typed program graph, or a content-addressed typed ledger?

The proposed architecture is the last one. A learned front end would route
surface text into typed ledger entries; a deterministic verifier and module
executor would own execution. This probe isolates the representation question
before spending time on a learned parser.

## Method

The generator creates held-out synthetic dataflow programs with shuffled
surface facts, linear chains, and branch/merge graphs. Each architecture gets
the same task and must reconstruct the exact typed program. We measure:

- exact graph recovery;
- recovery by graph depth and branch shape;
- relevant counterfactual change rate;
- irrelevant-distractor preservation;
- invariance to surface-fact permutation;
- abstract learned-parameter budget and audit surface.

The representation is given the ground-truth facts. Therefore this is an
architectural capacity and causal-legibility test, not evidence that a neural
parser can infer the facts from natural language. A positive result earns a
follow-up parser experiment; it does not earn a capability claim.

Run:

```text
python experiments/22_interpretable_40m_architecture/architecture_probe.py
```

The script uses only the Python standard library and writes its result beside
the script. `FINDINGS.md` is the verdict-first record.
