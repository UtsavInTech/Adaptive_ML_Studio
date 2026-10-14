# Static Kaggle snapshots

Downloaded 9 October 2026. Files live under `data/kaggle/` (ignored by Git).
The tracked `catalog.json` records archive and prepared-file SHA-256, source,
version, labels, order, features, and dataset-specific limitations.

## Restore

From the repository root:

```sh
python3 scripts/prepare_kaggle.py
```

This downloads version 1 of both public Kaggle datasets without storing credentials.
To use browser downloads instead:

```sh
python3 scripts/prepare_kaggle.py --elec2-archive /path/elec2.zip --occupancy-archive /path/occupancy.zip
```

The script only accepts the registered archive checksums, and verifies prepared
bytes before saving them. An upstream change requires explicit catalog review.
There is no download or network dependency while running experiments.

## Electricity (ELEC2)

- Kaggle: https://www.kaggle.com/datasets/yashsharan/the-elec2-dataset
- Original authors cited by publisher: M. Harries, J. Gama, A. Bifet.
- Reference: M. Harries, *Splice-2 comparative evaluation: Electricity pricing*, 1999.
- 45,312 rows, one every 30 minutes: 7 May 1996 – 5 December 1998 (944 days).
  All eight numeric input columns are retained; `class` is excluded.
- 42.5 % of rows are UP. 85.3 % of rows carry the same label as the row before, so a model that
  can see how recent rows were labelled scores well without learning anything about electricity.
  `date` rises steadily from 0 to 1 and `period` is the half-hour of the day, which lets a
  continually learning tree approximate "what happened recently". This is a known property of the
  benchmark and the reason overall accuracy on it should be read with care.
- UP = positive (1), DOWN = negative (0). CSV byte content and file order are unchanged.
- The publisher supplies normalized features. No additional global fit is performed.
  This pre-normalized benchmark cannot establish absence of upstream normalization leakage.
- Classifies contemporaneous movement relative to the previous 24-hour price average;
  it is not future-price forecasting, and current price is an input.
- Kaggle license: Open Database / Database Contents License:
  https://opendatacommons.org/licenses/dbcl/1.0/

## Room occupancy

- Kaggle: https://www.kaggle.com/datasets/robmarkcole/occupancy-detection-data-set-uci
- Original: Luis Candanedo (2016), *Occupancy Detection*, UCI Machine Learning
  Repository, https://doi.org/10.24432/C5X01N (CC BY 4.0).
- Source record/license: https://archive.ics.uci.edu/dataset/357/occupancy+detection
  Kaggle mirror labels its license "Unknown"; this is recorded separately from UCI's license.
- Retain all 20,560 rows from datatest.txt, datatraining.txt and datatest2.txt.
  Repair the original missing row-ID header, then stable-sort by ISO timestamp.
  These files have 20,560 unique timestamps. No labels or sensor values are changed.
- Features: Temperature, Humidity, Light, CO2, HumidityRatio. Row ID, timestamp,
  source filename and Occupancy are excluded from inputs. Occupancy 1 is positive.
- One row per minute, 2–18 February 2015 (about 16 days). 23.1 % of rows are occupied, and two
  whole stretches (weekends) contain none. 99.4 % of rows carry the same label as the row before.
  `Light` alone correlates 0.915 with the label.
- **Warm-up: 3,000 rows recommended, not 1,000.** 1,000 rows is 17 hours — one afternoon and one
  night. A model trained once on that has never seen a morning: measured on 13 October 2026, the
  train-once baseline learned a single rule on CO2, predicted "occupied" for 99.5 % of later rows
  and scored 23.8 %. With 3,000 rows (two full days) the same baseline scores 97.9 %. Both
  figures are kept; the form defaults to 3,000 for this dataset and says why.
- Raw source files are retained beside the prepared CSV for inspection.
- This is chronological prequential replay, not the source paper's train/test protocol.

## Shared evaluation

After a configurable initial warm-up (default 1,000 rows), score each prediction
before using that row's label for learning. The static baseline stops updating;
incremental learns continually; adaptive adds ADWIN and model replacement; ARF
uses the existing ensemble baseline. Every method receives identical rows.

No label noise, shuffle, fitted global preprocessing or oversampling is applied.

### Natural replay (the default)

The rows are replayed exactly as recorded. Both sources drift on their own, but nobody has
marked where: detector alerts are measured algorithm events, not confirmed ground truth.
Detection delay and before/after scores are unavailable in this mode. Favorable results are
not guaranteed or selected.

### Controlled drift (opt-in, always labelled)

A run may ask for one change at a known row (`stream.injection`). From that row on, the values
of two input columns are exchanged. No row is added, removed or reordered and no label is
altered, so the columns keep all their information: only the relationship a model had learned
between each column and the label breaks. How the exchange arrives is the drift type:

| Type | What happens to the rows |
|---|---|
| Sudden (abrupt) | every row from the chosen row is exchanged |
| Gradual | over a set number of rows, a rising share of rows is exchanged; each row is fully old or fully new |
| Incremental | over a set number of rows, every row is a blend that moves steadily from old to new |
| Recurring | exchanged for a set number of rows, restored for the same number, and so on |

These are the four classes in Gama et al., *A survey on concept drift adaptation*, ACM Computing
Surveys 46(4), 2014. Gradual drift decides row by row whether a row is old or new from a fixed
random stream that depends only on the injection settings, so model seeds still never change the data.

Defaults, fixed before any result was looked at:

- **Columns:** the two inputs most correlated with the label over the whole file — ELEC2
  `nswprice` and `nswdemand` (|r| 0.379, 0.334); Occupancy `Light` and `Temperature` (0.915, 0.556).
- **Position:** the middle of the replay, rounded down to 1,000 rows.
- **Gradual / incremental:** 2,000 rows. **Recurring:** 4,000 rows per arrangement.

Because the position is known, each method is scored **before** (the 2,000 rows ahead of the
change), **during** (from the first changed row until 1,000 rows after the change is complete)
and **after** (the next 2,000 rows), with accuracy, precision, recall and F1, and the detector
alerts and model replacements inside each window. The window sizes are configuration
(`evaluation.phases`) and, like the stability figures, reference computations: which definition
to adopt is a research-team decision.

**Control trials.** Real data moves on its own, so a drop after the change is not necessarily
caused by it. With `control: true` every method is also run on the untouched rows and scored
over the identical windows. Before the change the two runs are bit-identical; afterwards the gap
between a figure and its control is what the added change accounts for. This matters most for
the detector: on ELEC2 the adaptive pipeline raises an alert roughly every 1,150 rows on
untouched data, so "first alert after the change" is only meaningful beside its control.

A run with an added change is **real data plus controlled drift**. It is recorded that way
(`provenance.injected_drift`, `scenario.drift_ground_truth = "injected"`) and labelled that way
everywhere it is shown. It is never reported as plain real-data drift.

Model seeds do not change dataset order. Repeated seeds quantify model randomness,
not independent datasets; deterministic methods may repeat predictions exactly.
Software edge budgets remain simulated, not measurements on a physical edge device.

The CSV is validated and loaded before pipeline timing starts. Per-row parsing is
recorded separately as stream time. Peak process memory includes the loaded snapshot.
Per-stage and total service latencies retain the existing instrumentation. Live replay
shares a worker across its two methods; isolated Experiments is the timing comparison.
