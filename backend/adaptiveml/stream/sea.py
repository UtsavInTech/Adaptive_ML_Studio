"""SEA concepts stream with sample-indexed drift (River `synth.SEA` concepts).

SEA draws x0, x1, x2 ~ U(0, 10); the label is `x0 + x1 > θ`, where θ depends on the concept
variant. x2 is irrelevant by construction, which gives feature selection a known right answer.

Drifts are sigmoid concept transitions with the semantics of River's ConceptDriftStream (see
`transition.py`). The chain is evaluated as a flat loop that is draw-for-draw identical to nesting
one transition per drift (tests/test_stream_inject.py), which also allows `inject()`: a drift added
during a live run yields exactly the stream that replaying the resolved config yields.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from dataclasses import dataclass

from river.datasets import synth

from adaptiveml.config import DriftSpec, StreamConfig, derive_seed
from adaptiveml.stream.transition import _EXP_LIMIT, transition_probability

SEA_THRESHOLDS = {0: 8.0, 1: 9.0, 2: 7.0, 3: 9.5}
FEATURES = ("x0", "x1", "x2")


def label_flip_fraction(from_variant: int, to_variant: int) -> float:
    """Share of the input space whose label changes between two SEA concepts (before noise).

    With x0, x1 ~ U(0, 10) and θ < 10, P(x0 + x1 ≤ θ) = θ² / 200, so the band between two
    thresholds covers |θb² − θa²| / 200 of the space.
    """
    a, b = SEA_THRESHOLDS[from_variant], SEA_THRESHOLDS[to_variant]
    return abs(b * b - a * a) / 200.0


def injection_margin(width: int) -> int:
    """Samples ahead of the stream at which an injected drift must be placed so that every earlier
    sample had a transition probability of exactly 0 (the exponent exceeds the clamp)."""
    return math.ceil(_EXP_LIMIT * width / 4) + 1


@dataclass(frozen=True)
class GroundTruthDrift:
    index: int
    width: int
    from_variant: int
    to_variant: int
    label_flip_fraction: float

    @property
    def kind(self) -> str:
        return "abrupt" if self.width == 1 else "gradual"

    # A sigmoid transition has tails: 2·width either side of its centre covers all but 0.03 % of it.
    @property
    def start(self) -> int:
        return self.index if self.width == 1 else max(0, self.index - 2 * self.width)

    @property
    def end(self) -> int:
        return self.index + 1 if self.width == 1 else self.index + 2 * self.width


class SeaScenario:
    is_synthetic = True
    feature_names = FEATURES

    def __init__(self, cfg: StreamConfig, seed: int):
        self.cfg = cfg
        self.seed = seed
        self._drifts: list[DriftSpec] = list(cfg.drifts)
        self._variants = [cfg.initial_variant] + [d.to_variant for d in cfg.drifts]
        self._live: dict | None = None  # iteration state, present while iterating
        self.cursor = -1  # index of the last sample produced

    @property
    def drifts(self) -> tuple[DriftSpec, ...]:
        """Scheduled plus injected drifts — what a replay config must contain."""
        return tuple(self._drifts)

    @property
    def ground_truth_drifts(self) -> tuple[GroundTruthDrift, ...]:
        v = self._variants
        return tuple(
            GroundTruthDrift(d.position, d.width, v[k], v[k + 1], label_flip_fraction(v[k], v[k + 1]))
            for k, d in enumerate(self._drifts)
        )

    @property
    def current_variant(self) -> int:
        """The concept of the most recent drift the stream has passed (by sample index)."""
        passed = [k for k, d in enumerate(self._drifts) if d.position <= self.cursor]
        return self._variants[passed[-1] + 1] if passed else self._variants[0]

    @property
    def info(self) -> dict:
        return {
            "name": "SEA",
            "source": "river.datasets.synth.SEA concepts (river 0.26.1) + sigmoid concept transitions",
            "real": False,
            "feature_names": list(FEATURES),
            "n_features": len(FEATURES),
            "length": self.cfg.length,
            "noise": self.cfg.noise,
            "variants": list(self._variants),
            "thresholds": {str(v): SEA_THRESHOLDS[v] for v in sorted(set(self._variants))},
            "drifts": [gt.__dict__ | {"kind": gt.kind} for gt in self.ground_truth_drifts],
        }

    def _concept(self, k: int):
        return iter(synth.SEA(variant=self._variants[k], noise=self.cfg.noise, seed=derive_seed(self.seed, f"sea.concept.{k}")))

    def _transition_rng(self, k: int) -> random.Random:
        return random.Random(derive_seed(self.seed, f"sea.transition.{k}"))

    def __iter__(self) -> Iterator[tuple[int, dict[str, float], bool]]:
        drifts = self._drifts
        live = {
            "concepts": [self._concept(k) for k in range(len(self._variants))],
            "rngs": [self._transition_rng(k) for k in range(len(drifts))],
            # A transition's position is relative to the previous change (+1: counters start at 1).
            "rel": [d.position - (drifts[k - 1].position if k else 0) + 1 for k, d in enumerate(drifts)],
            "widths": [d.width for d in drifts],
            "entered": [0] * len(self._variants),  # how often each level of the chain was reached
        }
        self._live = live
        concepts, rngs, rel, widths, entered = (live[k] for k in ("concepts", "rngs", "rel", "widths", "entered"))
        a, b, c = FEATURES
        try:
            for i in range(self.cfg.length):
                level = 0
                while True:
                    entered[level] += 1
                    if level == len(rngs):
                        break
                    if rngs[level].random() > transition_probability(entered[level], rel[level], widths[level]):
                        break
                    level += 1
                x, y = next(concepts[level])
                self.cursor = i
                yield i, {a: x[0], b: x[1], c: x[2]}, y
        finally:
            self._live = None

    def inject(self, to_variant: int, *, width: int = 1, at: int | None = None) -> DriftSpec:
        """Add a drift during iteration, reproducibly.

        The drift is placed at least `injection_margin(width)` samples ahead of the stream. Every
        earlier sample then had a transition probability of exactly 0 in a replay, so resuming the
        new transition (its counter and random stream fast-forwarded) yields the identical stream
        that replaying the resolved config produces.
        """
        live = self._live
        if live is None:
            raise RuntimeError("drift injection is only possible while the stream is running")
        pending = [d.position for d in self._drifts if d.position > self.cursor]
        if pending:
            raise ValueError(f"a scheduled drift is still pending at sample {pending[0]:,}")
        if to_variant == self.current_variant:
            raise ValueError(f"the stream is already in SEA concept {to_variant}")
        earliest = self.cursor + 1 + injection_margin(width)
        position = max(at if at is not None else earliest, earliest)
        if position >= self.cfg.length:
            raise ValueError(f"not enough stream left: the drift would land at {position:,} ≥ length {self.cfg.length:,}")

        k = len(self._drifts)  # the new transition sits on the chain's former terminal level
        previous = self._drifts[-1].position if self._drifts else 0
        spec = DriftSpec(position=position, width=width, to_variant=to_variant)
        self._drifts.append(spec)
        self._variants.append(to_variant)

        rng = self._transition_rng(k)
        for _ in range(live["entered"][k]):  # replay draws the transition would have made so far
            rng.random()
        live["rngs"].append(rng)
        live["rel"].append(position - previous + 1)
        live["widths"].append(width)
        live["concepts"].append(self._concept(k + 1))
        live["entered"].append(0)
        return spec
