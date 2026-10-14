# Real data with controlled drift — measured results

Recorded on 13 October 2026 on the project machine (Apple M1, 8 GB), through the application's own
experiment API. Every figure below is read from the saved result bundles in `results/experiments/`;
this file is generated from them, not typed.

**What was run.** Four methods × four drift types × two Kaggle datasets, each method alone in a
fresh process, seed 42, standard profile. Every trial has a **control**: the same method on the
same rows with no change added, scored over the identical row windows.

**How to read a cell.** `during 53.6 (77.6)` means 53.6 % with the added change and 77.6 % on the
untouched rows. The gap, not the figure alone, is what the added change accounts for, because real
data moves on its own. "Before" is identical in both runs by construction and is shown once.

**Windows.** Before = the 2,000 rows ahead of the change. During = from the first changed row
until 1,000 rows after the change is complete. After = the next 2,000 rows. These are configurable
reference computations; which definition to adopt is a research-team decision.

These are measurements. Interpreting them, and choosing which of them belong in the paper, is the
research workstream's job.


## Electricity · ELEC2

45,312 rows · warm-up 1,000 · `nswprice` ↔ `nswdemand` from row 22,000


### Sudden

Run `20261013-134510-076470-experiment-electricity-elec2-sudden-drift-method-co`

| Method | Accuracy before | during (untouched) | after (untouched) | Precision before | during (untouched) | after (untouched) | Whole run | µs / row |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Static (train once) | 65.2 | 42.9 (58.1) | 40.8 (66.1) | 100.0 | 42.7 (100.0) | 39.5 (100.0) | 51.9 | 6.2 |
| Incremental (no detection) | 81.5 | 53.6 (77.6) | 59.5 (72.6) | 80.3 | 43.8 (92.1) | 47.8 (72.3) | 79.3 | 29.4 |
| Adaptive pipeline | 80.2 | 70.5 (76.3) | 71.2 (75.9) | 73.9 | 66.1 (81.5) | 65.1 (69.1) | 81.9 | 34.0 |
| Adaptive Random Forest | 89.1 | 87.7 (88.0) | 87.6 (87.4) | 86.0 | 86.9 (89.3) | 84.4 (86.8) | 89.9 | 430.3 |

Adaptive pipeline, detector: first alert 125 rows after the change (untouched rows: 509); alerts during the window 2 (untouched: 1), model replacements during 1 (untouched: 1).


### Gradual (over 2,000 rows)

Run `20261013-134707-375602-experiment-electricity-elec2-gradual-drift-method-c`

| Method | Accuracy before | during (untouched) | after (untouched) | Precision before | during (untouched) | after (untouched) | Whole run | µs / row |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Static (train once) | 65.2 | 48.2 (63.5) | 46.9 (57.7) | 100.0 | 41.1 (100.0) | 44.5 (100.0) | 52.4 | 6.2 |
| Incremental (no detection) | 81.5 | 60.5 (74.3) | 73.9 (81.2) | 80.3 | 50.6 (78.7) | 63.4 (89.7) | 78.6 | 29.7 |
| Adaptive pipeline | 80.2 | 74.0 (76.1) | 83.1 (84.9) | 73.9 | 72.4 (72.6) | 77.2 (84.1) | 82.5 | 34.2 |
| Adaptive Random Forest | 89.1 | 85.7 (87.6) | 92.2 (90.2) | 86.0 | 84.0 (87.7) | 90.5 (89.2) | 89.7 | 431.0 |

Adaptive pipeline, detector: first alert 541 rows after the change (untouched rows: 509); alerts during the window 2 (untouched: 3), model replacements during 2 (untouched: 2).


### Incremental (over 2,000 rows)

Run `20261013-134807-704039-experiment-electricity-elec2-incremental-drift-meth`

| Method | Accuracy before | during (untouched) | after (untouched) | Precision before | during (untouched) | after (untouched) | Whole run | µs / row |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Static (train once) | 65.2 | 48.7 (63.5) | 46.9 (57.7) | 100.0 | 43.4 (100.0) | 44.5 (100.0) | 52.4 | 8.1 |
| Incremental (no detection) | 81.5 | 68.0 (74.3) | 73.7 (81.2) | 80.3 | 57.0 (78.7) | 67.1 (89.7) | 79.2 | 35.1 |
| Adaptive pipeline | 80.2 | 73.0 (76.1) | 83.0 (84.9) | 73.9 | 65.8 (72.6) | 78.1 (84.1) | 81.9 | 36.5 |
| Adaptive Random Forest | 89.1 | 87.1 (87.6) | 91.5 (90.2) | 86.0 | 86.0 (87.7) | 90.3 (89.2) | 89.6 | 450.5 |

Adaptive pipeline, detector: first alert 157 rows after the change (untouched rows: 509); alerts during the window 3 (untouched: 3), model replacements during 2 (untouched: 2).


### Recurring (every 4,000 rows; first switch scored)

Run `20261013-134905-975411-experiment-electricity-elec2-recurring-drift-method`

| Method | Accuracy before | during (untouched) | after (untouched) | Precision before | during (untouched) | after (untouched) | Whole run | µs / row |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Static (train once) | 65.2 | 42.9 (58.1) | 40.8 (66.1) | 100.0 | 42.7 (100.0) | 39.5 (100.0) | 57.9 | 5.8 |
| Incremental (no detection) | 81.5 | 53.6 (77.6) | 59.5 (72.6) | 80.3 | 43.8 (92.1) | 47.8 (72.3) | 78.3 | 31.3 |
| Adaptive pipeline | 80.2 | 70.5 (76.3) | 71.2 (75.9) | 73.9 | 66.1 (81.5) | 65.1 (69.1) | 81.2 | 35.5 |
| Adaptive Random Forest | 89.1 | 87.7 (88.0) | 87.6 (87.4) | 86.0 | 86.9 (89.3) | 84.4 (86.8) | 89.8 | 507.5 |

Adaptive pipeline, detector: first alert 125 rows after the change (untouched rows: 509); alerts during the window 2 (untouched: 1), model replacements during 1 (untouched: 1).


## Room occupancy · UCI

20,560 rows · warm-up 3,000 · `Light` ↔ `Temperature` from row 10,000


### Sudden

Run `20261013-135008-234229-experiment-room-occupancy-uci-sudden-drift-method-c`

| Method | Accuracy before | during (untouched) | after (untouched) | Precision before | during (untouched) | after (untouched) | Whole run | µs / row |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Static (train once) | 99.7 | 75.6 (99.5) | 86.6 (98.9) | 99.3 | — (98.0) | — (94.2) | 86.7 | 6.3 |
| Incremental (no detection) | 99.6 | 84.8 (99.5) | 90.5 (98.5) | 98.7 | 100.0 (98.0) | 62.4 (91.0) | 95.9 | 22.8 |
| Adaptive pipeline | 99.8 | 86.7 (96.2) | 99.1 (99.2) | 99.8 | 100.0 (99.0) | 96.3 (96.3) | 97.1 | 21.4 |
| Adaptive Random Forest | 99.1 | 98.2 (99.3) | 97.5 (99.2) | 98.9 | 98.7 (98.0) | 90.7 (98.1) | 98.4 | 232.6 |

Adaptive pipeline, detector: first alert 782 rows after the change (untouched rows: 782); alerts during the window 1 (untouched: 1), model replacements during 1 (untouched: 1).


### Gradual (over 2,000 rows)

Run `20261013-135030-383757-experiment-room-occupancy-uci-gradual-drift-method-`

| Method | Accuracy before | during (untouched) | after (untouched) | Precision before | during (untouched) | after (untouched) | Whole run | µs / row |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Static (train once) | 99.7 | 87.9 (99.1) | 75.3 (98.9) | 99.3 | 97.5 (96.0) | — (95.7) | 87.6 | 5.9 |
| Incremental (no detection) | 99.6 | 87.6 (98.8) | 98.1 (98.9) | 98.7 | 61.9 (94.2) | 97.3 (95.9) | 96.6 | 22.3 |
| Adaptive pipeline | 99.8 | 94.8 (98.2) | 97.9 (94.8) | 99.8 | 93.2 (97.5) | 94.0 (90.4) | 97.5 | 23.0 |
| Adaptive Random Forest | 99.1 | 97.9 (99.2) | 98.2 (98.8) | 98.9 | 94.1 (98.0) | 96.6 (96.8) | 98.4 | 222.6 |

Adaptive pipeline, detector: first alert 782 rows after the change (untouched rows: 782); alerts during the window 1 (untouched: 1), model replacements during 1 (untouched: 1).


### Incremental (over 2,000 rows)

Run `20261013-135052-537727-experiment-room-occupancy-uci-incremental-drift-met`

| Method | Accuracy before | during (untouched) | after (untouched) | Precision before | during (untouched) | after (untouched) | Whole run | µs / row |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Static (train once) | 99.7 | 82.9 (99.1) | 75.3 (98.9) | 99.3 | — (96.0) | — (95.7) | 86.7 | 6.7 |
| Incremental (no detection) | 99.6 | 89.6 (98.8) | 88.4 (98.9) | 98.7 | 73.0 (94.2) | 68.3 (95.9) | 91.1 | 22.2 |
| Adaptive pipeline | 99.8 | 96.0 (98.2) | 97.8 (94.8) | 99.8 | 91.9 (97.5) | 95.4 (90.4) | 97.9 | 22.6 |
| Adaptive Random Forest | 99.1 | 98.4 (99.2) | 98.0 (98.8) | 98.9 | 94.4 (98.0) | 96.5 (96.8) | 98.5 | 226.6 |

Adaptive pipeline, detector: first alert 782 rows after the change (untouched rows: 782); alerts during the window 3 (untouched: 1), model replacements during 2 (untouched: 1).


### Recurring (every 4,000 rows; first switch scored)

Run `20261013-135114-691606-experiment-room-occupancy-uci-recurring-drift-metho`

| Method | Accuracy before | during (untouched) | after (untouched) | Precision before | during (untouched) | after (untouched) | Whole run | µs / row |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Static (train once) | 99.7 | 75.6 (99.5) | 86.6 (98.9) | 99.3 | — (98.0) | — (94.2) | 88.2 | 5.7 |
| Incremental (no detection) | 99.6 | 84.8 (99.5) | 90.5 (98.5) | 98.7 | 100.0 (98.0) | 62.4 (91.0) | 94.6 | 22.1 |
| Adaptive pipeline | 99.8 | 86.7 (96.2) | 99.1 (99.2) | 99.8 | 100.0 (99.0) | 96.3 (96.3) | 97.6 | 22.1 |
| Adaptive Random Forest | 99.1 | 98.2 (99.3) | 97.5 (99.2) | 98.9 | 98.7 (98.0) | 90.7 (98.1) | 98.5 | 239.5 |

Adaptive pipeline, detector: first alert 782 rows after the change (untouched rows: 782); alerts during the window 1 (untouched: 1), model replacements during 1 (untouched: 1).


## What the measurements show, and what they do not

Stated as observations of these runs only.

- **The added change is visible in every method that depends on the exchanged columns.** On ELEC2
  with a sudden change the static model's accuracy in the "during" window is 42.9 % against 58.1 %
  untouched, and the incremental model's is 53.6 % against 77.6 %.
- **The adaptive pipeline loses less than the incremental one on ELEC2** (70.5 % against 76.3 %
  untouched, in the same window).
- **The Adaptive Random Forest is barely affected** by this kind of change on either dataset, and
  costs roughly 10 to 14 times the processing time per row of the adaptive pipeline
  (ELEC2 430–508 µs against 34–37 µs; Occupancy 223–240 µs against 21–23 µs).
- **A dash for precision** means the model predicted no positive rows in that window: after the
  exchange on Occupancy, the static model reads temperature where it expects light and never
  predicts "occupied".

Caveats that must travel with these numbers:

1. **The detector's response cannot always be attributed to the added change.** On ELEC2 the
   adaptive pipeline raises an alert about every 1,150 rows on untouched data. For the sudden and
   incremental changes the first alert comes earlier than in the control (125 and 157 rows against
   509), which the change accounts for. For the gradual change it does not (541 against 509), and
   on Occupancy the first alert falls on the same row with and without the change (782).
2. **In the ELEC2 sudden run the alert at +125 rows led to no model replacement.** A natural alert
   67 rows before the change had just triggered one, and the 300-row cooldown was still running.
   The position of the change was fixed before any result was seen and has not been moved.
3. **Occupancy needs a longer warm-up than the default.** With 1,000 warm-up rows (17 hours of
   data) the static baseline learns a single rule on CO2 and scores 23.8 % over the whole run, with
   or without any added change; with 3,000 rows (two days) it scores 97.9 %. The runs above use
   3,000. Both figures are kept; see `data/README.md`.
4. **High overall accuracy on these datasets is partly temporal dependence.** 85.3 % of ELEC2 rows
   and 99.4 % of Occupancy rows carry the same label as the row before, and a continually learning
   tree can exploit the time columns to follow that.
5. **One seed, one position, one pair of columns per dataset.** Nothing here has been repeated
   across seeds or positions, so no figure has an error bar.
6. **Timings** were taken with the application's own interface open in a browser on the same
   machine, as is normal for a run started from it. The isolated benchmark in
   `docs/performance.md` remains the reference for timing claims.
