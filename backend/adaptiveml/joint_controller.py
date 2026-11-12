"""Joint drift-and-resource controller: the review's decision rules R1-R5 (method "joint").

The review (§6.2) proposes, but does not test, an adaptation process that reads the data and the
machine at the same time. This controller makes each rule a concrete, logged check. It runs after
every row, once that row's label is known.

Signals
- drift: an ADWIN alarm on a rising error rate, raised by the pipeline this row.
- accuracy: over the last `window` rows.
- deadline misses: rows in the last `deadline_window` whose service time exceeded the profile's
  per-row deadline.
- CPU: an exponentially weighted mean of the service time, as a share of the profile's per-row
  CPU budget (compute share / stream rate). It is the pipeline's own time, measured in-process.
- memory: River's estimate of the model size (plus a replacement in training), every
  `memory_check_every` rows, as a share of the profile's model-memory budget.
A resource is "tight" above its `*_high` share and "spare" below its `*_low` share; in between, the
previous mode holds. Without a budget a resource is never tight.

Rules, highest priority first (the review gives resource limits priority over accuracy)
- R5 memory above budget → drop the replacement model; if none, a fresh model on the same features;
  if a fresh model fills the budget again within `relax_after` rows, a fresh model on half the features.
  The budget is fixed for the run, so features cut by R5 stay cut: R3 only restores its own cuts.
- R3 too many deadline misses → halve the features, and from the first step preprocess and rank
  only the features in use ("narrow processing"; preprocessing all inputs dominates the cost on
  wide data). At the minimum, learn from every 2nd/4th row. After `relax_after` calm rows it steps
  back up one step at a time; full processing resumes once all features are restored.
- R2 drift while resources are tight → lightweight adaptation: an immediate reset, no replacement
  model training alongside.
- R1 drift while resources are spare → incremental adaptation: a replacement trains in the
  background and is swapped in once ready (the pipeline's normal path).
- R4 rolling accuracy below the floor, resources spare → retrain a fresh model on the last
  `retrain_buffer` labelled rows and swap it in. While resources are tight it is deferred.
R3, R4 and R5 share a cooldown, and an adaptation by the pipeline restarts it.

The thresholds are implementation defaults, not tuned on results; the budgets come from the
resource profile, which is simulated. The rules are a rule ladder, not an optimiser, and this is
not presented as a new learning algorithm.
"""
from __future__ import annotations

from collections import Counter, deque
from time import perf_counter_ns

from adaptiveml.config import ControllerConfig, ResourceBudgets


class JointController:
    def __init__(self, pipe, cfg: ControllerConfig, budgets: ResourceBudgets, cpu_budget_ns: float | None,
                 cpu_budget_now=None):
        """`cpu_budget_now`, when given, returns the current per-row CPU budget (ns) or None; it is
        used when rows arrive at the dataset's recorded rate, so the budget shrinks during bursts."""
        self.pipe, self.cfg, self.budgets = pipe, cfg, budgets
        self.rules = set(cfg.rules)
        self.cpu_budget_ns = cpu_budget_ns
        self._budget_now = cpu_budget_now
        self.budget_min_ns: float | None = None
        self.deadline_ns = budgets.latency_deadline_ms * 1e6 if budgets.latency_deadline_ms else None
        self.memory_budget = budgets.model_memory_mib * 2**20 if budgets.model_memory_mib else None
        self.min_features = budgets.min_features
        self.max_stride = budgets.max_update_stride if budgets.max_update_stride > 1 else 4
        self.warmup = pipe._warmup

        self._correct = deque(maxlen=cfg.window)
        self._correct_sum = 0
        self._misses = deque(maxlen=cfg.deadline_window)
        self._miss_count = 0
        self.cpu_ewma: float | None = None
        self.memory_bytes: int | None = None
        self.memory_probes = 0
        self.memory_probes_over = 0  # probes that found the model over its budget
        self.memory_peak: int | None = None
        self._last_r5_reset = -(10**12)
        self.k_ceiling: int | None = None  # set by R5: R3 may restore features up to here, not beyond
        self.last_structural = -(10**12)
        self.calm_since = 0
        self._last_deferred = -(10**12)
        self.lightweight_rows = 0
        self.actions: Counter = Counter()
        self.constrained = False
        if "R4" in self.rules:
            pipe.recent = deque(maxlen=cfg.retrain_buffer)
        self._apply_drift_response()

    # ------------------------------------------------------------------ engine interface
    @property
    def decisions(self) -> int:
        return sum(v for k, v in self.actions.items() if not k.endswith(("DEFERRED_RESOURCES_TIGHT", "AT_MINIMUM", "IGNORED")))

    def process(self, index, x, y):
        pipe = self.pipe
        offset = len(pipe.events)
        prediction, service, stages = pipe.process(index, x, y)
        if index < self.warmup:
            return prediction, service, stages
        start = perf_counter_ns()
        # Only labels that have arrived are known: with delayed labels, judge by those.
        outcomes = pipe.revealed if pipe.delayed else (prediction == y,)
        retrain_ns = self._step(index, outcomes, service, pipe.events[offset:])
        elapsed = perf_counter_ns() - start
        pipe.controller_cost_ns[0] += elapsed - retrain_ns
        pipe.controller_cost_ns[1] += retrain_ns
        measured = list(stages)
        measured[4] += elapsed  # the controller's time counts as adaptation time, as in the rest of the engine
        return prediction, service + elapsed, tuple(measured)

    # ------------------------------------------------------------------ signals
    def _levels(self, i: int, service: int):
        cfg = self.cfg
        a = cfg.cpu_smoothing
        self.cpu_ewma = service if self.cpu_ewma is None else (1 - a) * self.cpu_ewma + a * service
        if self.memory_budget is not None and (i - self.warmup) % cfg.memory_check_every == 0:
            self._probe_memory()
        if self._budget_now is not None:
            budget = self._budget_now()
            if budget is not None:
                self.cpu_budget_ns = budget
                if self.budget_min_ns is None or budget < self.budget_min_ns:
                    self.budget_min_ns = budget
        cpu = self.cpu_ewma / self.cpu_budget_ns if self.cpu_budget_ns else None
        mem = self.memory_bytes / self.memory_budget if self.memory_budget and self.memory_bytes is not None else None
        tight = (cpu is not None and cpu > cfg.cpu_high) or (mem is not None and mem > cfg.memory_high)
        spare = (cpu is None or cpu < cfg.cpu_low) and (mem is None or mem < cfg.memory_low)
        return cpu, mem, tight, spare

    def _probe_memory(self) -> None:
        self.memory_bytes = size = self.pipe.model_bytes()
        self.memory_probes += 1
        if self.memory_peak is None or size > self.memory_peak:
            self.memory_peak = size
        if self.memory_budget and size > self.memory_budget:
            self.memory_probes_over += 1

    def _apply_drift_response(self) -> None:
        rule = "R2" if self.pipe.lightweight else "R1"
        self.pipe.respond_to_drift = rule in self.rules

    def _act(self, i: int, action: str, **signals) -> None:
        self.actions[action] += 1
        self.pipe.emit(i, "controller_action", action=action, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in signals.items()})

    # ------------------------------------------------------------------ rules
    def _step(self, i: int, outcomes, service: int, events: list[dict]) -> int:
        cfg, pipe, rules = self.cfg, self.pipe, self.rules
        if isinstance(outcomes, bool):
            outcomes = (outcomes,)
        # rolling accuracy over the labels known so far, and deadline misses
        for correct in outcomes:
            if len(self._correct) == self._correct.maxlen:
                self._correct_sum -= self._correct[0]
            self._correct.append(correct)
            self._correct_sum += correct
        accuracy = self._correct_sum / len(self._correct) if len(self._correct) == self._correct.maxlen else None
        miss = self.deadline_ns is not None and service > self.deadline_ns
        if len(self._misses) == self._misses.maxlen:
            self._miss_count -= self._misses[0]
        self._misses.append(miss)
        self._miss_count += miss
        cpu, mem, tight, spare = self._levels(i, service)
        self.constrained = tight
        if pipe.lightweight:
            self.lightweight_rows += 1
        if any(e["type"] == "adaptation_completed" for e in events):
            self.last_structural = i
        if self._miss_count or tight:
            self.calm_since = i
        free = i - self.last_structural >= cfg.cooldown
        signals = {"accuracy": accuracy, "cpu_share": cpu, "memory_share": mem, "deadline_misses": self._miss_count}
        k = len(pipe.active.features)
        k_initial = pipe.selector.k_initial if self.k_ceiling is None else min(pipe.selector.k_initial, self.k_ceiling)
        retrain_ns = 0

        # R5 — memory over budget (highest priority)
        if "R5" in rules and mem is not None and mem > 1.0 and free:
            refilled_soon = i - self._last_r5_reset < cfg.relax_after
            if pipe.drop_background(i, "R5: model memory over budget"):
                self._act(i, "R5_DROP_REPLACEMENT", **signals)
            elif refilled_soon and k > self.min_features:
                # a fresh model filled the budget again quickly: a smaller configuration is needed
                new_k = max(self.min_features, k // 2)
                pipe.reconfigure_features(i, new_k, f"R5: model memory over budget again ({mem:.0%})", immediate=True)
                self._act(i, f"R5_SHRINK_MODEL_{k}_TO_{new_k}", **signals)
                self._last_r5_reset = i
                self.k_ceiling = new_k  # the memory budget does not change, so this cut is kept
            else:
                pipe._reset_model(i, f"R5: model memory over budget ({mem:.0%}); a fresh model on the same features", action="memory_reset")
                self._act(i, "R5_FRESH_MODEL", **signals)
                self._last_r5_reset = i
            self.last_structural = i
            self._probe_memory()
        # R3 — per-row deadline missed too often
        elif "R3" in rules and self._miss_count >= cfg.deadline_misses and free:
            if k > self.min_features:
                new_k = max(self.min_features, k // 2)
                pipe.reconfigure_features(i, new_k, "R3: per-row deadline missed too often", immediate=True)
                if not pipe.narrow:  # fewer features only saves time if preprocessing narrows too
                    pipe.set_narrow(i, True, "R3: preprocess and rank only the features in use")
                self._act(i, f"R3_HALVE_FEATURES_{k}_TO_{new_k}", **signals)
            elif pipe.update_stride < self.max_stride:
                stride = min(self.max_stride, pipe.update_stride * 2)
                pipe.set_update_stride(i, stride, "R3: per-row deadline missed too often")
                self._act(i, f"R3_UPDATE_EVERY_{stride}", **signals)
            else:
                self._act(i, "R3_AT_MINIMUM", **signals)
            self.last_structural = i
            self._misses.clear()
            self._miss_count = 0
        # R3 — step back up after a long calm stretch
        elif "R3" in rules and free and i - self.calm_since >= cfg.relax_after and (pipe.update_stride > 1 or k < k_initial):
            if pipe.update_stride > 1:
                stride = pipe.update_stride // 2
                pipe.set_update_stride(i, stride, "R3: deadline met for a long stretch")
                self._act(i, f"R3_RELAX_UPDATE_EVERY_{stride}", **signals)
            else:
                new_k = min(k_initial, k * 2)
                pipe.reconfigure_features(i, new_k, "R3: deadline met for a long stretch", immediate=pipe.lightweight)
                if new_k >= pipe.selector.k_initial and pipe.narrow:
                    pipe.set_narrow(i, False, "R3: all features restored; full preprocessing and ranking resume")
                self._act(i, f"R3_RELAX_FEATURES_{k}_TO_{new_k}", **signals)
            self.last_structural = self.calm_since = i

        # R1 / R2 — how a drift is handled, chosen by the resource state (with hysteresis)
        if cfg.resource_gating and "R2" in rules:
            if tight and not pipe.lightweight:
                pipe.set_lightweight(i, True, "R2: resources tight — adapt by reset, no replacement model")
                self._apply_drift_response()
            elif spare and pipe.lightweight:
                pipe.set_lightweight(i, False, "R1: resources sufficient — adapt with a background replacement")
                self._apply_drift_response()
        for e in events:
            if e["type"] == "drift_detected" and e.get("error_increased"):
                rule = "R2" if pipe.lightweight else "R1"
                self._act(i, f"{rule}_DRIFT" if rule in rules else f"{rule}_OFF_DRIFT_IGNORED", **signals)

        # R4 — low accuracy: retrain on recent rows, only with resources to spare
        if ("R4" in rules and accuracy is not None and accuracy < cfg.accuracy_floor
                and i - self.last_structural >= cfg.cooldown and pipe.pending_since is None):
            if cfg.resource_gating and not spare:
                if i - self._last_deferred >= cfg.cooldown:
                    self._act(i, "R4_DEFERRED_RESOURCES_TIGHT", **signals)
                    self._last_deferred = i
            else:
                retrain_ns = pipe.retrain(i, f"R4: rolling accuracy {accuracy:.1%} below {cfg.accuracy_floor:.0%}")
                self._act(i, "R4_RETRAIN", **signals)
                self.last_structural = i
                self._correct.clear()
                self._correct_sum = 0
        return retrain_ns

    # ------------------------------------------------------------------ reporting
    def report(self) -> dict:
        return {
            "rules": sorted(self.rules),
            "resource_gating": self.cfg.resource_gating,
            "actions": dict(sorted(self.actions.items())),
            "decisions": self.decisions,
            "rows_in_lightweight_mode": self.lightweight_rows,
            "final_features": len(self.pipe.active.features),
            "final_update_stride": self.pipe.update_stride,
            "final_narrow_processing": self.pipe.narrow,
            "budgets": {
                "cpu_us_per_row": self.cpu_budget_ns / 1e3 if self.cpu_budget_ns else None,
                "cpu_us_per_row_lowest": self.budget_min_ns / 1e3 if self.budget_min_ns else None,
                "cpu_follows_arrival_rate": self._budget_now is not None,
                "deadline_ms": self.budgets.latency_deadline_ms,
                "model_memory_mib": self.budgets.model_memory_mib,
            },
            "last_cpu_share": None if not self.cpu_budget_ns or self.cpu_ewma is None else self.cpu_ewma / self.cpu_budget_ns,
            "last_model_bytes": self.memory_bytes,
            "memory_probes": self.memory_probes,
            "memory_probes_over_budget": self.memory_probes_over,
            "peak_model_bytes": self.memory_peak,
        }
