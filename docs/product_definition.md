# Stage 2 — Product Definition: AdaptiveML Studio

**Adaptive ML Experimentation and Monitoring Platform** — *Real-Time Monitoring and Adaptation for Evolving Data Streams*

> **Status:** This is a proposal from the Implementation workstream (Utsav), for team review.
> - Items marked **[Team]** need a decision from the research or review member, or the whole team.
> - **Every number in this document is a placeholder that shows the format only.** None of them is a result.

**Inputs fixed for this stage** (from Utsav, 2026-09-11):
- **Cross Scale** (provisional and configurable) means the same pipeline evaluated across two scales:
  - *stream scale*: stream rate and stream volume
  - *resource scale*: a Standard profile and a Simulated Edge-Constrained profile
- **Accuracy stability** is represented only through measured quantities. It has no formula yet.
- The final paper and its graphs are not available. The platform generates **only its own measurements**.
- No edge hardware is confirmed, so the product has a **Standard** profile and a **Simulated Edge-Constrained** profile.

---

## 1. Product vision

AdaptiveML Studio lets the team **configure, execute, observe and reproduce** experiments where an adaptive ML pipeline processes an evolving data stream. For every run it records four things:
- what the pipeline predicted
- when drift was detected
- how the pipeline adapted
- what each of those steps cost in time and resources

It is the working form of the paper's §VI direction:
- **G1:** one integrated pipeline.
- **G2, G3:** accuracy is always reported next to latency and resource cost.
- **G5:** adaptation reads both the drift signal and the resource state.
- **G6:** one reproducible evaluation protocol.
- **G4 (partial only):** edge constraints are simulated and labelled as simulated.

```
CONFIGURE → STREAM → DETECT → ADAPT → MEASURE → COMPARE → EXPORT
```

The dashboard is the interface layer. The product is the experimental system underneath it.

## 2. Positioning

| AdaptiveML Studio **is** | It is **not** |
|---|---|
| A research testbed for this team's experiments | A production MLOps or monitoring product |
| An integration of established, cited techniques (e.g. ADWIN [5] on River [10]) | A new ML algorithm or drift detector |
| An instrument that measures and records | A system that draws conclusions ("adaptive is better") |
| Local, file-based and reproducible | Cloud, distributed or multi-user |
| Standard and **simulated** edge profiles | A source of edge-hardware results (unless hardware is used later and labelled) |

> *For a student research team studying adaptive ML on evolving streams, AdaptiveML Studio is an experimentation platform. It runs a complete adaptive pipeline and records its predictive performance together with its latency and resource cost, so the accuracy–cost trade-off can be observed, reproduced and compared under one protocol.*

## 3. Users / personas

| Persona | Context | Needs | Success = |
|---|---|---|---|
| **P1 Evaluation panel member** | Non-specialist; has a 3–5 min window; sees it on a projector | One clear causal story, plain-language explanations, visible cost | Can explain drift → detection → adaptation → cost after the demo |
| **P2 Research / Experimentation member** | Designs protocol, runs many trials, analyses in notebooks | Every variable configurable; identical reruns; raw exports; no hidden defaults | Can run a full comparison without touching code and get CSV/JSON out |
| **P3 Review / Literature member** | Owns the paper and its references | See which technique implements which reference and gap; check the wording of claims | Can sign off the traceability matrix |
| **P4 Implementation member (Utsav)** | Builds and operates the platform; presents the live section | Per-stage timings, errors and profiling; demo reliability | Demo runs reliably; bottlenecks are visible |
| P5 Supervisor | Checks progress and alignment with the paper | Served by the P1 and P3 features | — |

## 4. Team-to-product responsibility mapping

| Product area | Implementation (Utsav) | Research / Experimentation | Review / Literature |
|---|---|---|---|
| Pipeline engine (preprocess, feature selection, detection, learning, adaptation) | **Builds** | Sets experiment parameters | Verifies the techniques match the cited references |
| Streams and scenarios | **Builds** the generator and dataset loaders | **Chooses** datasets and drift parameters | Checks the drift types match the literature (abrupt, gradual, recurring [7]) |
| Method presets / comparators | **Builds** a pluggable interface and presets | **Selects** comparators | Confirms the comparators are literature-cited |
| Resource profiles | **Builds** enforcement and labelling | **Sets** budget values | Checks alignment with [12], [14], [15] |
| Measurement and logging | **Builds** raw measurement and logs | **Defines** derived metrics; analyses | Checks the metric set matches §VI |
| Experiment runner and result bundles | **Builds** | **Runs**, exports, analyses | — |
| Method page (traceability, glossary) | Builds the page | Reviews the measurement definitions | **Authors / verifies** traceability content |
| Research conclusions | — | **Authors** | Checks against the literature |
| Panel demo | Presents the live section | Presents the results section | Presents the problem and gap section |

## 5. Core user journeys

| # | Journey | Who | Steps | Output |
|---|---|---|---|---|
| J1 | **Observe a live run** | Panel, anyone | Live → pick scenario → Start → watch; optionally *Inject drift* | Live view, plus a saved run bundle (type `live`) |
| J2 | **Controlled comparison** | Research | Experiments → New → preset → choose methods × profiles → Run → open result | Comparison table, charts, bundle |
| J3 | **Cross-scale sweep** | Research | CLI with a config listing rates × volumes × profiles × seeds | One bundle per trial, plus an index CSV |
| J4 | **Reproduce a run** | Research, supervisor | History → open run → *Re-run* → reproducibility check | New bundle, "predictions identical ✓/✗" |
| J5 | **Verify literature alignment** | Review | Method page → traceability table; Live → click a pipeline stage → reference and gap | Signed-off traceability matrix |
| J6 | **Profile and optimise** | Implementation | Benchmark CLI; per-stage cost panel | Before/after timing tables (feeds performance.md) |

## 6. Main panel demo journey

The whole story happens on **one screen (Live)** and **one timeline (sample index)**. The causal chain is never split across pages.

| Story beat | Pipeline state | What the panel sees | Provenance |
|---|---|---|---|
| 1 Start stream | RUNNING · STABLE | Pipeline strip turns active; two accuracy lines (adaptive, static) rise and settle together | Measured |
| 2 Stable operation | STABLE | KPIs steady; per-sample latency flat | Measured |
| 3 Drift occurs | STABLE (true drift not yet detected) | "True drift" marker on the timeline; the **data snapshot** shows the class boundary / distribution change | Scheduled (synthetic ground truth) |
| 4 Performance changes | STABLE | Both accuracy lines drop | Measured |
| 5 Drift detected | DRIFT DETECTED | "Detected" marker; detection delay in samples; ADWIN window visibly shrinks | Measured |
| 6 Adaptation triggered | ADAPTING | Decision card shows the action and its reason; model v1 → v2 | Measured |
| 7 Model recovers / changes | MONITORING RECOVERY | Adaptive line vs static line after adaptation; episode card fills in before/after numbers | Measured |
| 8 Measure cost | — | Update-time spike in the cost panel; adaptation duration; per-stage overhead | Measured (local machine) |
| 9 Compare methods | — | Experiments → recorded comparison: methods × profiles, accuracy–cost chart | Recorded run, labelled with ID and date |

## 7. Information architecture

**Three screens**, plus a guided demo overlay and a detail drawer.

```
AdaptiveML Studio
├── Live           ← panel story; live monitoring; Demo Mode
│   ├── Stage drawer  (per pipeline stage: settings, timing, reference, gap)
│   └── Demo Mode overlay (narration driven by real events)
├── Experiments    ← configure, run, history, compare, export
│   ├── List / history
│   ├── New experiment (presets · MVP fields · Advanced · config view)
│   └── Experiment detail (results · comparison · reproducibility · export)
└── Method         ← concepts, pipeline ↔ literature traceability, measurement definitions
```

**Where each candidate screen went, and why**

| Candidate screen | Where it lives | Why merged |
|---|---|---|
| A Experiment / Control Center | Quick controls on **Live**; full config on **Experiments** | Live needs 5 controls; research needs 20 |
| B Live Stream & Pipeline | **Live** | — |
| C Drift & Adaptation | **Live** (same timeline) | The causal story breaks if drift and performance are on different pages |
| D Performance / Comparison | **Experiments → detail** | Comparison is about completed runs |
| E Resource / Edge Profile | Budgets and resources on **Live**; cross-profile comparison in **Experiments** | A profile is a run parameter, not a destination |
| F Experiment History | **Experiments → list** | History *is* the experiment list |
| *(new)* Method | **Method** | Answers "what is drift / how is it measured"; hosts traceability for the review member |

**Panel questions and where they are answered**

| Question | Answered by |
|---|---|
| What is the problem? | Live header line and Method page opening |
| What is concept drift? | InfoTip, the data snapshot (before vs now), Method glossary |
| What does the system do? | Pipeline strip (7 stages), Method page |
| When does adaptation happen? | Markers on the hero chart, pipeline state strip, event log |
| What changes after adaptation? | Episode card (before/after), model version, adaptive vs static lines |
| What does adaptation cost? | Cost panel spike, adaptation duration, per-stage overhead |
| How are accuracy and latency evaluated? | Method → Measurement section; InfoTips on every KPI |
| How does resource availability affect it? | Profile toggle, decision card, cross-profile comparison |
| How can experiments be reproduced? | Reproducibility card (seed, config hash, dataset checksum, environment), Re-run check, export |

## 8. Screen-by-screen specification

### 8.1 Live

**Purpose:** watch one run unfold. This is the panel story and the operator view. **Primary users:** P1, P4.

```
┌ AdaptiveML Studio   [Live]  Experiments  Method            ● Connected   ▣ Standard profile ┐
├ Scenario [Synthetic · abrupt ▾]  Rate [100/s ▾]  Seed 42  Profile [Standard|Edge (sim)]   │
│ [▶ Start] [⏸] [■ Stop]  [⚡ Inject drift]  [🎬 Demo mode]           sample 3,412 / 12,000  │
├ STATE ● STABLE     Stable ─ Drift detected ─ Adapting ─ Monitoring recovery                  │
├ PIPELINE  Stream → Preprocess → Feature sel. → Drift detect → Adaptation → Predict → Monitor │
│           (each: status dot · µs/sample · one-line detail, click → drawer)                   │
├ MODEL HEALTH  Acc · F1 · P/R │ STREAM HEALTH  processed · rate · drift signal │ SYSTEM HEALTH  p95 latency · update time · CPU · RSS │
├──────────────────────────────────────────────────────┬───────────────────────────────────────┤
│ HERO  Windowed accuracy (or F1) vs sample index       │ DECISION CARD  resource state +       │
│  adaptive ━━  static ╌╌   │true drift  ▼detected       │   current adaptation decision         │
│  ▲adaptation   phase bands                            │ EPISODE CARD  last drift→adapt episode│
├──────────────┬──────────────────┬────────────────────┤   (factual before/after numbers)      │
│ DATA SNAPSHOT│ DRIFT SIGNAL     │ COST PER SAMPLE    │ EVENT LOG  (drift, adaptation,         │
│ before vs now│ ADWIN window/err │ stacked by stage   │   budget, errors; newest first)        │
└──────────────┴──────────────────┴────────────────────┴───────────────────────────────────────┘
```

**Regions**
- **Control bar**
  - *MVP controls only* (see §11).
  - The seed is always visible.
  - *Inject drift* schedules drift at the next sample and records that sample in the run config.
- **Phase strip**
  - Shows the pipeline state (§14) as a labelled step indicator, not colour alone.
- **Pipeline strip**
  - Seven stages, following the activity-diagram order.
  - A return arrow from Monitor to Drift detect shows the test-then-train loop.
  - Each stage shows a status dot, its mean µs/sample, and a detail line, e.g. "7/10 features selected", "ADWIN window 1,204", "Model v2 since sample 5,142".
- **KPI strip**
  - Groups metrics into Model, Stream and System health.
  - Each value shows its unit and an InfoTip.
- **Hero chart**
  - Always shows the static baseline alongside the adaptive pipeline.
  - Both run on the **same samples** in live mode.
- **Data snapshot**
  - Synthetic data: a 2-feature scatter of the reference window vs the current window, coloured by label.
  - Real data: per-feature mean/variance shift bars.
  - Sampled to ≤300 points and refreshed at 1 Hz.
- **Drift signal**
  - Shows a detector-specific signal: ADWIN window width and estimated error.
  - Also shows the input-distribution monitor, if implemented.
  - It is labelled "detector signal". It is not called a universal "drift score".
- **Cost per sample**
  - Stacked area of time by stage per window.
  - Adaptation actions appear as spikes marked with ▲.
- **Decision card**
  - Resource state: CPU, RSS, p95 latency vs budget.
  - Current decision, e.g. *✓ Continue current model · ✓ Incremental update · ⚠ Reduce feature count (reason)*.
- **Episode card**
  - One card per drift → adaptation episode.
  - Contents: accuracy/F1 before drift, lowest after drift, after adaptation, detection delay, adaptation duration, recovery (reference criterion).
  - Labelled "Stability measures — definitions pending team decision".
- **Event log**
  - Factual, timestamped entries in sample index and wall-clock time; filterable.
- **Stage drawer**
  - Opens from a pipeline stage.
  - Shows the stage's settings, timing distribution (p50/p95), live detail (e.g. selected/dropped features with weights), the paper reference and gap, and InfoTips.

**Cadence:** aggregates reach the UI at a fixed rate (default 4 Hz). Raw samples are never streamed to the UI.

**Demo Mode overlay**
- Locks a preset config (scenario, seed, rate, drift position).
- Shows a narration banner ("Step 3/7 — Drift injected at sample 4,000").
- The banner **advances on real events, not timers**. For example, "Drift detected" appears only when the detector fires.
- Space bar pauses or resumes.
- At the end it shows a factual summary card, with a link to the recorded run in Experiments.

### 8.2 Experiments

**Purpose:** configure, execute, store, compare and export runs. **Primary user:** P2.

**List / history**
- Table columns: ID, name, date, scenario (real/synthetic tag), methods, profiles, status, headline metrics.
- Filter by scenario and status.
- Empty state: "No experiments yet — start from a preset".

**New experiment**
- Choose a preset, then fill in the MVP fields.
- An *Advanced* section is collapsed by default.
- *View config* shows the exact file the CLI would use, and can be copied.
- Validation happens inline before Run.
- While running: a progress bar per trial and a Cancel button.

**Experiment detail**
```
Run 0007 · "Abrupt drift — methods × profiles" · completed · seed 42 · config a1b2c3 · SYNTHETIC  [Re-run] [Export ▾]
┌ Summary table: rows = method × profile; columns = Acc, F1, (P/R), stability measures (pre/post/after, delay, recovery),
│                p50/p95 prediction latency, mean update time, adaptation time, throughput, CPU time/sample, peak RSS
├ Accuracy over time (overlay)            ┬ Accuracy vs cost (trade-off scatter)
├ Segment bars (pre / post-drift / post-adaptation) ┬ Cost breakdown by stage
├ Events (drift, adaptation, budget)       ┬ Reproducibility card (config, dataset + checksum, env, versions)
```
- All tables state their units.
- A note under the table reads: "Values are measurements from this run; interpretation is by the research team."

### 8.3 Method

**Purpose:** make the research visible and checkable. **Primary users:** P1, P3, P5. The page has four parts:

1. **Problem, in one paragraph**, plus the pipeline diagram.
2. **Traceability matrix**: pipeline component ↔ technique ↔ paper reference ↔ gap ↔ *verified by review member ✓/pending*.
   - The content lives in one file that the review member edits, and the page renders it.

   | Component | Technique (proposed; finalised in Stage 3) | References | Gap |
   |---|---|---|---|
   | Adaptive preprocessing | Incremental normalisation, missing-value handling | [3], [17], [19] | G1 |
   | Online feature selection | Lightweight online selection (e.g. the truncation approach of [4]) | [4], [16] | G1, G2 |
   | Concept drift detection | ADWIN | [5] | G1, G3 |
   | Incremental learning | Online learner (River) | [10], [18] | G1 |
   | Model adaptation | Drift-triggered update / replace / bounded retrain | §VI options | G1, G2 |
   | Resource-aware adaptation | Budget-driven policy under the simulated edge profile | [12], [14], [15]; §VI | G4 (partial), G5 |
   | Monitoring | Per-stage timing, CPU, memory | §VI metrics | G2, G3 |
   | Unified evaluation | Config + seed + result bundle | Table III | G6 |

3. **Measurement definitions**: how each metric is measured, including what latency does and does not include (§15).
4. **Glossary**: the same text as the InfoTips. Examples:
   - *Concept drift:* A change in the stream's data distribution or in the input–label relationship that is large enough to affect model behaviour.
   - *Prequential evaluation:* Each sample first tests the model and then, once its label is known, trains it.
   - *ADWIN [5]:* Keeps a variable-size window of recent errors and drops the older part when it differs significantly from the newer part.
   - *Static baseline:* Trained once on the first N samples, then frozen. This is the "train once" pipeline the paper contrasts with.
   - *Prediction latency:* Time for the model to produce one prediction. Excludes network and display.
   - *Simulated edge profile:* Budgets enforced in software on this machine. Not a hardware measurement.

### 8.4 Global elements

- **Top bar** contains:
  - the product name
  - three tabs
  - connection status: Connected / Reconnecting / Offline
  - the active-profile badge
- **Provenance tags** appear wherever numbers are shown:
  - `MEASURED · <machine>`
  - `SIMULATED EDGE CONSTRAINT`
  - `SYNTHETIC DATA` / `REAL DATA`
  - `RECORDED RUN <id>`
  - `REPLAY`

## 9. UI components

| Component | Purpose |
|---|---|
| RunControlBar | Scenario, rate, seed, profile, start/pause/stop, inject drift, demo |
| ProfileToggle + ProvenanceTag | Standard vs Simulated Edge; honest labelling of every number |
| StateStrip | Pipeline state as a step indicator (text, icon and colour) |
| PipelineStrip + StageDrawer | Seven stages with status, timing and reference |
| KpiGroup / KpiTile | Value, unit, InfoTip, small trend |
| TimelineChart | Hero chart: samples on the x-axis, method series, event markers, phase bands, synced crosshair |
| SyncedMiniChart | Drift signal, cost per sample |
| DataSnapshot | Before-vs-now distribution view |
| DecisionCard | Resource state vs budgets, plus the current adaptation decision and reason |
| EpisodeCard | Factual before/after numbers for one drift episode |
| EventLog | Filterable factual event stream |
| ConfigForm | Presets, MVP fields, Advanced, config view |
| RunTable / ComparisonTable | History; methods × profiles results |
| TradeoffScatter, SegmentBars, CostBreakdown | Comparison charts |
| ReproducibilityCard | Seed, config hash, dataset checksum, environment, re-run check |
| InfoTip | One-sentence concept explanations (≤25 words) |
| DemoNarration | Step banner driven by events; end summary |
| StatusBanner | Loading, error, disconnected, adaptation-failed messages |

**Design language**
- It should feel like an *instrument panel / lab notebook*, not a marketing dashboard.
- Neutral surfaces, with one colour per meaning:
  - adaptive = one hue
  - static = grey, dashed
  - drift = amber
  - adaptation = violet
  - error = red
- Colour is never the only signal. Every state also has a pattern, icon or text.
- Numbers use tabular figures.
- Contrast and minimum type sizes must be safe on a projector.
- The sample index is the organising axis everywhere.
- No decorative charts, no gradients, no gratuitous animation. Transitions are used only to show state changes.
- Light and dark themes; the default will be picked in Stage 3 for projector legibility.

## 10. Charts and what each one measures

Rules that apply to all charts:
- The **x-axis is the sample index**, not wall-clock time. This keeps runs comparable across stream rates.
- All live charts share one crosshair.
- Series are decimated to a bounded number of points.
- Every axis has a unit.

| ID | Chart | Screen | Measures | Marks |
|---|---|---|---|---|
| C1 | **Windowed accuracy / F1 over time** (hero) | Live, Experiment detail | Prequential accuracy or F1 over a sliding window of W samples, per method | True-drift line (synthetic only), detected ▼, adaptation ▲, phase bands |
| C2 | Drift signal | Live | Detector-specific: ADWIN window width and estimated error rate | Detection points |
| C3 | Cost per sample by stage | Live | Mean time per sample per window, stacked: preprocess, feature selection, predict, detect, update, adaptation | Adaptation spikes |
| C4 | Resource sparkline | Live (decision card) | Process CPU %, RSS (MB), model size (where the library supports it) | Budget line (edge profile) |
| C5 | Data snapshot | Live | Reference-window vs current-window distribution | — |
| C6 | **Accuracy vs cost trade-off** | Experiment detail | One point per method × profile (× rate). x = CPU time or processing time per sample; y = accuracy or F1 | Standard ↔ Edge points joined |
| C7 | Segment bars | Experiment detail | Accuracy/F1 per segment: pre-drift, post-drift before detection, post-adaptation | — |
| C8 | Cost breakdown | Experiment detail | Mean per-stage time per sample, per method | — |
| C9 | Cross-scale lines (SHOULD) | Experiment detail (sweeps) | A chosen metric vs stream rate or volume, one line per profile | — |

Live mode has at most **one hero chart and three small charts**. Everything else is in Experiments.

## 11. Experiment configuration

- There is **one config schema** used by both the UI and the CLI. The UI writes the same file the CLI reads.
- The **resolved config** (all defaults filled in) is saved with every run.
- Named **presets** cover the common cases:
  - Demo · abrupt drift
  - Gradual drift
  - No-drift control
  - Real dataset
  - Cross-scale sweep (CLI)

| Dimension | Tier | Proposed default | Decided by |
|---|---|---|---|
| Scenario / dataset | **MVP** | Synthetic, abrupt | Research [Team] |
| Stream rate (samples/s, or *max speed*) | **MVP** | 100/s live; max speed in experiments | Research |
| Stream volume (samples) | **MVP** (Experiments), Advanced (Live) | 12,000 | Research |
| Drift type: none / abrupt / gradual | **MVP** | abrupt | Research |
| Drift position (sample index) | Advanced | middle of stream | Research |
| Drift intensity (magnitude of change) | Advanced | medium | Research |
| Drift width (gradual only) | Advanced | — | Research |
| Methods to compare | **MVP** (Experiments) | static + adaptive | Research + Review [Team] |
| Resource profile(s) | **MVP** | Standard | Research |
| Random seed | **MVP** (always visible) | 42 | Research |
| Model (learner) | Advanced | set in Stage 3 | Implementation, justified by references |
| Drift detector + sensitivity | Advanced | ADWIN, library default δ | Implementation; Research may vary |
| Metric window W | Advanced | 500 | Research |
| Feature budget k | Advanced (set by profile) | all features (Standard) | Research |
| Warm-up length (static baseline training) | Advanced | e.g. 1,000 | Research [Team] |
| Edge budgets (latency, memory, features, update stride) | CLI / config only (shown read-only in UI) | TBD | Research [Team] |
| Adaptation policy thresholds | CLI / config only | Stage 3 | Implementation; Research may vary |
| Stability reference parameters (e.g. recovery tolerance) | CLI / config only | e.g. within 2% of pre-drift | Research [Team] |
| Segment anchoring (drift-anchored / detection-anchored) | CLI / config only | drift-anchored | Research [Team] |
| Repetitions (seed list), sweeps (rate × volume × profile grid) | CLI / config only | — | Research |
| Label delay | CLI / config only (OPTIONAL) | 0 (immediate labels) | Research |
| Output detail (e.g. per-sample outcomes) | CLI / config only | on | Research |

**Cross Scale is configuration, not product structure.** A `scale` block names the stream scales (rates, volumes) and resource scales (profiles) to sweep. If the team redefines Cross Scale, only the preset changes.

**What varies with stream scale (by design):**
- Drift happens at a *sample index*, and every sample is processed.
- So without load-shedding, **predictions are identical at any rate**. Rate affects only latency, backlog and CPU.
- Rate can affect predictive results only if the edge-profile policy reduces work under load (e.g. updating on every k-th sample).
- The research member should know this when designing the stream-scale experiments.

## 12. Experiment result structure

- **Terminology:** an **Experiment** is one config. It runs one or more **Trials**, one per method × profile × rate × seed.
- In Live mode, the static and adaptive methods share one trial on the same samples.
- In Experiment mode, each method runs as an **isolated trial** so that its resource numbers are not mixed with another method's.

```
results/
  index.csv                        one row per trial: ids, config hash, key metrics (for quick filtering)
  <experiment_id>/
    manifest.json                  experiment id, name, type (live|experiment|sweep), timestamps, status,
                                   app version, config hash, seed(s), dataset id + version + checksum,
                                   real/synthetic flag, environment (OS, CPU model, cores, RAM,
                                   Python and library versions), provenance labels
    config.resolved.yaml           full config incl. defaults
    <trial_id>/
      summary.json                 per method: overall Acc/F1/P/R, segment metrics, stability measures
                                   (reference computations + their parameters), latency p50/p95/p99 per
                                   stage, update and adaptation time, throughput, CPU time/sample,
                                   peak/mean RSS, model size; counts of drifts/adaptations/failures
      windows.csv                  per window × method: sample index, acc, f1, per-stage mean/p95 time,
                                   throughput, CPU %, RSS, model size, feature count, model version, state
      events.jsonl                 true drift (synthetic), detections, adaptation decisions (inputs,
                                   action, reason), adaptation completed/failed (+duration),
                                   budget exceeded, config changes, state transitions, errors
      outcomes.parquet|csv         per sample × method: y_true, y_pred, correct, processing time
```

**Rules**
- **Measurements only.**
- Derived "stability" numbers are marked `reference_computation` and stored with their parameters.
- The raw per-sample outcomes let the research member recompute any definition later.
- No field contains an interpretation.
- File formats are finalised in Stage 3.

## 13. Reproducibility design

1. **Deterministic streams.** Synthetic data comes from a seeded generator. Real datasets are pinned files checked by checksum.
2. **Drift is defined by sample index**, never by wall-clock time. A live *Inject drift* click is saved as "drift at sample N", so replaying the config reproduces it.
3. **One master seed** derives the sub-seeds (stream, model, tie-breaks). All seeds are recorded.
4. **Same engine code** for Live, Experiment and CLI. The demo is an experiment.
5. **Pacing is not processing.** The stream-rate delay is excluded from latency. If the engine falls behind the configured rate, the backlog is recorded.
6. **Config hash + predictions hash.** *Re-run* compares the new predictions hash with the old one and shows *"Predictions identical ✓"* or *"differ ✗"*. Timings are expected to vary, and the environment is shown next to them.
7. **Environment capture** in every manifest.
8. **Library versions pinned** in the project.

## 14. States

Three independent state machines, never merged into one badge.

**Run lifecycle**

| State | Entered when | UI |
|---|---|---|
| IDLE / READY | App loaded, config valid | Start enabled |
| LOADING | Dataset or model initialising | Progress, controls disabled |
| WARMING UP | Initial training window (static baseline fit) | "Warm-up: 640 / 1,000 samples" |
| RUNNING | Stream processing | Live updates |
| PAUSED | User pause | Frozen charts, "Paused at sample N" |
| COMPLETED | Stream exhausted | Summary, link to results |
| STOPPED | User stop | Partial results saved, marked `stopped` |
| ERROR | Unrecoverable failure | Message and cause; partial bundle saved, marked `error` |

**Pipeline state** (adaptive method, while RUNNING)

| State | Entered when | Leaves when |
|---|---|---|
| STABLE | Default | Detector fires |
| DRIFT DETECTED | Detector fires | Adaptation action begins |
| ADAPTING | Adaptation action running | Action completes or fails |
| MONITORING RECOVERY | After adaptation (an observation window; *not* a claim that recovery happened) | Reference criterion met, or horizon ends → STABLE |
| ⚑ RESOURCE CONSTRAINED *(flag, combines with any state)* | A simulated budget is exceeded | Back under budget |

**Connection** (frontend): CONNECTED · RECONNECTING · DISCONNECTED.
- The run continues on the server and the bundle is unaffected.
- On reconnect, the UI resyncs from the aggregated state.

**Message copy** (factual wording; numbers are placeholders)
- "Drift injected at sample 5,000 (scheduled · synthetic scenario)"
- "Drift detected at sample 5,142 — 142 samples after injection"
- "Adaptation: replacing model v1 with v2 (reason: drift detected)"
- "Adaptation completed in 38.2 ms — model v2 active"
- "Adaptation failed — continuing with previous model (v1). Cause: <error>"
- "Budget exceeded: p95 latency 4.1 ms > 3.0 ms (simulated edge profile)"
- "Processing configuration changed: feature budget 8 → 5"
- "Windowed accuracy within 2% of pre-drift level at sample 5,900 (reference criterion)"
- "Connection lost — the run continues on the server. Reconnecting…"
- Config validation: "Drift position (15,000) is beyond stream length (12,000)"

## 15. Performance and latency requirements

Performance shapes the architecture. It is not just a group of KPIs.

**Measurement definitions** (shown on the Method page)

| Quantity | Definition |
|---|---|
| Preprocessing time | Time per sample in the preprocessing stage |
| Feature-selection time | Time per sample to select and update features |
| **Prediction latency** | Time for the model's predict call on one prepared sample |
| **Drift-detection overhead** | Time per sample for the detector update(s) |
| **Model-update time** | Routine incremental learn call per labelled sample |
| **Adaptation time** | Duration of an adaptation action (replace / reset / bounded retrain), reported separately |
| **End-to-end processing latency** | Engine time from taking a sample to finishing all stages. Excludes pacing, network and UI |
| Monitoring overhead | Time spent measuring and aggregating, reported as its own stage so the observer's cost is visible |
| **Throughput** | Samples processed per second at max speed; plus backlog at a configured rate |
| CPU | Process CPU % (sampled) and CPU time per sample (more robust) |
| Memory | Process RSS; model size where the library can estimate it |
| *Computational overhead* | **[Team]** Definition pending. The platform provides candidates: CPU time per sample, and adaptive minus static time per sample |

API/transport latency and UI render time are **diagnostics only**. They are never reported as ML latency.

**Requirements**
- **PR-1** The ML loop never waits on the UI, the network or disk.
- **PR-2** The UI receives bounded, aggregated snapshots at a fixed cadence (default 4 Hz). Raw samples are never sent.
- **PR-3** Timings use a high-resolution monotonic clock and are aggregated into windows in memory.
- **PR-4** Disk writes are buffered and batched, never done synchronously per sample. No database server.
- **PR-5** Resource sampling runs in the background at 1–2 Hz, never per sample.
- **PR-6** Models are initialised once per trial and never reloaded per prediction.
- **PR-7** The default adaptation is incremental. Any retrain is bounded to a recent-window buffer of configurable size, and its duration is logged.
- **PR-8** Summary metrics use running counters. History is never rescanned.
- **PR-9** Charts render decimated series (bounded points per series) and never re-render full history.
- **PR-10** Monitoring overhead is measured and reported (PR-3 and PR-5 cost something, and that cost is shown).
- **PR-11** Processing granularity (per-sample vs micro-batch) is a Stage 3 decision. Either way, timings are reported **per sample**.

**Provisional design targets** (to be verified by the benchmark in Phases 8 and 12; *not claims*)
- At max speed, the Standard profile should sustain **≥10× the live demo rate**, so the live demo never lags.
- Monitoring overhead should be a small, reported fraction of processing time.

## 16. Standard vs simulated edge experience

| | Standard profile | Simulated Edge-Constrained profile |
|---|---|---|
| Hardware | Local machine | **Same local machine** |
| Constraints | None beyond the machine itself | Software-enforced budgets: feature budget *k*, model memory cap, per-sample latency budget, update stride, background-model allowance. **Values: [Team], set by research** |
| Measurements | Real, local | Real, local, **under simulated constraints** |
| Adaptation policy | Drift-driven | Drift-driven **and** budget-aware (G5): it may reduce features, throttle updates or skip background models, and every such change is logged with its reason |
| Labelling | `MEASURED · <machine> · Standard` | Persistent amber banner: *"Simulated edge-constrained profile — constraints enforced in software on <machine>. Not measured on edge hardware."* |

- The policy's actions map to the §VI options.
  - *Changing the processing configuration*: e.g. reducing the feature count or the update stride.
  - *Updating parameters / choosing a model / retraining if necessary*: e.g. drift-triggered replacement.
- The policy is **rule-based and transparent**. It is not an optimiser.
- The Live decision card shows the resource state and the current decision.
- Experiments can run the same config under both profiles. The accuracy vs cost chart (C6) joins the Standard and Edge points of each method.
- **Later, if hardware becomes available:** run the CLI on the device and import the bundle. It gets the provenance "Measured on <device>". This is OPTIONAL, and the design leaves room for it.

## 17. MVP scope — MUST HAVE

| Feature | Why |
|---|---|
| Deterministic synthetic stream with scheduled abrupt drift; no-drift control | Core story; known ground truth |
| Support for ≥1 real benchmark dataset (choice: Research) | The paper targets real-world evolving streams |
| Pipeline: incremental preprocessing, lightweight online feature selection, ADWIN detection, incremental learner, drift-triggered adaptation | G1; the §VI components |
| Static (train-once) baseline | Required comparison |
| Minimal resource-aware policy (at least budget-driven feature reduction) under the simulated edge profile | G5 is the paper's key goal |
| Per-stage timing, throughput, CPU, memory; monitoring overhead | G2, G3; §VI metrics |
| Live screen: phase strip, pipeline strip, KPIs, hero chart, drift signal, cost panel, data snapshot, decision and episode cards, event log | Panel story |
| Experiments: config form + presets, runner, history, detail with comparison table and C6–C8, export | Research workstream |
| CLI runner using the same config | Research workstream |
| Result bundle + manifest + environment capture | Reproducibility, G6 |
| Standard + simulated edge profiles with provenance labels | Honest G4 |
| Demo Mode (event-driven narration) | Panel |
| Method page: traceability, glossary, measurement definitions; InfoTips | Review workstream; panel |
| States and failure handling, incl. "adaptation failed — continuing" | Robustness |
| Benchmark script; tests for critical paths | Performance evidence |

## 18. SHOULD HAVE and OPTIONAL

| Feature | Class | Note |
|---|---|---|
| Gradual drift | SHOULD | Common in the literature; cheap with a generator |
| Incremental-only method (no detection) | SHOULD | Ablation: separates the effect of detection and adaptation from continuous learning |
| Literature comparator, e.g. ARF [20] | SHOULD | §VI promises a comparison with existing adaptive approaches. Final choice: Research + Review |
| Periodic-retraining baseline | SHOULD | Represents the paper's "static datasets and periodic retraining" framing |
| Input-distribution monitor alongside the error-based detector | SHOULD | Resolves the diagram-order tension (Stage 1 §F) |
| Replay of a recorded run (labelled REPLAY) | SHOULD | Keeps the demo safe if something fails on the day |
| Re-run reproducibility check (predictions hash) | SHOULD | Strong, cheap evidence for G6 |
| Cross-scale sweep via CLI + C9 chart | SHOULD | The provisional Cross Scale definition needs it |
| Light/dark theme | SHOULD | Projector legibility |
| Recurring drift | OPTIONAL | [7]; only if the time exists |
| Alternative detectors (e.g. DDM, Page-Hinkley) | OPTIONAL | Research may want them |
| Label delay | OPTIONAL | Realism; adds complexity |
| Multi-seed aggregation (mean ± sd) in the UI | OPTIONAL | The CLI and notebooks can do this |
| Edge-hardware profile via imported bundle | OPTIONAL | Only if a device exists |
| Presenter shortcuts / larger type mode | OPTIONAL | — |
| Loading a CSV dataset via config path | OPTIONAL | For the research member's own data |

## 19. Explicitly excluded — DO NOT BUILD

| Excluded | Reason |
|---|---|
| Accounts, auth, multi-user | Local research tool |
| Postgres / Redis / any DB server | Files are enough; a DB adds write latency and setup |
| Kafka, Spark, Docker orchestration, cloud deployment | Infrastructure with no research value here |
| Deep learning / PyTorch models | Not needed by §VI; conflicts with the resource-efficiency theme |
| LLM features or any paid API | No research justification |
| Automatic conclusions or recommendations | Interpretation belongs to the research member |
| AutoML, hyperparameter search, model zoo | Scope creep |
| Drag-and-drop pipeline builder | High complexity, low research value |
| Re-implementing DFDT / Modyn / SAMOA | Not claimed; out of scope |
| Energy measurement | Not measurable reliably; stated as a limitation |
| Raw per-event streaming to the frontend | Violates PR-2 |
| Dataset upload UI | The CLI config path (optional) is enough |
| Recreating the paper's missing graph values | No fabricated or assumed results |

## 20. Proposed 3–5 minute panel demo

| Time | Presenter | Screen | Action / what is said (factual) |
|---|---|---|---|
| 0:00–0:40 | Review member | Method | Problem in one sentence; the pipeline; the gaps G1–G6: "the literature rarely evaluates accuracy together with latency and resources" |
| 0:40–1:20 | Utsav | Live → Demo Mode | Start. "Stable stream: accuracy ≈ [measured], p95 latency ≈ [measured] ms, both methods behave alike." |
| 1:20–2:00 | Utsav | Live | Scheduled drift at sample N. "The data changed" (data snapshot). "Both accuracy lines drop." |
| 2:00–2:50 | Utsav | Live | "ADWIN detected the change [k] samples later. The pipeline adapted in [t] ms. The static model keeps its old concept." Point at the episode card and the cost spike. |
| 2:50–3:30 | Utsav | Live (stage drawer / decision card) | "Under the simulated edge profile the policy also reduces processing when a budget is exceeded, and logs why. These constraints are simulated on this laptop." |
| 3:30–4:30 | Research member | Experiments → recorded run | Methods × profiles table, accuracy vs cost chart, segment bars. The research member gives their interpretation. |
| 4:30–5:00 | Research member | Reproducibility card | Seed, config hash, environment, re-run check. Closing line: *"The prototype evaluates adaptation not only by predictive performance but also by latency and resource efficiency."* |

- **Fallback:** if the live run fails, use Replay of a recorded run, labelled REPLAY.
- The live streaming portion runs about 2 minutes (default 100 samples/s × ~12,000 samples).

---

## A. What the panel will see

- One live timeline: stable operation, drift occurring, performance dropping, drift detected, adaptation, post-adaptation performance. The adaptive and static methods are shown side by side.
- The cost of each step: per-stage time, adaptation duration, CPU and memory.
- A simulated edge profile that changes the pipeline's processing decisions, clearly labelled as simulation.
- A recorded, reproducible comparison of methods and profiles.
- Plain-language explanations wherever a concept appears.

## B. What the research member can control

- **In the UI:** scenario, stream rate and volume, drift type, methods, profile(s), seed.
- **In Advanced:** drift position, intensity and width; model; detector and sensitivity; metric window; feature budget; warm-up length.
- **In config/CLI:** edge budget values, policy thresholds, stability reference parameters, segment anchoring, seed lists, cross-scale sweep grids, label delay, output detail.
- **Outputs:** raw per-sample outcomes, windowed metrics, events and manifests, for any analysis.

## C. What the implementation member must build

- The pipeline engine and its stages.
- The deterministic stream generator and dataset loaders.
- The static baseline and the method presets.
- The resource profiles and the budget-aware policy.
- The measurement layer: per-stage timing, resources, monitoring overhead.
- The experiment runner (UI + CLI) and the result bundles.
- The FastAPI backend with live aggregated updates.
- The React UI: Live, Experiments, Method, Demo Mode.
- The benchmark script and tests.
- The implementation documentation.

## D. What the review member can verify

- The traceability matrix: each component ↔ technique ↔ reference ↔ gap, with a sign-off column.
- That the stage drawers and the Method page cite the right references.
- That the comparators and drift types come from the reviewed literature.
- That UI and docs make no claims beyond the paper: no novel algorithm, no hardware claims, no fabricated values.
- That the metrics match §VI.

## E. What remains a team decision

1. The final definition of Cross Scale (provisional one adopted).
2. The mathematical definition of accuracy stability, the recovery criterion and the segment anchoring.
3. The definition of computational overhead.
4. Datasets: which real benchmark, and the synthetic generator parameters (including irrelevant features, so feature selection has something to drop).
5. The comparator methods, which must be literature-cited.
6. What the static baseline freezes, and the warm-up length. Proposal: preprocessing, feature selection and model are all frozen after warm-up.
7. The simulated edge budget values.
8. The experimental protocol: seeds, repetitions, drift positions, rates and volumes.
9. Whether edge hardware is available.
10. The label-availability assumption: immediate labels (proposed) or delayed labels.
11. Alignment with the final submitted paper, once it is available.
12. Demo speaker allocation, and updating slide 10 in the next deck.
