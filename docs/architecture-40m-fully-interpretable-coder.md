# A falsifiable route to an interpretable 40M coder

This is a design hypothesis, not a claim that a 40M model can match a 27B
model on unrestricted coding.

## Reframe the target

Parameter parity is the wrong comparison. A small system can only plausibly
rival a much larger coder on a declared task distribution if it gets leverage
from computation that is not stored in dense learned weights:

\[
  \text{success} = f(\text{parser},\ \text{retrieval},\ \text{typed search},
  \text{deterministic modules},\ \text{verification},\ \text{execution budget}).
\]

The public claim should therefore be: *under distribution D, with retrieval
corpus M, module library L, verifier V, and search budget B, the 40M system
matches or exceeds the larger baseline on metric Q*. It should not be “40M has
the knowledge or generality of 27B.”

## Proposed architecture: typed program ledger coder

1. A byte-level or small code vocabulary encoder reads the prompt and emits
   distributions over atomic facts: identifiers, types, literals, constraints,
   control-flow predicates, and candidate operations.
2. A binder writes those facts into a content-addressed ledger. Each entry is a
   typed node with provenance and explicit input edges. Node identity is stable
   under surface-fact permutation.
3. A legality kernel rejects ill-typed graphs before code emission. The kernel
   is deterministic and has no learned bypass.
4. A router chooses among a fixed library of auditable modules: collection
   transforms, arithmetic, string operations, recursion schemes, API-call
   templates, and repair edits. Modules execute against the ledger and append
   new nodes with receipts.
5. A code renderer lowers the verified graph to Python. Search proposes several
   legal graphs; execution tests and the verifier select among them.

The learned part is a proposal distribution over typed objects, not a free
latent channel from prompt to arbitrary source. The output program must be a
deterministic function of the accepted ledger, module arguments, and disclosed
search trace.

## Mathematical invariants

Let a ledger be \(G=(V,E,\tau,\pi)\), where \(V\) are nodes, \(E\) are dataflow
edges, \(\tau\) are types, and \(\pi\) is provenance. A candidate is accepted
only if:

\[
  \mathrm{welltyped}(G) \land \mathrm{acyclic}(G) \land
  \mathrm{module\_legal}(G) \land \mathrm{replay}(G)=\mathrm{true}.
\]

Rendering is deterministic:

\[
  y = R(G, L, a),
\]

where \(a\) is the recorded search/action trace. This makes the causal test
well-defined. For a relevant intervention \(I_r\) on node or edge \(u\),

\[
  \Pr[R(I_r(G))\ne R(G)]
\]

should be high for programs that depend on \(u\). For an irrelevant placebo
\(I_0\),

\[
  \Pr[R(I_0(G))=R(G)]
\]

should be high. The test must be within task, not just across aggregate
outputs.

The ledger has an important advantage over a flat state: the binding relation
is explicit. But this does not make the parser interpretable. A parser that
quietly encodes the answer in an unused field would still pass superficial
type checks. The no-bypass test must erase every raw-prompt path and verify
that only named nodes can affect rendering.

## 40M allocation principle

Use the learned budget for proposal diversity, not for reimplementing a large
opaque language model:

- byte/code embeddings and a small low-rank encoder;
- slot/binding queries;
- typed-state and module routers;
- schema and legality heads;
- no large opaque residual from prompt to renderer.

The deterministic module library, retrieval index, verifier, compiler, and
search procedure are not counted as learned parameters, but they must be
reported as part of the system. Otherwise the comparison is misleading. The
budget frontier in `experiments/23_40m_budget_frontier/` is deliberately a
ledger of assumptions, not evidence of performance.

## What could make this rival a larger coder

The strongest plausible route is specialization plus test-time computation:

- retrieval supplies long-tail APIs and repository-local conventions;
- typed graphs prevent binding and argument-order errors;
- fixed modules solve common transformations exactly;
- verifier-guided search spends compute only on legal alternatives;
- repair modules exploit compiler/test feedback;
- external memory stores reusable verified subgraphs.

This is closer to a compact neural semantic parser plus compiler than to a
small imitation of a large autoregressive model. It may rival a large coder on
repository repair, API-constrained synthesis, or a known language subset while
losing badly on open-ended explanation and novel library discovery.

## Kill sheet

Stop or downgrade the design if any of these occur:

- a raw-prompt ablation leaves performance unchanged;
- relevant ledger interventions rarely change dependent programs;
- a placebo changes programs frequently;
- graph validity is high only because answer bits or benchmark tests leak into
  the state;
- removing retrieval/modules causes collapse on the claimed task distribution;
- the system matches the larger baseline only after unreported search,
  retrieval, or verifier calls;
- a dense control at the same external compute wins on the frozen suite.

## Next experiment

Train no model yet. First build a learned-parser surrogate that maps paraphrased
synthetic requirements to ledger graphs, with held-out operation compositions,
identifier renaming, distractors, and counterfactual edits. Compare a flat
sequence decoder, slots-only decoder, and ledger decoder. Selection must use
exact graph recovery and causal gates before any code score. Only a ledger that
survives this parser test deserves a small PyTorch implementation.

Prior-art anchors include Slot Attention, neural module networks, and Perceiver
IO; this proposal's narrow difference is the typed, replayable, content-
addressed program ledger and the explicit no-bypass criterion.
