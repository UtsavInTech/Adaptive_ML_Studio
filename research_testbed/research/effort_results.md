# Budgeted effort controller — first, exploratory results

**Status: exploratory.** One seed (11), one 300k-row stretch (Wednesday, rows 693,702–993,701,
warm-up 1,000), simulated tiers with placeholder budgets, one machine (8 GB Apple Silicon), trials run
one at a time with nothing else heavy running (the app's backend was idle on port 8000). Wednesday was
used as the test slice. It is not a held-out result for the paper, and a Thursday/Friday stretch and
≥ 3 seeds are needed before any claim. Design: [METHOD.md](METHOD.md). Code:
`backend/adaptiveml/effort_controller.py`. Full tables: [reports/effort/report.md](../reports/effort/report.md).

## What was run

| Setting | Preset (`research_testbed/presets/`) | Run id (`results/experiments/`) |
|---|---|---|
| Core, small_sim + micro_sim | `effort_core.yaml` | `20261111-235411-732352-experiment-effort-core-comparison-small-sim-and-mic` |
| ARF reference (reused, see note) | quick protocol `ensembles` | `20261111-175111-293327-experiment-protocol-v1-quick-ensembles` |
| Label delay 1,000, small_sim | `effort_delay1000.yaml` | `20261112-000025-518699-experiment-effort-label-delay-1000-small-sim` |
| … effort without delay awareness (D3) | `effort_delay1000_without_delay_awareness.yaml` | `20261112-000419-652774-experiment-effort-ablation-delay-1000-without-delay` |
| … **post hoc** variant (see "Changes after seeing Wednesday") | `effort_posthoc_delay1000_race_only.yaml` | `20261112-001226-375009-experiment-effort-post-hoc-variant-delay-1000-repla` |
| Ablations, small_sim (10 runs) | `effort_ablation_*.yaml` | `20261112-000502-…` to `20261112-001143-…` (one per preset; listed in the report) |
| Determinism repeat, small_sim | `effort_repeat_small_sim.yaml` | `20261112-001306-019166-experiment-effort-repeat-on-small-sim-determinism-c` |

- **ARF note.** The ARF reference is the existing quick-protocol trial on the same rows and seed. Its
  predictions do not depend on timing, so a rerun would only repeat them. Its µs/row were measured
  with 3 trials in parallel, so they are inflated.
- **Compute.** About 25 minutes of trials, plus about 3 minutes of calibration and checks on Tuesday.
- **Tables.** Built by `scripts/report.py` (10,000-row block-bootstrap intervals, 1,000 resamples).
  Paired differences come from `scripts/paired_errors.py`: the same rows, 10,000-row blocks,
  2,000 resamples.

## The cost model (decisions read this, not timers)

- **Calibration.** `scripts/calibrate_effort_cost.py`, run on **Tuesday** rows 371,624–432,624. These
  include the FTP-Patator onset. Wednesday was not used.
  - The effort pipeline ran at k = 8, 28 and 56 features, with measured stage times.
  - Each stage was regressed on the work counts the pipeline records.
  - Statistics, ranking and model update were fitted on the pipeline's own per-step timers.
  - Result: `effort_cost_calibration.json`. The defaults in `EffortCostModel` are these values.
- **Coefficients (ns):**
  - base 12,878, controller 6,794;
  - transform 212 per input, statistics 321 per input, ranking 148 per input;
  - select 26 per feature;
  - predict 1,763 + 363 per feature (the tree's naive-Bayes leaves read every feature);
  - detect 1,498 per label;
  - model update 6,688 + 935 per feature, plus 22,807 per feature on a row whose update splits a leaf.
- **Fit on Tuesday.** The mean modelled cost was within 3 % of the measured mean at each k:
  45.1 / 46.2, 73.4 / 75.2 and 115.7 / 118.8 µs. The per-row correlation is only 0.37, because
  per-row timing noise is large. The model is meant for means, not single rows.
- **On Wednesday it under-predicts.**
  - Core small_sim: modelled 92.2 µs; measured 102.2 µs, and 98.8 µs in the repeat run.
  - The same decisions in the ablation runs that changed nothing measured 107–125 µs. That is
    timing noise for identical work.
  - So the budget is held **in modelled terms**. Measured, it is at or slightly over the budget.

## Results (Wednesday, seed 11)

| Setting · tier | Method | Errors | κ-temporal [95 % CI] | Attack recall | False alarms | Σ flows before first flag (onsets ≥ 100 flows) | Modelled µs/row | Measured µs/row | Budget | Rows over deadline (measured) |
|---|---|--:|---|--:|--:|--:|--:|--:|--:|--:|
| small_sim | Repeat last label | 7,570 | 0 | 97.8 % | 3.2 % | 14 | — | 62 | 100 | 0.0 % |
| small_sim | Incremental | 2,472 | 0.69 [0.53, 0.81] | 99.0 % | 0.5 % | 692 | — | 165 | 100 | 0.6 % |
| small_sim | Adaptive (old controller) | 6,872 | 0.09 [−0.12, 0.32] | 98.3 % | 3.3 % | 79 | — | 84 | 100 | 0.0 % |
| small_sim | Joint (R1–R5) | 2,275 | 0.71 [0.59, 0.79] | 99.2 % | 0.8 % | 66 | — | 160 | 100 | 0.6 % |
| small_sim | **Effort** | **1,660** | **0.78 [0.71, 0.83]** | 99.4 % | 0.5 % | 96 | 92.2 | 102 | 100 | 0.4 % |
| small_sim | ARF (reference) | 589 | 0.92 [0.90, 0.94] | 99.8 % | 0.2 % | 67 | — | 1,368* | 100 | 100 %* |
| micro_sim | Repeat last label | 7,570 | 0 | 97.8 % | 3.2 % | 14 | — | 64 | 50 | 0.1 % |
| micro_sim | Incremental | 78,655 | −8.2 [−15.1, −4.1] | 73.6 % | 20.6 % | 44,402 | — | 85 | 50 | 1.5 % |
| micro_sim | Adaptive | 6,920 | 0.09 [−0.14, 0.32] | 98.2 % | 3.3 % | 60 | — | 86 | 50 | 0.4 % |
| micro_sim | Joint (R1–R5) | **2,638** | **0.65 [0.52, 0.74]** | 99.0 % | 0.8 % | 82 | — | 90 | 50 | 0.8 % |
| micro_sim | **Effort** | 3,099 | 0.60 [0.44, 0.71] | 99.0 % | 1.1 % | 64 | 49.0 | **47** | 50 | 0.5 % |
| delay 1,000 · small_sim | Repeat last label | 42,338 | −4.6 | 87.7 % | 17.9 % | 1,817 | — | 71 | 100 | 0.0 % |
| delay 1,000 · small_sim | Incremental | **9,602** | −0.26 [−1.05, 0.30] | 95.5 % | 1.5 % | 1,813 | — | 183 | 100 | 0.6 % |
| delay 1,000 · small_sim | Adaptive | 67,347 | −7.9 | 68.3 % | 10.9 % | 2,123 | — | 90 | 100 | 0.0 % |
| delay 1,000 · small_sim | Joint | 60,387 | −7.0 [−10.2, −4.7] | 71.1 % | 9.1 % | 2,071 | — | 177 | 100 | 0.6 % |
| delay 1,000 · small_sim | Effort | 56,712 | −6.5 [−9.7, −4.2] | 71.2 % | 6.1 % | 3,727 | 87.3 | 100 | 100 | 0.5 % |
| delay 1,000 · small_sim | Effort without D3 | 39,973 | −4.3 [−6.8, −2.6] | 79.9 % | 4.6 % | 3,095 | 92.2 | 107 | 100 | 0.5 % |
| delay 1,000 · small_sim | Effort, post hoc race-only D3 | 43,792 | −4.7 [−7.6, −2.7] | 77.9 % | 4.7 % | 4,130 | 83.5 | 95 | 100 | 0.5 % |

\* ARF timings were measured with 3 trials in parallel, so they include contention.

Reading the columns:
- **False alarms** are benign rows flagged, including "Attempted" flows. Most fall inside attack
  periods, as noted in findings Q6.4.
- **Σ flows before first flag** sums, over the dated attack periods with ≥ 100 flows, the flows that
  passed before the first one was flagged. A period that was never flagged counts all its flows.

**Paired differences in errors** (negative = effort makes fewer):

| Comparison | Δ errors [95 % CI] | Blocks better / worse (of 29) |
|---|--:|--:|
| small_sim: effort − joint | **−563 [−966, −148]** | 19 / 5 |
| small_sim: effort − incremental | −702 [−1,838, +324] | 10 / 14 |
| small_sim: effort − ARF | +1,061 [+758, +1,377] | 1 / 24 |
| micro_sim: effort − joint | +427 [−140, +1,030] | 10 / 15 |
| delay 1,000: effort − joint | −3,675 [−13,231, +5,570] | 15 / 10 |
| delay 1,000: effort − incremental | +47,214 [+33,553, +61,681] | 1 / 24 |

### What the controller did (core runs)

- **small_sim:**
  - Rows per level: cheap 148,101, medium 63,278, rich 87,621.
  - The price reached its ceiling (5.0) in the attack stretches and ended at 0.
  - Model updates were skipped on 53.5 % of rows. Statistics were updated on 41.5 % of rows and
    the ranking on 7.6 %.
  - One price-driven cut to 28 features, restored to 56 later. Each change is a model reset.
  - 12 fast switches and 1 damped re-alarm.
- **micro_sim:**
  - The price sat at its ceiling with the cheapest level still over budget, so features were halved
    56 → 28 → 14 → 8. The floor held, and every cut came after the ranker had seen both classes.
  - It then met the 50 µs budget: 49.0 µs modelled, 46.7 µs measured.
  - **Joint** kept 28 features and ran at **90 µs**, 1.8× the budget, because its R3 trigger is
    deadline misses, not the mean.
- **Determinism.** The repeat of effort on small_sim gave **identical predictions**
  (`predictions_sha256 48afa595…` in both runs) and identical decisions. Its measured µs/row
  differed: 102.2 against 98.8.

## Ablations (small_sim, each lever or repair removed)

| Variant | Errors | κ-temporal [95 % CI] | Modelled / measured µs | Δ errors vs full effort [95 % CI] | Reading |
|---|--:|---|---|--:|---|
| Full effort | 1,660 | 0.78 [0.71, 0.83] | 92 / 102 | — | |
| − B1 narrow preprocessing | 1,741 | 0.77 [0.70, 0.82] | 96 / 106 | +91 [−153, +300] | within noise |
| − B2 sampled statistics | 2,144 | 0.72 [0.61, 0.79] | 83 / 87 | +494 [+66, +886] | worse quality, and *cheaper* (it went to 28 features) |
| − B3 live ranking (frozen when narrowed) | 2,342 | 0.69 [0.58, 0.76] | 94 / 106 | +692 [+410, +1,018] | worse |
| − B4 easy-row skip | 2,426 | 0.68 [0.55, 0.77] | 92 / 95 | +757 [+324, +1,185] | worse; budget then forced a cut to 28 features |
| − B5 feature gate (floor 4, no gate) | 1,660 | 0.78 | 92 / 122 | 0 (identical predictions) | the gate never bound on small_sim |
| − price (always the richest level) | 2,472 | 0.67 [0.53, 0.76] | **142** / 154 | +822 [+454, +1,197] | over budget by 42 %, *and* worse |
| − activity signal (constant 0.5) | 2,765 | 0.64 [0.51, 0.72] | 93 / 101 | +1,103 [+709, +1,510] | same budget, effort spread evenly: worst |
| − D1 fast switch | 2,645 | 0.65 [0.50, 0.75] | 92 / 108 | +995 [+342, +1,871] | worse; flows before first flag 127 vs 96 |
| − D2 damping | 1,683 | 0.78 [0.70, 0.83] | 92 / 125 | ≈ 0 | only one alarm was damped |
| measured cost instead of modelled | 1,847 | 0.76 [0.66, 0.82] | 75 / 78 | +197 [−391, +723] | within noise; not repeatable |
| − D3 at delay 1,000 | 39,973 vs 56,712 | −4.3 vs −6.5 | 92 / 107 | **D3 hurts:** −16,739 errors without it | see below |

Measured µs for identical decisions ranged from 99 to 125 (full, repeat, without B5, without D2).
**Measured time differences of up to 25 % are noise.** The modelled column is the comparable one.

## Plain reading

**Where effort helps (small_sim, immediate labels).**
- Fewer errors than joint: −563, 95 % interval [−966, −148], better in 19 of 29 blocks.
- At about the budget: 92 µs modelled, 99–102 µs measured. Joint used 160 µs against the same
  100 µs budget.
- Against incremental, which ignores the budget at 165 µs, the gain is not significant:
  −702 [−1,838, +324].
- Several pieces matter beyond the noise of a perturbed run (about ±200 errors, judging from the
  "measured cost" and "B1" rows):
  - the activity signal;
  - the price, without which it is both over budget and worse;
  - the fast switch (D1);
  - easy-row skipping (B4);
  - the live ranking (B3);
  - sampled statistics (B2).
- Two results are surprising and need explaining before they go in a paper:
  - Skipping updates on easy rows *improves* quality: removing B4 costs 757 errors.
  - Spending the budget unevenly beats spending it evenly: removing the activity signal costs
    1,103 errors.

  One hypothesis is that fewer updates during long same-label runs keep the tree from being
  swamped by the majority label. **Unverified.**

**Where it does not help.**
- **micro_sim (50 µs):**
  - Effort meets the budget (47 µs measured). Joint does not (90 µs).
  - But effort makes *more* errors: +427, interval [−140, +1,030], so not significant. It reached
    that cost by cutting to 8 features.
  - At equal error, the comparison favours effort only on cost. On this tier there is no evidence
    it is more accurate.
- **Label delay 1,000:**
  - Effort (56.7k errors) is no better than joint (60.4k). The paired interval [−13.2k, +5.6k]
    covers 0.
  - Both are far worse than incremental (9.6k).
  - **Repair D3, as designed, makes things worse:** without it, effort makes 40.0k errors.
  - D3 muted 20,480 labels, warm-started 137 models and made 111 fast switches. Effort under D3
    still adapted 138 times (169 alarms).
  - The likely problem: replacements still displace the old model, judged on stale labels.
    **Unverified.**
  - The finding Q4 bound ("reach incremental's ~9.6k") is **not** met by any variant.
- **ARF** is still much better: 589 errors, κt 0.92, at about 13× the cost.
- **Attack onsets** are not improved. Σ flows before the first flag is 96 for effort against 66
  for joint, with 14 for repeat-last-label. Removing D1 makes it worse (127), so D1 helps relative
  to effort without it, but effort does not beat joint here.

**Within noise:** B1 narrow preprocessing; B5 (never bound on small_sim); D2 damping (one alarm);
modelled against measured cost source.

**Unverified or open:**
- Only one seed and one stretch. The evaluation slice is the slice these numbers come from.
- The micro_sim result rests on one feature-cut path.
- The modelled cost under-predicts measured time on Wednesday by about 7–10 % (more under noise).
  A per-tree-size term, or recalibration on a longer stretch, may be needed.
- The feature cut → restore cycle (each a model reset) happened once on small_sim and 3 times at
  delay 1,000. A hysteresis or "restore only in quiet stretches" rule may help. Untested.
- R4 (low-accuracy retraining) is not part of effort.
- The full-stream gateway case that motivated B1–B5 (findings Q2, Q3) was not run here.
- The delay-10,000 and partial-coverage cases were not run.

## Changes after seeing Wednesday

- **No default was changed after any Wednesday run.** Everything in the core, delay and ablation
  runs is as designed before Wednesday.
- **Decided on Tuesday rows (a development slice), before any Wednesday run:**
  - adding a per-feature predict term to the cost model (inference grows with features);
  - ranking every row of a class the ranker has seen fewer than 200 times. On Tuesday micro_sim the
    1-in-20 sampling left the B5 gate shut.
  - Tuesday is not held out either. The calibration used Tuesday as well.
- **One option added after seeing the Wednesday delay-1,000 result:** `effort.delay_race_only`
  (default **off**). With delayed labels, a replacement may replace the old model only once it
  beats it on the last 20 arrived labels; it is discarded after 2,000 rows otherwise.
  - It reduced errors from 56.7k to 43.8k, but stayed worse than simply removing D3 (40.0k).
  - It is post hoc, tested on the same slice, and **must not be reported as a result** without a
    held-out stretch.
- **For the paper:** fix the configuration, then run Thursday/Friday (and ideally the full stream),
  ≥ 3 seeds, `--workers 1`. Protocol v2 (`protocol/protocol.yaml`) has the grids: `core`, `labels`
  and `effort_ablations`.
