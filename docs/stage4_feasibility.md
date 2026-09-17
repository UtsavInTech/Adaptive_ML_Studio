# Stage 4 — Feasibility spike report

**Current status (2026-09-12):**

- **Original check 4 — FAIL, permanently recorded.** Configuration: SEA 0→3, noise 0.1, drift at 5,000. Detection: 1/10 seeds.
- **Check 4b (held-out validation) — PASS, 20/20.** It validates the explicitly chosen demo configuration: noise 0.05, drift at 10,000. The configuration was chosen on seeds 1–10 and validated on held-out seeds 11–30. Its criteria were fixed in code, and their hash was recorded before the run.
- **Checks 1–3, 5–7 — PASS.**
- **Go/no-go:** the gate for continuing the build is met.

The original result is kept in §2 and §4 below, unchanged.

All numbers were measured on an Apple M1 with 8 GB RAM, Python 3.11.5 and river 0.26.1. Accuracy figures are **measurements, not research results**; interpretation belongs to the research workstream.

## 1. What exists now

- **Headless engine** (`backend/adaptiveml/`):
  - SEA stream with sample-indexed drift
  - adaptive preprocessing
  - online feature selection
  - error-stream ADWIN detection
  - the adaptation policy
  - method pipelines: static, incremental, adaptive, ARF
  - block-level recording, the trial loop, reference stability computations
- **Tests:** 47, all passing.
- **Tooling** (run from `backend/`):
  - `python -m adaptiveml.experiments.feasibility [--only N]` — the 7 checks
  - `python -m adaptiveml.experiments.validation` — check 4b (pre-registered)
  - `python -m adaptiveml.experiments.benchmark --reps 5`
  - `python -m adaptiveml.experiments.sensitivity`
- **Outputs:** timestamped folders under `results/`, never overwritten.

## 2. Check results (original run)

| # | Check | Result | Key measurement |
|---|---|---|---|
| 1 | Install | PASS | Python 3.11.5, river 0.26.1 |
| 2 | Stream determinism and drift placement | PASS | 0 wrong-concept samples outside ±3 of the drift; label-flip fraction z = 0.84 / 0.02 / −0.86 |
| 3 | Throughput headroom | PASS | Static + adaptive: 30,472 samples/s (305 × the 100/s demo rate) |
| 4 | ADWIN drift detection (SEA 0→3, noise 0.1, drift at 5,000, δ 0.002) | **FAIL — permanently recorded** | **1/10** seeds detected within 2,000 samples; 0 false alarms |
| 5 | Feature selection ranks x2 last | PASS | 10/10 |
| 6 | Model-size probe cost | PASS | 0.26 % of service time |
| 7 | IPC snapshot overhead | PASS (after protocol revision) | +0.21 % wall at 4 Hz. The first run (3 reps, battery power) failed at +5.3 %, within run-to-run noise. Both runs are kept |

Sources: `results/feasibility/20260911-233051/` (all checks) and `results/feasibility/20260911-233703/` (check 7 re-run).

## 3. Defects found and fixed during the spike

| # | Defect | Evidence | Fix |
|---|---|---|---|
| 1 | River 0.26.1 `ConceptDriftStream` overflows for abrupt drifts more than ~177 samples away | Reproduced in `tests/test_transition.py` | `ConceptTransition`: identical draws, exponent clamped |
| 2 | River's default `AdaptiveStandardScaler` memory (≈6 samples) destabilises tree splits | Pre-drift accuracy 0.774 → 0.862 as `fading_factor` goes 0.3 → 0.001 (static: 0.872) | Default `fading_factor = 0.001` |
| 3 | Clipping (σ units) was applied to unscaled inputs | The no-scaler configuration truncated inputs in 0–10 at 5 | Clip only after a scaler |
| 4 | The bounded retrain after drift used mostly old-concept samples | ADWIN width at detection 3,840–4,352 samples vs a true post-drift span of 351–1,375 | Promote a replacement trained after the warning/detection; reset when background models are disallowed |

## 4. Original check 4 and the sensitivity analysis

Source: `results/sensitivity/20260911-233831/`. Seeds 1–10; no defaults changed.

- **Detection power depends mostly on the length of the stable period and on noise.** δ has a secondary effect.
- **False alarms:** 0 in 80 no-drift runs and in all 320 pre-drift periods.
- **The original configuration is a hard case.** A 4,000-sample stable period, a 13 % label change and 10 % label noise leave the error increase near ADWIN's bound. This matches the noise sensitivity the review records for ADWIN [5]. The configuration is kept as a **hard scenario** for the research evaluation.

## 5. Decision taken (2026-09-11)

- Utsav chose the recommended demo configuration: SEA 0→3, noise 0.05, drift at 10,000, River's default ADWIN δ.
- It was validated on held-out seeds 11–30 with a pre-registered target of **≥ 18/20 detected within 2,000 samples**.
- Nothing is tuned on the held-out results.

## 6. Check 4b — held-out validation (PASS)

- **Sources:** `results/validation/20260911-235439/check4b.{md,json}`.
- **Registration:** `results/validation/REGISTRATION.txt` holds the SHA-256 of `validation.py`, recorded before the run.
- **Measurement conditions:** battery power. Two isolated runs per seed.

| Item | Measured |
|---|---|
| 1. Detection rate | **20/20** within 2,000 samples (target ≥ 18/20) |
| 2. Detection delay (samples) | min 151 · p25 247 · **median 311** · p75 447 · max 663 |
| 3. False alarms | **0** error-increase detections before the drift (20 seeds × 9,000 monitored samples); 1 early warning (a replacement model was started, then discarded); 0 adaptations before the drift |
| 4. Accuracy / F1 (median [min – max]) | See the table below |
| 5. Adaptation | Completed after the drift in 20/20 seeds, all by `swap`; **0 failures**. Detection to promotion: median 135 samples [0 – 199] |
| 6. Reproducibility | **20/20** seeds bit-identical in a second isolated run (static and adaptive) |
| 7. Throughput / latency | Static + adaptive: 31,479 samples/s [29,579 – 32,093]. Service time: static 5.6 µs mean / 6.1 p95; adaptive 19.7 µs mean / 23.4 p95 / 37.8 p99 |

| Segment | Static accuracy | Static F1 | Adaptive accuracy | Adaptive F1 |
|---|---|---|---|---|
| Pre-drift [9,000, 10,000) | 0.913 [0.879 – 0.938] | 0.937 | 0.923 [0.912 – 0.940] | 0.943 |
| Post-drift early [10,000, 11,000) | 0.796 [0.765 – 0.828] | 0.838 | 0.871 [0.838 – 0.889] | 0.889 |
| Post-drift late [12,000, 13,000) | 0.796 [0.765 – 0.827] | 0.836 | 0.921 [0.897 – 0.949] | 0.927 |
| Post-adaptation (1,000 samples after promotion) | — | — | 0.917 [0.894 – 0.931] | 0.923 |

**An additional finding, reported as measured.** 11 of the 20 seeds had a **second adaptation** about 3,400–4,100 samples after the first, although there is no second drift.
- A read-only diagnostic (seeds 13 and 14) shows the adaptive model's own 500-sample error rising from about 0.06 to 0.11–0.14 at that point, while the static error stays flat. So the detector reacted to a genuine rise in the model's error, not to a data drift.
- A plausible cause, not proven: a transient effect when the young Hoeffding tree splits and its new leaves start with no statistics.
- This matters for the research member, because error-based detection can fire for model-internal reasons. No parameter was changed.
- In the demo, such an event appears in the log as a detection that doesn't coincide with a scheduled drift.

## 7. Next build steps

1. Recording-path optimization before the UI (in progress; see `docs/performance.md`).
2. Pacing loop, run manager and result-bundle writer.
3. FastAPI + SSE.
4. Live screen.
5. Experiments screen.
6. Edge-profile rules.
7. Demo Mode.
8. Documentation.
