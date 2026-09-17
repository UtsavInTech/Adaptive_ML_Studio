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
    def __init__(self, features: Sequence[str], cfg: PreprocessingConfig):
        self._features = tuple(features)
        self._means = {f: stats.Mean() for f in self._features}
        if cfg.scaler == "adaptive_standard":
            self._scaler = preprocessing.AdaptiveStandardScaler(fading_factor=cfg.fading_factor)
        elif cfg.scaler == "standard":
            self._scaler = preprocessing.StandardScaler()
        else:
            self._scaler = None
        self._clip = cfg.clip if self._scaler is not None else None  # clip is in σ units

    def transform(self, x: dict) -> tuple[dict, dict]:
        """Return (imputed, scaled). `imputed` is what `learn` needs; `scaled` feeds the model."""
        means = self._means
        imputed = {f: (means[f].get() if _is_missing(v := x.get(f)) else v) for f in self._features}
        scaled = self._scaler.transform_one(imputed) if self._scaler is not None else imputed
        if self._clip is not None:
            c = self._clip
            scaled = {f: (c if v > c else -c if v < -c else v) for f, v in scaled.items()}
        return imputed, scaled

    def learn(self, x: dict, imputed: dict) -> None:
        for f in self._features:
            v = x.get(f)
            if not _is_missing(v):
                self._means[f].update(v)  # impute from observed values only
        if self._scaler is not None:
            self._scaler.learn_one(imputed)
