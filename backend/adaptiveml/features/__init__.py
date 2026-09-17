"""Online feature selection ([4], [16]).

Relevance is |w_j| of an online logistic regression on standardized inputs, and the top-k
features are kept. This adapts the truncation step of OFS (Hoi et al., 2012 [4]); it is not a
full re-implementation of OFS, which uses the sparse linear model itself as the classifier.
Limitation: relevance is linear, so features with non-monotonic effects can be under-ranked.

The ranking updates every sample. The *applied* selection lives with each model (ModelSlot) and
only changes at model boundaries, because a River tree routes samples that lack a split feature
down its most-traversed branch, which would silently degrade a live model.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from river import linear_model, optim

from adaptiveml.config import FeatureSelectionConfig


class OnlineFeatureSelector:
    def __init__(self, features: Sequence[str], cfg: FeatureSelectionConfig):
        self.features = tuple(features)
        n = len(self.features)
        if cfg.method == "none":
            self.k = n
            self._ranker = None
        else:
            self.k = min(cfg.k if cfg.k is not None else math.ceil(2 * n / 3), cfg.k_max or n, n)
            self._ranker = linear_model.LogisticRegression(optimizer=optim.SGD(cfg.learning_rate))
        self.k_initial = self.k  # a resource governor may lower k and later restore it up to this value
        self._order = {f: j for j, f in enumerate(self.features)}

    def learn(self, scaled: dict, y) -> None:
        if self._ranker is not None:
            self._ranker.learn_one(scaled, y)

    def ranking(self) -> list[tuple[str, float]]:
        """Features by decreasing relevance; ties keep the original feature order."""
        w = self._ranker.weights if self._ranker is not None else {}
        return sorted(
            ((f, abs(w.get(f, 0.0))) for f in self.features),
            key=lambda fw: (-fw[1], self._order[fw[0]]),
        )

    def proposed(self) -> tuple[str, ...]:
        """The top-k features, in original feature order."""
        if self.k >= len(self.features):
            return self.features
        top = {f for f, _ in self.ranking()[: self.k]}
        return tuple(f for f in self.features if f in top)
