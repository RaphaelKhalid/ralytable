# Prior art: is there already a public, competitive interpretability arena?

Research date: 2026-08-26. Method note: this session's web-search budget was exhausted before I
started, and DuckDuckGo/Bing both returned CAPTCHAs or garbage. Everything below therefore comes
from **direct fetches of canonical URLs, the arXiv API, the GitHub search API, and the Hugging Face
Hub search API** - all live, all dated. Where I could not verify something, I say so explicitly.
Claims marked **[training]** come from my prior knowledge and are *not* verified by a source I
fetched; treat them as leads, not facts.

---

## 1. Does an interpretability ARENA exist?

**No. I could not find one, and I looked hard.**

Searched and found nothing matching "public + competitive + ongoing + open submissions +
leaderboard + interpretability/auditing":

- **GitHub search API**, queries `interpretability arena`, `auditing arena llm`, `auditing game llm`,
  `interpretability benchmark leaderboard`, `sabotage evaluations leaderboard`. The only hits for
  "interpretability arena" are forks of the **ARENA curriculum** (an educational mech-interp course,
  not a contest) - a name collision that will be a real branding problem if you build this.
  The single closest repo is `rkaunismaa/AuditingLLMs` (last push 2026-07-12, 0 stars),
  "Reproducing the auditing game for hidden objectives (Marks et al. 2025) on a local RTX 4090" -
  i.e. one person re-running a paper, not a venue.
- **Hugging Face Spaces search** for "interpretability leaderboard" returns MTEB, UGI, Artificial
  Analysis - general capability leaderboards. No interpretability/auditing arena in the results.
- **Neuronpedia** (https://www.neuronpedia.org/, fetched live): a hosted interpretability *platform*
  - Jacobian Lens, natural-language autoencoders, Circuit Tracer, plus hosting for third-party
  releases such as AxBench (Stanford NLP / pyvene). I fetched `/game/search` and found **no game and
  no competitive leaderboard**. Neuronpedia is infrastructure, not an arena. (It did once host a
  neuron-naming game surface **[training]**, but nothing competitive is live on it today.)
- **Apart Research sprints** (https://www.apartresearch.com/sprints, fetched live): an active
  hackathon pipeline through 2026 - AI Control Hackathon (Mar 20-22 2026), AIxBio (Apr 2026),
  Secure Program Synthesis (May 2026), Global South AI Safety (Jun 2026), Digital Minds (Aug 2026),
  AI Incident Response (Sep 11-13 2026). These are **48-hour one-offs judged on write-ups**, not a
  standing leaderboard, and none of the 2026 ones is an auditing / hidden-property contest.
- **NeurIPS/ICML competition tracks**: no interpretability or auditing competition found for
  2024, 2025 or 2026. The only relevant ones ever run were the Trojan Detection Challenges
  (section 3), which stopped after 2023.
- **LMSYS / Chatbot-Arena-style interp effort**: could not find one. Nothing exists.

## 2. Interpretability BENCHMARKS that exist

These are the adjacent ground. All are *benchmarks* (fixed task, you run it yourself), not arenas.

| Thing | Status | Leaderboard | Live submissions |
|---|---|---|---|
| **SAEBench** (`adamkarvonen/SAEBench`, 183 stars, last push 2026-05-01, not archived) | maintained but quiet | website + HF **[training]** | no open competitive submission flow found |
| **MIB: Mechanistic Interpretability Benchmark** (https://mib-bench.github.io, ICML 2025, arXiv 2504.13151) | **exists and is live** | yes - HF Space `mib-bench/leaderboard`, status *Running*, 12 likes | tracks: circuit localization + causal variable localization. Repo `aaronmueller/MIB` last push **2025-08-15**, a year stale. Submission count not published. |
| **AxBench** (Stanford NLP, hosted on Neuronpedia) | released | comparative results | steering-methods benchmark, not auditing |
| **Anthropic auditing game** (Marks et al. 2025, arXiv 2503.10965) | **one-off, internal** | none | see section 4 |
| **Cywinski et al., "Towards eliciting latent knowledge from LLMs with mechanistic interpretability"** (arXiv 2505.14352, May 2025) - the taboo models | models public | none | static artifacts |
| **"Eliciting Secret Knowledge from Language Models"** (arXiv 2510.01070, Oct 2025; Cywinski, Ryd, Wang, Rajamanoharan, Nanda, Conmy, **Samuel Marks**) | **live, closest benchmark** | none found | authors "release our models and code, **establishing a public benchmark for evaluating secret elicitation methods**" - but I found **no leaderboard and no submission mechanism**. |
| OpenXAI (`AI4LIFE-GROUP/OpenXAI`, 258 stars) | **dead** - last push 2024-08-17 | had one | saliency-map era, not LLM |

The last row matters: OpenXAI is exactly this genre (a public XAI evaluation leaderboard) and it
stopped being touched two years ago.

## 3. Trojan/backdoor detection competitions - the closest analogue, and it is dead

This is the most informative section.

- **IARPA/NIST TrojAI** (https://pages.nist.gov/trojai/, fetched live 2026-08-26): the page header
  now reads **"Competition Closed with Results Archived Here."** Every round shows
  `Accepting submissions: False`. Final rounds were LLM-Instruct, RL-SafetyGymnasium and
  Mitigation-LLM-Instruct, all **October 2024**; last submissions Sep-Oct 2024. **Dead, ~22 months.**
- **NeurIPS Trojan Detection Challenge**: TDC 2022 (`mmazeika/tdc-starter-kit`, 33 stars) and TDC
  2023 LLM Edition (`centerforaisafety/tdc2023-starter-kit`, 92 stars, last push 2024-05-19).
  **No 2024, 2025 or 2026 edition exists.** The domain **trojandetection.ai now fails DNS
  resolution entirely** (`getaddrinfo ENOTFOUND`, verified 2026-08-26); the Wayback API shows its
  last successful 200 snapshot on **2026-05-17**, so the site went dark within the last three
  months. **Dead.**
- **SaTML**: satml.org's current live page is a **Call for Competitions for SaTML 2027** - the
  competition track solicits *proposals* each year rather than running a standing contest. I could
  not retrieve the list of past SaTML competitions (the "past editions" pages 404'd). SaTML has run
  an LLM CTF **[training]**, but I could not verify it, and it is prompt-injection, not
  interpretability.

**Why did they die - and this reason applies directly to us.** The post-mortem paper
*"Trojan Detection in Large Language Models: Insights from The Trojan Detection Challenge"*
(arXiv 2404.13660, 2024-04-21) reports that the **best competition entries achieved Recall around
0.16 - comparable to randomly sampling sentences from the training-prefix distribution.** The
winning methods were, on the metric that actually matters, indistinguishable from chance. A
competition where nobody can beat random is not a competition: it produces no ranking signal, no
year-on-year progress story, and no reason for anyone to return. That, far more than funding, is
the plausible cause of death, and it is the single biggest risk to the proposed arena:
**hidden-property recovery may simply be too hard to produce a usable leaderboard gradient.**

## 4. Auditing and evals organisations

- **Anthropic alignment stress-testing**: the auditing game (Marks et al. 2025, arXiv 2503.10965)
  was a **closed red-team/blue-team exercise with four internal teams**. The public write-up
  (anthropic.com/research/auditing-hidden-objectives, fetched live) contains **no** ongoing
  competition, **no** leaderboard, and **no** release of the RM-sycophant model organism. Critically,
  it says: *"just as cybersecurity experts use Capture the Flag games to practice relevant skills
  ... we hope that a mature field of alignment auditing could use methodologies like ours."*
  **They named the exact idea and did not build it.** That is the strongest evidence both that the
  ground is empty and that the obvious incumbent has chosen not to occupy it.
- **Anthropic Petri** (announced 2025-10-06): an open-source *auditing tool*, explicitly **not** a
  leaderboard - they say quantitative distillation is "inherently reductive" and their metrics are
  "very provisional."
- **Apollo Research**: GitHub org repos are libraries and papers (`deception-detection`, `apd`,
  `watcher`, `e2e_sae`). **No public competition.**
- **METR**: no public competitive leaderboard found; their task suites are run by them.
- **UK AISI** (aisi.gov.uk/work, fetched live): runs an **Evals Bounty** (2024-11-05), the **AISI
  Challenge Fund** (2025-06-05) and **Systemic AI Safety Grants** (2024-10-15). These are grants and
  bounties, **not leaderboards**. Their GitHub org publishes model organisms
  (`AI-Safety-Institute/consistency-misalignment`, 2026-07-02) but hosts no arena.

**Obvious incumbent:** Anthropic's stress-testing team, or Neel Nanda's group (they produced
2505.14352 and 2510.01070). Either could out-execute you. Neither has, in 17 months.

---

## IS THIS GROUND OCCUPIED

**Genuinely empty - but empty for a reason that should worry you.**

Nothing I found is a public, ongoing, open-submission competitive arena for uncovering hidden model
properties. The nearest four things, and why each falls short:

1. **MIB** (live, has a leaderboard) - measures whether a *method* localises a known circuit. The
   ground truth is published. It is not adversarial and there is no hidden secret.
2. **"Eliciting Secret Knowledge" (arXiv 2510.01070)** - the closest in *content*: real model
   organisms with real hidden knowledge, publicly released, explicitly framed as "a public
   benchmark." It lacks only the arena layer: no leaderboard, no ongoing submissions, no hidden
   held-out set. This is your most likely competitor and your most likely collaborator; talk to the
   authors before building.
3. **Anthropic's auditing game** - right format, wrong distribution: internal, one-off, models never
   released, and Anthropic themselves flagged the CTF version as future work they have not done.
4. **TrojAI / TDC** - right format, right adversarial structure, **both dead** (Oct 2024 and 2023
   respectively; trojandetection.ai no longer resolves at all).

**The specific reason nobody has done it** - and this is the thing to solve before writing code - is
**difficulty calibration, not demand.** TDC 2023 died because its top entrants scored at chance
level (arXiv 2404.13660). An arena needs a leaderboard that separates entrants; hidden-property
recovery is a needle-in-a-haystack task where methods tend to be either trivially successful (a
prefill attack recovers the secret word) or hopeless (nobody finds the backdoor trigger), with very
little middle. The secondary reason is **cost of the red team**: every round requires training fresh
model organisms nobody has seen, which is expensive, must not leak, and has no obvious funder -
TrojAI had IARPA money and still stopped. The regulatory pitch may be correct and still not fix
either problem.

**Recommendation:** build only if you can first show, on the already-public 2510.01070 and 2505.14352
model organisms, that you can construct a difficulty ladder on which current methods score
meaningfully between 0 and 1. If you cannot, you will rebuild TDC and die the same way.

---

### Sources (all fetched 2026-08-26 unless noted)

- https://pages.nist.gov/trojai/ - TrojAI, "Competition Closed with Results Archived Here"
- https://mib-bench.github.io/ and https://huggingface.co/spaces/mib-bench/leaderboard - MIB
- https://arxiv.org/abs/2404.13660 - TDC 2023 post-mortem, Recall ~0.16
- https://arxiv.org/abs/2503.10965 - Marks et al., Auditing language models for hidden objectives
- https://www.anthropic.com/research/auditing-hidden-objectives
- https://www.anthropic.com/research/petri-open-source-auditing
- https://arxiv.org/abs/2510.01070 - Eliciting Secret Knowledge from Language Models
- https://arxiv.org/abs/2505.14352 - Cywinski et al., taboo / latent knowledge models
- https://www.neuronpedia.org/ and /game/search
- https://www.apartresearch.com/sprints
- https://www.aisi.gov.uk/work
- https://satml.org/ and https://satml.org/call-for-competitions/
- github.com/centerforaisafety/tdc2023-starter-kit, github.com/mmazeika/tdc-starter-kit,
  github.com/adamkarvonen/SAEBench, github.com/aaronmueller/MIB, github.com/AI4LIFE-GROUP/OpenXAI
