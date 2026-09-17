"""Measurement recording and factual summaries.

MethodRecorder keeps per-sample outcomes in compact arrays so any metric can be recomputed later by
the research team, and aggregates fixed-size blocks. Nothing here interprets results.
"""

from __future__ import annotations

import hashlib
import math
from array import array
from collections import Counter

import numpy as np

from adaptiveml.config import StabilityConfig
from adaptiveml.pipeline import STAGE_NAMES

N_STAGES = len(STAGE_NAMES)
_TN, _FP, _FN, _TP = b"\x00", b"\x01", b"\x02", b"\x03"


class MethodRecorder:
    """Per-method recording.

    Per sample the engine performs three C-level appends (`sinks`): an outcome code
    2·[label is positive] + [prediction is positive] (0 = TN, 1 = FP, 2 = FN, 3 = TP), the service
    time, and the six stage durations. Confusion counts, stage totals and percentiles are computed
    once per block; see the optimization log in docs/performance.md for the measurements behind this.
    """

    def __init__(self, method: str, positive_class):
        self.method = method
        self.positive_class = positive_class
        self.outcomes = array("b")
        self.service_ns = array("q")
        self._stages = array("q")  # current block only: six stage durations per sample, flattened
        self._block_lo = 0
        self.blocks: list[dict] = []
        self.sinks = (self.outcomes.append, self.service_ns.append, self._stages.extend)

    def add(self, y, y_pred, service: int, stages) -> None:
        """Record one sample — the same three appends the engine performs inline."""
        outcome, svc, st = self.sinks
        positive = self.positive_class
        outcome(((y == positive) << 1) | (y_pred == positive))
        svc(service)
        st(stages)

    def true_labels(self) -> np.ndarray:
        """1 where the label is the positive class (int8)."""
        return np.frombuffer(self.outcomes, dtype=np.int8) >> 1

    def predicted_labels(self) -> np.ndarray:
        """1 where the prediction is the positive class (int8)."""
        return np.frombuffer(self.outcomes, dtype=np.int8) & 1

    def close_block(self, index: int, start: int, extra: dict) -> dict | None:
        lo, hi = self._block_lo, len(self.outcomes)
        n = hi - lo
        if n == 0:
            return None
        codes = self.outcomes[lo:hi].tobytes()
        svc = sorted(self.service_ns[lo:hi])
        stage_totals = np.frombuffer(self._stages, dtype=np.int64).reshape(n, N_STAGES).sum(axis=0).tolist()
        del self._stages[:]
        self._block_lo = hi
        record = {
            "method": self.method,
            "block": index,
            "start": start,
            "n": n,
            "tp": codes.count(_TP),
            "fp": codes.count(_FP),
            "tn": codes.count(_TN),
            "fn": codes.count(_FN),
            "service_mean_ns": sum(svc) / n,
            "service_p95_ns": svc[max(0, math.ceil(0.95 * n) - 1)],
            "service_max_ns": svc[-1],
            **{f"{name}_mean_ns": total / n for name, total in zip(STAGE_NAMES, stage_totals)},
            **extra,
        }
        self.blocks.append(record)
        return record


def _ratio(a: float, b: float) -> float | None:
    return a / b if b else None


def classification_scores(tp: int, fp: int, tn: int, fn: int) -> dict:
    """Binary scores for the configured positive class; None where a score is undefined."""
    n = tp + fp + tn + fn
    return {
        "n": n,
        "accuracy": _ratio(tp + tn, n),
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, tp + fn),
        "f1": _ratio(2 * tp, 2 * tp + fp + fn),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def _scores_between(y_true: np.ndarray, y_pred: np.ndarray, lo: int, hi: int) -> dict | None:
    lo, hi = max(lo, 0), min(hi, len(y_true))
    if hi <= lo:
        return None
    t, p = y_true[lo:hi], y_pred[lo:hi]
    s = classification_scores(int(np.sum(t & p)), int(np.sum(~t & p)), int(np.sum(~t & ~p)), int(np.sum(t & ~p)))
    return {"range": [lo, hi], "accuracy": s["accuracy"], "f1": s["f1"]}


def rolling_accuracy(correct: np.ndarray, window: int) -> np.ndarray:
    """out[j] = accuracy over samples [j, j + window)."""
    c = np.concatenate(([0], np.cumsum(correct, dtype=np.int64)))
    return (c[window:] - c[:-window]) / window


def stability_reference(
    y_true: np.ndarray, y_pred: np.ndarray, drift_index: int, events: list[dict], cfg: StabilityConfig
) -> dict:
    """Reference computations for the "accuracy stability" measures.

    These are placeholders for discussion: the formula is a research-team decision. Segments are
    anchored at the true drift so that every method is measured over the same samples.
    """
    correct = (y_true == y_pred).astype(np.int8)
    n, w = len(correct), cfg.window
    pre = _scores_between(y_true, y_pred, drift_index - cfg.pre_window, drift_index)
    early = _scores_between(y_true, y_pred, drift_index, drift_index + cfg.pre_window)
    late = _scores_between(
        y_true, y_pred, drift_index + cfg.horizon - cfg.pre_window, drift_index + cfg.horizon
    )

    roll = rolling_accuracy(correct, w) if n >= w else np.array([])
    hi = min(drift_index + cfg.horizon, n) - w + 1
    min_after = float(roll[drift_index:hi].min()) if hi > drift_index else None

    detection = next(
        (e["i"] for e in events if e["type"] == "drift_detected" and e.get("error_increased") and e["i"] >= drift_index),
        None,
    )
    adaptation = next((e for e in events if e["type"] == "adaptation_completed" and e["i"] >= drift_index), None)
    post_adaptation = None
    if adaptation is not None:
        a = adaptation["i"] + 1 + cfg.post_gap
        post_adaptation = _scores_between(y_true, y_pred, a, a + cfg.pre_window)

    recovery = None
    if pre is not None and pre["accuracy"] is not None and len(roll) > drift_index:
        ok = (roll[drift_index:] >= pre["accuracy"] - cfg.tolerance).astype(np.int8)
        run = cfg.sustain + 1
        if len(ok) >= run:
            full = np.flatnonzero(np.convolve(ok, np.ones(run, dtype=np.int8), "valid") == run)
            if len(full):
                recovery = int(full[0]) + w  # end of the first qualifying window, relative to the drift

    return {
        "reference_computation": True,
        "parameters": cfg.model_dump(),
        "definitions": {
            "pre_drift": "scores over [drift - pre_window, drift)",
            "post_drift_early": "scores over [drift, drift + pre_window)",
            "post_drift_late": "scores over [drift + horizon - pre_window, drift + horizon)",
            "min_windowed_accuracy": "lowest accuracy of a window (size `window`) starting in [drift, drift + horizon - window]",
            "post_adaptation": "scores over [adaptation + 1 + post_gap, … + pre_window)",
            "recovery_samples": "samples from the drift to the end of the first window whose accuracy is ≥ pre-drift − tolerance and stays so for `sustain` further windows",
        },
        "drift_index": drift_index,
        "pre_drift": pre,
        "post_drift_early": early,
        "post_drift_late": late,
        "min_windowed_accuracy": min_after,
        "detection_delay_samples": None if detection is None else detection - drift_index,
        "adaptation_index": None if adaptation is None else adaptation["i"],
        "post_adaptation": post_adaptation,
        "recovery_samples": recovery,
    }


def summarize_method(rec: MethodRecorder, pipe, *, warmup: int, drift_index: int | None, stability: StabilityConfig) -> dict:
    predicted = rec.predicted_labels()
    y_true = rec.true_labels().astype(bool)
    y_pred = predicted.astype(bool)
    t, p = y_true[warmup:], y_pred[warmup:]
    scores = classification_scores(int(np.sum(t & p)), int(np.sum(~t & p)), int(np.sum(~t & ~p)), int(np.sum(t & ~p)))

    svc_us = np.frombuffer(rec.service_ns, dtype=np.int64)[warmup:] / 1_000.0
    post_blocks = [b for b in rec.blocks if b["start"] >= warmup]
    n_post = sum(b["n"] for b in post_blocks) or 1
    stage_us = {
        name: sum(b[f"{name}_mean_ns"] * b["n"] for b in post_blocks) / n_post / 1_000.0 for name in STAGE_NAMES
    }

    events = [e for e in pipe.events if e["i"] >= warmup]
    completed = [e for e in events if e["type"] == "adaptation_completed"]
    durations = [e["duration_ns"] / 1_000.0 for e in completed]
    if len(svc_us):
        latency = {
            "mean": float(svc_us.mean()),
            "p50": float(np.percentile(svc_us, 50)),
            "p95": float(np.percentile(svc_us, 95)),
            "p99": float(np.percentile(svc_us, 99)),
            "max": float(svc_us.max()),
        }
    else:  # e.g. a trial stopped during warm-up: no post-warm-up samples to summarise
        latency = dict.fromkeys(("mean", "p50", "p95", "p99", "max"))
    return {
        "method": rec.method,
        "scores_after_warmup": scores,
        "latency_us": latency,
        "stage_mean_us": stage_us,
        "processing_throughput_per_s": 1e6 / latency["mean"] if latency["mean"] else None,
        "drift_detections_error_increase": sum(
            1 for e in events if e["type"] == "drift_detected" and e["error_increased"]
        ),
        "adaptations": {
            "count": len(completed),
            "failed": sum(1 for e in events if e["type"] == "adaptation_failed"),
            "by_action": dict(Counter(e["action"] for e in completed)),
            "duration_us_mean": float(np.mean(durations)) if durations else None,
            "duration_us_max": float(np.max(durations)) if durations else None,
            "samples_from_detection_to_completion": [e["samples_after_detection"] for e in completed],
        },
        "fallback_predictions": pipe.n_fallback_predictions,
        "final_model": {
            "version": pipe.active.version,
            "features": list(pipe.active.features),
            "size_bytes": pipe.model_size_bytes,
        },
        "stability_reference": (
            None
            if drift_index is None
            else stability_reference(y_true, y_pred, drift_index, pipe.events, stability)
        ),
        # int8 0/1 bytes — identical to the earlier per-sample prediction arrays, so hashes stay comparable
        "predictions_sha256": hashlib.sha256(predicted.tobytes()).hexdigest(),
    }
