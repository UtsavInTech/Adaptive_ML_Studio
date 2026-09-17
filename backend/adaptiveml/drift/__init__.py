"""Error-stream drift detection with ADWIN [5].

Two ADWIN instances watch the model's 0/1 error stream: a sensitive one (larger δ) raises
warnings and a strict one (smaller δ) raises drift — the two-detector pattern ARF uses [20].
ADWIN flags a change in either direction, so each signal also reports whether the error rate
went up; the policy decides what to do with decreases.
"""

from __future__ import annotations

from enum import IntEnum

from river import drift

from adaptiveml.config import DetectorConfig


class Signal(IntEnum):
    NONE = 0
    WARNING = 1
    DRIFT = 2


class ErrorStreamDetector:
    def __init__(self, cfg: DetectorConfig):
        self._cfg = cfg
        self.reset()

    def reset(self) -> None:
        c = self._cfg
        self._drift = drift.ADWIN(delta=c.delta_drift, clock=c.clock)
        self._warning = (
            drift.ADWIN(delta=c.delta_warning, clock=c.clock) if c.delta_warning is not None else None
        )

    def update(self, error: int) -> tuple[Signal, bool]:
        """Feed one 0/1 error. Returns (signal, error_increased)."""
        detector = self._drift
        before = detector.estimation
        detector.update(error)
        drift_detected = detector.drift_detected
        increased = drift_detected and detector.estimation > before

        warning = self._warning
        if warning is not None:
            w_before = warning.estimation
            warning.update(error)
            if not drift_detected and warning.drift_detected:
                return Signal.WARNING, warning.estimation > w_before
        return (Signal.DRIFT, increased) if drift_detected else (Signal.NONE, False)

    @property
    def width(self) -> int:
        return self._drift.width

    @property
    def estimation(self) -> float:
        return self._drift.estimation
