# Stage 1 — Research & Understanding

**Project:** Cross Scale Adaptive ML for Accuracy Stability Under Varying Data Conditions (Team 225, Sharda University; supervisor Dr. Neha Kumari)
**Basis:** *Adaptive Machine Learning Pipelines for Evolving Data Streams: A Comprehensive Review* (Shikha, Kumar, Bansal, Kumari)

**Sources read**
- `Adaptive ML-reviewed (3).docx`: the review paper as reviewed by the supervisor, with 9 comments. It has 20 references, 3 tables and 1 figure (the review methodology).
- `Evaluation-1 Project PPT (2).pptx`: 21 slides, including the submission summary (Int'l Conf. on AI Based Cyber Resilience, Paper ID 202, 30 Aug 2026), a sequence diagram, an activity diagram and a progress slide.

## A. Problem statement

Traditional ML pipelines are built around **static datasets and periodic retraining**. Streams from IoT devices, sensors, financial platforms and other real-time sources show **distribution drift and concept drift**, and these degrade models that were trained once (paper §I; refs [5], [7]).

Adaptive ML techniques help with this: adaptive preprocessing, online feature selection, drift detection, incremental learning and adaptive model updating. However, **existing systems evaluate predictive performance without accounting for latency and computational efficiency**. That is a problem in real-time and resource-limited (edge) settings.

PPT slide 4 gives the short form:
> Static ML models may lose performance over time → adaptive ML framework → data-change detection + model adaptation → focus on accuracy, latency, resource utilization → edge-based processing → **Outcome: adaptive ML prototype + monitoring dashboard** (monitoring data drift, model performance, latency, resource usage).

**One-line version for this project:** Build and evaluate an integrated adaptive pipeline for evolving streams where every accuracy number is measured together with its latency and resource cost.

## B + C. Existing approaches, by literature category

The strengths and limitations below come from paper Tables I and II. They are the paper's own wording, condensed.

| # | Category | Refs | Contribution | Limitation (per paper) |
|---|---|---|---|---|
| 1 | Adaptive preprocessing | [3] Žliobaitė & Gabrys 2014; [17] Niloy 2025; [19] Gupta & Hewett 2019 (adaptive normalization) | Adjusts preprocessing to changing data; less manual intervention | Extra overhead; limited large-scale validation; [19] numerical features only |
| 2 | Online feature selection | [4] Hoi et al. 2012; [16] Hochma & Last 2025 | Removes irrelevant features, lowers compute; supports changing relevance | Sensitive to data characteristics and parameters |
| 3 | Concept drift detection | [5] ADWIN (Bifet & Gavaldà 2007); [7] Halstead 2022 (probabilistic, recurring) | Detects distribution change early; [7] handles recurring concepts | Detection errors and overhead; ADWIN affected by noisy streams |
| 4 | Incremental / continual learning | [18] Zhang 2021; [1] Ashrafee 2026; [2] Yu 2026 | Continuous updates, knowledge retention | Memory/update cost grows; abrupt drift is hard |
| 5 | Adaptive learning algorithms | [20] Adaptive Random Forest (Gomes 2017) | Strong classification under drift | Higher computational and model-management complexity |
| 6 | Streaming ML frameworks | [9] SAMOA; [10] River | Reusable infrastructure for online stream processing | River has limited distributed support; SAMOA needs distributed infrastructure; limited end-to-end adaptation |
| 7 | Pipeline orchestration | [6] Modyn 2025; [8] Celik & Vanschoren 2021 (adaptive AutoML; Table I only) | Automates data selection and retraining | Limited validation on heterogeneous streams; [8] has limited preprocessing integration |
| 8 | Edge-based adaptive ML | [11] edge–cloud; [12] resource-aware edge; [13] edge drift detection | Less data transfer, real-time and resource-aware processing | Limited edge resources; deployment complexity |
| 9 | TinyML / resource-constrained ML | [14] Disabato & Roveri 2024; [15] DFDT 2026 | Adaptation on constrained devices; considers runtime and memory | Hardware limits force accuracy–latency–resource trade-offs |

**The paper's cross-cutting findings** (§II, subsections "Accuracy Analysis" and "Latency and Efficiency Analysis"):
- Adaptive methods are *likely to retain or regain* predictive performance under change. However, accuracy is usually assessed **without** the computational or latency cost, especially when cloud and edge are compared.
- Cloud processing adds data-transfer latency. Edge–cloud [11], resource-aware [12] and TinyML [14] approaches address this. Modyn [6] avoids reprocessing the full history.
- Latency is **reported inconsistently**: different studies use different methods and units, so direct comparison is hard.

## D. Research gaps

These are the six gaps from paper Table III. PPT slide 9 lists five and adds *energy*.

| ID | Gap (paper wording, condensed) | What an honest prototype can do about it |
|---|---|---|
| **G1** Pipeline integration | Limited integration of multiple adaptive components into a unified pipeline | Run preprocessing, feature selection, drift detection, adaptation, prediction and monitoring as **one pipeline on one stream** |
| **G2** Accuracy optimization | Accuracy is evaluated without the computational cost of continuous adaptation | Pair **every accuracy/F1 figure with its cost** (update time, CPU, memory) |
| **G3** Latency & efficiency | Latency is not evaluated consistently together with accuracy | Measure **per-stage latency in the same run** that produces the accuracy numbers |
| **G4** Edge deployment | Limited evaluation of complete adaptive pipelines under real-world edge constraints | Only partly addressable: a **simulated** constraint profile. Real results need real hardware (a Raspberry Pi is "optional" per slide 17) |
| **G5** Resource-aware adaptation | Limited dynamic adaptation based **simultaneously** on data drift and available resources | An adaptation decision that reads **both** the drift signal and the resource state. This is the one decision-making element |
| **G6** Unified evaluation | Different datasets, metrics and environments make comparison difficult | A **single reproducible harness**: same stream, seed, machine and metrics for every compared model. This demonstrates the protocol; it does not solve cross-study comparability |

## E. Proposed research direction (paper §VI)

- Explore an **accuracy–latency-aware adaptive ML framework for an edge-based streaming environment**.
- **Components:** adaptive preprocessing, concept drift detection, incremental learning, online feature selection.
- **System-level monitoring:** resource usage, processing time and prediction performance *during operation*.
- **Key goal:** *dynamically adapt the adaptation process* to changes in both **data flow** and **computational resources**. The paper names four options:
  1. choosing the right model
  2. updating model parameters
  3. changing the processing configuration
  4. starting retraining if necessary
- Consider edge processing to minimize data transfer.
- **Evaluation:** on changing data-stream datasets, **compared with existing adaptive learning approaches**, using accuracy, F1-score, prediction latency, model-update time, computational overhead and memory usage.
- **Intended output:** empirical evidence on the performance vs. processing-efficiency trade-off, i.e. "foundational models and measurements".

The paper presents this as a *direction to explore*. It does **not** claim a new algorithm or a validated system.

## F. Proposed system workflow (PPT slides 19–20)

**Activity diagram:**
`1 Input data stream → 2 Adaptive preprocessing (cleaning, normalization, missing values) → 3 Online feature selection → 4 Concept drift detection ("monitor data distribution") → 5 Drift? → [No] 6A Continue with current model | [Yes] 6B Adaptation (update/retrain model incrementally) → 7 Make predictions → 8 Monitor & evaluate (accuracy, latency, memory, CPU, update time) → 9 Continue streaming? (loop / stop)`

**Sequence diagram:** six lifelines (User, Web Dashboard, Backend API Server, Stream Processor, Adaptive ML Engine, Monitoring Module):
1. Provide stream/configure
2. Send request
3. Forward stream/config
4. Preprocess & extract features
5. Detect drift & decide adaptation (self-call)
6. Updated model/predictions
7. Send metrics (accuracy, latency, memory, CPU, update time)
8. Store/update logs & metrics
9. Return results
10. Display (dashboard/alerts)

**Workflow observations:**
- **Ordering tension.** The diagrams put drift detection *before* prediction. Label-based concept drift detection (on the error stream) needs the prediction and the true label first, which is standard prequential "test-then-train". There are two faithful ways to resolve this; decide in Stage 3:
  - an **input-distribution monitor** before prediction (matches "monitor data distribution") plus an **error-rate monitor** after the label arrives, or
  - a documented reordering.
- Step 6B says "update/**retrain** model incrementally", and §VI allows "retraining if necessary". So **incremental update as the default, with model reset/replacement as an escalation** is faithful to the sources. Retraining from scratch on every drift is not required anywhere.
- Step 8, "store/update logs & metrics", implies only lightweight persistence (experiment logs/results). A database is not implied.

## G. Evaluation metrics

| Metric | Where stated | Notes |
|---|---|---|
| Accuracy | Paper §VI; PPT 5, 14; both diagrams | Prequential (test-then-train), both windowed and cumulative |
| F1-score | Paper §VI; PPT 5, 14 | |
| Prediction latency | Paper §VI; PPT 14; diagrams | Must be separated from API/UI latency |
| Model-update time | Paper §VI; PPT 14; diagrams ("update time") | |
| Computational overhead | Paper §VI; PPT 5, 14 | **Not defined in the sources.** Needs an explicit operational definition (e.g. CPU time per sample, or adaptive minus static cost) |
| Memory usage | Paper §VI; PPT 5, 14; diagrams | Process memory and model size |
| CPU usage | Sequence step 7; activity step 8 | |
| Drift status | PPT 4 (dashboard) | |
| Energy | PPT slide 9 (gap only) | Not in the paper's metric list and not reliably measurable on a laptop, so **out of scope, stated as a limitation** |

**Prototype-defined metrics** (not in the sources, so they must be labelled as ours). These operationalize "accuracy stability" from the title:
- accuracy drop after drift
- recovery time (samples needed to regain the pre-drift level)
- detection delay
- false alarms
- throughput

## H. Constraints

- **Implementation** (PPT 15): continuous adaptation raises compute and memory; integrating many components raises complexity; high-rate or long streams raise processing and update time.
- **Data** (PPT 15): datasets differ in drift type, volume and feature distribution; limited domain coverage limits generalization. The paper's abstract targets *real-world* evolving streams, so **at least one real dataset** is needed alongside synthetic controlled drift.
- **Model** (PPT 16): models respond differently to abrupt vs. gradual drift; continuous updates can cause **instability or unnecessary retraining**.
- **Evaluation** (PPT 16): accuracy and latency depend on hardware and deployment configuration; cross-paper results aren't directly comparable.
- **Hardware/stack** (PPT 17): 8 GB RAM, i5/Ryzen 5, optional Raspberry Pi; Python, scikit-learn/River/PyTorch, Pandas/NumPy, Flask/FastAPI, React/Streamlit; open-source only.
- **Project:** three-member team (see §K). The implementation is one member's workstream, so the prototype should stay small, credible and measurable.

## I. What the PPT claims is completed (slide 18)

- ✓ Research topic finalized
- ✓ 20-paper literature survey
- ✓ Review paper prepared
- ✓ Methodology and research gaps
- ✓ Accuracy and latency graphs

Also: the paper was submitted as ICAIBCR Paper ID 202 on 30 Aug 2026. The implementation phase was approved at the zeroth evaluation (21 Apr 2026), and the implementation approach was discussed on 17 Aug 2026.

## J. Next implementation phase (slide 18)

- → **Adaptive ML prototype**
- → **Edge deployment and dashboard**
- → **Experimental evaluation**

The acceptance criteria are the six objectives on slide 5:
1. Develop an adaptive pipeline.
2. Detect drift and trigger adaptation.
3. Integrate preprocessing, online feature selection and incremental learning.
4. Monitor accuracy, F1, latency, memory and computational overhead.
5. Evaluate edge-based processing.
6. Study the performance vs. resource-efficiency trade-off.

## K. Team structure and research-chain interfaces

Utsav clarified this after the Stage 1 presentation. It **supersedes slide 10**.

| Role | Owns |
|---|---|
| **Review / Literature member** | Literature survey, review paper, existing approaches, research gaps, related work; checks that the implementation stays aligned with the reviewed literature |
| **Implementation member (Utsav)** | Adaptive ML prototype, concept drift detection, incremental learning, model adaptation, backend, dashboard, pipeline integration, runtime/performance |
| **Research / Experimentation member** | Experimental methodology, datasets, evaluation design, comparative analysis, accuracy/F1/latency/resource analysis, interpretation, conclusions |

Slide 10 of the Evaluation-1 PPT split the work by pipeline stage:
- Simran: pipeline, preprocessing, feature selection
- Utsav: drift, incremental learning, adaptation
- Aastha: edge, monitoring, evaluation, integration

The next evaluation deck should show the current split so the panel sees a consistent story.

**Research chain and handoffs**

| Link | Handoff artifact | Produced by | Used / verified by |
|---|---|---|---|
| Literature → Gap | Paper Tables I–III, §VI | Review | All |
| Gap → Implementation | **Traceability matrix**: pipeline component ↔ cited reference ↔ gap (G1–G6) | Implementation drafts | Review verifies |
| Implementation → Experiment | **Config-driven experiment runner** (dashboard + CLI): pluggable datasets/models/detectors, fixed seeds, edge profiles | Implementation | Research |
| Experiment → Results | **Per-run output bundle**: config snapshot, per-window metrics, drift/adaptation event log, per-stage timings, resource samples, environment info (machine, library versions) | Runner, automatically | Research |
| Results → Analysis | Raw machine-readable files (CSV/JSON), with no conclusions baked in | — | Research |
| Analysis → Conclusion | Interpretation and claims | Research | Review checks against the literature |

**Principles for the implementation**
1. **Platform, not verdict.** The system measures and records; it does not interpret. UI text describes events ("drift detected at sample 5,012"), never research claims.
2. **Record primitives.** Log per-stage timings, CPU time, memory, model size, predictions, labels, detector state and events. The research member can then define derived metrics (computational overhead, recovery time, accuracy stability) without code changes.
3. **Everything experimental is configuration.** Dataset, drift type/position/intensity, model, detector sensitivity, window size, stream rate, feature budget, edge profile and seed are all parameters, not code.
4. **Reproducible.** The same config and seed give the same predictive results. Timing varies by machine, so each run records its environment.
5. **Traceable.** Every component names the reference it implements, so the review member can verify alignment.
6. **Attributed.** Docs and UI credit each role. Implementation docs describe the implementation, not the review or the experimental findings.

**Who decides what**

| Decision | Owner | What the implementation provides |
|---|---|---|
| Meaning of "Cross Scale" / "accuracy stability" | Whole team | Support for the agreed definition (resource profiles, stream rates) |
| Datasets | Research | Loaders for real and synthetic streams |
| Derived metric definitions (overhead, recovery, stability) | Research | Raw primitives plus a reference computation |
| Comparator methods | Research, with Review (must be literature-cited) | Pluggable model interface; static baseline and candidate models |
| Experimental protocol (runs, seeds, rates, drift positions) | Research | Batch runner |
| Default detector / model / adaptation logic | Implementation, justified by cited references; Review verifies | — |
| Edge constraint profile values | Research designs; Implementation enforces | Configurable profiles, labelled "simulated" |
| Claims and conclusions | Research; Review checks | Nothing: the platform does not generate claims |

## Source-fidelity notes

1. **"Cross Scale" and "Accuracy Stability" are not defined anywhere** in the paper or the PPT. The paper's own framing is *accuracy–latency-aware*. This needs a definition before Stage 2 (see open questions).
2. **Version mismatch.** The docx is the supervisor-reviewed draft. The supervisor asked for Table II to be replaced by at least two comparative graphs on accuracy and latency, and the PPT says the graphs are complete. Those graphs are **not in the file provided**, and the abstract on the submission summary is reworded compared with the docx. Prototype documentation should therefore cite §VI and Table III wording, which is stable across versions.
3. The paper says the framework will be **"compared with existing adaptive learning approaches"**. A static baseline alone falls short of the paper's own stated plan, so at least one method the paper cites (e.g. ARF [20]) should be a reference comparator.
4. **Literature numbers vs. prototype numbers.** The review's comparative graphs come from the literature. Every number the prototype shows is new and comes from our own experiments. The two must never be mixed.
5. **PyTorch** is listed in the stack (slide 17), but nothing in §VI needs deep learning. Dropping it fits the resource-efficiency theme.
6. **Team roles:** see §K. The slide 10 split is out of date, and the next deck should be updated.
7. **Prototype-defined metrics** (recovery time, detection delay, stability) and the definition of "computational overhead" are proposed by the implementation but **decided by the research member**.

## Implications for implementation (inputs to Stages 2–3, not decisions)

Several methods the paper cites are lightweight and directly usable, so the prototype can be built *from the paper's own references*:
- **ADWIN [5]** for drift detection; River provides it.
- **River [10]** as the streaming framework.
- **Adaptive normalization [19]** → a running mean/variance scaler.
- **Online feature selection [4] (Hoi et al.)** → a truncation-based sparse online linear model. It is small enough to implement correctly. [16] is heavier.
- **ARF [20]** as the "existing adaptive approach" comparator. The paper itself notes ARF's higher compute cost, which gives a natural accuracy-vs-cost story.
- **Hoeffding-tree family**: DFDT [15] belongs to this family, and River's Hoeffding trees are a close relative. They are **not DFDT**, so do not claim DFDT.
- **Resource-aware [12] / TinyML [14]** → a *simulated* edge constraint profile (feature budget, memory budget, update frequency).
- **Recurring concepts [7]** → an optional recurring-drift scenario.

## What we must not claim

- A novel ML algorithm.
- Edge-hardware results without testing on real hardware.
- Energy measurements.
- Production scalability.
- Universal drift detection.
- Guaranteed accuracy or latency gains.
- DFDT/Modyn/SAMOA re-implementations.

We may say: *prototype, experimental evaluation, controlled stream simulation, resource-constrained simulation, measured on local machine.*

## Open questions before Stage 2

1. **What does "Cross Scale" mean to the team/supervisor?** Proposed interpretation, which ties the title to G2–G5 without inventing a contribution: *the same adaptive pipeline evaluated across resource scales (normal vs. constrained edge profile) and stream scales (rates/volumes)*. **"Accuracy stability"** would mean how steady prequential accuracy stays through drift (drop depth, recovery time, variance).
2. Is the **final submitted paper** available, with the accuracy/latency graphs and any Results & Discussion section?
3. Is a **Raspberry Pi or other edge device** actually available? This decides whether edge mode is simulation-only.
4. ~~Team ownership~~ **Resolved:** see §K.
