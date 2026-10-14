# Local stress validation results — 14 October 2026

These runs used the final script, project engine, and local catalog-verified Kaggle snapshots. They were executed sequentially. Wall-time policy decisions remain sensitive to other MacBook activity; these are local observations, not controlled performance benchmarks.

| Dataset / run | Rows | Flipped labels | Before accuracy | Window accuracy | After accuracy | Rows >15 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| elec2 / clean | 45312 | 0 | 85.87% | 80.40% | 82.13% | 1 |
| elec2 / bomb | 45312 | 200 | 85.69% | 51.00% | 81.23% | 1 |
| occupancy / clean | 20560 | 0 | 98.02% | 99.60% | 98.30% | 0 |
| occupancy / bomb | 20560 | 200 | 97.73% | 57.80% | 98.26% | 2 |
| elec2 / fault | 3000 | 200 | 89.00% | 52.40% | 85.80% | 1 |

Window accuracy uses observed (possibly corrupted) labels. Full runs use recommended warm-ups; the 3,000-row fault smoke test uses warm-up 500 and is not directly comparable. After-window data retains the feature shift.

The adversarial runs fell below the 70% target during corruption. Feature reduction and model refreshes occurred, but neither accuracy nor latency is universally guaranteed. Clean and adversarial runs can choose different feature counts because R2 responds to measured wall time.

## Saved evidence

- [elec2 / clean](/Users/utsavsingh/Documents/Adaptive_ML_Studio/results/stress/20261014T142337Z-29d39a14/summary.json): {'R2_HALVE_8_TO_4': 1, 'R1_DRIFT': 41, 'R3_LOW_ACCURACY_REFRESH': 1, 'R4_COOLDOWN': 45}
- [elec2 / bomb](/Users/utsavsingh/Documents/Adaptive_ML_Studio/results/stress/20261014T142341Z-a97d0996/summary.json): {'R2_HALVE_8_TO_4': 1, 'R1_DRIFT': 44, 'R4_COOLDOWN': 1040, 'R3_LOW_ACCURACY_REFRESH': 3}
- [occupancy / clean](/Users/utsavsingh/Documents/Adaptive_ML_Studio/results/stress/20261014T142344Z-3fcafe24/summary.json): {'R1_DRIFT': 9}
- [occupancy / bomb](/Users/utsavsingh/Documents/Adaptive_ML_Studio/results/stress/20261014T142346Z-fa78d8a2/summary.json): {'R2_HALVE_5_TO_2': 1, 'R2_HALVE_2_TO_1': 1, 'R1_DRIFT': 10, 'R4_COOLDOWN': 323, 'R3_LOW_ACCURACY_REFRESH': 1}
- [elec2 / fault](/Users/utsavsingh/Documents/Adaptive_ML_Studio/results/stress/20261014T142347Z-1cab52f3/summary.json): {'R2_HALVE_8_TO_4': 1, 'R4_COOLDOWN': 572, 'R3_LOW_ACCURACY_REFRESH': 1}

  At index 1500, the intentional 20 ms fault produced C_pre=25.026 ms and C_total=25.534 ms; action `R2_HALVE_8_TO_4` left 4 active features.


## Checks

- Backend suite: 95 passed (before the final additional CLI integration test).
- Final harness suite: 7 passed, including stage accounting, exact corruption count, cooldown behavior, both engines, invalid inputs and a portable CLI run.
- All five final run artifacts checked for one record per input row, exact flip counts and additive timing accounting.
- Python compilation and git whitespace checks passed.

The existing UI and production resource governor were not changed by this harness addition. See [the run guide](stress_test_mvp.md) for commands, policy definitions and measurement limits.
