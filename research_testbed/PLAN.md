# Research Testbed — Application Plan

**Status:** proposal for team review, 11 November 2026. Nothing here is built yet. Every number in this file is either quoted from a saved run in `docs/` or marked as an estimate.

**Working title for the study:** *Resource-Aware Adaptive Learning for Real-Time Intrusion Detection at the Network Edge: an empirical test of the review's decision rules*

---

## 1. Why a second application

AdaptiveML Studio already proves the basic story: data changes, accuracy falls, ADWIN detects it, the model adapts, and the cost is measured in the same run. That covers gaps **G1–G3** well.

The review paper (§VI and the decision rules R1–R5 in §6.2) proposes more than that. It proposes an adaptation process that reacts to **drift and resources at the same time**. `docs/paper_alignment.md` records that this part is still missing:

| Paper rule | What it says | Status in the Studio |
|---|---|---|
| R1 | Drift + enough resources → incremental adaptation | Partial: resource check missing |
| R2 | Drift + tight CPU/memory → *lightweight* adaptation | **Missing** |
| R3 | Latency over budget → simpler preprocessing / fewer features / simpler model | Partial: only feature halving |
| R4 | Low accuracy + spare resources → stronger retraining | Partial: resource check missing |
| R5 | Memory over limit → shrink model/buffers | **Missing** |

The saved results also show four weaknesses that a reviewer would raise:

1. **The drift is artificial.** On ELEC2 and Occupancy we create drift by swapping two columns. Real data has no labelled drift points.
2. **One seed, no error bars** (`real_data_drift_results.md`, caveat 5).
3. **Labels arrive instantly.** In real systems the true label comes late or never (decision #13 in `architecture.md` §14).
4. **High accuracy is partly label persistence.** 85.3 % of ELEC2 rows have the same label as the row before, so a "repeat the last label" baseline is needed to show that learning adds anything.

So the new application has one job: **test the paper's full R1–R5 proposal on a large real problem with real drift, at several device sizes, with a protocol a reviewer can trust.** The Studio stays as the demo and teaching tool. The testbed produces the paper's evidence.

## 2. The real use case: intrusion detection on edge gateways

**Recommendation:** network intrusion detection (NIDS) running on edge devices such as home routers, IoT gateways and small-office firewalls.

Why this case fits the paper better than any other:

- **It matches the venue.** The review was submitted to the International Conference on AI Based Cyber Resilience. A cyber-security use case speaks directly to that audience.
- **The drift is real and dated.** Attackers change tactics, new attack types appear, and normal traffic changes by hour and weekday. Public datasets record *when* each attack happened, so we get real drift points without inventing them. This fixes weakness 1.
- **It is large.** Public NIDS datasets hold millions of network flows (estimate: 2–3 million for CIC-IDS2017; to be checked on download). That is 50–100× the size of ELEC2.
- **Latency matters for real.** A gateway that takes too long per flow drops packets or lets attacks through, so the per-row deadline (R3) has a physical meaning.
- **Resources are really limited.** Gateways have little RAM and weak CPUs, which is what R2 and R5 are for (G4, G5).
- **Labels come late.** An analyst confirms an alert hours later, if ever. That gives a natural reason to study delayed and partial labels (weakness 3).

**Candidate datasets** (the research member decides; licence and row counts must be checked on download):

| Dataset | Why | Known caveat |
|---|---|---|
| CIC-IDS2017 (Canadian Institute for Cybersecurity) | 5 working days, a different attack family each day, so drift points are known by timestamp | Original labels have known errors; a corrected re-labelling has been published (Engelen et al., 2021) and should be preferred |
| UNSW-NB15 | Widely cited, different network and attack mix | Train/test split is not chronological in the common release |
| An IoT set (e.g. CIC-IoT2023 or Kitsune) | Traffic from real IoT devices, matching the edge story | Size and format differ; check feasibility |

Plan to use **one main dataset (CIC-IDS2017, corrected labels)** and **one second dataset** to show the results are not a one-dataset effect. Keep ELEC2 and Occupancy as small sanity checks, since the Studio already has results for them.

> If the team prefers a different domain (smart buildings, energy, fraud), the application design below stays the same. Only the dataset adapter and the story change.

## 3. Research questions

Each question names the gap it answers and what would count as an answer.

- **RQ1 — Joint control (G5).** Does a controller that follows all five rules (R1–R5, with resource checks) keep accuracy as stable as drift-only adaptation, at lower latency and memory? *Answered by:* accuracy-stability and cost metrics for each policy across seeds, with confidence intervals and a significance test.
- **RQ2 — Cross scale (G4, title).** How does the accuracy–cost trade-off change across **device scale** (three simulated tiers, optionally one real Raspberry Pi) and **stream scale** (flows per second, from normal to attack-burst rates)? *Answered by:* trade-off curves (Pareto fronts) per tier and rate.
- **RQ3 — Realistic labels.** When labels are delayed or only partly available, how many false adaptations, missed drifts and how much extra cost do the policies produce? *Answered by:* the same metrics under label delays of 0, 1k, 10k rows and 10 % / 50 % label coverage.
- **RQ4 — Unified evaluation (G6).** Can a fixed, published protocol (seeds, baselines, statistics, environment record) make these comparisons repeatable? *Answered by:* the released protocol plus a re-run check on a second machine.

The platform still only measures. The research member answers the questions.

## 4. What the application does

```
DATASET ADAPTER ─► STREAM SCHEDULER ─► EDGE NODE (one process per device tier)
 (large CSV/Parquet,   (rate, bursts,        preprocess ─► select ─► predict ─► detect ─► CONTROLLER v2 ─► learn
  real timestamps)      label delay/coverage)                                       (R1–R5, reads drift + CPU + memory + latency)
                                                    │
                                                    ▼
                                    RESULT BUNDLE (per-row records, events, costs, environment)
                                                    │
                                                    ▼
                         ANALYSIS & REPORT (seeds → CIs → significance tests → paper tables and figures)
```

**It reuses the Studio's engine** (`backend/adaptiveml`): preprocessing, feature selection, ADWIN, the models, the result bundles and the reproducibility checks. Only the parts below are new.

### 4.1 New pieces

| # | Component | What it does | Gap |
|---|---|---|---|
| 1 | **Large dataset adapter** | Streams millions of rows from disk in chunks (no full load into 8 GB RAM), keeps real timestamps and attack labels, records SHA-256 like the Studio does, and stores the known drift points from the dataset's schedule | G6 |
| 2 | **Controller v2 (full R1–R5)** | Every decision reads four signals together: drift alarm, rolling accuracy, per-row latency, CPU and memory headroom. Adds the missing R2 (cheap adaptation under pressure) and R5 (shrink model/buffers when memory is over budget). Resource limits win over accuracy, as the paper says. Each rule can be switched off for ablations | G5 |
| 3 | **Device tiers** | Three profiles (example names: *micro* ≈ IoT gateway, *small* ≈ Raspberry Pi class, *standard* ≈ laptop) with memory, latency and update budgets. Enforced in software and labelled **simulated**. Optional real run on a Raspberry Pi if the team can get one | G4 |
| 4 | **Stream scheduler** | Replays at a set rate or with attack-time bursts; adds **label delay** and **label coverage** settings | RQ2, RQ3 |
| 5 | **Fleet runner** | Runs many edge nodes in parallel (one process each, different tiers or seeds) and collects their bundles | RQ2 |
| 6 | **Full cost breakdown** | Reports every term of the paper's `C_total = C_pre + C_fs + C_drift + C_inf + C_upd + C_ret (+ C_comm)` separately; the current harness merges some of them | G2, G3 |
| 7 | **Evaluation protocol** | Fixed seed list, repeated runs, 95 % confidence intervals, Friedman + Nemenyi tests across datasets and tiers (the usual method for comparing many classifiers), and a "repeat the last label" baseline with kappa-temporal | G6 |
| 8 | **Paper report generator** | Turns saved bundles into the paper's tables and figures (PNG + SVG + CSV) with the run IDs printed underneath, so every figure can be traced back to its runs | G6 |
| 9 | **Testbed screen** in the Studio | One new page: choose dataset, tier, rate, label delay; watch several edge nodes side by side; open the generated report. Kept small: the paper is the main output | demo |

### 4.2 Methods compared

All methods use the same preprocessing, features, seeds and stream.

| Method | Role |
|---|---|
| No-change ("repeat last label") | Checks how much is just label persistence |
| Static (train once) | Shows the drift damage |
| Incremental Hoeffding tree, no detection | Learning without detection |
| Drift-only (ADWIN + reset) | The Studio's current adaptive pipeline |
| Adaptive Random Forest [20] | Strong method from the literature, expensive |
| One more River ensemble (e.g. Streaming Random Patches or Leveraging Bagging) | Second literature comparator; Review member to confirm a citation |
| **Controller v2 (R1–R5)** | The paper's proposal under test |
| Controller v2 ablations: without resource checks, without R2, without R5, without feature reduction | Shows which part actually helps |

### 4.3 Metrics

- **Accuracy side:** accuracy, macro-F1 and per-attack recall (attacks are rare, so plain accuracy can mislead), kappa and kappa-temporal, drop depth, recovery time and detection delay against the dataset's real drift points, false and missed alarms.
- **Cost side:** per-stage latency (p50/p95/p99), deadline misses, CPU time per row, peak memory, model size, adaptation count and cost.
- **Controller side:** how often each rule fired, and the accuracy and cost just before and after each firing.
- **Not measured:** energy. It stays a stated limitation unless real hardware with a power meter becomes available.

## 5. Experiment matrix and compute estimate

| Factor | Levels |
|---|---|
| Dataset | CIC-IDS2017 (main), second NIDS set, ELEC2 + Occupancy (sanity) |
| Method | 7 methods + 4 ablations |
| Device tier | micro, small, standard (+ real Pi if available) |
| Stream rate | as recorded; 2×; attack bursts |
| Label setting | immediate; delayed (1k, 10k rows); 10 % / 50 % coverage |
| Seeds | 10 |

The full grid is too big, so the team runs it in layers. All timings below are **estimates** extrapolated from the saved Studio timings (about 35 µs/row for the adaptive pipeline, about 430 µs/row for ARF on ELEC2):

- **Core grid:** main dataset × all methods × 3 tiers × immediate labels × 10 seeds. ARF alone ≈ 2.8 M rows × 0.43 ms ≈ 20 min per run, so the whole core grid fits in a few nights on one machine, with runs in parallel.
- **Label study:** controller v2 and drift-only only, on all label settings.
- **Rate study:** controller v2 and drift-only only, on all rates.
- **Second dataset:** the core grid again, with 5 seeds.

## 6. What the paper can show (figures and tables)

1. Accuracy over time on CIC-IDS2017 with the real attack days marked, for every method (shows real drift and recovery).
2. Accuracy-vs-cost Pareto fronts per device tier (the main "cross scale" figure).
3. Ablation table: what each rule of controller v2 adds or costs, with confidence intervals.
4. Label-delay curves: false adaptations and accuracy as labels arrive later.
5. Cost breakdown stacked bars (`C_pre … C_ret`) per method and tier.
6. Critical-difference diagram from the Friedman/Nemenyi test across datasets and tiers.
7. A table of rule firings: what the controller did and when.

These turn the review's §VI proposal into a tested result. Whatever the outcome, positive or negative, it is publishable as an empirical study, because the review explicitly says its rules are untested.

## 7. Build phases

| Phase | Builds | Done when |
|---|---|---|
| **1. Data** | Dataset adapter for CIC-IDS2017 (corrected labels), drift schedule, checksum catalog | Full dataset streams through the existing pipeline on 8 GB RAM without loading it all; drift points listed |
| **2. Baselines** | No-change baseline, kappa-temporal, macro-F1, per-class recall, second River ensemble | Core methods run end-to-end on the main dataset with one seed |
| **3. Controller v2** | R1–R5 with resource checks, ablation switches, full cost breakdown | Unit tests show each rule fires on a crafted case; every cost term is reported |
| **4. Scale** | Device tiers, stream scheduler, label delay/coverage, fleet runner | Three tiers run in parallel; label delay is checked by tests |
| **5. Protocol & report** | Seed list, CIs, statistical tests, report generator | One command turns bundles into all paper figures; re-run gives identical predictions |
| **6. Screen** | Testbed page in the Studio | A run can be started and watched from the browser |
| **7. Real device (optional)** | Raspberry Pi run | Same bundle format from the device |

Phases 1–3 are the minimum for a paper. Phases 4–5 make it strong. 6–7 are for the demo and for G4.

## 8. Decisions the team needs to make

| # | Decision | Owner | Proposed default |
|---|---|---|---|
| 1 | Use case: network intrusion detection? | Team | Yes |
| 2 | Main and second dataset | Research | CIC-IDS2017 (corrected labels) + one IoT or UNSW-NB15 set |
| 3 | Device tier budget values | Research | Placeholders, labelled simulated |
| 4 | Second literature comparator | Review | Streaming Random Patches or Leveraging Bagging |
| 5 | Accuracy-stability formula | Research | Drop depth + recovery time + variance, as reference computations |
| 6 | Is a Raspberry Pi available? | Team | No; simulation only |
| 7 | Binary (attack / benign) or multi-class | Research | Binary first, multi-class as an extension |

## 9. What we will not claim

- A new learning algorithm. We test the review's own proposal.
- Real edge-hardware results, unless a real device is used.
- Energy figures.
- That the system is ready for real network deployment.
- That one dataset proves a general rule.
