# Stage 3 — Technical Architecture: AdaptiveML Studio

> **Status:** This is a proposal from the Implementation workstream (Utsav). Nothing has been implemented yet.
> - **[Team]** marks a decision owned by the research member, the review member or the whole team. The architecture supports any answer through configuration. §14 collects all of them.
> - **Verified** means checked against the River 0.26.1 source and PyPI metadata on 2026-09-11.
> - All numbers are proposed defaults or placeholders. None of them is a result.

---

## 0. Environment facts (verified)

| Item | Finding | Consequence |
|---|---|---|
| Machine | Apple M1, 8 cores (4 performance + 4 efficiency), 8 GB RAM | Matches the PPT's minimum spec. This machine *is* the Standard profile |
| System Python | 3.9.6 | Too old for current River |
| Anaconda Python | 3.11.5 at `~/anaconda3/bin/python3.11` (the conda shell function is broken, so call the binary directly) | Use it to create a project venv |
| River | 0.26.1 (2026-08-21); requires Python ≥3.11; prebuilt `universal2` wheel, 3.1 MB | No compilation. Brings in scipy, numpy ≥2.2.5 and narwhals |
| numpy latest | 2.5.x requires Python ≥3.12 | pip resolves a 3.11-compatible numpy; it gets pinned in the lock file |
| Node / npm | 22.14 / 10.9 | Fine for Vite + React |
| Not installed yet | river, pytest, httpx | Installed into the project venv in Stage 4, after you confirm |

---

## 1. System overview

```
┌──────────────────────────── Browser (React + Vite) ────────────────────────────┐
│  Live · Experiments · Method          store ◄── SSE (≈4 Hz)      REST ──► control│
└──────────────────▲─────────────────────────────────────────────────┬───────────┘
                   │ SSE: status · blocks · events · resources         │ REST (JSON)
┌──────────────────┴────────────── API server process (FastAPI) ─────▼───────────┐
│ api/ routes, SSE hub, RunManager (≤1 live run; sequential experiment trials)    │
│ monitoring/ ResourceSampler — psutil on the ENGINE PID, 1 Hz (outside the loop) │
│ results/ reader + decimation     config/ validation, presets, hashing           │
└──────────────────▲────────────────────────────────┬────────────────────────────┘
   mp.Queue ▲ status/blocks/events                   │ mp.Queue ▼ commands
┌──────────────────┴────────── Engine worker process (one per trial) ─▼──────────┐
│ stream → preprocessing → features → models.predict → metrics.evaluate           │
│        → drift → adaptation (policy + actions) → models.learn → monitoring      │
│        → results.writer (buffered)                                              │
└──────────────────────────────────────────────────┬─────────────────────────────┘
                                                   ▼
                               results/<experiment_id>/…   (plain files; no database)
experiments/cli ── runs the same engine directly, with no server ────────────┘
```

**Why this shape**

1. **The engine runs in its own process.**
   - *Measurement isolation:* Python's GIL means a web server in the same process would steal time from the ML loop and distort its timings.
   - *Correct resource attribution:* CPU and RSS belong to the engine alone, not the web server.
   - *Clean memory per trial:* each Experiment-mode trial gets a fresh process.
   - *Crash isolation:* if the engine dies, the server marks the run ERROR and keeps the partial results.
2. **The observer sits outside the observed process.** The server samples the engine's CPU% and RSS through psutil, so this adds nothing to the engine's work. Only the stage timers, per-block CPU time and a low-frequency model-size probe run inside the engine, and their cost is measured.
3. **Files, not a database.**
   - The data is append-only with one writer per trial, and it's read after completion.
   - Files are the simplest and cheapest option for that.
   - They satisfy the sequence diagram's step 8, "Store/Update Logs & Metrics".
4. **SSE + REST instead of WebSocket.**
   - Live data flows one way at about 4 Hz, and control is plain request/response.
   - SSE (`EventSource`) reconnects automatically with `Last-Event-ID`.
   - It needs no extra dependency.
5. **One engine for Live, Experiment, CLI and benchmark.** The demo *is* an experiment.

**Mapping to the PPT sequence diagram:**
- *User* and *Web Dashboard* → the browser
- *Backend API Server* → the API process
- *Stream Processor* and *Adaptive ML Engine* → the engine worker
- *Monitoring Module* → split into in-engine timers, the out-of-process resource sampler, and the results writer

---

## 2. Backend package layout and module interfaces

```
backend/adaptiveml/
  config/        pydantic schema, presets/*.yaml, profiles/*.yaml, loader, canonical hashing
  stream/        sources (River generators, pinned real datasets), drift composition, pacing clock
  preprocessing/ imputer, scaler, clipper — adaptive and frozen variants
  features/      online selector, selection state
  models/        learner factory (River), ModelSlot (active + background model, version)
  drift/         error-stream detector wrapper; optional input-distribution monitor
  adaptation/    policy (rule ladder), actions, resource budgets
  pipeline/      MethodPipeline (one full pipeline instance), method presets
  metrics/       block aggregator, confusion counts, stability reference computations
  monitoring/    stage timers, CPU-time per block, model-size probe; server-side resource sampler
  engine/        trial loop, state machines, command handling, IPC emitter
  results/       buffered bundle writer, bundle reader, decimation, export
  experiments/   trial-matrix runner, CLI, benchmark
  api/           FastAPI app, routes, SSE hub, RunManager
backend/tests/
```

Your suggested modules are all kept. I added four more, each for one distinct job and nothing else:
- `pipeline/`: composes the stages into one method.
- `engine/`: the loop and its state.
- `results/`: file input/output.
- `config/`: the single configuration schema.

The table below gives each module's conceptual interface. These are responsibilities and data flow, not code.

| Module | Interface | Contract |
|---|---|---|
| stream | `Scenario.from_config(cfg)` → `iter() → (i, x: dict[str,float], y)`; `ground_truth_drifts`, `feature_names`, `dataset_info`, `is_synthetic` | Deterministic for a given seed; drift positions are sample indices |
| preprocessing | `transform(x) → x′`; `learn(x)`; `freeze()` | `transform` uses only stats learned from earlier samples |
| features | `select(x′) → x″`; `learn(x′, y)`; `ranking()`; `propose(k) → SelectionChange?` | The ranking updates continuously; the *applied* set changes only at defined boundaries (§4.3) |
| models | `make_learner(spec, seed)`; `ModelSlot{active, background?, version}` | Models are created once and never reloaded per prediction |
| drift | `update(err: 0/1) → NONE / WARNING / DRIFT`; `width`, `estimation`, `reset()` | Wraps River detectors |
| adaptation | `Policy.decide(signal, resource_state, ctx) → Decision{actions, reasons}`; `Action.apply(pipeline) → {ok, duration_ns, error?}` | Actions are guarded; a failure leaves the previous model in place |
| pipeline | `MethodPipeline.process(i, x, y) → SampleOutcome` | Runs the ordered stages of §3.1 and records per-stage timings |
| metrics | `BlockAggregator.add(outcome)`; `close() → BlockRecord` | O(1) per sample; O(B) per block |
| engine | `run_trial(trial_spec, emitter, commands) → TrialResult` | Owns the lifecycle and pipeline state machines |
| results | `BundleWriter` (buffered, flushed periodically and in `finally`); `BundleReader` | No per-sample disk writes |

---

## 3. Execution semantics

### 3.1 Per-sample order (one method pipeline, prequential "test-then-train")

| # | Stage | What happens | Timed as |
|---|---|---|---|
| 1 | Ingest | Source yields `(i, x, y)`; `y` is held back until step 5 | `stream` |
| 2 | Preprocess | Impute → scale → clip, using the current stats | `preprocess` |
| 2½ | *(SHOULD)* Input monitor | Update the input-distribution monitor on a subsample | `input_monitor` |
| 3 | Select | Project `x′` onto the selected set S | `feature_select` |
| 4 | Predict | `ŷ = model.predict_one(x″)` | `predict` |
| 5 | Evaluate | Label revealed; `err = [ŷ ≠ y]`; confusion counts | `monitor` |
| 6 | Detect | Warning and drift detectors update with `err` | `detect` |
| 7 | Decide & adapt | The policy checks `(signal, resource state)`; rarely it runs actions | `adaptation` (separate series) |
| 8 | Learn | Update preprocessor stats, selector stats and `model.learn_one(x″, y)` (plus the background model), respecting the update stride | `update` |
| 9 | Record | Block aggregation; per-sample outcome arrays | `monitor` |

**How this fits the PPT's activity diagram.**
- The diagram puts detection and adaptation *before* prediction. With label-based detection, sample *i*'s error is only known after its prediction.
- In this loop, the decision made at step 7 for sample *i* takes effect before step 4 of sample *i+1*. So from each incoming sample's point of view, detection and adaptation still come before its prediction, exactly as drawn. It's the same cycle, just started at a different point.
- The optional step 2½ is the literal "monitor data distribution" step, and it does run before prediction.
- **No leakage:** every transform and prediction for sample *i* uses only state learned from samples before *i*.

### 3.2 Methods are independent pipeline instances

Every compared method has its **own** preprocessor, selector, model and detectors. All methods see the identical sample sequence, and they share no state.

| Preset | During warm-up (first W samples) | After warm-up |
|---|---|---|
| `static` | All components learn | **Everything frozen**: no learning, no detection, no adaptation |
| `incremental` (SHOULD) | Learn | Keeps learning; no detection or adaptation (ablation) |
| `adaptive` | Learn | Learns, detects, applies the policy and runs actions |
| `periodic` (SHOULD) | Learn | Every P samples, a new model is trained on the last N buffered samples (the "periodic retraining" pipeline) |
| `arf` (SHOULD, [20]) | Learn | River `ARFClassifier` with its own internal ADWIN detectors; the pipeline's own detector is disabled |

**[Team]** decisions for this table:
- the static freeze semantics (proposal: everything frozen)
- whether all methods share the same preprocessing and feature-selection configuration (proposal: yes, so only the learner and adaptation differ)
- W (proposal: 1,000)
- whether metrics count only after warm-up for every method (proposal: yes)

### 3.3 Trials, modes, isolation

- **Live mode:** one trial runs all selected methods in one engine process, interleaved per sample.
  - Per-method stage timings are exact.
  - Process CPU and RSS cover the whole engine and are labelled *"engine process, all methods"*.
- **Experiment mode:** one trial per method × profile × rate × length × seed, each in a **fresh process**.
  - Trials run **sequentially**; concurrent trials would compete for cores and invalidate the timings.
  - The CLI allows `--parallel N` for accuracy-only sweeps. The bundle then records `timing_valid: false`.
- **Benchmark:** Experiment mode at max speed, with repetitions.
- **The official timing and resource numbers come from Experiment mode.**

### 3.4 Time, pacing, queueing

- **Arrival schedule:** sample *i* arrives at `a_i = t0 + i / rate`. It's deterministic, not random.
- **Pacing:** the engine wakes on a ~10 ms tick and processes every sample that has arrived. Sleep time is excluded from every latency figure.
- **Service time** `s_i` is the sum of the stage times for sample *i* and method *m*. This is the **processing latency**.
- **Response time** `r_i = finish_i − a_i`, which is queueing delay plus service time. It's reported separately as "response time at rate R".
- **Backlog and utilization:** backlog is arrived minus processed, recorded per block. **Utilization** is `ρ = rate × mean service time`, per method and for the whole engine.
- **Max speed:** there is no arrival schedule, and `throughput = samples / Σ engine time`.
- **Alignment:** the x-axis is always the **sample index**. Wall time is recorded but never used for alignment.

**By design, rate doesn't change predictions.** Drift is placed at a sample index and every sample gets processed, so rate changes only cost metrics (response time, backlog, CPU%). Rate can change *predictions* only when the edge-profile policy sheds work (§4.6). The research member should know this when designing the stream-scale experiments.

### 3.5 Control and drift injection

- **Command polling:** commands (`pause`, `resume`, `stop`, `inject_drift`) are read without blocking on every pacing tick in paced mode, or at every block boundary at max speed.
- **Inject drift** (synthetic scenarios only):
  - It becomes a drift spec at `sample = next unprocessed index`.
  - That spec is written into the resolved config, so a rerun reproduces it.
- **Stop:** the engine finishes the current sample, then flushes the bundle with status `stopped`.

### 3.6 Labels

- **Proposal:** immediate labels, i.e. standard prequential evaluation **[Team: confirm]**.
- **Label delay** (OPTIONAL) would add a pending-label queue between steps 4 and 5. `SampleOutcome` already carries both the prediction index and the label index, so the interfaces leave room for it.

### 3.7 State machines

- **Run lifecycle.** The states are those in Stage 2 §14. The engine owns them; the server mirrors them and adds `ERROR` if the engine exits abnormally.
- **Adaptive pipeline state:**
  ```
  STABLE → DRIFT_DETECTED → ADAPTING → MONITORING_RECOVERY → STABLE
                                  └─(action fails)→ STABLE + event adaptation_failed (previous model kept)
  ```
- **Leaving MONITORING_RECOVERY:** the state ends when the recovery reference criterion is met or horizon H has passed.
- **RESOURCE_CONSTRAINED** is a flag that combines with any state. It's set while a simulated budget is exceeded.
- **Cool-down:** detectors are reset after each adaptation. There is a minimum gap of **G samples** between adaptations, which guards against the "unnecessary retraining" constraint on PPT slide 16. Drift signals during the cool-down are logged but not acted on. **[Team: G; proposal 300]**

---

## 4. Algorithm choices

### 4.1 Streams and scenarios — **[Team: final dataset selection]**

| Candidate | Type | Features | Drift | For | Against |
|---|---|---|---|---|---|
| **SEA** + `ConceptDriftStream` (verified) | Synthetic | 3 (`x0`, `x1` relevant; `x2` irrelevant) | Threshold switch θ ∈ {8, 9, 7, 9.5}; abrupt (`width=1`) or gradual; true concept drift (P(y∣x) changes, P(x) doesn't) | Classic benchmark; 2-D boundary makes the data snapshot intuitive; `x2` gives feature selection a known right answer; intensity is analytically known | Only 3 features; linear concept |
| Agrawal (verified) | Synthetic | 9 | Switch `classification_function` (10 functions) | Nonlinear; relevant features change with the function | Some functions are non-monotonic, so linear relevance can mis-rank (§4.3) |
| Hyperplane (verified) | Synthetic | 10 (configurable) | Incremental/gradual (`mag_change`, `n_drift_features`) | Gradual drift; linear concept | No abrupt mode on its own |
| **Elec2** (verified) | Real | 8 | Unknown positions | Widely used real evolving stream; 45,312 samples; 3.1 MB download | No ground-truth drift markers; download and citation to confirm |
| INSECTS `abrupt_balanced` (verified) | Real | 33 | Abrupt, by dataset design | Real data with built-in drift | 14 MB; whether River exposes drift positions is unverified; heavier |

**Proposed development and demo default** (a working default, not a research choice):
- SEA, switching from variant 0 to variant 3 at sample 5,000, abrupt, noise 0.1 **[Team]**
- stream length 12,000; warm-up 1,000
- The first real dataset to support is Elec2 **[Team]**.

**SEA drift intensity, derived analytically.** SEA draws `x0, x1 ~ U(0,10)` (verified). A threshold change from θa to θb flips the label for the fraction `|θb² − θa²| / 200` of the input space (before noise).

| Preset | Switch | θ | Label-flip fraction |
|---|---|---|---|
| — | 1→3 | 9 → 9.5 | 4.6 % |
| — | 2→0 | 7 → 8 | 7.5 % |
| low | 0→1 | 8 → 9 | 8.5 % |
| **medium** | 0→3 | 8 → 9.5 | 13.1 % |
| high | 2→3 | 7 → 9.5 | 20.6 % |

- The flip fraction is recorded in the manifest as a *scenario property*.
- **Gradual drift:** `width > 1`. **Recurring drift** (OPTIONAL): nested `ConceptDriftStream`.
- **No custom generators:** only River's standard generators are used, to avoid a "dataset tailored to the method" criticism.
- **Optional padding:** an "irrelevant-feature padding" wrapper would be added only on the research member's request, and labelled, because it changes the benchmark **[Team]**.

### 4.2 Adaptive preprocessing ([3], [17], [19])

- **Missing values:** `StatImputer` (running mean per feature).
  - The synthetic generators produce no missing values. The real datasets get checked in the spike.
  - A seeded missing-value injector is OPTIONAL **[Team]**.
- **Scaling:**
  - *Adaptive methods:* `AdaptiveStandardScaler` (verified; exponentially weighted mean and variance). This implements **adaptive normalization [19]**.
  - *Incremental methods:* `StandardScaler`.
  - *Static baseline:* `StandardScaler`, frozen after warm-up.
- **Outliers:** clip standardized values to ±c (default 5). SHOULD.
- **Honest note:** Hoeffding trees aren't affected by monotonic scaling. Scaling matters for the feature-selection relevance model and for linear learners. It's included because the paper's pipeline includes it, and its time is measured.

### 4.3 Online feature selection ([4], [16]) — **[Review: verify acceptability]**

- **Proposal:** a feature's relevance is the size of its weight `|w_j|` in an online logistic regression trained on standardized features. The top-k features are kept.
  - This adapts the truncation step of OFS [4]. It is **not** a full reimplementation of OFS, which uses the sparse linear model itself as the classifier and adds a projection step.
- **Alternative:** River `SelectKBest(stats.PearsonCorr(), k)`.
- **Limitation (both options):** they measure *linear* relevance. Features with non-monotonic effects, as in some Agrawal functions, can be under-ranked.
- **Go/no-go check in the spike:** on SEA, `x2` must rank last.
- **When the applied set changes** (for stability):
  - The ranking updates every sample. The *applied* set S changes only:
    - (a) at the end of warm-up
    - (b) at adaptation boundaries, where a new model is built on the new S
    - (c) at an edge-profile reconfiguration
  - It never changes under a live tree in the middle of a concept.
  - Reason (verified in `tree/base.py`): a River tree sends a sample that's missing a split feature down the most-traversed branch. That would degrade predictions silently.
- **Default k:** `ceil(2n/3)`, so k = 2 on SEA **[Team]**.

### 4.4 Incremental learner

**Default: `HoeffdingTreeClassifier` (VFDT).** Reasons:
1. It's the standard streaming classifier and the base learner of ARF [20]. It's in the same family as DFDT [15], though it is **not** DFDT.
2. It handles nonlinear concepts.
3. Its memory can be bounded (`max_size`, `memory_estimate_period`, both verified).
4. It has **no internal drift handling**, so adaptation effects can be attributed to the pipeline's own detector and policy. That wouldn't be true of HoeffdingAdaptiveTree or ARF.
5. It's easy to explain: "a decision tree that grows as data arrives".

**Alternatives** (Advanced config; the research member may compare): `LogisticRegression`, `GaussianNB`.

**Rejected as default:** HoeffdingAdaptiveTree (its internal ADWIN duplicates the pipeline's detection); ARF (used as a comparator instead).

**Known cost pattern:** the tree attempts splits every `grace_period` (200) samples, which causes periodic spikes in learn time. These are plotted as `update`, separate from `adaptation`, so they can't be confused.

### 4.5 Drift detection ([5])

- **Default:** ADWIN on the adaptive model's 0/1 error stream.
  - *Drift detector:* δ = 0.002 (River default).
  - *Warning detector:* δ = 0.01. It fires earlier. This two-detector pattern is the one ARF uses [20].
  - *`clock` = 32* (verified: it checks for change only every 32 samples, so detection is granular to 32 samples; `clock = 1` is available at a higher cost).
- **Why ADWIN:**
  - It's cited in the paper and has theoretical guarantees.
  - It exposes `width`, which sizes the bounded retrain, and `estimation`, which is plotted as the error estimate.
  - Its amortized cost is low.
  - The paper notes it's sensitive to noise, and SEA's `noise` parameter lets the research member probe that.
- **Alternatives** (Advanced config): `DDM` (warning and drift built in), `PageHinkley`.
- **Input monitor** (SHOULD): `KSWIN` per feature (verified: `window_size=100`, `stat_size=30`) on a subsample.
  - It runs a KS test on each update, so it's subsampled and its cost is measured.
  - *Expected behaviour:* it stays silent on SEA, Agrawal and Hyperplane, because P(x) doesn't change there. That makes a useful teaching point: concept drift without data drift.
- **The "drift signal" in the UI** is ADWIN's `estimation` and `width`. There is no invented "drift score".

### 4.6 Adaptation policy and actions (§VI options) — Implementation's core

The rule ladder is evaluated at step 7 on every sample and costs O(1).

| Trigger | Condition | Action | §VI option |
|---|---|---|---|
| — | No signal | Continue with routine incremental learning | Update parameters |
| Warning | The profile allows a background model | Start a background model (a fresh learner that learns in parallel) | Choose the right model |
| Drift | Background model has ≥ *m* samples | **Swap** background → active (version +1); reset detectors; apply the pending feature set | Choose the right model |
| Drift | No usable background model | **New model + bounded retrain** on the last `min(ADWIN width, N_max)` buffered samples; reset detectors | Retraining if necessary |
| Resource (edge sim) | Over budget for T consecutive blocks | Step down in this order: (1) drop background models, (2) raise the update stride, (3) reduce *k* through a reconfiguration (new model + bounded retrain on the reduced S). Step back up after `T_up` blocks under budget | Change the processing configuration |

- **Retrain buffer:** a ring buffer holds the last `N_max` preprocessed samples (default 1,000), so memory is bounded. After a detection, ADWIN's width approximates how much recent data belongs to the new concept.
- **Logging:** every decision records its inputs (signal, width, resource state), the action, the reason, the duration and the outcome.
- **Failure:** actions run inside a guard. If one fails, the previous model stays active, an `adaptation_failed` event is logged with the cause, the state returns to STABLE, and the stream continues.
- **What this is:** rule-based, transparent and not optimized. It's **not claimed as novel**.
  - The background-learner strategy is adopted from ARF [20].
  - The bounded retrain follows §VI's "retraining if necessary".
- **Parameters** (defaults in presets; the research member may vary them): δ_w, δ_d, *m* (proposed 200), `N_max`, G, T, `T_up`.

### 4.7 Resource profiles (simulated edge) — **[Team: all budget values]**

| Budget | Meaning | Enforcement |
|---|---|---|
| `compute_share` | The largest fraction of one core the pipeline may use | Per-sample service budget = `compute_share / rate` (paced) or `/ nominal_rate` (max-speed runs), so behaviour matches across both |
| `model_memory_mib` | Model memory cap | Passed to the tree's `max_size`, with `memory_estimate_period` lowered so River's own memory management enforces it; our probe also measures it |
| `feature_budget_k` | Starting *k* | Selector |
| `allow_background_model` | Whether background learners are allowed | Policy |
| `max_update_stride` | Largest stride the policy may use (learn on every *s*-th labelled sample) | Policy |
| `hysteresis.down/up` | T / `T_up` in blocks | Policy |

- **Standard profile:** every budget is `null`.
- **What's real and what's simulated:** measurements are always real and taken on this machine; only the *constraint* is simulated.
- **No fake slowdown:** an edge device's slower CPU is **not** emulated with any artificial slowdown factor. Tying budgets to a specific device would require measuring that device **[Team]**.
- **Placeholder budgets:** until the research member sets real values, development uses budgets marked `placeholder: true`, and the UI shows "placeholder budgets".

### 4.8 Metrics and measurement

- **Aggregation unit:** a block of B samples. The default is B = 100 in experiments and B = 25 in the live preset, so the chart advances about 4 times a second at 100 samples/s.
- **Per block and per method, the engine records:**
  - confusion counts (TP, FP, TN, FN)
  - per-stage time sum, maximum and p95
  - update and adaptation time
  - CPU time for the whole engine (`time.process_time` difference)
  - backlog
  - model version, *k*, and state flags
- **Windowed display metrics:** accuracy and F1 over W = 500 samples, computed from block counts. Any W that's a multiple of B can be recomputed offline.
- **Overall metrics:** prequential accuracy, F1, precision and recall after warm-up.
  - **[Team]** F1 variant and positive class. Proposal: binary F1 of the positive class. Confusion counts are always logged, so macro-F1 or kappa can be derived.
- **Timing:**
  - `time.perf_counter_ns` at stage boundaries.
  - Per-sample service times go into a preallocated array, which gives exact p50/p95/p99 at the end.
  - Warm-up samples are excluded from latency statistics.
  - Timer overhead is calibrated at the start of each trial and reported.
- **Resources:**
  - CPU% and RSS come from the server-side psutil sampler at 1 Hz.
  - Model size comes from `model._raw_memory_usage` (verified), called every M samples (default 2,000). Its own cost is timed and counted as monitoring.
- **Monitoring overhead** is the time spent recording and probing, reported per sample.
- **Stability measures** are *reference computations*; they're stored with their parameters and labelled as such **[Team: formula]**. Definitions:
  - *Pre-drift accuracy:* over `[t_d − P, t_d)`.
  - *Minimum windowed accuracy:* in `[t_d, t_d + H)`.
  - *Post-adaptation accuracy:* over `[t_a + g, t_a + g + P′)`.
  - *Detection delay:* `t_detect − t_d`.
  - *Recovery samples:* the first index after `t_d` where windowed accuracy is ≥ (pre-drift − tol), sustained for S samples.
  - *Anchoring:* drift-anchored (t_d = the true drift) gives a method-independent comparison. Detection-anchored is used for real data.

---

## 5. Data contracts

### 5.1 Experiment config

One YAML schema, validated with pydantic and used by both the UI and the CLI. The example is illustrative.

```yaml
schema_version: 1
experiment: { name: "SEA abrupt — methods × profiles", seed: 42 }
stream:
  scenario: sea                    # sea | agrawal | hyperplane | elec2 | insects
  params: { noise: 0.1 }
  length: 12000
  rate: 100                        # samples/s, or "max"
drift:
  - { type: abrupt, position: 5000, from_variant: 0, to_variant: 3 }
evaluation:
  warmup: 1000
  block_size: 100
  display_window: 500
  positive_class: true
  stability: { anchor: drift, pre_window: 1000, horizon: 3000, tolerance: 0.02, sustain: 500 }
methods: [static, adaptive]        # presets; per-method overrides allowed
pipeline:
  preprocessing:     { scaler: adaptive_standard, fading_factor: library_default, clip: 5.0 }
  feature_selection: { method: ofs_truncation, k: 2 }
  learner:           { type: hoeffding_tree, grace_period: 200 }
  detector:          { type: adwin, delta_drift: 0.002, delta_warning: 0.01, clock: 32 }
  adaptation:        { background_min_samples: 200, retrain_buffer: 1000, cooldown: 300 }
profiles: [standard]               # profiles/*.yaml
scale:                             # Cross Scale (provisional) — sweep axes
  stream_rates: [100]
  stream_lengths: [12000]
  resource_profiles: [standard]
repetitions: { seeds: [42] }
output: { outcomes: true }
```

- Unknown keys are rejected.
- The resolved config, with every default filled in, is written to the bundle.
- `config_hash` is the SHA-256 of the canonical JSON of the resolved config, excluding output paths.
- **Sub-seeds** are derived as `hash(master_seed, component_name)`, so adding a component doesn't shift the other seeds.
- **Engine processes start with a fixed `PYTHONHASHSEED`**, and feature iteration always uses sorted keys. That removes the one hidden source of non-determinism in CPython.

### 5.2 Resource profile file

```yaml
name: edge_sim
label: "Simulated edge-constrained"
simulated: true
placeholder: true                  # until research sets values
budgets: { compute_share: TBD, nominal_rate: TBD, model_memory_mib: TBD, feature_budget_k: TBD,
           allow_background_model: TBD, max_update_stride: TBD, hysteresis: { down: TBD, up: TBD } }
```

### 5.3 Engine ↔ server messages (multiprocessing queues)

| Direction | Message | Content | Delivery |
|---|---|---|---|
| E→S | `status` | run/trial ids, lifecycle, sample index / total | Latest wins |
| E→S | `blocks` | All blocks closed since the last tick (fields of §4.8), per method | Droppable when the queue is full; drops are counted |
| E→S | `event` | `seq`, trial, method, sample index, wall time, type, payload | **Never dropped** (separate, larger bound; overflow = error) |
| E→S | `extras` (1 Hz) | Data snapshot (≤300 points), feature ranking, detector width/estimation | Droppable |
| S→E | `command` | `pause · resume · stop · inject_drift{…}` | — |
| S internal | `resource` | 1 Hz psutil sample `{ts, cpu_percent, rss_mb}` for the engine PID | Merged into the SSE stream and `resources.csv` |

### 5.4 Event types (`events.jsonl`; facts only, no interpretation fields)

- **Drift:** `drift_true` (synthetic ground truth), `drift_warning`, `drift_detected{delay_samples, detector, width}`
- **Adaptation:** `adaptation_decision{signal, resource_state, actions, reason}`, `adaptation_started` / `adaptation_completed{action, duration_us, model_version}`, `adaptation_failed{action, error}`
- **Background model:** `background_started` / `background_discarded`
- **Configuration:** `selection_changed{added, removed, k}`, `config_changed{field, old, new, reason}`
- **Resources:** `budget_exceeded` / `budget_cleared{budget, measured, limit}`
- **State:** `state_changed{from, to}`, `lifecycle{state}`
- **Errors:** `error{where, message}`

### 5.5 Result bundle

```
results/index.csv                          one row per trial across all experiments
results/<experiment_id>/
  manifest.json          ids, type (live|experiment|sweep|replay), status, timestamps, app version (git
                         commit), config_hash, seeds, dataset{name, version, n_samples, sha256, real|synthetic,
                         source}, scenario properties (e.g. label-flip fraction), environment{os, cpu model,
                         P/E cores, RAM, python, pip freeze, power source}, provenance, timing_valid,
                         dropped_snapshots, predictions_hash per trial
  config.resolved.yaml
  resources.csv          1 Hz: ts, trial_id, cpu_percent, rss_mb
  trials/<trial_id>/
    blocks.csv           block × method rows (§4.8 fields)
    events.jsonl
    outcomes.csv.gz      sample × method: i, y_true, y_pred, service_ns[, response_ns]
    summary.json         overall metrics; latency p50/p95/p99 per stage; update/adaptation stats;
                         throughput; CPU time/sample; peak/mean RSS; model size; counts; stability
                         reference computations + parameters
```

CSV and JSON can be read by pandas or Excel with no extra dependency. Outcomes are gzipped. Parquet is not used, because it would add pyarrow.

### 5.6 REST + SSE API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness, versions |
| GET | `/api/presets` · `/api/profiles` · `/api/scenarios` | Form options |
| POST | `/api/config/validate` | Validate → resolved config and hash, or field errors |
| POST | `/api/live` | Start a live run (409 if one is running) |
| POST | `/api/live/{pause\|resume\|stop\|inject-drift}` | Control |
| GET | `/api/live/state` | Full current state for (re)sync: bounded recent blocks, events, lifecycle |
| GET | `/api/live/stream` | **SSE**: status, blocks, events, resources; `id:` = seq for `Last-Event-ID` resume |
| POST | `/api/experiments` | Start an experiment (trials run sequentially in the background) |
| GET | `/api/experiments` · `/api/experiments/{id}` | List (from the index) · manifest and summaries |
| GET | `/api/experiments/{id}/trials/{tid}/series?metric=&max_points=` | Decimated series (min/max bucketing, so spikes survive; default 2,000 points) |
| GET | `/api/experiments/{id}/events` | Events |
| POST | `/api/experiments/{id}/rerun` | Same resolved config, new ID; the result includes a predictions-hash comparison |
| GET | `/api/experiments/{id}/export` | Zip of the bundle |
| GET | `/api/method/traceability` | Traceability content |

### 5.7 Traceability source

`docs/traceability.yaml` has one entry per component with these fields:
- component
- technique
- references
- gaps
- `implemented_in` (module)
- status
- `verified_by`

The Method page renders it. The review member owns the content; the implementation fills in `implemented_in`. **[Review: is the format acceptable?]**

---

## 6. Frontend architecture

- **Stack:** Vite + React 18 + TypeScript. No UI kit. Plain CSS with design tokens (CSS variables) for light and dark themes.
- **Data layer:**
  - `api.ts` for REST.
  - `liveStream.ts` wraps `EventSource`. After a reconnect it calls `GET /api/live/state` to resync.
  - `liveStore.ts` is a small external store (React's `useSyncExternalStore`; no state library). It holds columnar typed arrays per method and series (a capped ring), the latest KPIs and events.
- **Update discipline:**
  - SSE messages mutate the store.
  - A single `requestAnimationFrame` flush notifies subscribers at most once per frame.
  - Charts append with `setData`.
  - Tiles subscribe to scalar selectors, so the component tree never fully re-renders.
- **Charts:** **uPlot** everywhere.
  - It draws on canvas, handles large series quickly, and is about 50 KB.
  - Small plugins draw the event markers and phase bands.
  - The scatter and bar charts use the same library, so there's only one chart dependency.
  - *Rejected:* ECharts (richer, but around 1 MB) and Recharts (SVG, slow with many points).
- **Routing:** hash routes (`#/live`, `#/experiments`, `#/experiments/:id`, `#/method`), with no router dependency.
- **Demo Mode:** a client-side state machine driven by events (`drift_true` → `drift_detected` → `adaptation_completed` …). Only the start is manual.
- **Replay** (SHOULD): the server replays a bundle's blocks and events through the same SSE channel, with provenance `REPLAY`.
- **Accessibility:**
  - Every state has text and an icon, not colour alone.
  - Series use colour-blind-safe colours plus dash patterns.
  - The demo supports keyboard control.

---

## 7. Dependency choices

| Layer | Dependency | Justification | Rejected |
|---|---|---|---|
| Runtime | Python 3.11 (venv from the Anaconda binary) | River requires ≥3.11; available locally | System 3.9 |
| Runtime | **river 0.26.1** (brings numpy, scipy) | Learners, ADWIN, generators, datasets, metrics — the paper's [10] | scikit-learn at runtime (batch-oriented); MOA/SAMOA (Java, distributed) |
| Runtime | fastapi + uvicorn | Async API and SSE with minimal code | Flask |
| Runtime | pydantic v2 (comes with FastAPI) | Config schema and validation | Hand-written validation |
| Runtime | PyYAML | Configs the research member can read and edit | JSON-only |
| Runtime | psutil | CPU and RSS of the engine process on macOS | — |
| Dev | pytest, httpx | Tests, FastAPI TestClient | — |
| Analysis (optional extra, research notebooks) | pandas, matplotlib, jupyter | Reading bundles | Not runtime dependencies |
| Frontend | react, react-dom, **uplot** | UI and fast charts | ECharts, Recharts, Chart.js |
| Frontend dev | vite, typescript, @vitejs/plugin-react, vitest | Build and unit tests | Playwright (heavy; a manual demo checklist is used instead) |

**Deliberately not used:**
- Frameworks: scikit-learn, pandas (at runtime), PyTorch.
- Infrastructure: any database, Kafka, Celery, Docker.
- Transport and serialization: Socket.IO, WebSocket libraries, orjson (the standard `json` is enough at 4 Hz; revisit only if profiling says otherwise).
- Frontend libraries: Tailwind or UI kits, router and state libraries.
- AI: any LLM or paid API.

**Downloads in Stage 4 need your go-ahead:**
- The PyPI and npm installs.
- Datasets: Elec2 (3.1 MB) and optionally INSECTS (14 MB), fetched once into `data/` and pinned by SHA-256. Only after team confirmation.

---

## 8. Performance strategy

### 8.1 Hot-path discipline

| Cadence | Work |
|---|---|
| **Per sample** (hot) | River `predict_one` / `learn_one`; one small dict for the feature projection; about 9 timer reads; appends to preallocated arrays; O(1) policy check |
| **Per block** (B samples) | Aggregate; p95 over B values; CPU-time difference; budget check; command poll at max speed |
| **Per tick** (≈250 ms) | Assemble the snapshot and `put_nowait` it; drop it if the queue is full |
| **Low cadence** | Model-size probe (every M samples); data snapshot (1 Hz, reservoir of ≤300 points); buffered file flush (~2 s). All timed as `monitor` |
| **Outside the engine** | Resource sampling, SSE serialization, decimation, all HTTP |

- **Per-sample, not batched:** ML processing is strictly per sample. Detection is inherently per sample, and Hoeffding trees have no batch `learn`. Micro-batching is used **only** for pacing wake-ups.
- **No retraining from scratch:** the only retrain is bounded by `N_max`.
- **Models:** built once per trial and never reloaded.
- **No synchronous per-event I/O:** events and blocks go through buffers.

### 8.2 How the Stage 2 requirements are met

| Requirement | Mechanism |
|---|---|
| PR-1 Loop never waits on UI, network or disk | Separate process; non-blocking queue; buffered writer |
| PR-2 Bounded snapshots at a fixed cadence | Per-tick emission of closed blocks; droppable; UI never gets raw samples |
| PR-3 High-resolution timers, windowed | `perf_counter_ns` + block aggregation |
| PR-4 Batched writes, no database | `BundleWriter` flush every ~2 s and in `finally` |
| PR-5 Resource sampling off the hot path | Server-side psutil on the engine PID |
| PR-6 No model reloads | `ModelSlot` holds the instances |
| PR-7 Incremental by default, bounded retrain | Policy ladder; `N_max` ring buffer |
| PR-8 Running counters | Block counts; no rescans |
| PR-9 Decimated charts | Server min/max decimation; capped client rings |
| PR-10 Monitoring overhead reported | `monitor` stage + timer calibration |
| PR-11 Per-sample reporting | Service time per sample in the outcomes array |

### 8.3 Measurement validity — threats and mitigations

| Threat | Mitigation |
|---|---|
| The M1 has performance and efficiency cores, and macOS can't pin a process to a core (psutil affinity is unsupported) | Sequential trials; repetitions with the spread reported; AC power, other apps closed; power source recorded in the manifest |
| Python garbage-collection pauses | Left enabled (realistic); they show up as tail latency; GC counts recorded per trial |
| Observer effect | Monitoring overhead and timer overhead measured and reported |
| Warm-up effects | Warm-up samples excluded from latency statistics |
| Thermal drift on long sweeps | Interleave method order across repetitions (**[Team]** protocol) |
| Several methods share caches in Live mode | Official timings come from isolated Experiment-mode trials |

### 8.4 Profiling and benchmark plan

- **Benchmark command:** `adaptiveml bench --config presets/bench_sea.yaml --reps 5`.
  - Output per method × profile: throughput, per-stage p50/p95/p99, CPU time per sample, peak RSS, monitoring overhead.
  - It writes a normal bundle plus a markdown table for `docs/performance.md`.
- **Finding bottlenecks:** cProfile (standard library) on a max-speed trial. Only measured hotspots get optimized, and every change is recorded as before/after.
- **Watch list** (hotspots to *verify*, not assumed):
  - tree split attempts
  - ARF ensemble cost
  - growth of `_raw_memory_usage` cost with model size
  - KSWIN tests
  - bounded-retrain bursts
  - the feature-selection logistic-regression update
- **Provisional targets** (checked in the spike; not claims):
  - At max speed, the Standard profile runs static + adaptive together at ≥10× the live demo rate.
  - Monitoring overhead is reported, with a small single-digit percentage as the aim.
  - SSE messages stay around ≤8 KB at 4 Hz.
  - Charts show ≤2,000 points per series.

---

## 9. Failure handling

| Failure | Detected by | Behaviour |
|---|---|---|
| Invalid config | pydantic (UI inline; CLI exit code) | Not started; field-level errors |
| Dataset missing or checksum mismatch | Loader | LOADING → ERROR with a message; no silent fallback |
| Adaptation action raises | Action guard | Previous model kept; `adaptation_failed` event; stream continues |
| Other exception in the loop | Engine top-level guard | Lifecycle ERROR; bundle flushed with status `error` and a traceback summary |
| Engine process dies (OOM, kill) | Server sees a non-zero exit code or queue silence | ERROR; files kept (anything unflushed, at most ~2 s, is lost) |
| Frontend disconnects | SSE drop | Engine unaffected; `EventSource` reconnects and resyncs |
| Slow consumer | `put_nowait` fails | Snapshot dropped and counted; events are never dropped |
| Budget exceeded | Policy | RESOURCE_CONSTRAINED flag; not an error |
| Empty or zero-length stream | Validation / loader | Rejected before start / ERROR |
| Server stops mid-run | Engine is a daemon child | Engine exits; the next server start marks the run `interrupted` from its partial manifest |

---

## 10. Testing strategy (tests are written alongside each phase)

- **Stream:**
  - The same seed gives identical samples.
  - Drift lands at the exact index.
  - SEA's empirical flip fraction is close to the analytical value.
  - Zero length is rejected.
- **Preprocessing:** no leakage; `freeze()` really freezes.
- **Features:** SEA's `x2` is dropped after warm-up; the applied set changes only at the defined boundaries.
- **Drift:**
  - On a stationary seeded stream with the default δ, there are no detections over N samples.
  - An abrupt SEA switch is detected within a recorded bound.
- **Adaptation:**
  - A swap or retrain increments the model version.
  - An injected exception leaves the previous model in place and continues the stream.
  - The cool-down is respected.
- **Metrics:** block counts match a brute-force count; F1 matches a hand calculation; the stability computations are correct on synthetic curves.
- **Engine:**
  - Lifecycle transitions; pause, resume and stop.
  - `inject_drift` is written into the resolved config.
  - A max-speed run completes.
  - Budget breaches produce logged actions.
  - **Two identical runs produce the same predictions hash.**
- **API:** endpoints via TestClient; the SSE stream yields messages; a second live run gets 409; resync after reconnect works.
- **Demo flow:** the demo preset at max speed produces the expected event order.
- **Frontend:** vitest for the store, decimation and the demo narration state machine; a manual browser checklist.

---

## 11. Repository layout

```
Adaptive_ML_Studio/
  README.md
  docs/      research_understanding.md · product_definition.md · architecture.md · traceability.yaml
             experiments.md · performance.md · demo.md
  backend/   pyproject.toml · requirements.lock · adaptiveml/ · presets/ · profiles/ · tests/
  frontend/  package.json · vite.config.ts · src/{api,store,pages,components,charts,styles}
  data/      pinned datasets (gitignored; checksums committed)
  results/   bundles (gitignored)
  scripts/   dev launcher, benchmark wrapper
```

The folder isn't a git repository yet. The proposal is `git init` at the start of Stage 4. A shared remote for the team is a **[Team]** decision.

---

## 12. First step of Stage 4: feasibility spike

The spike code becomes tests and benchmarks, so none of it is thrown away.

| # | Check | If it fails |
|---|---|---|
| 1 | River 0.26.1 installs in a 3.11 venv on this M1 | Try Homebrew Python 3.12 |
| 2 | SEA + `ConceptDriftStream`: drift at the exact index; flip fraction close to the analytical value | Fix composition before building anything else |
| 3 | Static + adaptive throughput at max speed is ≥10× the demo rate | Lower the demo rate or use a lighter learner |
| 4 | ADWIN detects SEA 0→3 (noise 0.1); detection delay and false alarms are *reported*, not tuned to look good | Report as-is; change δ only through documented config |
| 5 | The feature-selection ranking puts SEA `x2` last | Switch to `SelectKBest(PearsonCorr)`, or show feature selection as observational only |
| 6 | Cost of `_raw_memory_usage` at the model sizes seen | Probe less often |
| 7 | Snapshot and queue overhead on per-sample time | Emit less often |

**Build order after the spike** (your Phases 4–15):
1. Headless engine
2. CLI and result bundles
3. Drift detection and adaptation
4. Metrics and benchmark
5. API and SSE
6. Live screen
7. Experiments screen
8. Edge policy
9. Optimization pass
10. Tests
11. Demo Mode
12. Polish

---

## 13. Deviations from the source material (for the review member)

| Source says | Architecture does | Why |
|---|---|---|
| Drift detection before prediction (activity diagram) | Rotated loop (§3.1) + optional pre-prediction input monitor | Label-based detection needs the prediction first; the semantics are equivalent |
| "Store/Update logs & metrics" (sequence step 8) | Files, not a database | Append-only, single writer, lower overhead |
| PPT stack lists PyTorch, Streamlit, Flask | Not used | §VI needs no deep learning; React + FastAPI chosen |
| Edge-based deployment | Simulated edge profile | No hardware confirmed |
| One "Monitoring Module" | In-engine timers + out-of-process sampler + writer | Avoids the observer effect |

---

## 14. Team decision register

The build uses the "Proposed default" column until the owner decides.

| # | Decision | Owner | Proposed default | Blocks the build? |
|---|---|---|---|---|
| 1 | Final Cross Scale definition | Team | Rates, lengths × profiles (configurable) | No |
| 2 | Accuracy-stability formula, recovery criterion, anchoring | Research | Reference computations (§4.8) | No |
| 3 | Definition of computational overhead | Research | Candidates recorded (CPU time per sample; adaptive − static) | No |
| 4 | Datasets and synthetic parameters (incl. SEA noise) | Research | SEA 0→3, noise 0.1; Elec2 | Only the real-data download |
| 5 | Comparator methods | Research + Review | static, adaptive (+ incremental, periodic, ARF as SHOULD) | No |
| 6 | Static-baseline freeze semantics; warm-up W | Research | All frozen; W = 1,000 | No |
| 7 | Same preprocessing and feature selection for all methods | Research | Yes | No |
| 8 | F1 variant; positive class for real data | Research | Binary positive-class F1; confusion counts logged | No |
| 9 | Edge budget values | Research | `placeholder: true` values, labelled in the UI | Blocks edge *experiments*, not the build |
| 10 | Is the feature-selection technique acceptable (OFS truncation vs SelectKBest)? | Review | OFS-style truncation, documented as an adaptation | No |
| 11 | Feature budget *k* defaults | Research | `ceil(2n/3)` | No |
| 12 | Detector and adaptation parameters (δ_w, δ_d, clock, *m*, `N_max`, G, T) | Implementation defaults; Research may vary | §4.5–4.6 | No |
| 13 | Label availability | Research | Immediate labels | No |
| 14 | Protocol: seeds, repetitions, method order | Research | 5 repetitions in benchmarks | No |
| 15 | Edge hardware availability | Team | None | No |
| 16 | Traceability file format | Review | YAML | No |
| 17 | Repository hosting and collaboration | Team | Local git now; shared remote later | No |
| 18 | Alignment with the final submitted paper | Team | When it's available | No |

---

## 15. Amendments from Stage 4 evidence (2026-09-11)

These supersede the corresponding text above. Each one is backed by a measurement in `results/` or by a test.

| § | Originally | Amended to | Evidence |
|---|---|---|---|
| 4.1 | SEA drift built with River's `ConceptDriftStream` | `adaptiveml.stream.transition.ConceptTransition`: the same semantics and random-draw sequence, with the exponent clamped at ±700 | River 0.26.1 raises `OverflowError` for `width=1` whenever the drift is more than ~177 samples away. `tests/test_transition.py` reproduces the overflow and proves draw-for-draw equality where River does work |
| 4.2 | `AdaptiveStandardScaler` with the library default (`fading_factor` 0.3, ≈6-sample memory) | Default `fading_factor = 0.001` (≈2,000-sample memory); clipping applies only after a scaler, because it's defined in σ units | Adaptive pipeline, pre-drift accuracy by `fading_factor`: 0.3 → 0.774, 0.05 → 0.831, 0.01 → 0.847, 0.001 → 0.862 (static: 0.872). With no scaler, clip = 5 had been truncating raw inputs in 0–10 |
| 4.6 | Drift without a ready background model → new model + bounded retrain on the last `min(ADWIN width, N_max)` samples | Drift without a ready replacement → keep training a replacement (started at the warning, or at detection) and **promote it once it has `background_min_samples`** (200, the tree's grace period). A profile without background models → **reset** to a fresh model. The retrain buffer is removed; only warm-up keeps a buffer, for the one-time feature-set rebuild | ADWIN's width at detection was 3,840–4,352 samples, but the actual post-drift span was only 351–1,375. The retrain window was therefore mostly the old concept |
| 3.7 | ADAPTING = an action is running | ADAPTING = a replacement is being prepared (from detection to promotion) | Follows from 4.6 |
| 5.1 | `adaptation: {background_min_samples, retrain_buffer, cooldown}` | `adaptation: {allow_background, background_min_samples, background_timeout, cooldown}` | Follows from 4.6 |
| 12 | Check 7: 3 runs | 9 interleaved runs + an A/A baseline; thresholds unchanged | The first run failed within run-to-run noise (docs/performance.md) |
| 4.8 / 8.1 | Per-sample recorder call with Python-level counters | The engine performs **three C-level appends** per sample and method: an outcome code (2·label + prediction), the service time, and the six stage durations. Confusion counts come from `bytes.count` and stage totals from a numpy reshape, **once per block** | Profiling and benchmark (docs/performance.md, optimization log). Predictions, events and counts are bit-identical before and after |
| 3.1 | Stage timers with a gap before `update` | Stages are **contiguous** intervals, so their sum is exactly the service time (t6 − t0), with one timer read fewer per sample | Same |
| 4.8 | Model-size probe every M samples | Every M samples, but a method's probe interval **doubles** while one probe costs more than 0.5 % of its service time over the interval | ARF: one probe ≈ 170 ms at 67 MB (8 % of service time at a fixed interval) |
| 4.8 | Model size treated as a reproducible output | River's `_raw_memory_usage` is an *estimate* that varies by about 0.1 % between identical runs (16,214 vs 16,230 B for the same frozen tree). It is classed with timings as a **resource measurement**, excluded from bit-identical comparisons | Golden comparison: 400 differences, all in `model_size_bytes` |
| 3.4 / 3.5 | Pacing and control described only | Implemented: integer arrival schedule, response time and backlog per block, pause excluded from every timing, and **reproducible drift injection** — an injected drift is placed ≥ 176·width samples ahead, where the transition probability is exactly 0, so a replay of the resolved config reproduces the stream exactly | `tests/test_engine_control.py`, `tests/test_stream_inject.py` |
| 1 / 5.3 | Worker and SSE hub specified | Built as specified: bounded queue, block batches at ≈4 Hz (droppable), events never dropped, extras at 1 Hz, resources sampled by the server from the engine PID. Live runs and experiments are **mutually exclusive** (409), so runs never share the CPU | `tests/test_api.py` |
| 8.3 | — | **Paced runs inflate per-sample times** (cold caches, lower clock): predict 4.3 µs at max speed vs ≈29.7 µs at 200/s. Figures of record come from isolated max-speed trials | docs/performance.md |
| 14 | UI failure behaviour unspecified | A React error boundary reports a failed view and states that the run and its stored measurements are unaffected | — |

**Resolved:** check 4b (held-out validation of the chosen demo scenario) passed 20/20 — see `docs/stage4_feasibility.md` §6. The original check-4 failure stays recorded.
