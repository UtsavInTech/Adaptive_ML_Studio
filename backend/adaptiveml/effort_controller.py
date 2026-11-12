"""Budgeted effort controller (method "effort"): spend the CPU budget where the stream is hard.

The proposed method of research_testbed/research/METHOD.md. It runs the same pipeline as "joint"
(Hoeffding tree, ADWIN, online feature selection) and keeps the joint controller's hard-limit rules
for memory (R5) and the per-row deadline (R3), but replaces R3's "fewer features first" with a
choice of *effort level* per row, priced against the tier's CPU budget.

Effort levels (C). An ordered set of lever settings, cheapest first (config `effort.levels`):
  - B1 preprocess only the inputs the models need (narrowed from the end of warm-up);
  - B2 update scaler/imputer statistics on 1 row in s (gap-aware fading factor, so the statistics
       keep their memory in rows);
  - B3 update the feature ranking on 1 row in r, over all inputs, so it stays live while narrowed;
  - B4 skip the model update on easy rows (the last k arrived labels agree and were all predicted
       right), still learning from 1 easy row in m;
  - B5 the feature count changes only after the ranker has seen `gate_rows_per_class` rows of each
       class, never below a floor (8), and always from the live ranking.
B1, B3 and B5 are fixed for the run; B2 and B4 vary with the level. Each lever has a switch.

Activity signal. Over the last `activity_window` arrived labels: the label-switch rate and the error
rate, each divided by a reference rate and summed, capped at 1; a drift alarm sets it to 1 for
`alarm_hold` rows. a ≈ 0 in quiet benign traffic, a = 1 in interleaved attack stretches.

Price of compute (dual variable). With a per-row CPU budget B and the row's cost c_t (modelled or
measured, `cost_source`):
        λ_{t+1} = min(λ_max, max(0, λ_t + η · (c_t / B − 1)))        η = `price_step` (0.002)
λ rises while rows cost more than the budget and falls while they cost less, so the running mean
cost is held near B (projected dual ascent on the constraint mean(c) ≤ B; a virtual queue in the
sense of Lyapunov drift-plus-penalty, as in RCCDA, but over several pipeline stages).
Per row the next level is
        ℓ* = argmax_ℓ  a · benefit_ℓ − λ · ĉ_ℓ,     ĉ_ℓ = predicted cost of ℓ / B,
over the levels whose predicted cost meets the per-row deadline (hard); ties go to the cheaper
level. Without a CPU budget (standard tier) λ = `free_price` and ĉ is relative to the richest
level, so quiet rows still get the cheap levers and active rows the rich ones.

Hard limits, highest priority first:
  - R5 memory over budget → drop the replacement; else a fresh model; if that refills the budget
    soon, halve the features (not below the B5 floor). Same logic as the joint controller.
  - deadline: rows whose cost exceeds the per-row deadline, counted over `deadline_window`; too many
    → halve the features (gated and floored by B5), else thin the updates (stride ×2). Relaxes
    after `relax_after` calm rows, stride first.
  - price at the ceiling for `cut_after` rows while even the cheapest level costs more than B →
    halve the features (gated, floored). Restored when λ has been 0 for `relax_after` rows and the
    cheapest level at twice the features fits in `restore_share` of B.
  - R2/R1: drift handled by an immediate reset while λ ≥ `tight_price` (or memory is tight), by a
    background replacement once λ < `spare_price`.

Repairs (D), each switchable:
  - D1 fast switch: a waiting replacement is promoted as soon as it beats the active model on the
    last `switch_window` arrived labels, instead of always after `background_min_samples` rows.
  - D2 damped re-alarms: within `damp_rows` after an adaptation, a drift alarm is ignored while the
    label mix (share of positive labels over `mix_window` arrived labels) is within
    `mix_tolerance` of the mix at the adaptation.
  - D3 delay-aware adaptation (only with delayed or partial labels): no lightweight resets where a
    replacement is allowed (the old model predicts until the replacement has learned); new models
    are warm-started from the last `warm_start_rows` labelled rows; labels of rows predicted before
    the last adaptation are not fed to the detector (they are the replaced model's errors).

Deterministic decisions. With `cost_source: modelled` every decision reads a per-row cost computed
from the work the pipeline did (EffortCostModel coefficients × counts), never a timer, so the same
configuration gives the same predictions under any machine load. Measured time is still recorded
and reported. The memory checks use River's size estimate, which is deterministic.

Defaults are implementation choices, not tuned on the evaluation slice. This is a controller over a
fixed learner, not a new learning algorithm.
"""
from __future__ import annotations

from collections import deque
from time import perf_counter_ns

from adaptiveml.config import ControllerConfig, EffortLevel, ResourceBudgets
from adaptiveml.joint_controller import JointController
from adaptiveml.pipeline import (
    C_DETECT, C_RANK, C_REPLACEMENT, C_REPLACEMENT_FEATURES, C_REPLACEMENT_PREDICT, C_SELECT, C_SPLIT_FEATURES,
    C_STATS, C_TRANSFORM, C_UPDATE, C_UPDATE_FEATURES, Levers,
)


class EffortController(JointController):
    def __init__(self, pipe, cfg: ControllerConfig, budgets: ResourceBudgets, cpu_budget_ns: float | None,
                 cpu_budget_now=None):
        super().__init__(pipe, cfg, budgets, cpu_budget_ns, cpu_budget_now)
        e = self.e = cfg.effort
        self.modelled_source = e.cost_source == "modelled"
        self.floor = max(e.min_features, budgets.min_features) if e.feature_gate else budgets.min_features
        self.levels: list[EffortLevel] = [self._effective(lv) for lv in e.levels]
        self.levers = Levers(
            narrow=e.narrow_preprocessing, sample_stats=e.sample_statistics, live_ranking=e.live_ranking,
            skip_easy=e.skip_easy_updates, easy_k=e.easy_k, fast_switch=e.fast_switch,
            switch_window=e.switch_window, delay_aware=e.delay_aware,
            rank_min_per_class=e.gate_rows_per_class if e.live_ranking else 0,
        )
        pipe.enable_effort(self.levers)
        if pipe.recent is None:
            pipe.recent = deque(maxlen=cfg.retrain_buffer)
        self.delay_aware = e.delay_aware and pipe.delayed
        pipe._warm_start = e.warm_start_rows if self.delay_aware else 0
        self.levers.race_only = self.delay_aware and e.delay_race_only
        pipe.drift_gate = self._damp if e.damp_realarms else None
        self._cost_key, self._costs = None, []
        self.level = len(self.levels) - 1  # the richest level until the signals say otherwise
        self._set_level(self.level)
        # signals
        self._switches = deque(maxlen=e.activity_window)
        self._errors = deque(maxlen=e.activity_window)
        self._switch_sum = self._error_sum = 0
        self._last_y = None
        self._mix = deque(maxlen=e.mix_window)
        self._mix_sum = 0
        self._mix_at_adaptation: float | None = None
        self.alarm_until = -1
        self.activity = 0.0
        # price
        self.price = 0.0 if self.cpu_budget_ns else e.free_price
        self.price_peak = self.price
        self._ceiling_since: int | None = None
        self._free_since = 0
        # tallies after warm-up
        self.level_rows = [0] * len(self.levels)
        self.rows = 0
        self.cost_sum = self.modelled_sum = self.measured_sum = 0.0
        self.modelled_over_deadline = self.measured_over_deadline = 0
        self.damped_alarms = 0
        self.gate_opened_at: int | None = None

    @property
    def timing_dependent(self) -> bool:
        return not self.modelled_source

    # ------------------------------------------------------------------ levels
    def _effective(self, lv: EffortLevel) -> EffortLevel:
        """A level as the switched-on levers allow: a lever that is off is neutral at every level."""
        e = self.e
        return lv.model_copy(update={
            "stats_every": lv.stats_every if e.sample_statistics else 1,
            "rank_every": lv.rank_every if e.live_ranking else 1,
            "skip_easy": lv.skip_easy and e.skip_easy_updates,
        })

    def _set_level(self, k: int) -> None:
        lv, level = self.levers, self.levels[k]
        self.level = k
        lv.stats_rate = 1.0 / level.stats_every
        lv.rank_rate = 1.0 / level.rank_every
        lv.easy_rate = 1.0 / level.easy_learn_every if level.skip_easy else 1.0
        lv.skip_easy = level.skip_easy

    # ------------------------------------------------------------------ cost model
    def modelled_ns(self, counts) -> float:
        c = self.e.cost
        return (c.base_ns + c.controller_ns + c.predict_ns
                + c.transform_ns_per_input * counts[C_TRANSFORM]
                + c.stats_ns_per_input * counts[C_STATS]
                + c.rank_ns_per_input * counts[C_RANK]
                + (c.select_ns_per_feature + c.predict_ns_per_feature) * counts[C_SELECT]
                + c.detect_ns_per_label * counts[C_DETECT]
                + c.update_ns * (counts[C_UPDATE] + counts[C_REPLACEMENT])
                + c.update_ns_per_feature * (counts[C_UPDATE_FEATURES] + counts[C_REPLACEMENT_FEATURES])
                + c.split_ns_per_feature * counts[C_SPLIT_FEATURES]
                + (c.predict_ns + c.predict_ns_per_feature * counts[C_REPLACEMENT_FEATURES] / max(1, counts[C_REPLACEMENT]))
                * counts[C_REPLACEMENT_PREDICT])

    def level_costs(self) -> list[float]:
        """Predicted cost of every level for the next row, cached while nothing it depends on changes."""
        pipe = self.pipe
        bg = pipe.background
        key = (len(pipe.active.features), None if bg is None else len(bg.features), pipe.update_stride,
               self.levers.run >= self.levers.easy_k)
        if key != self._cost_key:
            self._cost_key = key
            self._costs = [self.predict_level_ns(lv) for lv in self.levels]
        return self._costs

    def predict_level_ns(self, level: EffortLevel, k: int | None = None) -> float:
        """Expected modelled cost of a row at `level` with k model features (amortised: ranking and
        statistics rows are spread over their periods; splits are not included)."""
        c, pipe, e = self.e.cost, self.pipe, self.e
        n_all = len(pipe._features)
        k = len(pipe.active.features) if k is None else k
        bg = pipe.background
        need = min(n_all, k + (len(bg.features) if bg is not None else 0)) if e.narrow_preprocessing else n_all
        p_rank = 1.0 / level.rank_every if e.live_ranking else 0.0
        p_stats = 1.0 / level.stats_every
        n_tf = need + (n_all * p_rank if need < n_all else 0.0)  # ranking rows re-read all inputs
        n_stats = n_all * p_rank + need * p_stats * (1 - p_rank)
        if e.live_ranking:
            n_rank = n_all * p_rank
        else:
            n_rank = 0.0 if e.narrow_preprocessing else n_all
        upd = 1.0 / self.pipe.update_stride
        if level.skip_easy and self.levers.run >= self.levers.easy_k:
            upd /= level.easy_learn_every
        cost = (c.base_ns + c.controller_ns + c.predict_ns + c.detect_ns_per_label
                + c.transform_ns_per_input * n_tf + c.stats_ns_per_input * n_stats + c.rank_ns_per_input * n_rank
                + (c.select_ns_per_feature + c.predict_ns_per_feature) * k + upd * (c.update_ns + c.update_ns_per_feature * k))
        if bg is not None:
            kb = len(bg.features)
            cost += c.update_ns + c.update_ns_per_feature * kb + ((c.predict_ns + c.predict_ns_per_feature * kb) if e.fast_switch else 0)
        return cost

    # ------------------------------------------------------------------ engine interface
    def process(self, index, x, y):
        pipe = self.pipe
        offset = len(pipe.events)
        prediction, service, stages = pipe.process(index, x, y)
        if index < self.warmup:
            return prediction, service, stages
        start = perf_counter_ns()
        modelled = self.modelled_ns(pipe.row_counts)
        if pipe.delayed:
            outcomes, labels = pipe.revealed, pipe.revealed_labels
        else:
            outcomes, labels = (prediction == y,), (y,)
        retrain_ns = self._step(index, outcomes, service, pipe.events[offset:], labels=labels, modelled=modelled)
        elapsed = perf_counter_ns() - start
        pipe.controller_cost_ns[0] += elapsed - retrain_ns
        pipe.controller_cost_ns[1] += retrain_ns
        measured = list(stages)
        measured[4] += elapsed
        self.measured_sum += service + elapsed
        if self.deadline_ns is not None and service + elapsed > self.deadline_ns:
            self.measured_over_deadline += 1
        return prediction, service + elapsed, tuple(measured)

    # ------------------------------------------------------------------ signals
    def _signals(self, i: int, outcomes, labels, events) -> None:
        e = self.e
        switches, errors, mix = self._switches, self._errors, self._mix
        full = switches.maxlen
        for correct, y in zip(outcomes, labels):
            sw = self._last_y is not None and y != self._last_y
            self._last_y = y
            if len(switches) == full:
                self._switch_sum -= switches[0]
                self._error_sum -= errors[0]
            switches.append(sw)
            errors.append(not correct)
            self._switch_sum += sw
            self._error_sum += not correct
            if len(mix) == mix.maxlen:
                self._mix_sum -= mix[0]
            positive = bool(y)
            mix.append(positive)
            self._mix_sum += positive
        for ev in events:
            if ev["type"] == "drift_detected" and ev.get("error_increased"):
                self.alarm_until = i + e.alarm_hold
            elif ev["type"] == "adaptation_completed":
                self._mix_at_adaptation = self._mix_share()
        if not e.activity_signal:
            self.activity = 0.5
        elif i < self.alarm_until:
            self.activity = 1.0
        else:
            n = len(switches) or 1
            self.activity = min(1.0, self._switch_sum / n / e.switch_ref + self._error_sum / n / e.error_ref)

    def _mix_share(self) -> float | None:
        return self._mix_sum / len(self._mix) if self._mix else None

    def _damp(self, i: int) -> str | None:
        """D2: veto a drift alarm soon after an adaptation while the label mix has not moved."""
        e, last = self.e, self.pipe.last_adaptation
        if last is None or i - last > e.damp_rows or self._mix_at_adaptation is None:
            return None
        now = self._mix_share()
        if now is None or abs(now - self._mix_at_adaptation) > e.mix_tolerance:
            return None
        self.damped_alarms += 1
        return (f"re-alarm damped: {i - last} rows after an adaptation, label mix {now:.2f} "
                f"vs {self._mix_at_adaptation:.2f} then")

    def _gate_open(self, i: int) -> bool:
        if not self.e.feature_gate:
            return True
        counts = self.levers.rank_counts
        ok = len(counts) >= 2 and min(counts.values()) >= self.e.gate_rows_per_class
        if ok and self.gate_opened_at is None:
            self.gate_opened_at = i
        return ok

    def _budget(self) -> float | None:
        if self._budget_now is not None:
            budget = self._budget_now()
            if budget is not None:
                self.cpu_budget_ns = budget
                if self.budget_min_ns is None or budget < self.budget_min_ns:
                    self.budget_min_ns = budget
        return self.cpu_budget_ns

    # ------------------------------------------------------------------ the step
    def _step(self, i: int, outcomes, service: int, events: list[dict], *, labels=None, modelled: float | None = None) -> int:
        cfg, e, pipe, rules = self.cfg, self.e, self.pipe, self.rules
        if isinstance(outcomes, bool):
            outcomes = (outcomes,)
        if labels is None:
            labels = (None,) * len(outcomes)
        if modelled is None:
            modelled = float(service)
        cost = modelled if self.modelled_source else float(service)
        # tallies for the row that has just been served, at the level it was served with
        self.rows += 1
        self.level_rows[self.level] += 1
        self.cost_sum += cost
        self.modelled_sum += modelled
        if self.deadline_ns is not None and modelled > self.deadline_ns:
            self.modelled_over_deadline += 1
        # rolling accuracy (reported like the joint controller) and the activity signal
        for correct in outcomes:
            if len(self._correct) == self._correct.maxlen:
                self._correct_sum -= self._correct[0]
            self._correct.append(correct)
            self._correct_sum += correct
        self._signals(i, outcomes, labels, events)
        # deadline misses on the decision cost
        miss = self.deadline_ns is not None and cost > self.deadline_ns
        if len(self._misses) == self._misses.maxlen:
            self._miss_count -= self._misses[0]
        self._misses.append(miss)
        self._miss_count += miss
        # CPU share (EWMA, reported) and memory
        a = cfg.cpu_smoothing
        self.cpu_ewma = cost if self.cpu_ewma is None else (1 - a) * self.cpu_ewma + a * cost
        if self.memory_budget is not None and (i - self.warmup) % cfg.memory_check_every == 0:
            self._probe_memory()
        budget = self._budget()
        # the price of compute
        if budget:
            if e.budget_control:
                self.price = min(e.price_max, max(0.0, self.price + e.price_step * (cost / budget - 1.0)))
            else:
                self.price = 0.0
        self.price_peak = max(self.price_peak, self.price)
        mem = self.memory_bytes / self.memory_budget if self.memory_budget and self.memory_bytes is not None else None
        price_tight = bool(budget) and e.budget_control and self.price >= e.tight_price
        price_spare = not budget or not e.budget_control or self.price < e.spare_price
        tight = price_tight or (mem is not None and mem > cfg.memory_high)
        spare = price_spare and (mem is None or mem < cfg.memory_low)
        self.constrained = tight
        if pipe.lightweight:
            self.lightweight_rows += 1
        if any(ev["type"] == "adaptation_completed" for ev in events):
            self.last_structural = i
        if self._miss_count or tight:
            self.calm_since = i
        if not budget or self.price > 0:
            self._free_since = i
        free = i - self.last_structural >= cfg.cooldown
        signals = {"activity": self.activity, "price": self.price, "memory_share": mem,
                   "deadline_misses": self._miss_count}
        k = len(pipe.active.features)
        k_top = pipe.selector.k_initial if self.k_ceiling is None else min(pipe.selector.k_initial, self.k_ceiling)
        cheapest = self.levels[0]
        at_ceiling = bool(budget) and e.budget_control and self.price >= 0.999 * e.price_max \
            and self.level_costs()[0] > budget
        if at_ceiling:
            if self._ceiling_since is None:
                self._ceiling_since = i
        else:
            self._ceiling_since = None

        # R5 — memory over budget (hard; highest priority)
        if "R5" in rules and mem is not None and mem > 1.0 and free:
            refilled_soon = i - self._last_r5_reset < cfg.relax_after
            if pipe.drop_background(i, "R5: model memory over budget"):
                self._act(i, "R5_DROP_REPLACEMENT", **signals)
            elif refilled_soon and k > self.floor:
                new_k = max(self.floor, k // 2)
                pipe.reconfigure_features(i, new_k, f"R5: model memory over budget again ({mem:.0%})", immediate=True)
                self._act(i, f"R5_SHRINK_MODEL_{k}_TO_{new_k}", **signals)
                self._last_r5_reset = i
                self.k_ceiling = new_k
            else:
                pipe._reset_model(i, f"R5: model memory over budget ({mem:.0%}); a fresh model on the same features", action="memory_reset")
                self._act(i, "R5_FRESH_MODEL", **signals)
                self._last_r5_reset = i
            self.last_structural = i
            self._probe_memory()
        # Deadline (hard): too many rows over the per-row deadline
        elif "R3" in rules and self._miss_count >= cfg.deadline_misses and free:
            if k > self.floor and self._gate_open(i):
                new_k = max(self.floor, k // 2)
                pipe.reconfigure_features(i, new_k, "deadline missed too often: fewer features (live ranking)", immediate=True)
                self._act(i, f"DEADLINE_HALVE_FEATURES_{k}_TO_{new_k}", **signals)
            elif pipe.update_stride < self.max_stride:
                stride = min(self.max_stride, pipe.update_stride * 2)
                pipe.set_update_stride(i, stride, "deadline missed too often")
                self._act(i, f"DEADLINE_UPDATE_EVERY_{stride}", **signals)
            else:
                self._act(i, "DEADLINE_AT_MINIMUM", **signals)
            self.last_structural = i
            self._misses.clear()
            self._miss_count = 0
        # Price at its ceiling and even the cheapest level over budget: fewer features
        elif (self._ceiling_since is not None and i - self._ceiling_since >= e.cut_after and free
              and k > self.floor and self._gate_open(i)):
            new_k = max(self.floor, k // 2)
            pipe.reconfigure_features(i, new_k, "CPU budget not reachable even at the cheapest effort: fewer features (live ranking)",
                                      immediate=True)
            self._act(i, f"PRICE_HALVE_FEATURES_{k}_TO_{new_k}", **signals)
            self.last_structural = i
            self._ceiling_since = None
        # Calm for long: thinner updates first, then more features if they fit
        elif free and i - self.calm_since >= cfg.relax_after and pipe.update_stride > 1:
            stride = pipe.update_stride // 2
            pipe.set_update_stride(i, stride, "deadline met for a long stretch")
            self._act(i, f"RELAX_UPDATE_EVERY_{stride}", **signals)
            self.last_structural = self.calm_since = i
        elif (free and k < k_top and i - self.calm_since >= cfg.relax_after and i - self._free_since >= cfg.relax_after
              and (not budget or self.predict_level_ns(cheapest, min(k_top, 2 * k)) <= e.restore_share * budget)):
            new_k = min(k_top, 2 * k)
            pipe.reconfigure_features(i, new_k, "budget and deadline met for a long stretch: more features",
                                      immediate=pipe.lightweight)
            self._act(i, f"RELAX_FEATURES_{k}_TO_{new_k}", **signals)
            self.last_structural = self.calm_since = self._free_since = i
        if self.gate_opened_at is None:
            self._gate_open(i)  # records when the gate opens

        # R1 / R2 — how a drift is handled, chosen by the price (with hysteresis)
        keep_old = self.delay_aware and pipe._base_adapt_cfg.allow_background  # D3: never reset blind
        if cfg.resource_gating and "R2" in rules:
            if tight and not pipe.lightweight and not keep_old:
                pipe.set_lightweight(i, True, "R2: compute price high — adapt by reset, no replacement model")
                self._apply_drift_response()
            elif (spare or keep_old) and pipe.lightweight:
                pipe.set_lightweight(i, False, "R1: compute price low — adapt with a background replacement")
                self._apply_drift_response()
        for ev in events:
            if ev["type"] == "drift_detected" and ev.get("error_increased"):
                rule = "R2" if pipe.lightweight else "R1"
                self._act(i, f"{rule}_DRIFT" if rule in rules else f"{rule}_OFF_DRIFT_IGNORED", **signals)

        # the effort level of the next row
        self._set_level(self._choose(budget))
        return 0

    def _choose(self, budget: float | None) -> int:
        levels, e = self.levels, self.e
        if len(levels) == 1:
            return 0
        costs = self.level_costs()
        feasible = [j for j, c in enumerate(costs) if self.deadline_ns is None or c <= self.deadline_ns] or [0]
        if budget and not e.budget_control:
            return feasible[-1]
        ref = budget if budget else max(costs)
        best, best_value = feasible[0], None
        for j in feasible:
            value = self.activity * levels[j].benefit - self.price * costs[j] / ref
            if best_value is None or value > best_value + 1e-12:
                best, best_value = j, value
        return best

    # ------------------------------------------------------------------ reporting
    def report(self) -> dict:
        out = super().report()
        lv, n = self.levers, self.rows or 1
        names = [level.name for level in self.levels]
        out["rules"] = sorted(r for r in self.rules if r in ("R1", "R2", "R3", "R5"))
        out["final_narrow_processing"] = lv.narrow
        out["effort"] = {
            "cost_source": self.e.cost_source,
            "decisions_depend_on_measured_time": self.timing_dependent,
            "rows_per_level": dict(zip(names, self.level_rows)),
            "levels": [level.model_dump() for level in self.levels],
            "budget_us_per_row": self.cpu_budget_ns / 1e3 if self.cpu_budget_ns else None,
            "mean_decision_cost_us": self.cost_sum / n / 1e3,
            "mean_modelled_us": self.modelled_sum / n / 1e3,
            "mean_measured_us": self.measured_sum / n / 1e3,
            "rows_over_deadline_modelled": self.modelled_over_deadline,
            "rows_over_deadline_measured": self.measured_over_deadline,
            "final_price": self.price,
            "peak_price": self.price_peak,
            "final_activity": self.activity,
            "share_rows_update_skipped": lv.skipped_updates / n,
            "easy_rows": lv.easy_rows,
            "share_rows_statistics_updated": lv.stats_rows / n,
            "share_rows_ranking_updated": lv.rank_rows / n,
            "ranker_rows_per_class": {str(k): v for k, v in sorted(lv.rank_counts.items(), key=lambda kv: str(kv[0]))},
            "feature_gate_opened_at_row": self.gate_opened_at,
            "feature_floor": self.floor,
            "levers": {
                "B1_narrow_preprocessing": self.e.narrow_preprocessing,
                "B2_sample_statistics": self.e.sample_statistics,
                "B3_live_ranking": self.e.live_ranking,
                "B4_skip_easy_updates": self.e.skip_easy_updates,
                "B5_feature_gate": self.e.feature_gate,
                "budget_control": self.e.budget_control,
                "activity_signal": self.e.activity_signal,
            },
            "repairs": {
                "D1_fast_switch": self.e.fast_switch, "fast_switch_promotions": lv.fast_promotions,
                "D2_damp_realarms": self.e.damp_realarms, "damped_alarms": self.damped_alarms,
                "D3_delay_aware": self.e.delay_aware, "D3_active": self.delay_aware,
                "muted_labels": lv.muted_labels, "warm_starts": lv.warm_starts,
                "D3_race_only_post_hoc": lv.race_only,
            },
            "cost_model_ns": self.e.cost.model_dump(),
        }
        return out

