# Method decision — 11 November 2026

Inputs: [literature_and_novelty.md](literature_and_novelty.md), [findings_from_results.md](findings_from_results.md),
the final review paper (`docs/paper/`, §4.3, §6.2, §6.3).

## What the two reports say

- **Literature.** The R1–R5 rule ladder is a baseline, not a method. The review's §6.3 (choose a
  configuration θ minimising J under hard limits; "the search over configurations" left open) is
  where a method can sit. It recommends a model cascade: a cheap tree for every flow, ARF for the
  uncertain ones, with an escalation threshold that adjusts itself to hold the budget.
- **Our results.** A cascade over *models at inference* would gain little here:
  - inference is only 5–17 % of the time; preprocessing and the model update are 75–85 %;
  - the label-free "easy row" test lets 48 % of errors through.

  The data instead shows where effort is wasted and where it is missing:
  - 77 % of rows are easy (0.05 % error rate) yet cost the same as hard ones;
  - errors cluster around label switches inside attack periods, in about 40 % of the blocks;
  - an oracle that meets the budget *on average* and spends it in attack stretches cuts gateway
    errors by about 90 % (a loose upper bound);
  - R3's collapse is a ranking frozen on benign-only rows, not a real trade-off;
  - under label delay, 84 % of errors follow the controller's own resets.

## Decision: a budgeted effort controller ("effort")

Keep the literature report's core idea — spend the budget where it matters, with a self-adjusting
threshold that holds the budget — but apply it to **effort across the pipeline stages**, where our
cost actually is, not to a choice between two models.

1. **Effort levels.** A configuration θ is an effort level: how many inputs are preprocessed, how
   often scaler statistics and the feature ranking are updated, whether the model learns from this
   row, how many features the model uses. Low effort is cheap and is enough on easy rows.
2. **Activity signal.** Recent label switches, errors on arrived labels and drift alarms say whether
   the stream is in a hard stretch.
3. **Budget on average, limits hard.** A dual variable (price of compute) rises when mean cost is
   over the CPU budget and falls when under; each row gets the highest effort whose expected value
   beats its price. The per-row deadline and the memory limit stay hard constraints (R3 as a last
   resort, R5). This is the §6.3 objective with α and γ, solved online.
4. **Repairs the results call for.** Live (sampled) ranking while narrowed; no feature cut before
   the ranker has seen both classes; floor of 8 features; faster response at attack onset; damped
   re-alarms inside long attacks; delay-aware adaptation (keep the old model until the new one has
   labelled rows; mute the detector after an adaptation).
5. **Deterministic decisions.** The controller can decide from a modelled cost (calibrated per
   stage) instead of measured time, so runs are repeatable; measured time is still reported.

R1–R5 (`joint`) stays as the baseline the review proposed. ARF escalation and a label-free
disagreement signal are left as extensions.

## Honest position on novelty

- Nearest work: RCCDA (NeurIPS 2025) decides update / no update against an average budget with
  Lyapunov control; Online Cascade Learning (ICML 2024) cascades models for text without drift or a
  hard per-item budget. What is new here is the scope: all pipeline stages, drift and delay
  awareness, hard per-row and memory limits, on a real-drift intrusion stream, with stage-level
  cost reporting. Confidence that this combination is unpublished: medium.
- Every gain quoted above is an estimate from one-seed runs on a loaded machine. The method has to
  earn its claim in the protocol; a null result is reported as such.
