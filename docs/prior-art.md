# Prior Art Review: VSA/Logic DSLs, Legible Language Models, Discrete Bottlenecks

Scope: literature/prior-art check for (a) a DSL whose primitives are VSA ops and differentiable
discrete logic rather than tensor contractions, and (b) an interpretable-by-construction LM with a
small discrete alphabet. Search conducted 2026-08. Claims sourced from search are cited; claims
resting on model priors rather than retrieved sources are marked [PRIOR].

---

## 1. Has anyone built a language/DSL for non-tensor ML primitives?

**Partially — for VSA there is a real DSL; for differentiable logic there is not.**

**Exists and works, as libraries:**
- **Torchhd** (Heddes et al., JMLR 24, 2023; arXiv:2205.09208; github.com/hyperdimensional-computing/torchhd).
  The de-facto VSA library. Bind/bundle/permute across MAP, BSC, HRR, FHRR, VTB as PyTorch tensor
  subclasses. It is a *library*: no own syntax, no type system, no VSA-aware static checking. Nothing
  stops you binding two vectors from incompatible symbol spaces.
- **OpenHD** (Kang et al., IEEE Trans. Computers 2022) and **HDTorch** — GPU-accelerated HDC frameworks,
  classification/clustering-focused. Libraries, not languages.

**Exists and works, as an actual language/compiler:**
- **HDCC** (Vergés et al., arXiv:2304.12398, 2023) — described in its own abstract as the first and only
  HDC compiler. Has an input language, an IR, and a C backend for embedded targets. But its semantics
  are narrow: HDC *classification* pipelines only. Not a general modelling language, no autodiff, no
  learning beyond centroid/retraining classifiers.
- **HDC++ / HPVM-HDC** (Ejjeh et al., ISCA 2025; arXiv:2410.15179) — the strongest hit for question 1.
  A domain-specific language embedded in C++ exposing HDC operations as first-class primitives, with a
  retargetable compiler (CPU/GPU/custom HDC accelerators) and approximation-tuning passes
  (arXiv:2606.26547). This is a genuine DSL with its own compilation semantics. What it does *not* do:
  it is a systems/performance artifact aimed at accelerators. No differentiable-logic primitives, no
  gradient-based training of the symbolic structure, no interpretability tooling, no notion of a
  legible model as an output artifact.

**Differentiable logic:** `difflogic` (Petersen, github.com/Felix-Petersen/difflogic) is a PyTorch
extension — `LogicLayer`, `GroupSum`, CUDA kernels. A library. There is **no DSL for differentiable
logic-gate networks** that I could find.

**Neurosymbolic DSLs (adjacent, do not cover this ground):**
- **Scallop** (Li et al., PLDI 2023; arXiv:2304.04812) — a real language: probabilistic Datalog with
  configurable provenance semirings, differentiable through the semiring. Beats DeepProbLog by orders
  of magnitude (MNIST-4-digit-sum: minutes vs an estimated 40 days).
- **DeepProbLog** (Manhaeve et al., NeurIPS 2018) — probabilistic logic programming with neural
  predicates; exact inference over possible worlds, does not scale.
- **PyReason** (Aditya et al., 2023) — annotated-logic temporal graph reasoner, a Python library.

**The gap:** Scallop/DeepProbLog/PyReason all assume a **relational/logical layer sitting on top of an
opaque neural perception layer**. The neural part stays a black box; the DSL only describes the symbolic
glue. Nobody has built a language where the *learned model itself* — the thing gradients flow through —
is expressed in VSA + differentiable-gate primitives with typed symbol spaces. HDC++ is closest, but it
is compilation-for-speed, not modelling-for-legibility.

## 2. Has anyone put logic-gate networks or VSA on a language task?

**Yes to both, at small scale. The results are weak but not zero. This is the most important section.**

**Logic gates on sequences — this exists, and it is very close to our idea:**
- **Recurrent Deep Differentiable Logic Gate Networks (RDDLGN)**, ETH Zürich, arXiv:2508.06097,
  EdgeFM workshop @ MobiCom 2025 (OpenReview `knHHCx1prj`). Explicitly states that DLGNs for sequential
  modelling were previously unexplored. Embeds flip-flop/latch-like sequential logic in a differentiable
  framework for seq2seq. **On WMT'14 English-German: 5.00 BLEU and 30.9% accuracy during training,
  degrading to 4.39 BLEU at inference; GRU baseline 5.41 BLEU.**
  *How it fails:* (i) the numbers sit near the floor — 5 BLEU is not a working translation system, so
  "approaching GRU" means approaching a badly-trained GRU; (ii) the **discretization gap** — the
  continuous relaxation used in training does not survive hardening into real gates, which is exactly
  the 5.00 to 4.39 drop. The discretization gap is a recognised open problem for DLGNs generally (see
  "Improving Discrete Optimisation Via Decoupled Straight-Through Estimator", arXiv:2410.13331, and
  depth-scalability work arXiv:2607.21633). **We must read this paper before writing any code.**

**Interpretability of logic-gate nets is oversold.** Convolutional DLGNs (Petersen et al., NeurIPS 2024)
reach 86.29% on CIFAR-10 using **61 million logic gates**. A 61M-gate circuit is not readable by a human.
The interpretability claim in the DLGN literature is asserted structurally and essentially never
demonstrated at scale. Small-scale exceptions exist for tabular data (Differentiable Logic Networks,
arXiv:2505.23615), where rules genuinely are extracted and inspected.

**VSA on language:**
- **Hrrformer** (Alam et al., ICML 2023; arXiv:2305.19534) — recasts self-attention as HRR bind/unbind.
  O(TH log H) time, 280x faster training, near-SOTA on Long Range Arena, first viable transformer for
  long malware sequences. This *works*, but it is an efficiency result: the model is no more legible.
- **Generalized HRR (GHRR)** (arXiv:2405.09689) — replaces transformer attention with GHRR binding and
  runs **language modelling on WikiText-2 and Penn Treebank**, reporting ~5.5% and ~2.8% perplexity
  improvement over a parameter-matched vanilla transformer. Small models, five seeds. The
  interpretability claim is mathematical (binding is equivalent to scaled dot-product attention, each
  hypervector component acting as an attention head), not empirical.
- **Hyperdimensional Probe** (arXiv:2509.25045, 2025) — uses VSA to *decode* an existing LLM's residual
  stream into interpretable concepts. An analysis tool, not an architecture.
- Classic HDC on text is confined to language ID, n-gram classification, and small-scale text
  classification (Kleyko/Rachkovskij/Osipov/Rahimi surveys, arXiv:2111.06077, arXiv:2112.15424).

**Could not find:** any VSA-native *generative* language model above roughly 10M parameters; any
differentiable-logic model trained on next-token prediction over a modern corpus; any published
negative result explicitly killing either idea. The space is thin, not closed.

## 3. Has anyone measured a legibility vs capability tradeoff curve?

**One paper does. Everyone else reports single points.**

- **Weight-sparse transformers have interpretable circuits** (Gao et al., OpenAI, arXiv:2511.13653,
  Nov 2025). The exception. They explicitly report a **capability-interpretability Pareto frontier**:
  scaling total parameter count *improves* the frontier; increasing sparsity at fixed parameter count
  moves *along* it, harming capability and improving interpretability. Legibility is operationalised as
  circuit node/edge count (a quote-matching circuit: 12 nodes, 9 edges). They flag that scaling beyond
  tens of millions of nonzero parameters while preserving interpretability is unsolved. A LessWrong
  critique ("Weight-Sparse Circuits May Be Interpretable Yet Unfaithful") questions faithfulness of the
  extracted circuits.
- **The Price of Interpretability** (Bertsimas et al., arXiv:1907.03419) — formalises the tradeoff, but
  for classical interpretable models, not deep nets, and not for language.
- **Concept Bottleneck LLMs** (Sun et al., ICLR 2025; arXiv:2412.07992) — roughly a 5% accuracy gap
  versus black-box, which an accuracy-correction module then largely closes. **A single point, not a
  curve**, and only on classification.
- **KANs** (Liu et al., ICLR 2025) — interpretability claimed, tradeoffs reported anecdotally per task;
  no legibility axis is defined, so no curve. Time-series work (arXiv:2411.14904) reports KANs as a
  balanced tradeoff point against HIVE-COTE 2.0 and MLPs, again pointwise.

**Verdict: outside the OpenAI sparse-circuits paper, nobody publishes the cost of interpretability as a
curve.** And nobody at all does so with a legibility metric defined *independently of the architecture*,
which is what would let a sparse transformer, a logic-gate net and a VSA model be plotted on the same
axes. That comparability is genuinely unoccupied.

## 4. State of discrete bottlenecks in language models

- VQ-VAE (van den Oord et al., 2017) is the ancestor; codebook size directly bounds latent entropy,
  making it a deterministic information bottleneck.
- **CLVQ-VAE / Cross-Layer Discrete Concept Discovery** (arXiv:2506.20040, 2025) — a VQ bottleneck
  between LM layers, mapping a lower layer to a higher one and collapsing duplicated residual-stream
  features into compact concept vectors. Codes are claimed to capture interpretable syntactic and
  semantic categories, and are argued to be cleaner than SAE features because a *single* code is
  selected rather than a linear combination of active neurons. This is the best "the codebook was
  actually inspected" hit.
- Codebook sizes in this literature are typically in the 512-65536 range [PRIOR: specific numbers were
  not confirmed in search; verify before citing]. Either way this is a *large* discrete alphabet, orders
  of magnitude from the small readable alphabet we want.
- **Could not find** any language model trained from scratch with a small (say under 256 symbols)
  discrete bottleneck alphabet where that alphabet is the reasoning substrate rather than a post-hoc
  analysis layer. Every discrete-code interpretability result I found analyses an existing dense model.

## 5. Tropical geometry — brief

**The claim is correct.** Zhang, Naitzat & Lim, *Tropical Geometry of Deep Neural Networks* (ICML 2018,
arXiv:1805.07091) prove an exact equivalence: a feedforward ReLU network with integer weights is a
tropical rational function (a tropical quotient of tropical polynomials). Linear regions correspond to
vertices of the associated Newton polytope; one-hidden-layer networks are characterised by zonotopes;
decision boundaries are tropical hypersurfaces.

Because the equivalence is *exact for networks you already have*, tropical algebra is an **analysis lens,
not a construction principle** — it re-describes ReLU nets, it does not hand you a different architecture.
Follow-on work is expressivity counting (Tropical Expressivity of Neural Networks, arXiv:2405.20174; MoE
expressivity, arXiv:2602.03204; transformer expressivity, arXiv:2604.14727) and robustness (tropical
decision boundaries, arXiv:2402.00576). One paper uses it for interpretability narrowly: *Interpretation
of Artificial Neural Network Overtraining Using Tropical Geometry* (Comp. Math. & Modeling, 2023). There
is a small line on tropical *activations* (arXiv:2502.01247), but that is architecture tweaking, not a
tropical-native model. **Nobody is doing serious mechanistic interpretability with it.**

---

## The gap, if any

Genuinely unoccupied:

1. **A typed modelling language whose primitives are VSA operations plus differentiable gates, where the
   object under gradient descent is itself the symbolic program.** HDC++/HPVM-HDC owns the
   compiler-for-speed niche; Scallop owns the logic-over-a-black-box niche. The intersection is empty.
2. **A legibility metric portable across architecture families, and a tradeoff *curve* measured with it.**
   OpenAI has a curve, but only inside the weight-sparse family, with circuit node-count as the axis.
3. **A small-alphabet (under 256 symbols) discrete reasoning core in a generative LM, built that way from
   scratch.** All existing discrete-code interpretability work is post-hoc on dense models.

Already occupied — do not reinvent:

- VSA primitives and their efficient kernels (Torchhd, HDC++/HPVM-HDC, HDCC).
- VSA-as-attention, including the language-modelling experiment (Hrrformer, GHRR).
- Sequential differentiable logic gates on a translation task (RDDLGN).
- The capability/interpretability Pareto framing itself (arXiv:2511.13653).

Honest risk: the two empirical precedents that matter — RDDLGN at 5 BLEU, and 61M-gate CIFAR circuits —
together suggest the discrete-substrate route is capability-poor *and* stops being readable once scaled
enough to be capable. That is the central risk to design against, and it is why the *curve* is the
defensible contribution even if the architecture underperforms.
