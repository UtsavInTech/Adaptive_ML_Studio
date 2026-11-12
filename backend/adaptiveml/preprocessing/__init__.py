"""Adaptive preprocessing ([3], [17], [19]): running-mean imputation → scaling → clipping.

`transform` uses only statistics learned from earlier samples (test-then-train); the caller
decides when `learn` is invoked, which is how the static baseline is frozen after warm-up.
"""

from __future__ import annotations

from collections.abc import Sequence

from river import preprocessing, stats

from adaptiveml.config import PreprocessingConfig


def _is_missing(v) -> bool:
    return v is None or v != v  # NaN is the only value not equal to itself


class Preprocessor:
    def __init__(self, features: Sequence[str], cfg: PreprocessingConfig, *, gap_aware: bool = False):
        """`gap_aware` (method "effort" only): the exponentially weighted scaler is kept here, per
        input, with the fading factor scaled by the rows since that input's last update,
        α_gap = 1 − (1 − α)^gap. Updating 1 row in s then keeps the same memory in rows as updating
        every row (lever B2). With gap = 1 it is the same recurrence as River's EWMean/EWVar."""
        self._features = tuple(features)
        self._means = {f: stats.Mean() for f in self._features}
        self._ew: dict | None = None
        if gap_aware and cfg.scaler == "adaptive_standard":
            self._ew, self._alpha = {}, cfg.fading_factor
            self._scaler = None
        elif cfg.scaler == "adaptive_standard":
            self._scaler = preprocessing.AdaptiveStandardScaler(fading_factor=cfg.fading_factor)
        elif cfg.scaler == "standard":
            self._scaler = preprocessing.StandardScaler()
        else:
            self._scaler = None
        self._clip = cfg.clip if (self._scaler is not None or self._ew is not None) else None  # clip is in σ units

    def transform(self, x: dict, only: tuple[str, ...] | None = None) -> tuple[dict, dict]:
        """Return (imputed, scaled). `imputed` is what `learn` needs; `scaled` feeds the model.
        `only` restricts the work to those features (narrow processing under a latency deadline)."""
        means = self._means
        imputed = {f: (means[f].get() if _is_missing(v := x.get(f)) else v) for f in (only or self._features)}
        if self._ew is not None:
            ew = self._ew
            scaled = {}
            for f, v in imputed.items():
                st = ew.get(f)
                scaled[f] = 0.0 if st is None or st[1] <= 0 else (v - st[0]) / st[1] ** 0.5
        elif self._scaler is not None:
            scaled = self._scaler.transform_one(imputed)
        else:
            scaled = imputed
        if self._clip is not None:
            c = self._clip
            scaled = {f: (c if v > c else -c if v < -c else v) for f, v in scaled.items()}
        return imputed, scaled

    def learn(self, x: dict, imputed: dict) -> None:
        for f in imputed:
            v = x.get(f)
            if not _is_missing(v):
                self._means[f].update(v)  # impute from observed values only
        if self._scaler is not None:
            self._scaler.learn_one(imputed)

    def learn_at(self, x: dict, imputed: dict, i: int) -> None:
        """Update the statistics of the inputs in `imputed` from row i (gap-aware scaler)."""
        means = self._means
        for f in imputed:
            v = x.get(f)
            if not _is_missing(v):
                means[f].update(v)
        ew = self._ew
        if ew is None:
            if self._scaler is not None:
                self._scaler.learn_one(imputed)
            return
        a0 = self._alpha
        for f, v in imputed.items():
            st = ew.get(f)
            if st is None:
                ew[f] = [v, 0.0, i]
                continue
            gap = i - st[2]
            a = a0 if gap <= 1 else 1.0 - (1.0 - a0) ** gap
            diff = v - st[0]
            incr = a * diff
            st[0] += incr
            st[1] = (1.0 - a) * (st[1] + diff * incr)
            st[2] = i
