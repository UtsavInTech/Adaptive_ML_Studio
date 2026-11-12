# Device run — Darwin arm64 (utsavs-MacBook-Air)

- Measured on: Darwin arm64 (utsavs-MacBook-Air) (Apple M1, 8.6 GB RAM, macOS-27.2-arm64-arm-64bit)
- Real device: NO — rehearsal on a machine that is not a single-board computer
- Slice: 40,000 Wednesday rows with two attacks (the Studio's demo slice), rows 730,000 + 40,000; seeds [11]
- Cost of a row in the calibration run on this machine: 82.8 µs
- CPU governor: not reported; temperature before None °C, after None °C
- Budgets are set by a rule from the calibration run (placeholder budgets). Energy was not measured.

| Method | Budget | Seed | Accuracy | κ-temporal | Mean µs/row | p95 µs/row | Budget µs | Mean vs budget |
|---|---|--:|--:|--:|--:|--:|--:|--:|
| no_change | standard | 11 | 93.76 % | 0.00 | 63 | 66 | none | — |
| incremental | standard | 11 | 98.16 % | 0.70 | 145 | 182 | none | — |
| adaptive | standard | 11 | 99.12 % | 0.86 | 126 | 148 | none | — |
| joint | device_small | 11 | 99.19 % | 0.87 | 173 | 197 | 103 | +67 % |
| effort | device_small | 11 | 99.06 % | 0.85 | 116 | 203 | 103 | +12 % |
| joint | device_micro | 11 | 99.23 % | 0.88 | 102 | 187 | 52 | +97 % |
| effort | device_micro | 11 | 99.01 % | 0.84 | 68 | 144 | 52 | +32 % |
