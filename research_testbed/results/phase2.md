## Overall (after warm-up)

| Method | Accuracy % | κ | κ-temporal | Macro-F1 | Attack recall % | False alarms % (benign) | Mean µs | p99 µs | Peak MB | Model changes |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Repeat last label | 98.70 | 0.965 | 0.000 | 0.982 | 97.3 | 0.84 | 85.8 | 194.3 | 163 | 0 |
| Static | 75.92 | 0.000 | -17.575 | 0.432 | 0.0 | 0.00 | 28.5 | 32.8 | 165 | 0 |
| Incremental | 99.14 | 0.976 | 0.334 | 0.988 | 97.3 | 0.29 | 197.1 | 332.6 | 168 | 0 |
| Adaptive pipeline | 99.34 | 0.982 | 0.491 | 0.991 | 98.7 | 0.44 | 125.0 | 170.7 | 164 | 256 |
| ARF | 99.86 | 0.996 | 0.892 | 0.998 | 99.7 | 0.08 | 656.6 | 1842.5 | 192 | 0 |
| SRP | 99.90 | 0.997 | 0.919 | 0.999 | 99.7 | 0.04 | 4790.0 | 16156.4 | 212 | 0 |
| Leveraging bagging | 99.76 | 0.994 | 0.818 | 0.997 | 99.2 | 0.04 | 5751.1 | 16437.0 | 199 | 0 |

Accuracy of repeating the previous row's label over the same rows: **98.70 %** (the reference for κ-temporal).

## Share of each original label flagged as an attack (%)

For an attack type this is its recall; for benign traffic it is the false-alarm rate.

| Original label | Counted as | Rows | Repeat last label | Static | Incremental | Adaptive pipeline | ARF | SRP | Leveraging bagging |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Botnet | attack | 736 | 21.1 | 0.0 | 97.4 | 34.2 | 77.7 | 74.9 | 64.9 |
| DDoS | attack | 95,144 | 99.1 | 0.0 | 99.8 | 99.4 | 100.0 | 100.0 | 100.0 |
| DoS GoldenEye | attack | 7,567 | 95.1 | 0.0 | 96.6 | 97.3 | 99.4 | 99.3 | 98.9 |
| DoS Hulk | attack | 158,468 | 98.7 | 0.0 | 99.8 | 99.2 | 99.9 | 100.0 | 100.0 |
| DoS Slowhttptest | attack | 1,740 | 82.4 | 0.0 | 89.3 | 85.5 | 94.6 | 93.6 | 91.7 |
| DoS Slowloris | attack | 3,859 | 71.2 | 0.0 | 64.1 | 94.5 | 97.8 | 98.5 | 95.8 |
| FTP-Patator | attack | 3,972 | 41.2 | 0.0 | 0.4 | 98.5 | 99.4 | 99.5 | 96.8 |
| Heartbleed | attack | 11 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Infiltration | attack | 36 | 5.6 | 0.0 | 27.8 | 11.1 | 2.8 | 0.0 | 0.0 |
| Infiltration - Portscan | attack | 71,767 | 95.9 | 0.0 | 94.0 | 96.9 | 99.1 | 99.2 | 96.5 |
| Portscan | attack | 159,066 | 99.3 | 0.0 | 99.7 | 99.3 | 99.9 | 99.9 | 99.7 |
| SSH-Patator | attack | 2,961 | 38.3 | 0.0 | 27.2 | 93.7 | 98.8 | 98.1 | 91.3 |
| Web Attack - Brute Force | attack | 73 | 0.0 | 0.0 | 16.4 | 0.0 | 0.0 | 0.0 | 0.0 |
| Web Attack - SQL Injection | attack | 13 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Web Attack - XSS | attack | 18 | 0.0 | 0.0 | 94.4 | 0.0 | 0.0 | 0.0 | 0.0 |
| BENIGN | benign | 1,581,566 | 0.8 | 0.0 | 0.3 | 0.4 | 0.1 | 0.0 | 0.0 |
| Botnet - Attempted | benign | 4,067 | 0.9 | 0.0 | 2.0 | 3.8 | 1.9 | 1.0 | 1.1 |
| DoS GoldenEye - Attempted | benign | 80 | 5.0 | 0.0 | 0.0 | 1.2 | 0.0 | 1.2 | 0.0 |
| DoS Hulk - Attempted | benign | 581 | 0.9 | 0.0 | 8.3 | 0.3 | 0.2 | 0.0 | 0.0 |
| DoS Slowhttptest - Attempted | benign | 3,368 | 0.1 | 0.0 | 0.1 | 0.0 | 0.0 | 0.0 | 0.0 |
| DoS Slowloris - Attempted | benign | 1,847 | 13.5 | 0.0 | 0.0 | 0.2 | 0.2 | 0.0 | 0.0 |
| FTP-Patator - Attempted | benign | 12 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Infiltration - Attempted | benign | 45 | 4.4 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| SSH-Patator - Attempted | benign | 27 | 18.5 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Web Attack - Brute Force - Attempted | benign | 1,292 | 2.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Web Attack - SQL Injection - Attempted | benign | 5 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Web Attack - XSS - Attempted | benign | 655 | 0.9 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Cost per row after warm-up, by the review's terms (µs)

Not recorded in these runs.

## Joint controller decisions

No joint-controller trials in these runs.

## Each dated attack period: recall % · flows of that attack before the first was flagged

| # | Attack period | Flows | Repeat last label | Static | Incremental | Adaptive pipeline | ARF | SRP | Leveraging bagging |
|--:|---|--:|---|---|---|---|---|---|---|
| 1 | FTP-Patator (rows 392,025–456,914) | 3,972 | 41 · 1 | 0 · never | 0 · 4 | 99 · 3 | 99 · 4 | 100 · 1 | 97 · 1 |
| 2 | SSH-Patator (rows 568,617–619,012) | 2,960 | 38 · 1 | 0 · never | 27 · 2126 | 94 · 12 | 99 · 4 | 98 · 5 | 91 · 3 |
| 3 | SSH-Patator (rows 648,624–648,624) | 1 | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never |
| 4 | DoS Slowloris (rows 734,892–758,098) | 3,859 | 71 · 7 | 0 · never | 64 · 1331 | 94 · 21 | 98 · 27 | 98 · 34 | 96 · 120 |
| 5 | DoS Slowhttptest (rows 762,135–784,262) | 1,740 | 82 · 5 | 0 · never | 89 · 11 | 86 · 42 | 95 · 15 | 94 · 19 | 92 · 13 |
| 6 | DoS Hulk (rows 791,449–962,827) | 158,468 | 99 · 1 | 0 · never | 100 · 238 | 99 · 2 | 100 · 6 | 100 · 6 | 100 · 1 |
| 7 | DoS GoldenEye (rows 969,085–982,739) | 7,567 | 95 · 1 | 0 · never | 97 · 0 | 97 · 14 | 99 · 24 | 99 · 30 | 99 · 64 |
| 8 | Heartbleed (rows 1,121,659–1,141,665) | 11 | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never |
| 9 | Web Attack - Brute Force (rows 1,202,815–1,237,556) | 73 | 0 · never | 0 · never | 16 · 61 | 0 · never | 0 · never | 0 · never | 0 · never |
| 10 | Web Attack - XSS (rows 1,245,167–1,254,739) | 18 | 0 · never | 0 · never | 94 · 1 | 0 · never | 0 · never | 0 · never | 0 · never |
| 11 | Web Attack - SQL Injection (rows 1,254,953–1,260,222) | 13 | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never |
| 12 | Infiltration - Portscan (rows 1,354,794–1,355,961) | 955 | 89 · 1 | 0 · never | 0 · never | 88 · 32 | 99 · 7 | 100 · 1 | 0 · never |
| 13 | Infiltration (rows 1,368,155–1,368,155) | 1 | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never | 0 · never |
| 14 | Infiltration (rows 1,372,093–1,383,604) | 14 | 7 · 11 | 0 · never | 29 · 5 | 0 · never | 0 · never | 0 · never | 0 · never |
| 15 | Infiltration - Portscan (rows 1,375,764–1,378,733) | 2,019 | 97 · 1 | 0 · never | 0 · 2002 | 98 · 14 | 99 · 14 | 98 · 28 | 58 · 807 |
| 16 | Infiltration (rows 1,391,981–1,506,113) | 21 | 5 · 7 | 0 · never | 29 · 4 | 19 · 7 | 5 · 7 | 0 · never | 0 · never |
| 17 | Infiltration - Portscan (rows 1,402,231–1,506,089) | 68,793 | 96 · 1 | 0 · never | 98 · 665 | 97 · 11 | 99 · 13 | 99 · 14 | 99 · 239 |
| 18 | Botnet (rows 1,594,877–1,646,421) | 736 | 21 · 3 | 0 · never | 97 · 1 | 34 · 128 | 78 · 128 | 75 · 173 | 65 · 245 |
| 19 | Portscan (rows 1,727,119–1,730,848) | 226 | 47 · 1 | 0 · never | 51 · 105 | 20 · 27 | 93 · 4 | 94 · 1 | 47 · 1 |
| 20 | Portscan (rows 1,739,810–1,741,394) | 118 | 52 · 2 | 0 · never | 69 · 1 | 8 · 16 | 78 · 5 | 83 · 2 | 69 · 10 |
| 21 | Portscan (rows 1,764,792–1,947,833) | 158,722 | 99 · 1 | 0 · never | 100 · 7 | 100 · 26 | 100 · 4 | 100 · 1 | 100 · 1 |
| 22 | DDoS (rows 1,968,178–2,079,562) | 95,144 | 99 · 1 | 0 · never | 100 · 3 | 99 · 31 | 100 · 3 | 100 · 1 | 100 · 4 |

Runs: `20261111-145934-568975-experiment-phase-2-core-methods-on-cic-ids2017`, `20261111-145938-211780-experiment-phase-2-srp-methods-on-cic-ids2017`, `20261111-145941-337166-experiment-phase-2-levbag-methods-on-cic-ids2017`
