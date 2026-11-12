# Research Testbed

The evidence-producing side of the project. [PLAN.md](PLAN.md) explains why it exists and what it
will build. AdaptiveML Studio stays the demo. The testbed reuses its engine (`backend/adaptiveml`)
and adds what the paper's experiments need.

## Status

| Phase | State |
|---|---|
| 1. Data: CIC-IDS2017 stream, schedule, checksums | **Done** |
| 2. Baselines and metrics | **Done** |
| 3. Joint controller (R1–R5), cost terms | **Done** |
| 4. Device tiers, scheduler, label delay, fleet | **Done** |
| 5. Protocol, statistics, report generator | **Done** (full protocol not yet run: about two days of compute) |
| 6. Testbed screen | **Done** |
| 7. Real device (optional) | **Kit done and rehearsed on the laptop; not yet run on a Raspberry Pi** |

## Phase 1 — what exists now

- **`scripts/prepare_cicids2017.py`** downloads the corrected CIC-IDS2017 release (or takes a
  zip you downloaded), checks it against the pinned checksum, and writes one chronological
  stream of 2,099,976 flows plus a schedule of the 22 real attack periods. Details and
  decisions are in [data/README.md](../data/README.md#network-intrusions-cic-ids2017-corrected).
- **`backend/adaptiveml/stream/streaming.py`** (`StreamingScenario`) reads that stream from disk
  one row at a time. Memory stays flat however long the stream is. Any catalog entry with
  `"streaming": true` uses it automatically, in the engine, the experiment runner and the API.
- **`backend/tests/test_streaming_data.py`**: tests for the reader and for the preparation logic
  (end-time ordering, "Attempted" labels, blank values, attack periods).
- **`presets/phase1_full_stream.yaml`**: the whole stream through the Studio's pipeline.

### Reproduce

```bash
backend/.venv/bin/python scripts/prepare_cicids2017.py
```

```bash
cd backend && PYTHONHASHSEED=0 .venv/bin/python -m adaptiveml.experiments.run ../research_testbed/presets/phase1_full_stream.yaml
```

### Phase 1 check, 11 November 2026 (Apple Silicon Mac, 8 GB)

Run `20261111-144535-206267-experiment-phase-1-full-cic-ids2017-stream-through-` (in `results/`,
not in Git). Seed 42, warm-up 1,000 rows, standard profile, each method in its own process.

| | Static (train once) | Adaptive pipeline |
|---|--:|--:|
| Flows processed | 2,099,976 | 2,099,976 |
| Peak process memory | 152 MB | 164 MB |
| Engine throughput | 26,918 flows/s | 8,483 flows/s |
| Mean service time | 22.0 µs | 101.8 µs |
| Accuracy after warm-up | 75.9 % | 99.6 % |
| Attack recall / precision | 0.0 % / — | 99.1 % / 99.4 % |
| Model replacements | 0 | 188 |

Wall time for both trials: about 6 minutes. Reading the file alone takes about 28 s and 89 MB.

**Phase 1 is done.** The whole dataset streams through the existing pipeline without loading it all,
and memory stays far below an 8 GB machine's limit. The attack periods are listed in the schedule.

**Do not read the accuracy figures as results.**
- The static model learned from the first 1,000 flows, which are all benign Monday traffic. It never
  predicts an attack, so its 75.9 % is simply the share of benign flows.
- The adaptive figure is very likely inflated by attacks arriving in long runs. For example,
  158,468 DoS Hulk flows arrive in 18 minutes, and a model that keeps learning can simply follow
  the most recent label.
- The "repeat last label" baseline and kappa-temporal planned for Phase 2 are needed before any
  accuracy on this stream means anything.

These numbers check the data path. They are not experimental results: one seed, default settings,
nothing tuned, and the Studio's web server was running on the same machine.

## Phase 2 — baselines and stream-aware scores

- **New methods** (`backend/adaptiveml/models`, `pipeline`):
  - `no_change` repeats the previous row's label and never looks at a feature.
  - `srp` (Streaming Random Patches) and `lev_bag` (leveraging bagging) are literature ensembles.
    The Review member picks which to keep.
- **New scores** (`backend/adaptiveml/metrics`), all after warm-up:
  - κ and κ-temporal (accuracy beyond "repeat last label") and macro-F1.
  - Every original label's share flagged as an attack: recall for attacks, false-alarm rate for benign.
  - Each of the 22 dated attack periods: recall, flows before the first one was flagged, false alarms
    and detector events.
- **`scripts/compare_runs.py`** turns run folders into these tables: [results/phase2.md](results/phase2.md).

**Main finding.** Copying the previous row's label scores **98.70 %** on this stream, so accuracy
alone cannot rank methods here. κ-temporal can:

| Method | Accuracy | κ-temporal [95 % CI] | Mean µs/row |
|---|--:|--:|--:|
| Repeat last label | 98.70 % | 0 | 85.8 |
| Static | 75.92 % | −17.6 | 28.5 |
| Incremental | 99.14 % | 0.34 [0.09, 0.52] | 197.1 |
| Adaptive pipeline | 99.34 % | 0.49 [0.35, 0.60] | 125.0 |
| ARF | 99.86 % | 0.89 [0.86, 0.92] | 656.6 |
| SRP | 99.90 % | 0.92 [0.90, 0.94] | 4,790 |
| Leveraging bagging | 99.76 % | 0.82 [0.70, 0.90] | 5,751 |

Intervals are 10,000-row block-bootstrap intervals from `scripts/report.py`. Per attack, the gap shows
where copying fails. On FTP-Patator and SSH-Patator, repeating the last label catches 41 % and 38 %,
and incremental learning without detection catches 0.4 % and 27 %. The adaptive pipeline catches
98.5 % and 93.7 %. All methods miss the tiny classes (Heartbleed, SQL injection, Infiltration).

The literature ensembles score highest but cost 5–46× the adaptive pipeline per row. SRP's p99 is
16 ms, about two orders of magnitude over the simulated tiers' budgets.
[Phase 2 report with intervals, figures and Friedman test](reports/phase2/report.md): the average
ranks over 27 stream segments are ARF 2.07, SRP 2.11, leveraging bagging 2.87, adaptive 4.43,
incremental 4.65 and static 5.94 (CD 1.73). One seed; the three runs shared the machine, so timings
include contention.

## Phase 3 — joint controller (R1–R5) and cost terms

- **`backend/adaptiveml/joint_controller.py`**, method `joint`. Every row, after the label, it reads
  drift, rolling accuracy, per-row deadline misses, CPU share of the budget and model memory. It then
  applies the review's rules, resource rules first:
  - **R5 (memory):** drop the replacement model, then shrink the model.
  - **R3 (deadline):** halve the features, narrow the preprocessing to the features in use, then
    thin the updates. It steps back up when calm.
  - **R2 / R1 (drift):** an immediate reset while resources are tight, a background replacement
    while they are spare.
  - **R4 (low accuracy):** retrain on the last 2,000 labelled rows, only with spare resources.
- Every rule and the resource checks can be switched off (`controller:` in a config).
- The `adaptive` method keeps the earlier subset controller, unchanged.
- **Cost terms.** Every method now reports the review's `C_pre, C_fs, C_inf, C_drift, C_upd, C_ret`,
  the controller's own `C_ctrl`, and `C_comm` as not applicable. They add up to the measured
  service time within a few µs.
- Tests: `backend/tests/test_joint_controller.py` makes each rule fire on a crafted case.
- Results: [results/phase3.md](results/phase3.md); presets `presets/phase3_*.yaml`.

**What the runs show** (whole stream, seed 42, one at a time, but alongside two long ensemble runs).
"Gateway" is a simulated placeholder budget: 100 µs CPU per row, 0.15 ms per-row deadline, 2 MiB.

| Run | κ-temporal | Mean µs/row | What the controller did |
|---|--:|--:|---|
| Adaptive (earlier controller), standard | 0.31 | 111 | 302 model changes |
| Joint, standard | 0.64 | 209 | R1 on 173 drifts; nothing tight |
| Joint, gateway | −0.94 | 40 | R3 cut 56 → 4 features, narrowed, updates every 4th row |
| Joint, gateway, without R3 | **0.76** | 298 | in lightweight mode (R2) almost throughout |
| Joint, gateway, without resource checks | −0.93 | 79 | as full, no R2 |
| Joint, gateway, without R2 | −0.97 | 70 | as full |
| Joint, gateway, without R5 | −0.49 | 37 | R5 never fired in these runs (see "R5 on a memory-limited tier") |

- **Narrowing matters.** Preprocessing all 83 inputs was 107 of 153 µs per row. Narrowing it to the
  features in use brought a tight run to about 30 µs.
- **Under the gateway budget, R3 trades quality for cost.** Cutting to four features meets the budget
  but loses most of the detection quality (κ-temporal below the copy baseline). Without R3, R2's cheap
  adaptation kept quality high at 3× the budget.
- **These runs are not repeatable to the decimal.** The controller reacts to measured time. The
  "without R5" run differs from the full run, although R5 never fired in either, so that gap is
  run-to-run variation under load. Use the protocol's repeated seeds before comparing ablations.
- **R5 did not fire in these runs.** The profile also capped River's tree at the budget, and R3
  kept the model small (about 52 KB against 2 MiB). This is fixed below.

### R5 on a memory-limited tier

- **The `joint` method no longer uses River's tree cap.** Its memory budget is enforced by R5 alone.
  The other methods keep the cap, so their results are unchanged.
- **New tier `memory_sim`:** a 256 KiB model budget (placeholder) and no CPU or deadline budget, so
  R5 is the only resource rule that can act. Without a cap, the joint model on this stream is
  usually about 216 KB, 602 KB at the 90th percentile and 1.2 MB at most, so the budget binds often.
- **R5 escalates in three steps:**
  1. drop the replacement model;
  2. if there is none, start a fresh model on the same features;
  3. if a fresh model fills the budget again within 5,000 rows, halve the features.

  Features cut by R5 stay cut, because the budget is fixed. R3 only restores its own cuts. An
  earlier version let R3 undo R5's cuts, and the two kept reversing each other.
- **Protocol grid `memory`:** whole stream, seeds 11, 23 and 37, one trial at a time
  ([report](reports/protocol/report.md)):

  | Joint controller, 256 KiB | κ-temporal [95 % CI] | Mean µs/row | Peak model | Memory checks over budget |
  |---|--:|--:|--:|--:|
  | with R5 | 0.57 [0.47, 0.66] | 107 | 392 KB | 19 of 2,118 (0.9 %) |
  | without R5 | 0.75 [0.70, 0.80] | 148 | 1,377 KB | 960 of 2,099 (46 %) |

  R5 keeps the model within budget 99 % of the time. Without R5 it is over budget nearly half the
  time, peaking at 5.4× the budget. Holding the budget costs detection quality. All three seeds
  gave identical results: with no time-based budget, the controller's decisions do not depend on
  machine load. Tests: `test_r5_*` and `test_joint_alone_leaves_rivers_memory_cap_to_r5`.

## Phase 4 — device tiers, stream scale, labels, fleet

- **Device tiers** (`adaptiveml/config/profiles.py`, simulated, placeholder budgets):

  | Tier | CPU per row | Deadline | Model memory | Notes |
  |---|--:|--:|--:|---|
  | `standard` | — | — | — | |
  | `small_sim` (Raspberry Pi class) | 100 µs | 0.5 ms | 8 MiB | |
  | `micro_sim` (IoT gateway class) | 50 µs | 0.2 ms | 1 MiB | no background replacement |
  | `memory_sim` (memory-limited) | — | — | 256 KiB | isolates R5 |

- **Stream settings** (`stream:`):
  - `start` replays from any row, e.g. Wednesday = 693,702. Schedules shift with it.
  - `arrival: recorded` with `rate_scale` makes rows "arrive" at the dataset's recorded rate, sped up.
    The joint controller's CPU budget per row follows that rate, so it shrinks during attack bursts:
    at ×10, about 100–160 flows/s before the DDoS attack and 900–1,250 during it.
- **Labels** (`label_delay`, `label_coverage`). After warm-up, a row's label reaches the pipeline
  `label_delay` rows later, and only for a `label_coverage` share of rows, the same rows for every
  method. Detection, adaptation and learning run on arriving labels only, and both controllers judge
  accuracy from arrived labels only. Scores still use every row's true label.
- **Fleet runner:** `python -m adaptiveml.experiments.run <file> --workers N` runs N trials at once,
  each in its own process. The manifest records `parallel_workers`, because timings then include
  contention.

## Phase 5 — protocol, statistics, report

- **[protocol/protocol.yaml](protocol/protocol.yaml)** (version 1) fixes the grids:
  - core methods × tiers;
  - literature ensembles × tiers;
  - joint-controller ablations (each rule, and the resource checks);
  - R5 with and without, on the memory-limited tier;
  - label delay × coverage;
  - recorded arrival × speed-up.

  It also fixes the seeds, warm-up and bootstrap block size. The full protocol is 231 trials (333 in v2, which adds `effort`), about
  two days on one worker. A quick version (Wednesday's DoS attacks, one seed, no SRP or leveraging
  bagging) is 71 trials.
- **`backend/adaptiveml/analysis`:**
  - block-bootstrap confidence intervals for accuracy, κ, κ-temporal, macro-F1, recall and false alarms;
  - Friedman (with Iman–Davenport) and the Nemenyi critical difference, checked against SciPy and
    Demšar's worked example.
- **`scripts/report.py`** writes `report.md`, `tables/*.csv` and the figures:
  - accuracy over time with the attack periods;
  - accuracy-vs-cost fronts per tier;
  - cost terms;
  - ablations;
  - label delay;
  - arrival rate;
  - critical-difference diagram.

  It also checks reproducibility: configurations that were run more than once, and whether their
  predictions matched.

```bash
backend/.venv/bin/python research_testbed/scripts/protocol.py run --quick --workers 3
```

```bash
backend/.venv/bin/python research_testbed/scripts/report.py --quick
```

Drop `--quick` for the full protocol. Timing figures of record come from `--workers 1`.

### Quick protocol run, 11 November 2026

Full report: [reports/protocol-quick/report.md](reports/protocol-quick/report.md), with 7 figures and
CSV tables. It covers 69 trials on Wednesday's denial-of-service traffic (300,000 rows from row
693,702) with seed 11, run 3 at a time alongside two long ensemble runs. **This checks the whole chain.
It is not the experiment of record.** Some things it already shows:

- **Tiers (κ-temporal):**

  | Method | standard | small_sim | micro_sim |
  |---|--:|--:|--:|
  | Joint controller | 0.58 | **0.65** | −0.03 |
  | Adaptive pipeline (earlier controller) | 0.67 | 0.08 | 0.09 |
  | ARF | 0.92 | 0.92 | 0.92 |

  ARF's mean cost is about 1,300 µs per row, 6–25× the others, which is outside every tier's
  placeholder budget. Under micro_sim, incremental learning without control collapses (−8.9): the
  1 MiB cap prunes its tree.
- **Ablations (small_sim):** without the resource checks, κ-temporal falls from 0.65 to 0.09, and
  without R2 to 0.19. Without R3 it is 0.70, but at 347 µs per row against a 100 µs budget.
- **Recorded arrival rate:** the joint controller adapts to the arrival rate (micro_sim: κ-temporal
  0.62–0.67 at 75–138 µs per row). The earlier controller ignores it.
- **Labels:** quality falls sharply with a 1,000- or 10,000-row label delay for every method.
  κ-temporal's reference is not reachable under delay, so read that grid across methods, not against 0.
- **Friedman** over 36 stream segments: p ≈ 4e-25. Average ranks: ARF 1.17, incremental 3.14,
  joint 3.25, adaptive 3.28, repeat last label 4.25, static 5.92. The Nemenyi CD is 1.26, so
  incremental, joint and adaptive are not separable here.
- **Reproducibility:** of 3 configurations run twice, 2 gave identical predictions. The joint
  controller's did not, because it reacts to measured time and the machine load differed.

## New method: budgeted effort controller

- **What it is.** Method `effort` (`backend/adaptiveml/effort_controller.py`): the same pipeline as
  `joint` (Hoeffding tree, ADWIN, online feature selection), under a controller that chooses an
  *effort level* for every row instead of cutting features first. The levels set:
  - how many inputs are preprocessed;
  - how often scaler statistics are updated (with a gap-aware fading factor);
  - how often the feature ranking learns, over all inputs;
  - whether easy rows update the model.

  A price of compute (a dual variable) holds the tier's CPU budget **on average**. An activity signal
  (label switches, errors, drift alarms) sends the effort to hard stretches. The per-row deadline
  and the memory limit stay hard (R5, then gated feature cuts with a floor of 8). Three repairs are
  included: a fast switch to a better replacement, damped re-alarms, and delay-aware adaptation.
- **Deterministic.** By default, decisions read a per-row cost model calibrated on Tuesday rows
  (`scripts/calibrate_effort_cost.py`, `research/effort_cost_calibration.json`), not timers. The
  same configuration gives the same predictions under any load. Measured time is still reported.
- **Ablations.** Every lever, the price, the activity signal and each repair can be switched off
  under `controller: effort:` in an experiment file. They are in the protocol grid
  `effort_ablations` (protocol v2) and in `presets/effort_ablation_*.yaml`.
- **Run it:**

  ```bash
  cd backend && PYTHONHASHSEED=0 .venv/bin/python -m adaptiveml.experiments.run ../research_testbed/presets/effort_core.yaml --workers 1
  ```

  ```bash
  backend/.venv/bin/python research_testbed/scripts/report.py --runs results/experiments/<id> --setting core --out research_testbed/reports/effort
  ```

- **Design:** [research/METHOD.md](research/METHOD.md). **Results so far:**
  [research/effort_results.md](research/effort_results.md). Tests: `backend/tests/test_effort_controller.py`.
- **Status:** implemented; under evaluation. The results are exploratory: one seed, one 300k-row
  slice. A held-out stretch and more seeds are still needed.

## Held-out test of the effort controller (12 November 2026)

Thursday and Friday, not used in the design, defaults unchanged, 3 seeds:
[research/heldout_results.md](research/heldout_results.md). In short: `effort` stays at or near the
CPU budget on both simulated tiers (`joint` runs 42–53 % over on the small tier), with errors equal
to `joint` on the small tier and equal or fewer on the micro tier, and identical predictions across
repeats. The Wednesday "fewer errors on the small tier" result was only partly confirmed.

## Open points

- **Joint runs before this change used River's tree cap,** so in those runs R5 rarely had work to
  do. This covers phase 3 and the quick protocol. Re-run them for figures of record.
- **Budgets are placeholders.** Values for each tier need a decision from the research member.
- **Friedman blocks.** Stream segments are not independent datasets, so the test is descriptive. A
  second dataset would make it stronger (PLAN.md §2).

## Phase 6 — the screen

The Studio's **Testbed** page (step 4 of the walkthrough) starts a run on the large dataset from the
browser and shows it while it runs: slice, methods, device tiers, label delay and coverage, arrival
rate, which rules are on. Its tabs list the saved testbed runs, the runs from a real device, and the
generated reports. **Findings** (step 5) reads its numbers from those reports. The small-dataset form
no longer offers CIC-IDS2017 with the column-exchange options it refuses.

## Phase 7 — a real device (optional)

[device/README.md](device/README.md) has the steps. In short: `device/pack.sh` on the laptop,
`device/setup.sh` and `device/run_on_device.py` on the device, `device/import_bundle.py` back on the
laptop. The device run calibrates the effort controller's cost model on the device, sets two time
budgets with the same relative tightness as the laptop's simulated tiers, runs the references and
both controllers, and packs the runs in the Studio's own bundle format.

- A run is labelled as a device run only when the machine names itself as a single-board computer
  (`/proc/device-tree/model`). Anything else is a rehearsal and keeps the "simulated" label.
- **Rehearsed on the laptop, end to end** (`results/device/rehearsal-*/summary.md`), including from a
  freshly unpacked kit with a new Python environment. **Not run on a Raspberry Pi**: no device was
  available. The rehearsal's numbers say nothing about a device.
- On a device the timings are real; the budgets are still set by a rule (placeholders), and energy
  is not measured.
