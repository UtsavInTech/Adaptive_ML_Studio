# Literature check and novelty assessment

**Prepared:** 11 November 2026, by web search (WebSearch/WebFetch). Every reference below was found online during this check, and its title, authors, venue and link were confirmed on at least one index or publisher page. The few items I could only partly confirm are marked **(partly verified)** and listed in §5.

**Baseline for comparison:** the team's final review, *Adaptive Machine Learning Pipelines for Evolving Data Streams: A Comprehensive Review* (`docs/paper/Paper_159_Revised_Manuscript.txt`). In particular:
- Table 3, the seven gaps:
  - **PI** Pipeline Integration
  - **LE** Latency and Efficiency
  - **HW** Hardware and Deployment Heterogeneity
  - **RA** Resource-Aware Adaptation
  - **UR** Update and Retraining Overhead
  - **SB** Stage Bottleneck Attribution
  - **UE** Unified Evaluation
- §4.3, the cost model C_total, and the stated open question about how preprocessing and feature selection affect end-to-end latency.
- §6.2, the rules R1–R5, with resource limits treated as hard constraints.
- §6.3, the multi-objective J(θ), where "the choice of weights, the normalisation, and the search over configurations remain open design questions".

---

## 1. Is it new? Verdict table

"Closest work" means the nearest thing I found. Confidence is how sure I am that the "what remains novel" column is correct, given that my search was not exhaustive.

| # | Our claim or finding | Review gap / section | Closest prior work | What remains novel | Confidence |
|---|---|---|---|---|---|
| 1 | One stream-learning pipeline (preprocessing → online feature selection → Hoeffding tree → ADWIN) controlled **jointly** by drift and resource state, under **per-row** CPU and deadline budgets and a model-memory budget | RA, PI, §6.2 | RCCDA (Piaseczny et al., NeurIPS 2025) chooses *when to update* under drift and a long-run resource budget, using Lyapunov drift-plus-penalty. Ekya (NSDI 2022) schedules retraining against inference on edge GPUs for video. Chameleon (SIGCOMM 2018) adapts pipeline configurations to save resources. Buschjäger, Gunasekara & Gomes (arXiv, Aug 2026) benchmark stream learners under memory budgets and *call for* budget-respecting learners. DFDT (AAAI 2026) is a memory-bounded Hoeffding tree. | No work I found controls **several pipeline stages** (preprocessing width, feature count, update stride, model reset or retrain) from drift **and** per-row CPU, deadline and memory signals at the same time, on a real-drift tabular stream. RCCDA controls one action (update yes/no) against an average budget, with no per-row latency or memory. Ekya and Chameleon address video DNNs. The *rule-based* controller itself is not a methodological contribution: the review proposed it, and reviewers will see it as engineering. | **Medium** for "the combination and its evaluation are new". **High** that the rules alone will not be accepted as a method contribution. |
| 2 | The "repeat previous label" baseline scores 98.7 % on the chronological corrected CIC-IDS2017 stream, so accuracy is meaningless. κ-temporal separates the methods. | UE | κ-temporal and the persistence baseline: Žliobaitė et al. (MLJ 2015). Critiques of NIDS evaluation: Arp et al. (USENIX Sec 2022), Engelen et al. (SPW 2021), Liu et al. (CNS 2022), Apruzzese et al. (EuroS&P 2023), Pendlebury et al. (TESSERACT, USENIX Sec 2019). κ-temporal has been reported for streaming NIDS before: a search snippet attributes it to Adewole et al. (Electronics 2022), but I could not open the full text to confirm. | I found no paper that quantifies label persistence on the **corrected (Liu 2022) CIC-IDS2017 replayed in flow-end-time order**, or that shows high-accuracy streaming NIDS results on that stream would be matched by copying the last label. This is a useful **evaluation finding**, but not a method. | **Medium** (simple to state, and someone may have reported it without my finding it) |
| 3 | Preprocessing all 83 inputs, not the model, dominates per-row cost (107 of 153 µs) | SB, §4.3 open question, LE | CATO (Wan et al., NSDI 2025) and Traffic Refinery (Bronzino et al., POMACS/SIGMETRICS 2022) show that feature computation dominates serving cost in traffic-analysis ML and optimise for it **offline**. Lukats et al. benchmark the *computational* cost of drift detectors. | Stage-level cost attribution **inside an adaptive streaming learner** (C_pre vs C_fs vs C_inf vs C_upd vs C_drift), measured in the same run as quality, answers the review's §4.3 open question directly. Caveat: the 107 µs is partly a Python/River artefact (one scaler update per input, in a dict). A reviewer will ask whether it holds in a compiled implementation. State it as "in this stack". | **Medium** |
| 4 | Under a tight CPU budget, R3's "halve the features" meets the budget but destroys detection (κ-temporal < 0). Without R3, quality stays high at 3× the budget. | RA, §6.2 (R3) | No direct prior test of the review's R3. Budgeted feature acquisition on streams exists: Fainman et al. (arXiv 2019); Beyer et al. (Ann. Telecom. 2020, under feature drift). CATO shows offline that the *choice* of features drives the accuracy–cost Pareto front. | A **negative empirical result** for a rule that the review (and many edge papers) suggest. It is valuable as motivation and as an ablation, but on its own it is a small contribution. | **High** that it is untested in the literature. **Low** importance alone. |
| 5 | R5 holds a 256 KiB model budget 99 % of the time, at a cost in quality (κ-temporal 0.57 vs 0.75) | RA, UR | Memory-bounded trees: DFDT (AAAI 2026). Memory-budget benchmark: Buschjäger et al. (2026). Green/energy-aware trees: GAHT (Garcia-Martin et al., 2022). | Enforcing a memory budget by **pipeline-level** actions (drop the replacement model → fresh model → fewer features) and pricing it in detection quality on NIDS. Incremental. DFDT-style trees are the obvious stronger baseline we lack. | **Medium-low** |
| 6 | With labels delayed by 1k–10k rows, every method collapses | UE, RA | Grzenda, Gomes & Bifet (DMKD 2020); Gomes et al. (ACM CSUR 2022/23); INSOMNIA (Andresini et al., AISec 2021: active learning and label estimation for drifting NIDS); label-free detectors (Sethi & Kantardzic 2017; Lukats et al. 2024). | Known phenomenon. New only if we *fix* it within the resource budget. | **Low** novelty as a finding |
| 7 | The controller is rule-based with fixed thresholds | §6.3 open question | See §2-C and candidate 2 below: Online AutoML (Celik et al. 2023), ChaCha (ICML 2021), OMS-MAB (Wilson et al. 2024), OnlineTune (SIGMOD 2022), Bandits with Knapsacks (JACM 2018), SafeOpt (ICML 2015). | The review itself says the optimiser for J(θ) under hard L, M constraints is open. No prior work I found solves it **for a stream-learning pipeline with per-row latency and memory constraints under drift**. This is where a method contribution can sit. | **Medium** |
| — | Per-row cost-term breakdown C_pre…C_ret in one harness, with κ-temporal, block-bootstrap intervals and Friedman/Nemenyi | UE, UR, SB, HW | Bifet et al. (KDD 2015); Demšar (JMLR 2006); Souza et al. (DMKD 2020); Apruzzese et al. (2023: deployment-oriented NIDS assessment on four hardware platforms) | A reproducible protocol that pairs stream-aware quality with stage-level cost on simulated device tiers is a fair "resource/benchmark" contribution, not a novelty claim. HW is only partly addressed: the tiers are simulated, with no real device. | **Medium** |

**Overall verdict.** The *combination* is new as far as I can find: a full adaptive pipeline, controlled jointly by drift and per-row resource limits, evaluated on a real-drift NIDS stream with stream-aware metrics and stage costs. The *components* are all known, and the *rule ladder* will not count as a method. The measured findings, especially 2, 3 and 4, are honest and useful, but they are mostly negative or evaluative. To publish a method, the paper needs something that **moves the accuracy–cost frontier**, not just a controller that picks a point on a bad frontier. Candidate 1 below targets exactly that.

---

## 2. Related-work map

### A. Jointly drift-aware and resource-aware stream learning

- **RCCDA: Adaptive Model Updates in the Presence of Concept Drift under a Constrained Resource Budget.** A. Piaseczny, M. K. C. Shisher, S. Wang, C. G. Brinton. NeurIPS 2025. [arXiv:2505.24149](https://arxiv.org/abs/2505.24149).
  - Lyapunov drift-plus-penalty policy that decides when to update, using only past loss and a budget.
  - **The closest work in spirit.** It has a single binary action, an average budget, no per-row latency or memory, and no pipeline stages.
- **Towards Stream Learning on Embedded Systems: Benchmarking the Memory Consumption of Stream Learning Methods.** S. Buschjäger, N. Gunasekara, H. M. Gomes. arXiv, 31 Aug 2026. [arXiv:2608.30923](https://arxiv.org/abs/2608.30923).
  - 7 learners, 13 streams, budgets from 128 KiB to about 8 MiB.
  - HT and EFDT grow 7.4× and 5.9× (median).
  - Argues that bounded resources should be a first-class goal alongside drift adaptation. This **supports our motivation**.
- **DFDT: Dynamic Fast Decision Tree for IoT Data Stream Mining on Edge Devices.** Lourenço, Rodrigo, Gama, Marreiros. AAAI 2026 / [arXiv:2502.14011](https://arxiv.org/abs/2502.14011).
  - Memory-constrained Hoeffding tree with adaptive grace period and leaf deactivation.
  - Ref [15] in the review. A natural stronger baseline for R5.
- **Tiny Machine Learning for Concept Drift.** S. Disabato, M. Roveri. IEEE TNNLS 2024 (preprint 2021). [arXiv:2107.14759](https://arxiv.org/abs/2107.14759).
  - kNN plus a change-detection test on MCUs. Drift and constrained hardware, but no resource-driven control.
- **Green Accelerated Hoeffding Tree.** E. Garcia-Martin, A. Bifet, N. Lavesson, R. König, H. Linusson. arXiv 2022 (TinyML Research Symposium 2021 poster). [arXiv:2205.03184](https://arxiv.org/abs/2205.03184).
  - Energy-aware splitting, with up to 70 % less energy than EFDT/ensembles. Static policy.
- **Ekya: Continuous Learning of Video Analytics Models on Edge Compute Servers.** R. Bhardwaj et al. NSDI 2022. [usenix.org](https://www.usenix.org/conference/nsdi22/presentation/bhardwaj).
  - Schedules GPU between retraining and inference under drift. Joint drift and resource, but for video DNNs.
- **Chameleon: Scalable Adaptation of Video Analytics.** J. Jiang, G. Ananthanarayanan, P. Bodík, S. Sen, I. Stoica. SIGCOMM 2018. [DOI 10.1145/3230543.3230574](https://doi.org/10.1145/3230543.3230574).
  - Online configuration adaptation under resource limits by periodic profiling. Video, no learning under drift.
- **Modyn: Data-Centric Machine Learning Pipeline Orchestration.** M. Böther et al. SIGMOD 2025 (PACMMOD 3(1)). [DOI 10.1145/3709705](https://doi.org/10.1145/3709705).
  - Triggering and data-selection policies for retraining on growing data. Batch DNN, no per-row budgets. Ref [6] in the review.
- **VHT: Vertical Hoeffding Tree.** N. Kourtellis, G. De Francisci Morales, A. Bifet, A. Murdopo. IEEE BigData 2016. [arXiv:1607.08325](https://arxiv.org/abs/1607.08325).
  - Distributed Hoeffding tree on SAMOA. Scales *out*, the opposite of our edge setting.

### B. Streaming / online NIDS under drift, and NIDS evaluation critiques

- **Error Prevalence in NIDS datasets: A Case Study on CIC-IDS-2017 and CSE-CIC-IDS-2018.** L. Liu, G. Engelen, T. Lynar, D. Essam, W. Joosen. IEEE CNS 2022. [DOI 10.1109/CNS56114.2022.9947235](https://doi.org/10.1109/CNS56114.2022.9947235). Our data source.
- **Troubleshooting an Intrusion Detection Dataset: the CICIDS2017 Case Study.** G. Engelen, V. Rimmer, W. Joosen. IEEE S&P Workshops (WTMC) 2021. [DOI 10.1109/SPW53761.2021.00009](https://doi.org/10.1109/SPW53761.2021.00009).
- **Dos and Don'ts of Machine Learning in Computer Security.** D. Arp et al. USENIX Security 2022. [usenix.org](https://www.usenix.org/conference/usenixsecurity22/presentation/arp).
  - Ten pitfalls, including inappropriate baselines and data snooping. Our persistence baseline addresses the "inappropriate baseline" pitfall.
- **SoK: Pragmatic Assessment of Machine Learning for Network Intrusion Detection.** G. Apruzzese, P. Laskov, J. Schneider. IEEE EuroS&P 2023. [DOI 10.1109/EuroSP57164.2023.00042](https://doi.org/10.1109/EuroSP57164.2023.00042).
  - Deployment-oriented evaluation, including four hardware platforms.
- **TESSERACT: Eliminating Experimental Bias in Malware Classification across Space and Time.** F. Pendlebury, F. Pierazzi, R. Jordaney, J. Kinder, L. Cavallaro. USENIX Security 2019. [usenix.org](https://www.usenix.org/conference/usenixsecurity19/presentation/pendlebury).
  - Temporal and spatial bias. INSOMNIA extends it to NIDS.
- **INSOMNIA: Towards Concept-Drift Robustness in Network Intrusion Detection.** G. Andresini, F. Pendlebury, F. Pierazzi, C. Loglisci, A. Appice, L. Cavallaro. AISec 2021. [Royal Holloway record](https://pure.royalholloway.ac.uk/en/publications/insomnia-towards-concept-drift-robustness-in-network-intrusion-de/).
  - Active learning and label estimation to reduce update latency and labelling cost under drift.
- **ENIDrift: A Fast and Adaptive Ensemble System for Network Intrusion Detection under Real-world Drift.** X. Wang et al. ACSAC 2022. [DOI 10.1145/3564625.3567992](https://doi.org/10.1145/3564625.3567992).
  - Incremental packet-field features plus an ensemble. Reports robustness to delayed labels and lower running time. **(Partly verified:** co-authors not confirmed.)
- **Kitsune: An Ensemble of Autoencoders for Online Network Intrusion Detection.** Y. Mirsky, T. Doitshman, Y. Elovici, A. Shabtai. NDSS 2018. [arXiv:1802.09089](https://arxiv.org/abs/1802.09089).
  - Online, unsupervised NIDS run on a Raspberry Pi. The classic "NIDS on an edge device" reference.
- **Binary Anomaly Detection in Streaming IoT Traffic under Concept Drift.** R. M. Carnier, L. Lahesoo, K. Fukuda. IEEE NOMS 2026. [arXiv:2510.27304](https://arxiv.org/abs/2510.27304).
  - ARF and HAT on mixed IoT streams, with compute cost compared to batch. No κ-temporal and no delay.
- Datasets for a second stream:
  - **UNSW-NB15** (N. Moustafa, J. Slay, MilCIS 2015, [UNSW page](https://research.unsw.edu.au/projects/unsw-nb15-dataset)).
  - **CICIoT2023** (E. C. P. Neto et al., Sensors 23(13):5941, 2023, [DOI 10.3390/s23135941](https://doi.org/10.3390/s23135941)).

### C. Methods that could replace the rules

- **Online Cascade Learning for Efficient Inference over Streams.** L. Nie, Z. Ding, E. Hu, C. Jermaine, S. Chaudhuri. ICML 2024. [arXiv:2402.04513](https://arxiv.org/abs/2402.04513).
  - Cascade from cheap to expensive models with an online-learned deferral policy. Up to 90 % lower cost, robust to input shift.
  - Text/LLM setting, with no drift detector and no per-item hard budget. **Nearest to candidate 1.**
- **CATO: End-to-End Optimization of ML-Based Traffic Analysis Pipelines.** G. Wan, S. Liu, F. Bronzino, N. Feamster, Z. Durumeric. NSDI 2025. [usenix.org](https://www.usenix.org/conference/nsdi25/presentation/wan-gerry).
  - Multi-objective Bayesian optimisation over feature sets and capture depth, measured with a real pipeline profiler.
  - Offline, no drift. **Nearest to our feature-cost findings.**
- **Traffic Refinery: Cost-Aware Data Representation for Machine Learning on Network Traffic.** F. Bronzino, P. Schmitt, S. Ayoubi, H. Kim, R. Teixeira, N. Feamster. POMACS / SIGMETRICS 2022. [arXiv:2010.14605](https://arxiv.org/abs/2010.14605).
  - Per-feature state, compute and volume costs.
- **Online AutoML: An adaptive AutoML framework for online learning.** B. Celik, P. Singh, J. Vanschoren. Machine Learning 112, 2023. [DOI 10.1007/s10994-022-06262-0](https://doi.org/10.1007/s10994-022-06262-0).
  - Drift-triggered re-search over pipelines, including preprocessing. Budget is only the *search* time, with no per-row latency or memory constraints. Ref [8] lineage in the review.
- **ChaCha for Online AutoML.** Q. Wu, C. Wang, J. Langford, P. Mineiro, M. Rossi. ICML 2021. [PMLR 139](https://proceedings.mlr.press/v139/wu21d.html).
  - Champion–challenger online configuration search with regret guarantees. No resource constraints.
- **Multi-armed bandit based online model selection for concept-drift adaptation (OMS-MAB).** J. Wilson, S. Chaudhury, B. Lall. Expert Systems 2024. [DOI 10.1111/exsy.13626](https://doi.org/10.1111/exsy.13626).
  - Non-stationary bandit over drift-resistant ensemble members. An exploration factor trades accuracy against compute, but compute is a soft trade-off, not a hard constraint.
- **Towards Dynamic and Safe Configuration Tuning for Cloud Databases (OnlineTune).** X. Zhang et al. SIGMOD 2022. [DOI 10.1145/3514221.3526176](https://doi.org/10.1145/3514221.3526176).
  - Contextual BO with safe-region expansion for *live* systems. The best template for "safe online configuration search".
- **Bandits with Knapsacks.** A. Badanidiyuru, R. Kleinberg, A. Slivkins. JACM 65(3), 2018. [arXiv:1305.2545](https://arxiv.org/abs/1305.2545).
  - Bandits under resource budgets (cumulative, not per-step).
- **Safe Exploration for Optimization with Gaussian Processes (SafeOpt).** Y. Sui, A. Gotovos, J. Burdick, A. Krause. ICML 2015. [PMLR 37](https://proceedings.mlr.press/v37/sui15.html).
  - Only evaluates configurations that are safe with high probability.
- **On Upper-Confidence Bound Policies for Switching Bandit Problems.** A. Garivier, E. Moulines. ALT 2011. [DOI 10.1007/978-3-642-24412-4_16](https://doi.org/10.1007/978-3-642-24412-4_16).
  - Sliding-window and discounted UCB for abrupt change.
- **Online Budgeted Learning for Classifier Induction.** E. Fainman, B. Shapira, L. Rokach, Y. Mirsky. arXiv 2019. [arXiv:1903.05382](https://arxiv.org/abs/1903.05382).
  - Bandit-based per-instance feature acquisition under a budget. No drift.
- **Active feature acquisition on data streams under feature drift.** C. Beyer, M. Büttner, V. Unnikrishnan, M. Schleicher, E. Ntoutsi, M. Spiliopoulou. Annals of Telecommunications 75, 2020. [DOI 10.1007/s12243-020-00775-2](https://doi.org/10.1007/s12243-020-00775-2).
- **Label-free drift detection:**
  - **On the reliable detection of concept drift from streaming unlabeled data (MD3).** T. S. Sethi, M. Kantardzic. Expert Systems with Applications 2017. [DOI 10.1016/j.eswa.2017.04.008](https://doi.org/10.1016/j.eswa.2017.04.008).
  - **A benchmark and survey of fully unsupervised concept drift detectors on real-world data streams.** D. Lukats, O. Zielinski, A. Hahn, F. Stahl. Int. J. Data Science and Analytics 2024. [DOI 10.1007/s41060-024-00620-y](https://doi.org/10.1007/s41060-024-00620-y).
- **Active learning with drifting streaming data.** I. Žliobaitė, A. Bifet, B. Pfahringer, G. Holmes. IEEE TNNLS 25(1), 2014. [DOI 10.1109/TNNLS.2012.2236570](https://doi.org/10.1109/TNNLS.2012.2236570).

### D. Evaluation practice

- **Evaluation methods and decision theory for classification of streaming data with temporal dependence.** I. Žliobaitė, A. Bifet, J. Read, B. Pfahringer, G. Holmes. Machine Learning 98(3), 2015. [DOI 10.1007/s10994-014-5441-4](https://doi.org/10.1007/s10994-014-5441-4).
  - κ-temporal. The paper notes it must be paired with an imbalance-aware measure. We already add macro-F1 and per-attack recall.
- **Efficient Online Evaluation of Big Data Stream Classifiers.** A. Bifet, G. De Francisci Morales, J. Read, G. Holmes, B. Pfahringer. KDD 2015. [DOI 10.1145/2783258.2783372](https://doi.org/10.1145/2783258.2783372).
  - Prequential evaluation gives no significance. Proposes k-fold distributed validation (bagging/cross-validation folds) for streams. Consider citing it when justifying the block bootstrap.
- **Delayed labelling evaluation for data streams.** M. Grzenda, H. M. Gomes, A. Bifet. DMKD 34(5), 2020. [DOI 10.1007/s10618-019-00654-y](https://doi.org/10.1007/s10618-019-00654-y).
  - Continuous re-evaluation under verification latency. Use it for the label-delay grid.
- **A Survey on Semi-supervised Learning for Delayed Partially Labelled Data Streams.** H. M. Gomes, M. Grzenda, R. Mello, J. Read, M. H. Le Nguyen, A. Bifet. ACM CSUR 55(4), art. 75. [DOI 10.1145/3523055](https://doi.org/10.1145/3523055).
- **Statistical Comparisons of Classifiers over Multiple Data Sets.** J. Demšar. JMLR 7, 2006. [jmlr.org](https://jmlr.org/papers/v7/demsar06a.html).
  - Friedman + Nemenyi + CD diagram. Our Friedman blocks are stream segments, not independent datasets; the README already notes this. Say it in the paper.
- **Challenges in benchmarking stream learning algorithms with real-world data.** V. M. A. Souza, D. M. dos Reis, A. G. Maletzke, G. E. A. P. A. Batista. DMKD 34(6), 2020. [DOI 10.1007/s10618-020-00698-5](https://doi.org/10.1007/s10618-020-00698-5).
- Comparators:
  - **Adaptive random forests for evolving data stream classification** (H. M. Gomes et al., MLJ 106, 2017, [DOI 10.1007/s10994-017-5642-8](https://doi.org/10.1007/s10994-017-5642-8)).
  - **Streaming Random Patches** (H. M. Gomes, J. Read, A. Bifet, ICDM 2019, [DOI 10.1109/ICDM.2019.00034](https://doi.org/10.1109/ICDM.2019.00034)).
  - **River** (J. Montiel et al., JMLR 22, 2021, [jmlr.org](https://jmlr.org/papers/v22/20-1380.html)).
- **Energy:**
  - **Estimation of energy consumption in machine learning.** E. García-Martín, C. F. Rodrigues, G. Riley, H. Grahn. JPDC 134, 2019. [DOI 10.1016/j.jpdc.2019.07.007](https://doi.org/10.1016/j.jpdc.2019.07.007).
    - Includes a drift-detection energy case study.
  - **On a Mac laptop:**
    - CodeCarbon reads Apple Silicon energy only through `powermetrics`, and that needs root ([CodeCarbon methodology](https://docs.codecarbon.io/latest/explanation/methodology/)). Without root it falls back to a constant estimate, which is useless for comparing methods.
    - `powermetrics` "package power" covers the whole SoC except DRAM, not just our process.
    - **Recommendation:** if E is reported at all, report it as *CPU-time × measured package-power delta from an idle baseline* using `sudo powermetrics`, label it approximate, and keep CPU-µs/row as the primary cost. Otherwise keep energy as a stated limitation.

---

## 3. Ranked candidate contributions

Our measured facts drive this ranking:
- (i) ARF/SRP give κ-temporal 0.89–0.92, but cost 5–46× more.
- (ii) Uniform feature cutting meets the CPU budget and kills quality.
- (iii) Preprocessing width is the main cost.
- (iv) Labels arrive late.
- (v) 98.7 % of rows have the same label as the previous one, so **most rows are easy**.

Fact (v) is the key opportunity: a budget is best spent on the *few hard rows*, not cut uniformly across all rows.

### Candidate 1 (recommended): budget-constrained online cascade with drift-aware deferral

- **Idea.**
  - A cheap stage (Hoeffding tree on a small, cheaply preprocessed feature set) answers every flow.
  - Only flows where it is uncertain, or where the drift state says it cannot be trusted, are escalated to an expensive stage (ARF on the full, fully preprocessed feature set).
  - The escalation threshold is not hand-set. A primal–dual / virtual-queue update keeps the running CPU cost per row at or below C_max, and memory is held by R5-style actions on the expensive stage.
- **Why it is new.**
  - The nearest work is Online Cascade Learning (Nie et al., ICML 2024). It learns a deferral policy online for text/LLM cascades, with cost controlled by hyperparameters, no drift detector, no hard per-item budget and no stream-learner state.
  - Classic NIDS cascades (rule gate → RF) and NetBeacon's multi-phase models (USENIX Sec 2023) are static and trained offline.
  - RCCDA uses Lyapunov control, but only for *when to update*.
  - I found no cascade for **stream** classifiers that combines (a) an online deferral threshold driven by a hard per-row compute budget with (b) drift-triggered escalation.
- **Expected benefit given our numbers.**
  - Persistence is 98.7 %, and the cheap stage already reaches κ-temporal 0.49–0.64, so a small escalation rate (plausibly 5–15 %) could recover most of ARF's quality (0.89) at well under ARF's cost.
  - This directly replaces R3, which reached the budget only by giving up detection (κ-temporal < 0).
  - It changes the *frontier*, not just the operating point, and gives a Pareto figure that can beat both "joint" and ARF.
- **Implementation sketch** (2–4 days):
  - A new model wrapper in `backend/adaptiveml/models` (e.g. `cascade`):
    - Stage 1 is the existing pipeline with narrowed preprocessing and top-k features (reuse R3's narrowing code).
    - Stage 2 is `river.forest.ARFClassifier` on all features, with its own full scaler that is called *only* on escalated rows. Lazy preprocessing is where the saving comes from.
  - Deferral score: `1 − max predict_proba` of stage 1. Escalate if the score is above τ, or if a drift warning or alarm was raised in the last *w* rows.
  - Budget control: `τ ← τ + η·(cost_ewma − C_max)/C_max` (projected to [0,1]). This is a Lagrangian/dual step and fits in `joint_controller.py` as a new rule.
  - Learning: stage 1 learns every labelled row. Stage 2 learns on escalated rows plus a random fraction ρ, to avoid selection bias; ρ is also charged to the budget.
  - Log the escalation rate and the cost per stage into the existing cost terms (`C_inf` is split per stage).
- **Experiment that shows it helps.**
  - Gateway and small_sim tiers, 3+ seeds, against: joint (full), joint without R3, adaptive, ARF, HT-only, and **cascade with fixed τ** (an ablation of the budget controller).
  - Metrics: κ-temporal, macro-F1, per-attack recall, and the share of rows over budget.
  - Success means a point above the joint/HT front and inside the budget.
  - A second dataset (CICIoT2023 or UNSW-NB15) guards against a one-dataset effect.
- **Risk.**
  - ARF *learning* on escalated rows may itself cost more than the budget allows (it is about 650 µs/row). Measure ARF's predict and learn costs separately first. If learning dominates, cap stage-2 learning by stride as well, or use a smaller ARF (n = 3–5).
  - Uncertainty from a Hoeffding tree is poorly calibrated, especially right after drift, which is why the drift-state escalation is included.
  - The gain could be small if errors are not concentrated in uncertain rows. That is measurable in a day with an *oracle-free* check: compute stage-1 confidence on rows where ARF and HT disagree.

### Candidate 2: online constrained configuration search for J(θ), as in §6.3 of the review (the coordinator asked for this to be assessed explicitly)

- **Idea.**
  - Treat a small discrete set of configurations θ as arms of a **non-stationary constrained bandit**. Each θ combines:
    - feature count k ∈ {4, 8, 16, 32, all};
    - preprocessing (narrow or full);
    - update stride (1, 2, 4);
    - model (HT or small ARF).
  - Pick θ to minimise J subject to L ≤ L_max and M ≤ M_max. Use:
    - sliding-window/discounted UCB (Garivier & Moulines 2011) for drift, with a window reset on ADWIN alarms;
    - pessimistic cost estimates (SafeOpt/OnlineTune-style) so that only configurations believed feasible are tried;
    - Lagrange multipliers for the constraints (BwK-style).
- **Prior work.**
  - Online configuration search for stream learners exists: OAML (Celik et al. 2023), ChaCha (ICML 2021) and OMS-MAB (Wilson et al. 2024). None imposes **hard per-row latency/memory constraints**: OAML budgets only search time, and OMS-MAB trades compute softly.
  - Safe online tuning under hard constraints exists for databases (OnlineTune, SIGMOD 2022) and video analytics (Chameleon 2018), but not for drifting stream learners.
  - RCCDA handles a budget but has one binary action.
  - **What would be new:** safe, constrained, non-stationary configuration selection *over pipeline stages of a stream learner* with per-row latency and memory limits. This is literally the review's open question.
- **Why it ranks second.**
  1. **The arms carry state.** A Hoeffding tree trained on 8 features cannot simply switch to 32. Every arm needs its own trained model, otherwise switching costs a cold start. Keeping shadow models for all arms breaks the very budget being enforced. Workable approaches:
     - restrict θ to knobs that do not change model state (stride, preprocessing width given a fixed feature set, number of ARF members used at prediction time); or
     - train only the incumbent and one challenger (ChaCha-style).
  2. **Our data say the feasible set may contain no good arm.** Under the gateway budget, every cheap uniform configuration we tried lost detection. A bandit can only pick the best of the arms it has, so it would rediscover R3's bad trade-off more efficiently. The cascade *creates* a better arm.
  3. **Reward needs labels.** With 1k–10k delay, reward feedback is late, and κ-temporal per window is noisy.
- **Recommended use.** Make it the *outer* layer: a constrained bandit over a 3–6-arm set that **includes cascade variants** (different k for stage 1, ARF size for stage 2). Use it as a second contribution only if time allows. Alternatively, present Candidate 1's dual update as the solution to §6.3 for a **one-dimensional** θ (the escalation budget) and leave the full search as future work.
- **Implementation:** about 3–5 days, given the state problem. **Risk:** medium-high.

### Candidate 3: label-free, delay-robust drift trigger inside the resource controller

- **Idea.**
  - Replace or augment error-based ADWIN, which needs labels and therefore collapses with delay, with a label-free signal.
  - Options:
    - MD3-style margin density (the share of rows with stage-1 confidence below a threshold);
    - in a cascade, the **disagreement rate between stage 1 and stage 2 on escalated rows**. This costs nothing extra and needs no labels.
  - Feed it to R1/R2 and to cascade escalation.
- **Why new.**
  - Label-free detectors exist (Sethi & Kantardzic 2017; Lukats et al. 2024 benchmark them, including compute cost), and INSOMNIA reduces NIDS labelling.
  - Using **cascade disagreement as the drift signal under a compute budget** is, as far as I found, new. Its novelty depends on Candidate 1.
- **Expected benefit.**
  - It targets finding 4. Even if accuracy under delay stays low, earlier reaction should cut the flows missed in the first part of each attack period. That is measurable with the existing per-attack "flows before first flag" metric.
- **Implementation:** about 1–2 days on top of Candidate 1 (River's `ADWIN` on a 0/1 disagreement stream).
- **Risk:** false alarms on benign traffic shifts (MD3 reports fewer than feature-based detectors). Labels are still needed to *learn*, so this improves reaction, not learning.

### Candidate 4: cost-aware online feature ranking (gain per microsecond)

- **Idea.** Rank features by measured predictive gain divided by measured per-feature preprocessing cost, and drop the worst ratio first, instead of halving by gain alone.
- **Prior work.**
  - Budgeted acquisition on streams: Fainman et al. 2019; Beyer et al. 2020.
  - Offline cost-aware feature search for traffic: CATO 2025.
- **What would be new:** making it online and drift-aware. This is a modest delta.
- **Expected benefit.** Could soften R3's damage. But on CIC-IDS2017 the per-feature preprocessing cost is nearly uniform (a running scaler per input), so the ratio mostly reduces to gain. CATO's large gains came from features that differ a lot in extraction cost (packet-level), which our CSV flow features do not have.
- **Effort and risk:** about 1 day. **Risk:** low benefit. Better as an ablation inside Candidate 1's stage-1 feature choice.

### Candidate 5: Lyapunov drift-plus-penalty controller replacing the rule ladder

- **Idea.** Virtual queues for CPU-budget and memory-budget deficits, with each row choosing the action (none / reset / background replacement / retrain / narrow) that minimises the queue-weighted cost minus the expected accuracy gain.
- **Nearest work.** RCCDA (NeurIPS 2025), with a single binary action.
- **What would be new:** multiple actions and constraints in a stream pipeline.
- **Benefit.** It gives principled thresholds, but it is still limited by the bad frontier (see Candidate 2, reason 2).
- **Implementation:** 2–3 days.
- **Risk:** needs a model of each action's accuracy gain, which is hard to estimate online. Use RCCDA as related work, and reuse its virtual-queue idea for Candidate 1's τ update.

---

## 4. Recommendation

**Build Candidate 1, a budget-constrained online cascade with drift-aware deferral, and make its dual-variable threshold update the concrete answer to the review's §6.3 for a one-dimensional θ.**
- Add Candidate 3 (disagreement-based, label-free drift signal) as a cheap second ingredient, because it reuses the cascade.
- Keep the R1–R5 joint controller as the **baseline that the review proposed**, with its measured failure of R3 as motivation.
- Mention Candidate 2 (the full constrained bandit over θ) as the outer layer and as future work, with the state-carrying problem explained honestly.

First step before building: measure ARF `predict_one` and `learn_one` separately, and the stage-1 confidence distribution on rows where HT and ARF disagree. Both are one-day checks, and they decide whether the idea can work.

**Suggested title:**
*Spend the Budget Where It Matters: Drift-Aware, Budget-Constrained Cascades for Streaming Intrusion Detection on Edge Devices*
(Plainer alternative: *Budget-Constrained Adaptive Cascades for Streaming Network Intrusion Detection under Concept Drift*.)

**Contribution bullets (only if the experiments confirm them):**
1. **An empirical test of a joint drift-and-resource rule controller** (the review's R1–R5) on 2.1 M flows of chronologically replayed, corrected CIC-IDS2017. It shows that uniform feature reduction meets a per-row CPU budget but drops detection below a copy-the-last-label baseline (κ-temporal < 0). It also shows that preprocessing, not the model, dominates per-row cost in this stack.
2. **A budget-constrained online cascade for stream classifiers.** A cheap Hoeffding-tree stage handles every flow. An ARF stage handles only flows that are uncertain or that arrive after drift. A dual-variable threshold update holds the running per-row CPU cost at the budget, which is the first constrained solution we know of to the review's §6.3 objective in a drifting stream setting.
3. **A label-free drift signal from stage disagreement.** It costs nothing extra under the budget, and we evaluate how much it shortens attack-onset reaction under 1k–10k-row label delay.
4. **A reproducible evaluation protocol** that pairs stream-aware quality (κ-temporal, macro-F1, per-attack recall, block-bootstrap intervals, Friedman/Nemenyi) with stage-level cost terms (C_pre…C_ret) on simulated device tiers. On this stream, accuracy alone is matched by a 98.7 % persistence baseline.

How this maps to the review's seven gaps:
- Bullets 1 and 2 address **RA**, **LE** and **PI**.
- Bullet 1 addresses **SB**.
- Bullet 3 addresses **RA** under realistic labels.
- Bullet 4 addresses **UE** and **UR**.
- **HW** is only partly addressed, by simulated tiers, unless a Raspberry Pi run is added.

---

## 5. What I could not verify

- **Adewole et al., Electronics 11(19):3109, 2022.** It exists, but I could not open the full text (HTTP 403). A search snippet says a streaming NIDS study reported "kappa temp", but I could not confirm which paper, which dataset, or whether a persistence baseline was reported. Someone may already have shown persistence effects on a NIDS stream. Finding 2's novelty is therefore **medium, not high**.
- **ENIDrift (ACSAC 2022).** First author Xian Wang confirmed; co-authors not retrieved.
- **RCCDA.** I read the abstract only. Its four datasets are "domain generalization" sets; I did not confirm their names or whether any per-sample timing is reported.
- **Buschjäger et al. 2026.** Abstract-level only, and the paper is not yet peer reviewed. I did not confirm whether its benchmark includes drift detectors or latency budgets beyond "prediction-plus-update latency".
- **DFDT.** The AAAI 2026 publication comes from the AAAI OJS link in search results. I did not open it.
- **VHT.** The IEEE BigData 2016 venue comes from the authors' slide title. The proceedings page was not retrieved.
- **Online Cascade Learning.** I took "no drift detector, cost via hyperparameters" from the abstract and summaries. The full paper may contain a budget-tracking mechanism that I did not see.
- **Search coverage.** I found no paper combining *stream-classifier cascades + hard per-row compute budget + drift*. Absence in my searches is not proof of absence. A targeted check on Google Scholar and DBLP ("cascade" AND "data stream" AND "budget"; "anytime" AND "Hoeffding") is advised before submission.
- **Our own finding 3 (preprocessing dominates)** may be partly specific to the Python/River implementation. It has not been checked against a compiled implementation.
- **Energy on Apple Silicon.** Any figure would be whole-package power via `sudo powermetrics`, not per-process. I did not test it on this machine.
