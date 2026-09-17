"""Numerically stable sigmoid concept transition between two streams.

Same semantics and random-draw sequence as `river.datasets.synth.ConceptDriftStream` (0.26.1):
sample k (1-based) is drawn from the new concept with probability 1 / (1 + exp(-4 (k - position) / width)).

River computes `math.exp` of that exponent directly, which raises OverflowError when the width is
small and the drift is far away (width = 1 and more than ~177 samples before the drift), so abrupt
drifts at realistic positions cannot be generated with it. Beyond |exponent| = 700 the probability
is already exactly 0.0 or 1.0 in float arithmetic, so clamping there yields identical draws.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Iterator

_EXP_LIMIT = 700.0


def transition_probability(k: int, position: int, width: int) -> float:
    v = -4.0 * (k - position) / width
    if v > _EXP_LIMIT:
        return 0.0
    if v < -_EXP_LIMIT:
        return 1.0
    return 1.0 / (1.0 + math.exp(v))


class ConceptTransition:
    def __init__(self, stream: Iterable, drift_stream: Iterable, *, position: int, width: int, seed: int | None):
        if width < 1:
            raise ValueError("width must be ≥ 1")
        self.stream = stream
        self.drift_stream = drift_stream
        self.position = position
        self.width = width
        self.seed = seed

    def __iter__(self) -> Iterator:
        rng = random.Random(self.seed)
        old, new = iter(self.stream), iter(self.drift_stream)
        k = 0
        while True:
            k += 1
            source = old if rng.random() > transition_probability(k, self.position, self.width) else new
            try:
                yield next(source)
            except StopIteration:
                return
