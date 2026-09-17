"""Resource-aware adaptation under a simulated budget — gap G5: adapt to data drift *and* resources.

Checked once per block, never per sample. When a method's mean service time stays above its
per-sample budget for `down_blocks` consecutive blocks, the governor steps down one level:

    1. learn from fewer samples: update stride × 2, up to `max_update_stride`
    2. then use one feature fewer: a reconfiguration (a new model on the reduced feature set)

When the service time stays below `up_margin × budget` for `up_blocks` blocks, it steps back up in
reverse order. Decisions depend on *measured* time, so trials under a budget are not bit-
reproducible; every decision is logged with the measurement that caused it.
"""

from __future__ import annotations

from adaptiveml.config import ResourceBudgets


class ResourceGovernor:
    def __init__(self, budgets: ResourceBudgets, budget_ns: float):
        self.budgets = budgets
        self.budget_ns = budget_ns
        self.constrained = False
        self.decisions = 0
        self._over = self._under = 0

    def check(self, pipe, record: dict, sample_index: int) -> None:
        b, mean = self.budgets, record["service_mean_ns"]
        over = mean > self.budget_ns
        if over != self.constrained:
            self.constrained = over
            pipe.emit(
                sample_index,
                "budget_exceeded" if over else "budget_cleared",
                budget="service time per sample (simulated)",
                measured_us=round(mean / 1e3, 2),
                limit_us=round(self.budget_ns / 1e3, 2),
            )
        if over:
            self._over, self._under = self._over + 1, 0
        elif mean < b.up_margin * self.budget_ns:
            self._over, self._under = 0, self._under + 1
        else:
            self._over = self._under = 0

        if self._over >= b.down_blocks:
            self._over = 0
            self._step_down(pipe, sample_index, mean)
        elif self._under >= b.up_blocks:
            self._under = 0
            self._step_up(pipe, sample_index, mean)

    def _reason(self, mean: float, comparison: str, blocks: int) -> str:
        return f"mean service {mean / 1e3:.1f} µs {comparison} budget {self.budget_ns / 1e3:.1f} µs for {blocks} blocks"

    def _step_down(self, pipe, i: int, mean: float) -> None:
        b = self.budgets
        reason = self._reason(mean, ">", b.down_blocks)
        if pipe.update_stride < b.max_update_stride:
            pipe.set_update_stride(i, min(pipe.update_stride * 2, b.max_update_stride), reason)
            self.decisions += 1
        elif len(pipe.active.features) > b.min_features and not pipe.adaptation_in_progress:
            pipe.reconfigure_features(i, len(pipe.active.features) - 1, reason)
            self.decisions += 1

    def _step_up(self, pipe, i: int, mean: float) -> None:
        b = self.budgets
        reason = self._reason(mean, f"< {b.up_margin:g} ×", b.up_blocks)
        if len(pipe.active.features) < pipe.selector.k_initial and not pipe.adaptation_in_progress and pipe.update_stride == 1:
            pipe.reconfigure_features(i, len(pipe.active.features) + 1, reason)
            self.decisions += 1
        elif pipe.update_stride > 1:
            pipe.set_update_stride(i, pipe.update_stride // 2, reason)
            self.decisions += 1
