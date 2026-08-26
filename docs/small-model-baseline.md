# Small-Model Baseline: What Counts As Capable, And At What Size

Scope: how small a language model can be and still be genuinely capable, as a concrete target
for Ralytable. Search conducted 2026-08. Benchmark numbers are cited; anything unconfirmed is
marked UNVERIFIED rather than filled in.

Two warnings. **Self-reported model-card numbers are the norm** here — the Open LLM
Leaderboard v2 was archived in March 2025, so there is no independent referee for most
2025-26 small models. And **harness disagreement exceeds the effects being claimed**:
Falcon-H1's card scores Llama-3.2-1B at MMLU 32.39 while Liquid's harness scores
Llama-3.2-1B-Instruct at 46.6 — a 14-point spread on the same model.

## 1. GPT-3 175B as the yardstick

| Benchmark | GPT-3 175B | Setting | Source |
|---|---|---|---|
| **MMLU** | **43.9** | 5-shot | [MMLU paper](https://ar5iv.labs.arxiv.org/html/2009.03300) Table 1 |
| HellaSwag | 78.9 / 79.3 | 0-shot / few-shot | [GPT-3](https://ar5iv.labs.arxiv.org/html/2005.14165) Table 3.2 |
| ARC-Easy / ARC-Challenge | 70.1 / 51.5 | few-shot | GPT-3 Table 3.6 |
| WinoGrande | 70.2 / 77.7 | 0-shot / few-shot | GPT-3 Table 3.5 |
| **GSM8K** | **15.6** standard, 46.9 CoT | 8-shot | [CoT paper](https://ar5iv.labs.arxiv.org/html/2201.11903) Table 1 |
| **HumanEval pass@1** | **~0** | 0-shot | [Codex paper](https://ar5iv.labs.arxiv.org/html/2107.03374): "GPT-3 solves 0%" |

**MMLU 43.9 is the reference line.** Note how weak the rest is — GPT-3 could not code at all
and could not do grade-school arithmetic without chain-of-thought. A lower bar than the name
connotes.

## 2. The smallest model that beats GPT-3 on MMLU

All self-reported from tech reports or model cards. Base (B) vs instruct (I) marked.

| Model | Params | Released | MMLU | HellaSwag | ARC-C | GSM8K | HumanEval |
|---|---|---|---|---|---|---|---|
| MobileLLM-125M (B) | 125M | Feb 2024 | not reported | 38.9 | 27.1 | — | — |
| SmolLM2-135M (B) | 135M | Nov 2024 | 31.5 **cloze** | 42.1 | — | 1.4 | — |
| Gemma 3 270M (B) | 268M | Aug 2025 | **not reported** | 40.9 | 29.0 | — | — |
| Granite 4.0-H-350M (I) | 340M | Oct 2025 | 36.2 | — | — | 39.3 | — |
| LFM2-350M (I) | 354M | Nov 2025 | 43.4 | — | — | 30.1 | — |
| MobileLLM-R1-360M (B) | 359M | Sep 2025 | 26.8 | 42.7 | 36.0 | 39.4 | 32.9 |
| SmolLM2-360M (B) | 360M | Nov 2024 | 35.8 cloze / **24.7 MC** | 54.5 | 42.0 | 3.2 | — |
| **Qwen2.5-0.5B (B)** | **494M** | **Sep 2024** | **47.5** | 52.1 | 35.6 | 41.6 | 30.5 |
| Falcon-H1-0.5B (B) | 521M | Jul 2025 | 55.0 | — | — | 60.2 | — |
| Qwen3-0.6B (B) | 596M | Apr 2025 | 52.8 | — | — | 59.6 CoT | 36.2 |
| Llama 3.2 1B (B / I) | 1B | Sep 2024 | 32.2 / 49.3 | — / 41.2 | 32.8 / 59.4 | — / 44.4 | — |
| Qwen2.5-1.5B (B) | 1.54B | Sep 2024 | 60.9 | 67.9 | 54.7 | 68.5 | 37.2 |
| SmolLM2-1.7B (B) | 1.7B | Nov 2024 | not reported | 68.7 | 60.5 | 31.1 | 22.6 |
| Gemma 2 2B (B) | 2B | Jun 2024 | 51.3 | 73.0 | 55.4 | 23.9 | 17.7 |
| SmolLM3-3B (I) | 3B | Jul 2025 | 44.1 (MMLU-CF) | 76.2 | 65.6 | 67.6 | 30.5 (+) |
| Llama 3.2 3B (I) | 3B | Sep 2024 | 63.4 | 69.8 | 78.6 | 77.7 | — |
| Phi-3-mini (I) | 3.8B | Apr 2024 | 68.8 | 76.7 | 84.9 | 82.5 | 58.5 |
| Phi-4-mini (I) | 3.8B | Feb 2025 | 67.3 | 69.1 | 83.7 | 88.6 | 74.4 |

Sources: [Qwen2.5](https://arxiv.org/html/2412.15115v2), [Qwen3](https://arxiv.org/html/2505.09388v1),
[SmolLM2](https://arxiv.org/html/2502.02737v1), [Llama 3.2](https://raw.githubusercontent.com/meta-llama/llama-models/main/models/llama3_2/MODEL_CARD.md),
[Gemma 2](https://ai.google.dev/gemma/docs/core/model_card_2) / [Gemma 3](https://ai.google.dev/gemma/docs/core/model_card_3),
[Phi-3](https://arxiv.org/html/2404.14219v4), [Phi-4-mini](https://arxiv.org/html/2503.01743v2),
[MobileLLM](https://arxiv.org/html/2402.14905v2), [MobileLLM-R1](https://arxiv.org/html/2509.24945v1),
[LFM2](https://arxiv.org/html/2511.23404v1), [Falcon-H1](https://arxiv.org/abs/2507.22448),
[Granite 4.0](https://huggingface.co/ibm-granite/granite-4.0-h-1b).

**Answer: Qwen2.5-0.5B — 494M parameters, MMLU 47.5 (5-shot, base). A 354x parameter
reduction over GPT-3 175B for +3.6 points.** Nothing verified below ~350M clears the line;
LFM2-350M at 43.4 lands just under.

Three reasons to distrust that headline. **Contamination is measured, not hypothetical**:
[Index-1.9B](https://huggingface.co/IndexTeam/Index-1.9B) ran the clean ablation — an
identical model with instruction-related data filtered from pretraining drops MMLU **52.53 →
43.75**, ~9 points, larger than Qwen2.5-0.5B's entire margin. [GSM1k](https://arxiv.org/html/2405.00332v3)
re-tests on a held-out clone: phi-3-mini 78.2 → 68.4, phi-2 56.9 → 49.5. **Harness spread
(~14 pts) exceeds the margin (3.6 pts).** And GPT-3 is a 2020 base model with no
benchmark-shaped pretraining data, so the comparison is not like-for-like.

Defensible claim: **sub-1B models are now in GPT-3's range on MMLU**, not that a specific
494M model cleanly beats it. Qwen3.5, Gemma 4, LFM2.5 and OLMo 3 have all stopped reporting
plain MMLU — a tacit admission it is saturated.

## 3. The absolute floor: coherent is not smart

Two thresholds, ~50x apart in parameters.

**Coherent English: ~8M.** [TinyStories](https://ar5iv.labs.arxiv.org/html/2305.07759)
(Eldan & Li 2023) sweeps a hidden x layers grid from ~1M to ~35M on GPT-4-generated stories
with a ~1500-word vocabulary. GPT-4-graded, out of 10:

| Config | ~Params | Grammar | Consistency | Creativity |
|---|---|---|---|---|
| hidden 64, 8L | ~1M | 6.14 | 4.45 | 4.68 |
| hidden 128, 12L | ~3M | 7.25 | 7.20 | 6.02 |
| **hidden 256, 4L** | **~8M** | **7.64** | **7.76** | 6.32 |
| hidden 512, 8L | ~28M | 8.34 | 8.95 | 6.85 |
| hidden 768, 8L | ~33M | 8.62 | 9.34 | 7.02 |
| GPT-2-large | 774M | 6.43 | 6.04 | 4.30 |
| GPT-4 | — | 8.75 | 9.93 | 8.21 |

**An ~8M model beats GPT-2-large (774M) on all three** — ~100x fewer parameters — because the
data distribution is narrow. One V100, under 30 hours. Two structural findings matter more
than the scores: consistency **emerges at the hidden 64 to 128 jump** (4.45 → 7.10), and there
is a **depth/width dissociation** — factual knowledge tracks embedding dimension,
context-tracking tracks layer count. A 1-layer 21M model gets facts right but scores 5.81 on
instruction-following; 2 layers suffices.

**Smart: nowhere near 300M.** In the 100-300M band, MMLU sits at or below chance (25%):
SmolLM2-360M is **24.7 under standard multiple-choice** despite 35.8 cloze on its own card —
never compare the two. Gemma-3-270M, MobileLLM-125M/350M and LFM2.5-230M **do not report MMLU
at all**; the non-reporting is the finding, and Meta states outright that sub-400M models
give unreliable scores. [Random Scaling of Emergent Capabilities](https://arxiv.org/html/2502.17356)
adds that even Qwen2.5-0.5B is *bimodal across seeds* on MMLU — the scaling "jump" is a
multimodal outcome distribution, not a discontinuity in any run.

What 100-350M does well is narrow, discriminative work.
[GLiNER-0.3B](https://ar5iv.labs.arxiv.org/html/2311.08526) scores 60.9 zero-shot OOD NER F1
vs UniNER-13B's 55.6 and ChatGPT's 47.5 — GLiNER-S at **50M** already beats ChatGPT at 52.7.
DistilBART-306M matches its 406M teacher on CNN/DM ROUGE-2. And phi-1-small — **350M, 7B
curated tokens — scores 45% HumanEval**, the strongest sub-500M datapoint anywhere. What
breaks: tool use has the sharpest cliff in the literature (BFCL V2: Llama-3.2-1B 25.7 → 3B
**67.0**), and world knowledge never appears — [BabyLM 2024](https://arxiv.org/pdf/2412.05149)'s
winning 119M GPT-BERT hits BLiMP 86.1 (within 2.5pp of human) while EWoK stays near chance.

## 4. What actually makes small models good

**1. Over-training past Chinchilla — the largest lever.** Optimal is 20 tokens/param. Gemma 2
2B ran 1,000; Gemma-3-270M ~22,200; **Qwen3-0.6B ~60,000 (36T tokens), 3,000x Chinchilla**.
Llama 3 states it plainly: smaller models trained "much longer than is compute-optimal...
perform better than compute-optimal models at the same inference budget"
([2407.21783](https://arxiv.org/html/2407.21783v3)). This, not architecture, is why a 0.5B
model reaches GPT-3's MMLU. Counterweight: [Scaling Laws for Precision](https://arxiv.org/html/2411.04330v2)
(465 runs) finds overtrained models are *more* damaged by post-training quantisation, with
degradation growing in tokens — hence QAT.

**2. Data curation — +4 to +11 points.** The clean fixed-size ablation is phi-1's at **350M**:
HumanEval 12.19 unfiltered Stack → 17.68 filtered → 20.12 filtered+synthetic
([2306.11644](https://arxiv.org/abs/2306.11644)). [FineWeb-Edu](https://arxiv.org/html/2406.17557v2)
at 1.71B/350B tokens: **MMLU 33 → 37, ARC 46 → 57** vs plain FineWeb, matching a competitor's
final MMLU with ~10x fewer tokens.

**3. Distillation — +7.4 MMLU at 2B.** Gemma 2's Table 6 is the cleanest ablation: 2B params,
500B tokens, 7B teacher, **from-scratch 60.3 → distilled 67.7**
([2408.00118](https://arxiv.org/html/2408.00118v3)). Logit- vs sequence-level barely differ —
[MiniLLM](https://arxiv.org/html/2306.08543v4) puts them within ±0.5 ROUGE-L and shows both
beaten by reverse KLD. Apple's [Distillation Scaling Laws](https://arxiv.org/html/2502.08606v1)
adds the constraint: distillation beats supervised learning only if a teacher **already
exists**, and optimal teacher size is only "slightly larger than the student" — bigger
teachers eventually *hurt*.

**4. Pruning + healing — compute efficiency, not capability.**
[Minitron](https://arxiv.org/html/2408.11796v3) prunes Llama-3.1-8B (MMLU 64.1) to 4B and
heals on **94B tokens (~150x fewer than the teacher's 15T)**, recovering MMLU 60.5 — ~94% of
teacher.

**Reachable on ~$10 and one 8GB GPU:** the entire TinyStories grid (community reproductions
hit story quality in 1-3h on 8GB); BabyLM Strict-Small (10M words, ~30M params); task-specific
distillation into 220-350M, exactly where "small beats large" is numerically real; QLoRA on
Gemma-3-270M (0.5GB at int4). **Not reachable:** any 1T+ token pretraining — SmolLM2-135M used
**64 H100s**, Pythia-160M cost ~$2,050 of A100 time at 300B tokens, SmolLM2-1.7B cost
**$250,000** by the authors' own figure.

## 5. Architecture: does anything beat a dense transformer under 1B?

**No.** Architecture buys inference economics — throughput, KV-cache size, footprint — which
is real and large. It does not buy capability per parameter.

The decisive controlled experiment is NVIDIA's: Nemotron-H 8B (hybrid Mamba) vs Nemotron-T 8B
(dense), **identical 15T tokens** — the dense transformer wins MMLU 73.2 vs 72.8, GSM8K 89.0
vs 87.1, HumanEval 59.8 vs 58.5 ([2504.03624](https://arxiv.org/html/2504.03624v2)). The
hybrid bought ~3x speed at parity.

**SSMs.** [Mamba](https://arxiv.org/html/2312.00752v2) beats Pythia by ~4 points at every size
— but Pythia is a 2022 recipe, and against Transformer++ the paper's own word is "match."
The failure is architectural: ["Repeat After Me"](https://arxiv.org/html/2402.01032v2) shows a
**410M transformer beating a 2.8B Mamba** on phone-book lookup despite Mamba's lower
perplexity everywhere. NVIDIA's 8B/3.5T study ([2406.07887](https://arxiv.org/html/2406.07887v1))
quantifies it — MMLU 50.07 dense / 48.70 Mamba-2 / **53.60 hybrid**; RULER-4K 77.62 /
**52.14** / 81.99. Tellingly, pure SSMs *match* dense on **cloze**-format MMLU: the knowledge
is there, they cannot route it to an answer token. The field's fix was putting attention back.

**Hybrids.** Few trained a same-data dense control. Samba-1.7B did and won (54.33 vs 51.17,
[2406.07522](https://arxiv.org/html/2406.07522v3)) — though pure Mamba also beat dense there,
so the gain is "SSM," not "hybrid." RecurrentGemma-2B *lost* to Gemma-2B on MMLU (38.4 vs
42.3). Zamba2, Falcon-H1, LFM2 and Qwen3-Next publish no dense control on their own corpus.

**MoE — a large win, sold backwards.** [OLMoE](https://arxiv.org/html/2409.02060v2), same lab
and data: at fixed **active** params, MMLU 54.1 vs dense OLMo-1B's 32.1, +22 points at equal
inference FLOPs. But at fixed **total** params it loses to dense OLMo-7B on 5 of 6 benchmarks.
It is 7B-of-memory at 1B-of-speed, not 7B quality at 1B cost. Nothing credible ships below
~1B active; IBM shipped Granite 4.0 Nano's 350M/1B tier **dense**.

**BitNet / ternary.** Microsoft's own matched experiment (same data, 100B tokens) shows
ternary *losing* at small scale: zero-shot avg 45.5 → 44.3 at 700M, 46.2 → 45.4 at 1.3B
([2402.17764](https://arxiv.org/html/2402.17764v1)). Parity is a crossover claim at ~3B from
four points on one run. The 2025 flagship BitNet b1.58 2B4T
([2504.12285](https://arxiv.org/html/2504.12285v1)) — 0.4GB, 0.028J/token — has **no same-data
FP16 baseline at all**, and loses MMLU to Qwen2.5-1.5B by 7.1 points; INT4-PTQ Qwen2.5-1.5B
beats it at 0.7GB. Spectra/TriLM ([2407.12327](https://arxiv.org/html/2407.12327v1)) is
franker: ternary "consistently underperforms FloatLM at identical parameter counts." The
honest metric is quality **per bit**, not per parameter.

**Nested and discrete.** MatFormer ([2310.07707](https://arxiv.org/html/2310.07707v2)) nested
submodels beat independently-trained equivalents by ≤1.4% but leave scaling exponents
unchanged — the product is elasticity, not quality. Meta's Large Concept Models
([2412.08821](https://arxiv.org/html/2412.08821v2)) — the closest published thing to a
discrete bottleneck at scale — **lost** to Meta's own same-data 1.4B smaLlama (ROUGE-L 33.40
vs 34.88), conceded in the paper. LLaDA (diffusion) *matched* at 1B under controls. Matryoshka
representation learning is embedding compression, not an LM architecture.

**One exception worth watching: H-Net** ([2507.07955](https://arxiv.org/abs/2507.07955), 2025).
Compute- and data-matched, its 2-stage byte-level model matches a transformer of **twice its
size**, and **the gap widens with more data** (overtaking BPE after ~30B bytes). A better
scaling *slope* rather than a better constant is what sets it apart.

**Two systemic tells.** Almost every "beats transformers" result under 3B comes from a
sub-Chinchilla token budget — the regime that flatters non-attention architectures, and where
the ordering has flipped with more data. And the most promoted models have no control:
BitNet's 2024 paper *ran* the matched experiment and showed ternary losing at ≤1.3B; the 2025
flagship dropped the baseline rather than repeating it.

**Implication for Ralytable.** A discrete codebook bottleneck is in the same family as LCM and
VQ, and the published prior is that such bottlenecks **cost** a little rather than gain.
Finding 06's "about 3 points of accuracy" is exactly the expected sign and roughly the
expected magnitude. The defensible claim is not that the discrete core is *better*, but that
legibility is **cheap** — and that needs a same-data dense control, which finding 06 has and
most of the literature above does not.

## 6. Honest calibration by scale

Ralytable's current model is 6.4M parameters, character-level, 6 layers
([finding 06](../experiments/06_discrete_core/FINDINGS.md)).

**6.4M — coherent prose in a narrow domain, zero general reasoning.** This is precisely the
TinyStories band, and TinyStories is the ceiling: fluent multi-paragraph text with near-perfect
grammar over a ~1500-word vocabulary, consistency ~7.8/10, and out-of-distribution instruction
composition *within that domain*. No MMLU above chance, no open factual recall, no code. One
extra penalty applies here: **character-level tokenisation spends capacity and context window
on spelling** that BPE gets free. A 6.4M model that cannot reason is not a bug — nothing at
6.4M reasons. The realistic ceiling is domain-restricted fluency plus shallow,
template-shaped multi-step structure of exactly the kind finding 06 measures at 0.84 top-1.

**50M — grammar solved, world knowledge absent.** BabyLM's 30M strict-small GPT-BERT reaches
BLiMP 81.2 and (Super)GLUE 76.5 while EWoK sits near chance. GLiNER-S at 50M beats ChatGPT at
zero-shot NER. Strong syntax, strong narrow discriminative tasks, no open-domain knowledge.

**200M — narrow task competence, MMLU still at chance.** Extraction, classification and
summarisation are solved (DeBERTa-v3-base 86M: MNLI 90.6). Generative MMLU stays at or below
25%. phi-1-small's 45% HumanEval at 350M shows the ceiling is set by **data narrowness, not
parameters** — but it took 7B curated tokens and a large teacher.

**1B — first scale where general capability is real but brittle.** Llama-3.2-1B-Instruct:
MMLU 49.3, GSM8K 44.4, IFEval 59.5. Qwen2.5-1.5B base: MMLU 60.9, GSM8K 68.5. Tool use still
broken (BFCL 25.7). This is the smallest scale at which "genuinely capable" holds without
qualification.

## THE BASELINE TO BEAT

Two numbers, because the field's frontier and the reachable target are different.

**Frontier, for reference: 494M parameters at MMLU 47.5** (Qwen2.5-0.5B base) — 354x smaller
than GPT-3 175B for +3.6 points. That is what extreme distillation currently means. It is
**not** reachable on $10 and an 8GB GPU; it took trillions of curated tokens.

**The target to actually aim at: 28M parameters, GPT-4-graded grammar ≥ 8.34 and consistency
≥ 8.95 on TinyStories, with the discrete bottleneck in place.**

That is the dense hidden-512 / 8-layer TinyStories row — ~4.4x the current 6.4M, trainable in
hours on one 8GB GPU, against a published baseline and a published grid. It converts the open
question from "can a small model reason" (no, and that is settled at this scale) into the
question the project is actually about: **does forcing state through a discrete codebook cost
anything, at a scale where the dense baseline is known to be good?** Finding 06 answers "about
3 points" on a bespoke task with no external baseline. Re-running against TinyStories makes
the claim legible outside the repo — which is the pitch.

Secondary, if the codebook holds: **135M parameters, HellaSwag ≥ 42.1** (matching
SmolLM2-135M). Honest warning — that needs ~2T tokens of pretraining and is out of budget by
roughly three orders of magnitude.
