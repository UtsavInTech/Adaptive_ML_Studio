# Performance

**Status:** these are baseline measurements taken in Stage 4, before any optimization. Every number was measured on the machine below. None of them is a claim about other hardware, including edge devices.

## Environment

- Apple M1 (4 performance + 4 efficiency cores), 8 GB RAM, macOS 26.6.2
- Python 3.11.5, river 0.26.1, numpy 2.4.6
- The benchmark and the final check-7 run were measured on AC power.
- The first feasibility run was on **battery power**. Its timing results are marked as such.
- Timer overhead: a back-to-back `perf_counter_ns` pair costs about 42 ns.

## What is measured

| Quantity | Definition |
|---|---|
| **Service time / sample** | preprocess + select + predict + detect + adapt + update, for one method. Engine work only: it excludes stream generation, recording, IPC and UI |
| **Engine throughput** | samples ÷ wall time of the whole trial loop (all methods, including stream generation and recording) |
| CPU µs / sample | process CPU time ÷ samples |
| Monitor µs / sample | loop time that is neither a pipeline stage nor stream generation: outcome recording, block closing, probes |
| Peak RSS | the process's maximum resident set. It includes the interpreter and libraries, which account for about 120 MB on their own |

- Latency statistics exclude the 1,000 warm-up samples.
- Official per-method figures come from **isolated trials**: one fresh process per method, with trials run sequentially.

## Baseline — raw engine benchmark

Source: `results/benchmarks/20260911-233309/`

- **Scenario:** SEA, concept 0 → 3 (abrupt drift), noise 0.1; 20,000 samples with the drift at sample 10,000.
- **Runs:** 5 repetitions (seeds 42–46), at max speed.
- **Values:** medians, with [min – max] ranges.

| Group | Throughput (samples/s) | CPU µs/sample | Monitor µs/sample (share) | Peak RSS MB |
|---|---|---|---|---|
| static | 111,422 [103,389 – 111,828] | 9.0 | 1.06 (11.7 %) | 124.1 |
| incremental | 45,524 [44,908 – 45,785] | 22.0 | 1.31 (6.0 %) | 124.4 |
| adaptive | 42,380 [41,708 – 43,210] | 23.6 | 1.35 (5.7 %) | 124.8 |
| arf | 996 [897 – 1,320] | 1,003.0 | 42.30 (4.1 %) | 239.7 |
| static + adaptive (live pairing) | 30,107 [26,520 – 31,525] | 32.9 | 2.49 (7.4 %) | 124.5 |

**Service time per sample (µs)**

| Method (isolated) | mean | p50 | p95 | p99 | preprocess | select | predict | detect | update |
|---|---|---|---|---|---|---|---|---|---|
| static | 5.1 | 5.0 | 5.3 | 5.8 | 1.09 | 0.17 | 3.75 | — | 0.04 |
| incremental | 18.3 | 17.6 | 19.8 | 34.0 | 1.22 | 0.19 | 4.34 | — | 12.46 |
| adaptive | 19.9 | 18.9 | 22.2 | 39.9 | 1.99 | 0.19 | 4.30 | 1.17 | 12.24 |
| arf | 977.0 | 641.5 | 2,607.3 | 3,977.9 | 3.44 | 0.34 | 91.98 | — | 881.16 |

**Observations** (facts, not conclusions):

- **Live-demo headroom.** The live pairing (static + adaptive in one process) sustains about 30,000 samples/s. That's roughly 300 times the 100 samples/s demo rate.
- **Where the adaptive pipeline's time goes:** the Hoeffding tree's `learn_one` (about 12 µs), prediction (about 4.3 µs), the forgetting scaler (about 2 µs) and the two ADWIN detectors (about 1.2 µs).
- **ARF cost (the literature comparator, 10 trees):**
  - Service time: about 49 times the adaptive pipeline's mean.
  - Model size: about 60 MB, against 77 KB for the adaptive tree.
- **Monitoring overhead** is above the "small single-digit %" aim for `static` (11.7 %) and for the live pairing (7.4 %). This is the **first optimization candidate** for Phase 12.
- **Isolated vs live timings.** Per-method service times are about 5 % higher in the live pairing than when isolated (static 5.9 vs 5.1 µs; adaptive 20.9 vs 19.9 µs). That's why isolated trials are the official figures.

## Feasibility timing checks

- **Check 3 — throughput.** Static + adaptive: median **30,472 samples/s** over 5 isolated runs. The target was ≥ 1,000.
- **Check 6 — model-size probe.**
  - Hoeffding tree at 76.6 KB: 102 µs per probe, which is 51 ns/sample when amortized over 2,000 samples (0.26 % of service time). **Pass.**
  - ARF at 67 MB (informational): 170 ms per probe, which would be 8 % of service time at the same interval.
  - Design note: the probe interval has to scale with the measured probe cost.
- **Check 7 — IPC.**

  | Run | Wall time | CPU | Direct cost | Result |
  |---|---|---|---|---|
  | First run (3 reps, battery power) | +5.3 % | — | — | **Fail** |
  | Revised protocol, designed ≈ 4 Hz cadence (9 interleaved reps, AC power) | **+0.21 %** | +0.24 % | 0.07 % | **Pass** |
  | A/A noise floor | −0.05 % | — | — | — |
  | Stress case: every block, 1,200 snapshots per run | +2.0 % | — | — | — |

  In the first run, the stress case with about 90 times more snapshots showed a *smaller* increase than the designed case. That means the run-to-run noise was at the threshold level.

## Optimization log

### 2026-09-12 — recording path ("monitor" time)

**Target.** In the live pairing, monitoring took 7.4 % of engine time (2.31 µs/sample). That was far above the 0.21 % cost of UI updates.

**Profiling, before any change** (micro-benchmarks, ns per call):

| Operation | ns per call |
|---|---|
| `MethodRecorder.add` | 374 |
| Engine-side sum of the 6 stage times | 70 |
| `perf_counter_ns` | 41 |
| Block close, amortized | 19 |

**Round 1:**
- The recorder hot path became four C-level appends, with aggregation moved to block close.
- Stage timers became contiguous (service = t6 − t0), removing one timer read and the engine-side sum.
- The engine loop chains timestamps: 2 timer reads per sample instead of 3.
- Model-size probing adapts to its own cost (at most 0.5 % of a method's service time).

**Round 2** (driven by an in-loop decomposition showing block close at ≈19 µs per block per method):
- One outcome-code append replaces two boolean appends. Confusion counts now use `bytes.count`: 3.0 → 0.55 µs per block.
- Stage totals use a numpy reshape: 7.5 → 1.8 µs per block.

**Results.** Same session, battery power, 5 repetitions, isolated trials, medians. Sources: `results/benchmarks/20260911-235839-before-recording-opt`, `…/20260912-000204-after-recording-opt`, `…/20260912-000823-after-recording-opt-round2`.

| Group | Metric | Before | Round 1 | Round 2 |
|---|---|---|---|---|
| static + adaptive (live pairing) | monitor µs/sample (share) | 2.31 (7.4 %) | 2.06 (6.7 %) | **1.96 (6.4 %)** |
| static + adaptive | engine throughput (samples/s) | 31,964 | 32,691 | 32,581 |
| adaptive | monitor µs/sample (share) | 1.29 (5.6 %) | 1.20 (5.3 %) | 1.13 (5.0 %) |
| adaptive | engine throughput | 43,350 | 43,964 | 44,127 |
| static | monitor µs/sample (share) | 1.03 (11.7 %) | 0.98 (11.2 %) | 0.91 (10.6 %) |
| static | engine throughput | 114,008 | 114,892 | 115,782 |

- Service time per sample is unchanged, as expected, because the pipeline work itself was not touched: static 4.95 → 5.00 → 4.98 µs; adaptive 19.43 → 19.26 → 19.23 µs.
- **Correctness after each round:**
  - all tests passed
  - every non-measurement output identical to a golden reference (predictions, events, block counts, scores, stability) at block sizes 25 and 100
  - **20/20 held-out seeds** gave bit-identical predictions against the check-4b hashes

**Assessment.**
- Monitoring time fell by **15 %** in the live pairing. The micro-benchmarked cost of the recording code itself fell by roughly 70 %.
- The gain is smaller than the micro-benchmarks suggested, because most of what remains is **orchestration and instrumentation**, not recording.
- Final attribution from an instrumented run (absolute values are inflated by the diagnostic timers; the shares are indicative):

  | Part | Share of non-service loop time |
  |---|---|
  | Loop and timer reads | 31.5 % |
  | Recording appends | 29.6 % |
  | Per-method call/return outside the stage window | 27.5 % |
  | Block close | 9.1 % |
  | Probes | 2.2 % |

- Monitoring time is excluded from the service-time figures (prediction latency, update time), so it doesn't contaminate them. It's reported separately (requirement PR-10).

**Not done — options with trade-offs, if more reduction is ever needed:**
1. **Sampled stage breakdown.** Per-stage timers on 1 sample in k, with service time still timed on every sample. Saves about 5 timer reads per method on most samples, but the stage means become estimates.
2. **Deriving the service time per block** from the stage rows instead of appending it per sample. Saves one append; adds per-block numpy work.
3. **Returning raw timestamps** and computing every duration per block. Fewer per-sample operations, but more per-block work, which hurts at the live block size of 25.

### Measurement note — model size

River's `_raw_memory_usage` is an **estimate**. It varies by about 0.1 % between identical runs; for example, 16,214 vs 16,230 bytes for the same frozen tree. It is therefore classed as a resource measurement, like RSS, and excluded from bit-identical reproducibility checks. `tests/test_recording.py` encodes this.

## Paced runs vs max speed

Per-sample times measured during a **paced** live run are several times higher than the same pipeline at max speed. Observed in the live demo at 200 samples/s, against the isolated max-speed benchmark:

| Quantity | Max speed (isolated) | Live, paced at 200/s |
|---|---|---|
| predict | 4.3 µs | ≈ 29.7 µs |
| preprocess | 2.0 µs | ≈ 18.2 µs |
| monitoring | 1.96 µs | ≈ 38.5 µs |

Each sample runs after a sleep, so caches are cold and the CPU has clocked down; the work itself is unchanged. This is why **official latency and cost figures come from isolated max-speed trials**, and why the live screen's numbers are read as a live indication rather than as the measurement of record.

## Measurement caveats

- macOS can't pin a process to a core, so timings vary with scheduling between the performance and efficiency cores. Mitigation: sequential isolated trials, repetitions with ranges, and the power source recorded.
- Engine throughput includes stream generation and recording. Per-method service time excludes both.
- Peak RSS is process-wide and includes about 120 MB for the interpreter and libraries.
