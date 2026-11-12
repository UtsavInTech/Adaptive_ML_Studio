# Research testbed report — protocol

6 trials from 2 experiment runs. Scores are after warm-up. κ-temporal is accuracy beyond repeating the previous row's label (0 = no better). Intervals are 95 % block-bootstrap intervals (10,000-row blocks, 1000 resamples, counts summed over seeds).

Device tiers other than `standard` are **simulated with placeholder budgets**. Energy is not measured.

## R5 on a memory-limited tier

| Setting | Method | Tier | κ-temporal [95 % CI] | Macro-F1 | Attack recall % | False alarms % | Mean µs/row | p99 µs | Model changes |
|---|---|---|---|--:|--:|--:|--:|--:|--:|
| memory_full | Joint controller | memory_sim | 0.574 [0.471, 0.660] | 0.992 | 98.5 | 0.3 | 106.6 | 176.1 | 194 |
| memory_without_R5 | Joint controller | memory_sim | 0.753 [0.696, 0.795] | 0.996 | 99.2 | 0.2 | 147.7 | 209.8 | 168 |

## Figures


## Methods compared over stream segments (Friedman, Nemenyi)

Not enough methods or segments in these runs.

## Joint controller decisions

| Setting | Tier | Seed | Rows in lightweight mode | Final features · stride · narrow | Peak model KB | Memory checks over budget | Actions |
|---|---|--:|--:|---|--:|--:|---|
| memory_full | memory_sim | 11 | 105,515 | 14 · 1 · no | 392 | 19 of 2118 | R1_DRIFT ×179, R2_DRIFT ×13, R5_DROP_REPLACEMENT ×9, R5_FRESH_MODEL ×8, R5_SHRINK_MODEL_28_TO_14 ×1, R5_SHRINK_MODEL_56_TO_28 ×1 |
| memory_full | memory_sim | 23 | 105,515 | 14 · 1 · no | 392 | 19 of 2118 | R1_DRIFT ×179, R2_DRIFT ×13, R5_DROP_REPLACEMENT ×9, R5_FRESH_MODEL ×8, R5_SHRINK_MODEL_28_TO_14 ×1, R5_SHRINK_MODEL_56_TO_28 ×1 |
| memory_full | memory_sim | 37 | 105,515 | 14 · 1 · no | 392 | 19 of 2118 | R1_DRIFT ×179, R2_DRIFT ×13, R5_DROP_REPLACEMENT ×9, R5_FRESH_MODEL ×8, R5_SHRINK_MODEL_28_TO_14 ×1, R5_SHRINK_MODEL_56_TO_28 ×1 |
| memory_without_R5 | memory_sim | 11 | 1,706,975 | 56 · 1 · no | 1377 | 960 of 2099 | R1_DRIFT ×1, R2_DRIFT ×170 |
| memory_without_R5 | memory_sim | 23 | 1,706,975 | 56 · 1 · no | 1377 | 960 of 2099 | R1_DRIFT ×1, R2_DRIFT ×170 |
| memory_without_R5 | memory_sim | 37 | 1,706,975 | 56 · 1 · no | 1377 | 960 of 2099 | R1_DRIFT ×1, R2_DRIFT ×170 |

## Reproducibility

No configuration was run more than once in these runs. Re-run one with `adaptiveml.experiments.rerun` (or run the protocol twice) to check reproducibility.

## Runs

- `memory_full`: `20261111-194052-088567-experiment-protocol-v1-memory-full`
- `memory_without_R5`: `20261111-195427-125877-experiment-protocol-v1-memory-without-r5`
