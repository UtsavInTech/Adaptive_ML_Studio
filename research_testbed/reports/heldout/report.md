# Research testbed report — heldout

32 trials from 4 experiment runs. Scores are after warm-up. κ-temporal is accuracy beyond repeating the previous row's label (0 = no better). Intervals are 95 % block-bootstrap intervals (10,000-row blocks, 1000 resamples, counts summed over seeds).

Device tiers other than `standard` are **simulated with placeholder budgets**. Energy is not measured.

## Figures


## Methods compared over stream segments (Friedman, Nemenyi)

Not enough methods or segments in these runs.

## Errors, onsets and cost against the budget

| Setting | Method | Tier | Errors | κ-temporal [95 % CI] | Attack recall % | False alarms % | Σ flows before first flag (onsets) | Modelled µs/row | Measured µs/row | Budget µs/row | Rows over deadline % |
|---|---|---|--:|---|--:|--:|--:|--:|--:|--:|--:|
| friday | Repeat last label | small_sim | 5,104 | 0.000 [0.000, 0.000] | 99.0 | 0.9 | 8 | — | 62.1 | — | 0.0 |
| friday | Repeat last label | micro_sim | 5,104 | 0.000 [0.000, 0.000] | 99.0 | 0.9 | 8 | — | 62.1 | — | 0.0 |
| friday | Incremental | small_sim | 3,566 | 0.302 [-0.261, 0.633] | 98.8 | 0.2 | 2,300 | — | 151.8 | — | 0.5 |
| friday | Incremental | micro_sim | 74,174 | -12.255 [-19.677, -6.298] | 85.7 | 10.9 | 27,156 | — | 108.6 | — | 1.3 |
| friday | Joint controller | small_sim | 1,982 | 0.612 [0.481, 0.715] | 99.6 | 0.4 | 164 | — | 142.3 | 100 | 0.5 |
| friday | Joint controller | micro_sim | 2,597 | 0.491 [0.357, 0.610] | 99.4 | 0.4 | 170 | — | 76.1 | 50 | 0.6 |
| friday | Budgeted effort controller | small_sim | 1,632 | 0.680 [0.561, 0.775] | 99.7 | 0.3 | 43 | 89.9 | 88.5 | 100 | 0.3 |
| friday | Budgeted effort controller | micro_sim | 2,002 | 0.608 [0.472, 0.721] | 99.6 | 0.4 | 48 | 59.6 | 57.0 | 50 | 0.4 |
| thursday | Repeat last label | small_sim | 6,188 | 0.000 [0.000, 0.000] | 95.7 | 1.1 | 3 | — | 61.9 | — | 0.0 |
| thursday | Repeat last label | micro_sim | 6,188 | 0.000 [0.000, 0.000] | 95.7 | 1.1 | 3 | — | 62.2 | — | 0.0 |
| thursday | Incremental | small_sim | 4,119 | 0.336 [-0.384, 0.700] | 95.0 | 0.2 | 2,245 | — | 149.4 | — | 0.6 |
| thursday | Incremental | micro_sim | 32,961 | -4.325 [-6.311, -2.498] | 58.1 | 1.0 | 2,585 | — | 105.5 | — | 2.1 |
| thursday | Joint controller | small_sim | 2,327 | 0.624 [0.563, 0.675] | 97.6 | 0.2 | 53 | — | 153.3 | 100 | 0.6 |
| thursday | Joint controller | micro_sim | 3,698 | 0.402 [0.345, 0.453] | 97.6 | 0.7 | 43 | — | 97.1 | 50 | 0.6 |
| thursday | Budgeted effort controller | small_sim | 2,377 | 0.616 [0.556, 0.664] | 97.5 | 0.2 | 99 | 83.7 | 74.8 | 100 | 0.3 |
| thursday | Budgeted effort controller | micro_sim | 2,331 | 0.623 [0.564, 0.667] | 97.8 | 0.3 | 53 | 59.8 | 47.9 | 50 | 0.3 |

## Budgeted effort controller

| Setting | Tier | Seed | Rows per level | Mean modelled / measured µs vs budget | Final · peak price | Updates skipped % | Statistics rows % | Ranking rows % | Final features | Fast switches · damped · muted · warm starts | Actions |
|---|---|--:|---|---|---|--:|--:|--:|--:|---|---|
| friday | small_sim | 11 | cheap 330,992 · medium 106,028 · rich 109,537 | 89.9 / 87.8 vs 100 | 0.00 · 5.00 | 63.9 | 33.0 | 7.0 | 56 | 8 · 3 · 0 · 0 | R1_DRIFT ×21, R2_DRIFT ×19 |
| friday | small_sim | 23 | cheap 330,992 · medium 106,028 · rich 109,537 | 89.9 / 87.5 vs 100 | 0.00 · 5.00 | 63.9 | 33.0 | 7.0 | 56 | 8 · 3 · 0 · 0 | R1_DRIFT ×21, R2_DRIFT ×19 |
| friday | small_sim | 37 | cheap 330,992 · medium 106,028 · rich 109,537 | 89.9 / 90.4 vs 100 | 0.00 · 5.00 | 63.9 | 33.0 | 7.0 | 56 | 8 · 3 · 0 · 0 | R1_DRIFT ×21, R2_DRIFT ×19 |
| friday | micro_sim | 11 | cheap 439,748 · medium 100,368 · rich 6,441 | 59.6 / 55.8 vs 50 | 2.50 · 5.00 | 65.5 | 15.9 | 6.0 | 28 | 0 · 4 · 0 · 0 | PRICE_HALVE_FEATURES_56_TO_28 ×1, R1_DRIFT ×3, R2_DRIFT ×42 |
| friday | micro_sim | 23 | cheap 439,748 · medium 100,368 · rich 6,441 | 59.6 / 57.5 vs 50 | 2.50 · 5.00 | 65.5 | 15.9 | 6.0 | 28 | 0 · 4 · 0 · 0 | PRICE_HALVE_FEATURES_56_TO_28 ×1, R1_DRIFT ×3, R2_DRIFT ×42 |
| friday | micro_sim | 37 | cheap 439,748 · medium 100,368 · rich 6,441 | 59.6 / 57.7 vs 50 | 2.50 · 5.00 | 65.5 | 15.9 | 6.0 | 28 | 0 · 4 · 0 · 0 | PRICE_HALVE_FEATURES_56_TO_28 ×1, R1_DRIFT ×3, R2_DRIFT ×42 |
| thursday | small_sim | 11 | cheap 256,755 · medium 67,062 · rich 37,259 | 83.7 / 75.0 vs 100 | 0.00 · 5.00 | 69.7 | 23.9 | 6.5 | 56 | 7 · 5 · 0 · 0 | PRICE_HALVE_FEATURES_56_TO_28 ×1, R1_DRIFT ×10, R2_DRIFT ×47, RELAX_FEATURES_28_TO_56 ×1 |
| thursday | small_sim | 23 | cheap 256,755 · medium 67,062 · rich 37,259 | 83.7 / 74.9 vs 100 | 0.00 · 5.00 | 69.7 | 23.9 | 6.5 | 56 | 7 · 5 · 0 · 0 | PRICE_HALVE_FEATURES_56_TO_28 ×1, R1_DRIFT ×10, R2_DRIFT ×47, RELAX_FEATURES_28_TO_56 ×1 |
| thursday | small_sim | 37 | cheap 256,755 · medium 67,062 · rich 37,259 | 83.7 / 74.6 vs 100 | 0.00 · 5.00 | 69.7 | 23.9 | 6.5 | 56 | 7 · 5 · 0 · 0 | PRICE_HALVE_FEATURES_56_TO_28 ×1, R1_DRIFT ×10, R2_DRIFT ×47, RELAX_FEATURES_28_TO_56 ×1 |
| thursday | micro_sim | 11 | cheap 281,487 · medium 21,943 · rich 57,646 | 59.8 / 47.9 vs 50 | 0.00 · 5.00 | 71.9 | 26.6 | 6.2 | 14 | 0 · 7 · 0 · 0 | PRICE_HALVE_FEATURES_28_TO_14 ×1, PRICE_HALVE_FEATURES_56_TO_28 ×1, R2_DRIFT ×59 |
| thursday | micro_sim | 23 | cheap 281,487 · medium 21,943 · rich 57,646 | 59.8 / 47.9 vs 50 | 0.00 · 5.00 | 71.9 | 26.6 | 6.2 | 14 | 0 · 7 · 0 · 0 | PRICE_HALVE_FEATURES_28_TO_14 ×1, PRICE_HALVE_FEATURES_56_TO_28 ×1, R2_DRIFT ×59 |
| thursday | micro_sim | 37 | cheap 281,487 · medium 21,943 · rich 57,646 | 59.8 / 48.0 vs 50 | 0.00 · 5.00 | 71.9 | 26.6 | 6.2 | 14 | 0 · 7 · 0 · 0 | PRICE_HALVE_FEATURES_28_TO_14 ×1, PRICE_HALVE_FEATURES_56_TO_28 ×1, R2_DRIFT ×59 |

## Controller decisions

| Setting | Method | Tier | Seed | Rows in lightweight mode | Final features · stride · narrow | Peak model KB | Memory checks over budget | Actions |
|---|---|---|--:|--:|---|--:|--:|---|
| friday | Joint controller | small_sim | 11 | 546,556 | 56 · 1 · no | 1030 | 0 of 547 | R2_DRIFT ×41 |
| friday | Joint controller | small_sim | 23 | 546,556 | 56 · 1 · no | 1030 | 0 of 547 | R2_DRIFT ×41 |
| friday | Joint controller | small_sim | 37 | 459,412 | 56 · 1 · no | 988 | 0 of 547 | R1_DRIFT ×7, R2_DRIFT ×32, R3_HALVE_FEATURES_28_TO_14 ×1, R3_HALVE_FEATURES_56_TO_28 ×1, R3_RELAX_FEATURES_14_TO_28 ×1, R3_RELAX_FEATURES_28_TO_56 ×1 |
| friday | Joint controller | micro_sim | 11 | 546,556 | 28 · 1 · yes | 497 | 0 of 547 | R2_DRIFT ×45, R3_HALVE_FEATURES_56_TO_28 ×1 |
| friday | Joint controller | micro_sim | 23 | 498,463 | 24 · 1 · yes | 775 | 0 of 547 | R1_DRIFT ×7, R2_DRIFT ×46, R3_HALVE_FEATURES_14_TO_7 ×1, R3_HALVE_FEATURES_28_TO_14 ×2, R3_HALVE_FEATURES_56_TO_28 ×1, R3_HALVE_FEATURES_7_TO_3 ×1, R3_RELAX_FEATURES_12_TO_24 ×1, R3_RELAX_FEATURES_14_TO_28 ×1, R3_RELAX_FEATURES_3_TO_6 ×1, R3_RELAX_FEATURES_6_TO_12 ×1 |
| friday | Joint controller | micro_sim | 37 | 415,131 | 28 · 1 · yes | 411 | 0 of 547 | R1_DRIFT ×3, R2_DRIFT ×56, R3_HALVE_FEATURES_14_TO_7 ×1, R3_HALVE_FEATURES_28_TO_14 ×3, R3_HALVE_FEATURES_56_TO_28 ×1, R3_RELAX_FEATURES_14_TO_28 ×3, R3_RELAX_FEATURES_7_TO_14 ×1 |
| friday | Budgeted effort controller | small_sim | 11 | 156,377 | 56 · 1 · yes | 1203 | 0 of 547 | R1_DRIFT ×21, R2_DRIFT ×19 |
| friday | Budgeted effort controller | small_sim | 23 | 156,377 | 56 · 1 · yes | 1203 | 0 of 547 | R1_DRIFT ×21, R2_DRIFT ×19 |
| friday | Budgeted effort controller | small_sim | 37 | 156,377 | 56 · 1 · yes | 1203 | 0 of 547 | R1_DRIFT ×21, R2_DRIFT ×19 |
| friday | Budgeted effort controller | micro_sim | 11 | 463,513 | 28 · 1 · yes | 602 | 0 of 547 | PRICE_HALVE_FEATURES_56_TO_28 ×1, R1_DRIFT ×3, R2_DRIFT ×42 |
| friday | Budgeted effort controller | micro_sim | 23 | 463,513 | 28 · 1 · yes | 602 | 0 of 547 | PRICE_HALVE_FEATURES_56_TO_28 ×1, R1_DRIFT ×3, R2_DRIFT ×42 |
| friday | Budgeted effort controller | micro_sim | 37 | 463,513 | 28 · 1 · yes | 602 | 0 of 547 | PRICE_HALVE_FEATURES_56_TO_28 ×1, R1_DRIFT ×3, R2_DRIFT ×42 |
| thursday | Joint controller | small_sim | 11 | 361,075 | 56 · 1 · no | 1033 | 0 of 362 | R2_DRIFT ×60 |
| thursday | Joint controller | small_sim | 23 | 361,075 | 56 · 1 · no | 1033 | 0 of 362 | R2_DRIFT ×60 |
| thursday | Joint controller | small_sim | 37 | 361,075 | 56 · 1 · no | 1033 | 0 of 362 | R2_DRIFT ×60 |
| thursday | Joint controller | micro_sim | 11 | 271,653 | 28 · 1 · yes | 582 | 0 of 362 | R1_DRIFT ×1, R2_DRIFT ×65, R3_HALVE_FEATURES_28_TO_14 ×1, R3_HALVE_FEATURES_56_TO_28 ×1, R3_RELAX_FEATURES_14_TO_28 ×1 |
| thursday | Joint controller | micro_sim | 23 | 361,075 | 28 · 1 · yes | 1033 | 1 of 363 | R2_DRIFT ×57, R3_HALVE_FEATURES_56_TO_28 ×1, R5_FRESH_MODEL ×1 |
| thursday | Joint controller | micro_sim | 37 | 361,075 | 28 · 1 · yes | 972 | 0 of 362 | R2_DRIFT ×61, R3_HALVE_FEATURES_56_TO_28 ×1 |
| thursday | Budgeted effort controller | small_sim | 11 | 91,746 | 56 · 1 · yes | 1376 | 0 of 362 | PRICE_HALVE_FEATURES_56_TO_28 ×1, R1_DRIFT ×10, R2_DRIFT ×47, RELAX_FEATURES_28_TO_56 ×1 |
| thursday | Budgeted effort controller | small_sim | 23 | 91,746 | 56 · 1 · yes | 1376 | 0 of 362 | PRICE_HALVE_FEATURES_56_TO_28 ×1, R1_DRIFT ×10, R2_DRIFT ×47, RELAX_FEATURES_28_TO_56 ×1 |
| thursday | Budgeted effort controller | small_sim | 37 | 91,746 | 56 · 1 · yes | 1376 | 0 of 362 | PRICE_HALVE_FEATURES_56_TO_28 ×1, R1_DRIFT ×10, R2_DRIFT ×47, RELAX_FEATURES_28_TO_56 ×1 |
| thursday | Budgeted effort controller | micro_sim | 11 | 313,923 | 14 · 1 · yes | 497 | 0 of 362 | PRICE_HALVE_FEATURES_28_TO_14 ×1, PRICE_HALVE_FEATURES_56_TO_28 ×1, R2_DRIFT ×59 |
| thursday | Budgeted effort controller | micro_sim | 23 | 313,923 | 14 · 1 · yes | 497 | 0 of 362 | PRICE_HALVE_FEATURES_28_TO_14 ×1, PRICE_HALVE_FEATURES_56_TO_28 ×1, R2_DRIFT ×59 |
| thursday | Budgeted effort controller | micro_sim | 37 | 313,923 | 14 · 1 · yes | 497 | 0 of 362 | PRICE_HALVE_FEATURES_28_TO_14 ×1, PRICE_HALVE_FEATURES_56_TO_28 ×1, R2_DRIFT ×59 |

## Reproducibility

No configuration was run more than once in these runs. Re-run one with `adaptiveml.experiments.rerun` (or run the protocol twice) to check reproducibility.

## Runs

- `thursday`: `20261112-094305-412948-experiment-held-out-thursday-controllers`
- `thursday`: `20261112-094008-815225-experiment-held-out-thursday-references`
- `friday`: `20261112-095616-360126-experiment-held-out-friday-controllers`
- `friday`: `20261112-095151-907292-experiment-held-out-friday-references`
