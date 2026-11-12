## Overall (after warm-up)

| Method | Accuracy % | κ | κ-temporal | Macro-F1 | Attack recall % | False alarms % (benign) | Mean µs | p99 µs | Peak MB | Model changes |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Adaptive pipeline · gateway_sim | 99.13 | 0.976 | 0.329 | 0.988 | 98.5 | 0.65 | 151.8 | 347.4 | 943 | 288 |
| Adaptive pipeline | 99.10 | 0.975 | 0.307 | 0.988 | 98.5 | 0.69 | 111.3 | 230.2 | 161 | 302 |
| Joint controller · gateway_sim | 97.49 | 0.931 | -0.937 | 0.966 | 94.5 | 1.53 | 40.1 | 139.5 | 164 | 315 |
| Joint controller · gateway_sim · without gating | 97.49 | 0.931 | -0.934 | 0.966 | 94.6 | 1.54 | 78.6 | 357.6 | 144 | 321 |
| Joint controller · gateway_sim · without r2 | 97.45 | 0.930 | -0.968 | 0.965 | 94.4 | 1.55 | 70.4 | 258.9 | 161 | 319 |
| Joint controller · gateway_sim · without r3 | 99.69 | 0.991 | 0.760 | 0.996 | 99.2 | 0.14 | 298.1 | 664.0 | 158 | 171 |
| Joint controller · gateway_sim · without r5 | 98.07 | 0.947 | -0.491 | 0.974 | 95.9 | 1.20 | 37.0 | 87.9 | 237 | 355 |
| Joint controller | 99.53 | 0.987 | 0.641 | 0.994 | 98.7 | 0.20 | 208.6 | 390.3 | 215 | 170 |

Accuracy of repeating the previous row's label over the same rows: **98.70 %** (the reference for κ-temporal).

## Share of each original label flagged as an attack (%)

For an attack type this is its recall; for benign traffic it is the false-alarm rate.

| Original label | Counted as | Rows | Adaptive pipeline · gateway_sim | Adaptive pipeline | Joint controller · gateway_sim | Joint controller · gateway_sim · without gating | Joint controller · gateway_sim · without r2 | Joint controller · gateway_sim · without r3 | Joint controller · gateway_sim · without r5 | Joint controller |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Botnet | attack | 736 | 32.6 | 31.0 | 66.7 | 60.3 | 60.3 | 72.7 | 73.9 | 81.4 |
| DDoS | attack | 95,144 | 99.3 | 99.3 | 97.8 | 98.0 | 98.0 | 99.7 | 98.7 | 99.6 |
| DoS GoldenEye | attack | 7,567 | 96.4 | 96.0 | 95.0 | 95.0 | 95.0 | 97.6 | 97.4 | 95.8 |
| DoS Hulk | attack | 158,468 | 99.6 | 99.5 | 98.3 | 98.3 | 98.3 | 99.5 | 98.7 | 99.3 |
| DoS Slowhttptest | attack | 1,740 | 82.1 | 82.5 | 40.6 | 42.8 | 42.8 | 84.4 | 71.7 | 87.1 |
| DoS Slowloris | attack | 3,859 | 77.0 | 77.1 | 42.5 | 39.3 | 39.3 | 97.0 | 62.7 | 92.9 |
| FTP-Patator | attack | 3,972 | 89.4 | 94.9 | 58.6 | 56.9 | 56.7 | 98.5 | 77.6 | 98.6 |
| Heartbleed | attack | 11 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Infiltration | attack | 36 | 5.6 | 8.3 | 11.1 | 13.9 | 13.9 | 2.8 | 13.9 | 2.8 |
| Infiltration - Portscan | attack | 71,767 | 96.9 | 96.9 | 81.7 | 81.8 | 80.7 | 97.9 | 85.7 | 96.0 |
| Portscan | attack | 159,066 | 99.3 | 99.3 | 98.0 | 98.1 | 98.1 | 99.7 | 98.1 | 99.5 |
| SSH-Patator | attack | 2,961 | 82.0 | 82.3 | 66.0 | 68.4 | 68.4 | 95.5 | 73.4 | 94.4 |
| Web Attack - Brute Force | attack | 73 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Web Attack - SQL Injection | attack | 13 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Web Attack - XSS | attack | 18 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| BENIGN | benign | 1,581,566 | 0.6 | 0.7 | 1.5 | 1.5 | 1.5 | 0.1 | 1.2 | 0.2 |
| Botnet - Attempted | benign | 4,067 | 3.6 | 3.3 | 2.7 | 2.6 | 2.6 | 1.6 | 2.6 | 1.7 |
| DoS GoldenEye - Attempted | benign | 80 | 48.8 | 48.8 | 75.0 | 75.0 | 75.0 | 0.0 | 53.8 | 0.0 |
| DoS Hulk - Attempted | benign | 581 | 2.2 | 3.1 | 4.0 | 6.2 | 6.2 | 1.2 | 4.5 | 0.5 |
| DoS Slowhttptest - Attempted | benign | 3,368 | 0.1 | 0.1 | 0.1 | 0.3 | 0.3 | 0.0 | 0.1 | 0.0 |
| DoS Slowloris - Attempted | benign | 1,847 | 4.3 | 5.3 | 28.6 | 26.9 | 26.9 | 0.1 | 39.0 | 0.2 |
| FTP-Patator - Attempted | benign | 12 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Infiltration - Attempted | benign | 45 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| SSH-Patator - Attempted | benign | 27 | 0.0 | 0.0 | 29.6 | 3.7 | 3.7 | 0.0 | 3.7 | 0.0 |
| Web Attack - Brute Force - Attempted | benign | 1,292 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.1 | 0.0 | 0.0 |
| Web Attack - SQL Injection - Attempted | benign | 5 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Web Attack - XSS - Attempted | benign | 655 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Cost per row after warm-up, by the review's terms (µs)

| Method | C_pre | C_fs | C_inf | C_drift | C_upd | C_ret | C_ctrl | unattributed | total |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Adaptive pipeline · gateway_sim | 97.46 | 18.55 | 7.59 | 2.49 | 16.30 | 0.59 | 7.35 | 1.45 | 151.78 |
| Adaptive pipeline | 72.82 | 13.81 | 5.19 | 1.76 | 11.66 | 0.36 | 4.67 | 1.07 | 111.34 |
| Joint controller · gateway_sim | 10.38 | 0.75 | 10.16 | 2.93 | 7.49 | 1.35 | 4.90 | 2.14 | 40.12 |
| Joint controller · gateway_sim · without gating | 20.22 | 1.44 | 19.74 | 5.86 | 14.64 | 2.82 | 9.95 | 3.90 | 78.56 |
| Joint controller · gateway_sim · without r2 | 18.40 | 1.31 | 17.57 | 5.31 | 13.10 | 2.29 | 8.96 | 3.46 | 70.40 |
| Joint controller · gateway_sim · without r3 | 104.51 | 24.48 | 24.14 | 2.79 | 131.97 | 0.02 | 5.72 | 4.46 | 298.08 |
| Joint controller · gateway_sim · without r5 | 8.10 | 0.60 | 7.22 | 2.17 | 11.52 | 1.06 | 3.52 | 2.77 | 36.96 |
| Joint controller | 76.88 | 17.61 | 18.33 | 1.94 | 83.43 | 3.95 | 3.01 | 3.42 | 208.57 |

C_comm is not applicable: every stage runs in one local process.

## Joint controller decisions

| Run | Rules | Resource checks | Rows in lightweight mode | Final features · stride · narrow | Actions |
|---|---|---|--:|---|---|
| Joint controller · gateway_sim | R1 R2 R3 R4 R5 | on | 7,980 | 4 · 4 · yes | R1_DRIFT ×432, R2_DRIFT ×4, R3_AT_MINIMUM ×26, R3_HALVE_FEATURES_14_TO_7 ×1, R3_HALVE_FEATURES_28_TO_14 ×1, R3_HALVE_FEATURES_56_TO_28 ×1, R3_HALVE_FEATURES_7_TO_4 ×1, R3_UPDATE_EVERY_2 ×1, R3_UPDATE_EVERY_4 ×1, R4_RETRAIN ×18 |
| Joint controller · gateway_sim · without gating | R1 R2 R3 R4 R5 | off | 0 | 4 · 4 · yes | R1_DRIFT ×431, R3_AT_MINIMUM ×804, R3_HALVE_FEATURES_14_TO_7 ×1, R3_HALVE_FEATURES_28_TO_14 ×1, R3_HALVE_FEATURES_56_TO_28 ×1, R3_HALVE_FEATURES_7_TO_4 ×1, R3_UPDATE_EVERY_2 ×1, R3_UPDATE_EVERY_4 ×1, R4_RETRAIN ×19 |
| Joint controller · gateway_sim · without r2 | R1 R3 R4 R5 | on | 0 | 4 · 4 · yes | R1_DRIFT ×429, R3_AT_MINIMUM ×344, R3_HALVE_FEATURES_14_TO_7 ×1, R3_HALVE_FEATURES_28_TO_14 ×1, R3_HALVE_FEATURES_56_TO_28 ×1, R3_HALVE_FEATURES_7_TO_4 ×1, R3_UPDATE_EVERY_2 ×1, R3_UPDATE_EVERY_4 ×1, R4_DEFERRED_RESOURCES_TIGHT ×8, R4_RETRAIN ×13 |
| Joint controller · gateway_sim · without r3 | R1 R2 R4 R5 | on | 2,098,975 | 56 · 1 · no | R2_DRIFT ×174 |
| Joint controller · gateway_sim · without r5 | R1 R2 R3 R4 | on | 9,227 | 4 · 2 · yes | R1_DRIFT ×399, R3_HALVE_FEATURES_14_TO_7 ×1, R3_HALVE_FEATURES_28_TO_14 ×1, R3_HALVE_FEATURES_56_TO_28 ×1, R3_HALVE_FEATURES_7_TO_4 ×1, R3_UPDATE_EVERY_2 ×1, R4_RETRAIN ×9 |
| Joint controller | R1 R2 R3 R4 R5 | on | 0 | 56 · 1 · no | R1_DRIFT ×173 |

## Each dated attack period: recall % · flows of that attack before the first was flagged

| # | Attack period | Flows | Adaptive pipeline · gateway_sim | Adaptive pipeline | Joint controller · gateway_sim | Joint controller · gateway_sim · without gating | Joint controller · gateway_sim · without r2 | Joint controller · gateway_sim · without r3 | Joint controller · gateway_sim · without r5 | Joint controller |
|--:|---|--:|---|---|---|---|---|---|---|---|
| 1 | FTP-Patator (rows 392,025–456,914) | 3,972 | 89 · 13 | 95 · 13 | 59 · 8 | 57 · 8 | 57 · 8 | 99 · 2 | 78 · 5 | 99 · 2 |
| 2 | SSH-Patator (rows 568,617–619,012) | 2,960 | 82 · 12 | 82 · 12 | 66 · 5 | 68 · 9 | 68 · 9 | 96 · 3 | 73 · 3 | 94 · 3 |
| 3 | SSH-Patator (rows 648,624–648,624) | 1 | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never |
| 4 | DoS Slowloris (rows 734,892–758,098) | 3,859 | 77 · 15 | 77 · 21 | 43 · 39 | 39 · 312 | 39 · 312 | 97 · 14 | 63 · 26 | 93 · 48 |
| 5 | DoS Slowhttptest (rows 762,135–784,262) | 1,740 | 82 · 16 | 82 · 7 | 41 · 137 | 43 · 153 | 43 · 153 | 84 · 51 | 72 · 115 | 87 · 19 |
| 6 | DoS Hulk (rows 791,449–962,827) | 158,468 | 100 · 16 | 99 · 21 | 98 · 9 | 98 · 9 | 98 · 9 | 100 · 6 | 99 · 78 | 99 · 6 |
| 7 | DoS GoldenEye (rows 969,085–982,739) | 7,567 | 96 · 13 | 96 · 14 | 95 · 57 | 95 · 57 | 95 · 57 | 98 · 14 | 97 · 96 | 96 · 161 |
| 8 | Heartbleed (rows 1,121,659–1,141,665) | 11 | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never |
| 9 | Web Attack - Brute Force (rows 1,202,815–1,237,556) | 73 | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never |
| 10 | Web Attack - XSS (rows 1,245,167–1,254,739) | 18 | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never |
| 11 | Web Attack - SQL Injection (rows 1,254,953–1,260,222) | 13 | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never |
| 12 | Infiltration - Portscan (rows 1,354,794–1,355,961) | 955 | 89 · 22 | 88 · 28 | 33 · 635 | 31 · 647 | 31 · 647 | 97 · 21 | 61 · 353 | 80 · 193 |
| 13 | Infiltration (rows 1,368,155–1,368,155) | 1 | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never |
| 14 | Infiltration (rows 1,372,093–1,383,604) | 14 | 0 · never | 0 · never | 0 · never | 7 · 3 | 7 · 3 | 0 · never | 7 · 3 | 0 · never |
| 15 | Infiltration - Portscan (rows 1,375,764–1,378,733) | 2,019 | 99 · 14 | 99 · 13 | 91 · 104 | 91 · 107 | 91 · 107 | 98 · 13 | 87 · 219 | 89 · 192 |
| 16 | Infiltration (rows 1,391,981–1,506,113) | 21 | 10 · 7 | 14 · 8 | 19 · 4 | 19 · 4 | 19 · 4 | 5 · 15 | 19 · 7 | 5 · 15 |
| 17 | Infiltration - Portscan (rows 1,402,231–1,506,089) | 68,793 | 97 · 13 | 97 · 13 | 82 · 355 | 82 · 467 | 81 · 467 | 98 · 12 | 86 · 385 | 96 · 198 |
| 18 | Botnet (rows 1,594,877–1,646,421) | 736 | 33 · 174 | 31 · 174 | 67 · 237 | 60 · 237 | 60 · 237 | 73 · 128 | 74 · 180 | 81 · 127 |
| 19 | Portscan (rows 1,727,119–1,730,848) | 226 | 19 · 20 | 18 · 8 | 2 · 10 | 20 · 7 | 22 · 7 | 89 · 15 | 1 · 7 | 91 · 2 |
| 20 | Portscan (rows 1,739,810–1,741,394) | 118 | 5 · 17 | 7 · 18 | 0 · never | 1 · 66 | 1 · 66 | 89 · 2 | 2 · 33 | 82 · 2 |
| 21 | Portscan (rows 1,764,792–1,947,833) | 158,722 | 100 · 17 | 100 · 11 | 98 · 695 | 98 · 715 | 98 · 711 | 100 · 16 | 98 · 404 | 99 · 215 |
| 22 | DDoS (rows 1,968,178–2,079,562) | 95,144 | 99 · 23 | 99 · 17 | 98 · 242 | 98 · 12 | 98 · 12 | 100 · 22 | 99 · 224 | 100 · 126 |

Runs: `20261111-165347-608995-experiment-phase-3-adaptive-vs-joint-standard-and-g`, `20261111-171732-036467-experiment-phase-3-ablation-no-gating`, `20261111-172314-227666-experiment-phase-3-ablation-no-r2`, `20261111-172824-164084-experiment-phase-3-ablation-no-r3`, `20261111-174022-182362-experiment-phase-3-ablation-no-r5`
