# Held-out test of the budgeted effort controller — 12 November 2026

**What makes it held out.** Thursday's and Friday's traffic played no part in designing,
calibrating or checking the `effort` controller: the design used Wednesday, and the cost model and
development checks used Tuesday. All defaults are unchanged from `effort_results.md`. Nothing was
adjusted after seeing these results.

**What was run.** Thursday (362,076 connections from row 1,190,343: web attacks, infiltration,
port scans) and Friday (547,557 from row 1,552,419: botnet, port scan, DDoS). Tiers `small_sim`
(100 µs per connection) and `micro_sim` (50 µs), both simulated with placeholder budgets.
`joint` (the review's R1–R5) and `effort` with seeds 11, 23, 37; `no_change` and `incremental`
with seed 11 (they are deterministic). One trial at a time. Presets:
`research_testbed/presets/heldout_*.yaml`. Full tables: `research_testbed/reports/heldout/report.md`.

Runs: `20261112-094008-815225-…thursday-references`, `20261112-094305-412948-…thursday-controllers`,
`20261112-095151-907292-…friday-references`, `20261112-095616-360126-…friday-controllers`.

## Results

Errors and κ-temporal [95 % block-bootstrap interval]; time is measured µs per connection.
For `joint`, values are the mean of 3 runs; its range across runs is given where the runs differ.

| Day | Tier (budget) | Method | Errors | κ-temporal | µs per connection |
|---|---|---|--:|---|--:|
| Thursday | small (100) | incremental | 4,119 | 0.34 [−0.38, 0.70] | 149 |
| | | joint (R1–R5) | 2,327 | 0.62 [0.56, 0.67] | 153 |
| | | **effort** | 2,377 | 0.62 [0.56, 0.66] | **75** |
| Thursday | micro (50) | joint (R1–R5) | 3,698 (κt 0.29–0.61 across runs) | 0.40 [0.35, 0.45] | 97 (75–121) |
| | | **effort** | 2,331 | 0.62 [0.56, 0.67] | **48** |
| Friday | small (100) | incremental | 3,566 | 0.30 [−0.26, 0.63] | 152 |
| | | joint (R1–R5) | 1,982 | 0.61 [0.48, 0.72] | 142 |
| | | **effort** | 1,632 | 0.68 [0.56, 0.78] | **89** |
| Friday | micro (50) | joint (R1–R5) | 2,597 (κt 0.42–0.58 across runs) | 0.49 [0.36, 0.61] | 76 (62–91) |
| | | **effort** | 2,002 | 0.61 [0.47, 0.72] | **57** |

Paired difference in errors, effort − joint, same rows (10,000-row blocks, 2,000 resamples):

| Day | Tier | Against joint run | Δ errors [95 % interval] |
|---|---|---|---|
| Thursday | small | seed 11 | +50 [−139, +282] |
| Thursday | micro | seeds 11 / 23 / 37 | −2,057 [−3,231, −1,015] / −58 [−382, +248] / −1,985 [−3,225, −890] |
| Friday | small | seed 11 | −326 [−683, +1] |
| Friday | micro | seeds 11 / 23 / 37 | −167 [−699, +390] / −651 [−1,325, −59] / −968 [−1,595, −397] |

Effort − incremental on the small tier: Thursday −1,732 [−5,007, +661]; Friday −1,930 [−4,751, −112].

## Reading

- **The cost result holds on both held-out days.** On the small tier `effort` runs at 75 and 89 µs
  against a 100 µs budget; `joint` runs at 142–153 µs, 42–53 % over. On the micro tier `effort`
  runs at 48 µs (Thursday, within the 50 µs budget) and 57 µs (Friday, 14 % over); `joint` runs at
  62–121 µs.
- **Quality on the small tier: no worse, at about half the cost.** Thursday is a tie (+50 errors,
  interval covers 0). Friday favours `effort` (−326), with the interval just touching 0. The
  Wednesday claim "fewer errors than the rules" is therefore not confirmed as a general result;
  "equal or fewer errors at the budget" is.
- **Quality on the micro tier: `effort` is equal or better, and stable.** It beats `joint` clearly
  in 4 of 6 paired comparisons and ties in 2. On Wednesday it had no advantage here, so this is a
  better outcome than the design day suggested.
- **`effort` is repeatable; `joint` is not.** The three `effort` runs gave identical predictions on
  each day and tier. `joint`'s κ-temporal on the micro tier ranged from 0.29 to 0.61 on the same
  data, because its decisions depend on measured time.
- **Attack onsets are mixed.** Flows before the first flag: Friday 43 (`effort`) against 164
  (`joint`) on the small tier; Thursday 99 against 53.

## Still not shown

- One dataset and one lab network. Thursday and Friday are held out from the design, but they are
  the same week and network as the design day.
- Delayed labels were not re-run here; the Wednesday result (both controllers fail) stands.
- `joint`'s seeds differ only through timing; `effort`'s and `incremental`'s seeds give identical
  runs, so "3 seeds" measures timing variation, not model variation.
- Simulated tiers, placeholder budgets, no energy, no real device.
- The cost model under-predicted on Friday's micro tier (57 µs measured against a 50 µs budget).
