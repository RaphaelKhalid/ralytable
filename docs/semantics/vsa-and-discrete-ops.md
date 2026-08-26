# VSA and Differentiable-Discrete Operations: Semantics Groundwork

Status: research note for language design. Confidence markers used throughout: **[solid]** textbook/derivable, **[empirical]** reported in literature, ranges vary, **[uncertain]** contested or extrapolated.

## 1. Operation inventory

| Family | Element type | Bind ⊗ | Bundle ⊕ | Permute ρ | Unbind |
|---|---|---|---|---|---|
| **MAP** | bipolar `{-1,+1}^D` (or real, pre-threshold) | Hadamard product | elementwise sum, then `sign` (or clip/keep-real) | cyclic shift / fixed permutation matrix | rebind with same key (self-inverse) |
| **BSC** | binary `{0,1}^D` | XOR | elementwise majority (ties broken randomly) | cyclic shift | XOR with same key (self-inverse) |
| **HRR** | real `R^D`, entries ~ N(0, 1/D) | circular convolution `⊛` | elementwise sum (+ optional renormalize) | cyclic shift | involution `x†[i] = x[(-i) mod D]`, **approximate**; exact deconvolution exists but is ill-conditioned |
| **FHRR** | complex phasors, `|z_j| = 1`, phase in `(-π,π]^D` | elementwise complex product (= phase addition mod 2π) | complex sum, then **renormalize phases** to unit magnitude | cyclic shift | complex conjugate, **exact** (pre-renormalization) |

Notes that matter more than the table: **all four binds above are commutative**. Ordered/nested structure therefore *cannot* come from bind alone — it must come from `ρ` or from a deliberately non-commutative binding (matrix binding, Vector-Derived Transformation Binding). This is a hard structural fact, not an implementation detail **[solid]**.

## 2. Algebraic law matrix

`+` = raw superposition (no normalization); `⊕` = the *normalized* bundle a user actually writes (sign / majority / phase-renorm). The distinction is where most silent breakage lives.

| Law | MAP | BSC | HRR | FHRR |
|---|---|---|---|---|
| bind assoc. `(a⊗b)⊗c = a⊗(b⊗c)` | ✅ exact | ✅ exact | ✅ exact | ✅ exact |
| bind comm. | ✅ | ✅ | ✅ | ✅ |
| bind identity | all-ones | all-zeros | delta `(1,0,…,0)` | all-zero-phase |
| bind self-inverse `a⊗a = 1` | ✅ | ✅ | ❌ | ❌ (inverse = conjugate) |
| exact inverse exists | ✅ | ✅ | ⚠️ yes generically, numerically unstable | ✅ |
| unbind exactness | exact *if* operand unbundled | exact *if* unbundled | **approximate** (involution) | exact |
| bind distributes over `+` | ✅ exact | ✅ exact (XOR-with-const commutes with per-coord majority) | ✅ exact (convolution is bilinear) | ✅ exact |
| bind distributes over `⊕` (normalized) | ⚠️ holds because `sign` commutes with ±1 multiply | ✅ | ⚠️ renormalization scale drifts | ⚠️ phase-renorm is not linear |
| raw `+` assoc/comm | ✅ | — | ✅ | ✅ |
| **normalized `⊕` associative** | ❌ `sign(sign(a+b)+c) ≠ sign(a+b+c)` | ❌ majority is **not** associative | ⚠️ only up to scale | ❌ phase renorm loses magnitude = loses count |
| `⊕` identity | none (zero vector isn't in the type) | none | zero vector | none |
| `⊕` idempotent | ❌ (`a⊕a = a` only under sign; counts are lost) | ⚠️ | ❌ | ❌ |
| `ρ` distributes over ⊗ and ⊕ | ✅ | ✅ | ✅ | ✅ |
| `ρ` exactly invertible | ✅ | ✅ | ✅ | ✅ |
| bind preserves similarity | ❌ by design (randomizing) | ❌ | ❌ | ❌ |
| `⊕` preserves similarity | ✅ (result similar to all operands) | ✅ | ✅ | ✅ |

**The most important negatives.** (a) Normalized bundling is *not associative* in any family — `bundle(bundle(a,b),c)` is a different vector than `bundle(a,b,c)`, and in BSC it is measurably worse because early majority destroys count information **[solid]**. A language must not let `⊕` be treated as a binary associative operator by default; n-ary bundling is the primitive. (b) HRR's standard unbind is approximate; the exact one (division in the Fourier domain) blows up whenever a frequency magnitude is near zero, which is common for Gaussian codes **[solid]**. (c) There is no bundle identity in the discretized types, so `⊕` is a semigroup at best, never a monoid — folds over possibly-empty collections are ill-typed.

## 3. Capacity

Model: bundle `M` items drawn from a codebook of `N` quasi-orthogonal atoms in dimension `D`. Cosine of a stored item to the bundle ≈ `1/√M`; crosstalk from each non-member is zero-mean with sd ≈ `1/√D`. So retrieval SNR ≈ `√(D/M)`, and correct nearest-neighbour cleanup against `N` candidates needs the signal to beat the max of `N` Gaussian nuisances, i.e. roughly

  `D ≳ c · M · ln N`, equivalently `M* = Θ(D / ln N)`.

Capacity is **linear in D and only logarithmic in vocabulary size** **[solid derivation; matches Frady–Kleyko–Sommer, arXiv:1707.01429, who put the information capacity of superposition at up to ≈0.5 bits per dimension]**.

Concrete, order-of-magnitude, ~99% top-1 retrieval, flat (non-nested) bundles **[empirical, ranges differ across sources — treat as ±2×]**:

| D | N ≈ 100 | N ≈ 10⁴ |
|---|---|---|
| 1,000 | ~10–15 items | ~7–10 |
| 10,000 | ~100–150 | ~70–100 |
| 100,000 | ~1,000+ | ~700+ |

Family differences are real but second-order: FHRR and sparse-binary variants sit at the top of published comparisons, BSC/MAP somewhat below, HRR lowest because the approximate inverse injects extra noise **[empirical — Schlegel, Neubert & Protzel, *A comparison of vector symbolic architectures*, arXiv:2001.11797]**.

**Nesting is where it collapses.** Noise is not additive across levels, it is roughly multiplicative in SNR: each unbind of a composite carries forward the residual of everything bundled at that level. Without a cleanup memory between levels, usable depth at D=1,000 is about **2, maybe 3** **[empirical/uncertain]**. With cleanup (project to nearest codebook atom) after every unbind, depth is bounded instead by the per-level capacity above. **Cleanup is therefore not an optimization; it is part of the semantics of nested access.** A language that lets users write `unbind(unbind(s, k1), k2)` without a cleanup in between is offering a footgun.

## 4. Learning VSA representations

Honest summary: **largely unsolved**. What is known:

- Codebooks are almost always *fixed random* by construction. The capacity results above are conditional on quasi-orthogonality of the atoms. Gradient descent on a codebook has no pressure to preserve quasi-orthogonality and typically increases mutual coherence, which silently shrinks `M*`. **This is the central open problem** and I have seen no published method that gives a training-time guarantee here **[uncertain — absence of evidence]**.
- HRR in end-to-end training is numerically unstable; Ganesan et al., *Learning with Holographic Reduced Representations* (NeurIPS 2021, arXiv:2109.02157) diagnose this and fix it with a projection step that conditions the Fourier spectrum, which is the clearest positive result in the area. *Generalized HRR* (arXiv:2405.09689) extends this.
- Neuro-vector-symbolic hybrids (Hersche et al., Raven's-progressive-matrices work) train a neural front end into a *fixed* VSA back end — the VSA part is not learned.
- Carzaniga et al., *Practical Lessons on Vector-Symbolic Architectures in Deep Learning-Inspired Environments* (PMLR v284, 2025) explicitly state there are no clear guidelines for deploying VSAs in gradient-trained settings.

Gradient behaviour of the ops themselves is fine — bind, raw bundle and permute are all differentiable (convolution and Hadamard are bilinear). The breakage is at the *normalizations* (`sign`, majority, phase-renorm), at *cleanup* (argmax over codebook), and in the loss of the statistical assumptions capacity rests on.

## 5. Differentiable discrete operations

| Technique | Forward | Gradient path | Bias | Pathologies | Standard mitigations |
|---|---|---|---|---|---|
| **Differentiable logic gates** (Petersen et al. 2022/2024) | softmax mixture over the 16 two-input gates; real relaxations (`AND→xy`, `OR→x+y−xy`) | true gradient of the relaxation | relaxation gap: the trained soft net ≠ the discretized net | dead gates (never receive gradient); accuracy drop at hardening; scaling wall past CIFAR-scale | temperature tuning (low forward / high backward), residual connections, large over-parameterization, gradient-friendly initialization |
| **VQ / VQ-VAE** | nearest-codebook lookup | straight-through: copy decoder grad to encoder | biased — the encoder gradient is evaluated at the wrong point (`z_q` not `z_e`) | **codebook collapse / dead codes** (often <10% utilization), index collapse, sensitivity to init | commitment loss, EMA codebook updates, k-means init, dead-code restart, low-dim + L2-normalized codes (ViT-VQGAN), or drop the codebook entirely (FSQ) |
| **Gumbel-softmax / Concrete** | sample soft one-hot at temperature τ | exact reparameterized gradient of the *relaxation* | biased for τ>0; bias→0 as τ→0 but variance→∞ | high-variance gradients at low τ; τ-annealing schedules are finicky; train/test mismatch if soft at train, hard at eval | τ annealing, ST-Gumbel (hard forward, soft backward — adds bias back), multiple samples, control variates (REBAR/RELAX) |
| **Plain STE** | hard threshold/sign | pretend identity (or hardtanh) inside `[-1,1]` | biased, no consistency guarantee | gradient/forward mismatch grows with depth | clipped STE, decoupled STE (arXiv:2410.13331), scale matching |

None of these is unbiased. A language that composes them must not pretend a "differentiable discrete" value is just a value — the estimator is part of its meaning.

## 6. Composition: VSA × differentiable gates

Composable in principle; the interfaces are the problem.

1. **Continuous encoder → discrete symbol.** This is a VQ. Inherits codebook collapse. If the VQ codebook *is* the VSA atom set, collapse doesn't just reduce quality — it destroys quasi-orthogonality and therefore invalidates every capacity bound in §3, silently.
2. **Symbol → VSA atom.** Fine if the codebook is fixed and random; see §4 if it is learned.
3. **VSA state → logic gates.** MAP/BSC states are naturally ±1/{0,1}, so DLGN inputs line up. But logic gates operate *per coordinate*, and VSA semantics is *distributed across all coordinates*. A per-coordinate gate has no access to the algebra; it can easily compute something that is coordinatewise sensible and symbolically meaningless.
4. **VSA state → continuous decoder.** Requires cleanup (argmax) to be meaningful, which is non-differentiable, which pushes you back to STE/Gumbel.
5. **Normalization mismatch.** Networks want normalized activations; bundling *encodes multiplicity in the magnitude/count*. Normalizing after every bundle throws that away. This is a genuine impedance mismatch with no clean fix.
6. **Batching/shape mismatch.** VSA composition is over *structures* of varying arity; tensor pipelines want fixed shapes.

## 7. The killer question: what the type system must enforce

Distinctions that must be type- or effect-level, with a silently-broken example for each.

1. **Family + dimension as part of the type.** `MAP<1024>` and `FHRR<1024>` are both length-1024 arrays. `bundle(map_v, fhrr_v)` type-checks in any tensor language and produces garbage. *Broken program:* mixing a MAP-encoded key with an HRR-encoded value store.
2. **Codebook provenance / orthogonality regime.** Two `MAP<1024>` vectors from *different* random codebooks are not comparable; similarity against the wrong cleanup memory returns a confident wrong answer. Type should carry the codebook identity, and mark learned codebooks as `coherence: unknown`.
3. **Bundle count as an affine/graded effect.** Track `M` in the type: `Bundle<MAP<D>, M>`. Reject or warn when `M > M*(D, N)`. *Broken program:* a loop that bundles one item per timestep for 50 steps at D=1000; nothing errors, accuracy just quietly degrades to chance around step ~15.
4. **Bind is commutative — so unbind keys are a multiset, and order carries no information.** *Broken program:* `s = bind(bind(subj, verb), obj)` intending a triple, then unbinding by `verb` and expecting `bind(subj,obj)` to be distinguishable from a different role assignment. It isn't. Roles must be permutation-tagged or use non-commutative binding, and the type should force the choice.
5. **Exactness qualifier on inverse.** `Exact` (MAP/BSC/FHRR) vs `Approx` (HRR involution) vs `Unstable` (HRR true deconvolution). *Broken program:* a hash-table-like structure that assumes `unbind(bind(a,b),b) == a` and does an equality test. In HRR this is never exact; the test always fails or, worse, is written as a threshold that passes for a while.
6. **Cleanliness state.** `Noisy` vs `Cleaned`. A value that has been unbound is `Noisy` until projected onto a codebook. Unbinding a `Noisy` value again should require an explicit cleanup or an explicit `unsafe_deep_unbind`. *Broken program:* three-level nested access with no cleanup at D=1024.
7. **Normalization state.** `Raw` (counts preserved, algebra exact) vs `Normalized` (counts destroyed, distributivity approximate). Silently mixing them breaks the distributive laws you were relying on.
8. **Bundle arity.** `⊕` must be n-ary, not a binary associative fold — the fold is a *different function* (§2). If a fold is offered, it must be a distinct, named, non-associative operator.
9. **Estimator/bias tags on discrete ops.** A value produced through STE or Gumbel should be marked; gradients through it are biased, and composing many such stages compounds bias in a way the user should be forced to see.
10. **Empty structures.** No bundle identity exists, so `bundle([])` must be a type error, not a zero vector.

## 8. What is genuinely uncertain

- **Exact capacity constants.** The `Θ(D/ln N)` scaling is solid; the constants and hence the table in §3 vary across papers depending on accuracy threshold, codebook statistics and cleanup method. Treat the numbers as ±2× and re-derive empirically for any specific configuration.
- **Nested-structure capacity.** I could not find a clean, agreed-upon closed form for capacity under depth-`d` nesting with cleanup. The "depth 2–3 without cleanup at D=1000" figure is a synthesis, not a citation.
- **Whether learned codebooks can retain VSA guarantees.** Open. Possibly addressable by an orthogonality regularizer or by keeping the codebook frozen and learning only the encoder — but I know of no result that *proves* capacity is preserved under training.
- **Family ranking.** FHRR generally leads in comparison studies, but rankings are task- and threshold-dependent; I would not hard-code a "best family" into the language.
- **Whether per-coordinate differentiable logic gates are compatible with distributed VSA semantics at all**, or whether the composition in §6.3 is fundamentally ill-posed. This is the biggest conceptual gap and deserves an experiment before the language commits to it.

### Sources

- [A Survey on HDC/VSA, Part I](https://arxiv.org/abs/2111.06077) · [Part II](https://arxiv.org/abs/2112.15424)
- [A comparison of vector symbolic architectures](https://arxiv.org/pdf/2001.11797)
- [Capacity Analysis of Vector Symbolic Architectures](https://arxiv.org/abs/2301.10352)
- [Theory of the superposition principle for randomized connectionist representations](https://arxiv.org/abs/1707.01429)
- [Learning with Holographic Reduced Representations](https://arxiv.org/pdf/2109.02157) · [Generalized HRR](https://arxiv.org/pdf/2405.09689)
- [Practical Lessons on VSAs in Deep Learning-Inspired Environments](https://proceedings.mlr.press/v284/carzaniga25a.html)
- [Deep Differentiable Logic Gate Networks](https://arxiv.org/abs/2210.08277) · [Convolutional DLGNs](https://proceedings.neurips.cc/paper_files/paper/2024/file/db988b089d8d97d0f159c15ed0be6a71-Paper-Conference.pdf) · [Scalability boundaries of DLGNs](https://arxiv.org/pdf/2509.25933)
- [Decoupled Straight-Through Estimator](https://arxiv.org/pdf/2410.13331)
