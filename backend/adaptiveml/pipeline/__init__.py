"""One complete pipeline instance per compared method.

Per sample, in prequential test-then-train order (docs/architecture.md §3.1):
    preprocess → select → predict → [label revealed] → detect → decide/adapt → learn
A decision taken on sample i takes effect before sample i+1 is predicted — the activity diagram's
"detect/adapt before predict" order, viewed from the next sample.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from time import perf_counter_ns

from river import base

from adaptiveml.adaptation import Action, AdaptationPolicy
from adaptiveml.config import MethodName, PipelineConfig, derive_seed
from adaptiveml.drift import ErrorStreamDetector, Signal
from adaptiveml.features import OnlineFeatureSelector
from adaptiveml.models import ModelSlot, make_learner, project
from adaptiveml.preprocessing import Preprocessor

STAGE_NAMES = ("preprocess", "select", "predict", "detect", "adapt", "update")
FAILED_MESSAGE = "Adaptation failed — continuing with previous model"


@dataclass(frozen=True)
class MethodSpec:
    name: str
    learns_after_warmup: bool
    detects: bool
    pipeline: PipelineConfig


def method_spec(name: MethodName, base_cfg: PipelineConfig) -> MethodSpec:
    """Method presets (docs/architecture.md §3.2). Non-adaptive baselines use a non-forgetting scaler."""
    pre = base_cfg.preprocessing
    non_adaptive = base_cfg.model_copy(
        update={
            "preprocessing": pre.model_copy(
                update={"scaler": "standard" if pre.scaler == "adaptive_standard" else pre.scaler}
            )
        }
    )
    if name == "static":
        return MethodSpec(name, learns_after_warmup=False, detects=False, pipeline=non_adaptive)
    if name == "incremental":
        return MethodSpec(name, learns_after_warmup=True, detects=False, pipeline=non_adaptive)
    if name == "adaptive":
        return MethodSpec(name, learns_after_warmup=True, detects=True, pipeline=base_cfg)
    if name == "arf":
        arf = base_cfg.model_copy(update={"learner": base_cfg.learner.model_copy(update={"type": "arf"})})
        return MethodSpec(name, learns_after_warmup=True, detects=False, pipeline=arf)
    raise ValueError(f"unknown method: {name}")


class MethodPipeline:
    def __init__(
        self,
        spec: MethodSpec,
        features: Sequence[str],
        *,
        warmup: int,
        seed: int,
        learner_factory: Callable[[int], base.Classifier] | None = None,
        fallback_label=False,
    ):
        cfg = spec.pipeline
        self.name = spec.name
        self.spec = spec
        self._features = tuple(features)
        self._warmup = warmup
        self._seed = seed
        self._learner_factory = learner_factory or (lambda s: make_learner(cfg.learner, s))
        self._n_learners = 0
        self._adapt_cfg = cfg.adaptation
        self._fallback = fallback_label

        self.pre = Preprocessor(self._features, cfg.preprocessing)
        self.selector = OnlineFeatureSelector(self._features, cfg.feature_selection)
        self.active = ModelSlot(self._new_learner(), self._features, version=1, started_at=0)
        self.background: ModelSlot | None = None
        self.detector = ErrorStreamDetector(cfg.detector) if spec.detects else None
        self.policy = AdaptationPolicy(cfg.adaptation)
        self._warmup_buffer: deque = deque(maxlen=warmup)
        self._labels: dict = {}

        self.learning = True
        self.update_stride = 1  # learn from every n-th labelled sample (a resource governor may raise it)
        self._stride_count = 0
        self.pending_since: int | None = None  # detection index while a replacement is being prepared
        self.last_adaptation: int | None = None
        self.model_size_bytes: int | None = None
        self.n_fallback_predictions = 0
        self.events: list[dict] = []

    @property
    def adaptation_in_progress(self) -> bool:
        return self.pending_since is not None

    # ------------------------------------------------------------------ per-sample path
    def process(self, i: int, x: dict, y) -> tuple[object, int, tuple[int, int, int, int, int, int]]:
        """Return (prediction, service ns, per-stage ns). Stages are contiguous intervals, so their sum
        is exactly the service time, and no timer is read that is not a stage boundary."""
        now = perf_counter_ns
        t0 = now()
        imputed, scaled = self.pre.transform(x)
        t1 = now()
        active = self.active
        xa = {f: scaled[f] for f in active.features}
        t2 = now()
        y_pred = active.model.predict_one(xa)
        if y_pred is None:
            y_pred = self._fallback_label()
        t3 = now()
        if self.detector is not None and i >= self._warmup:
            signal, increased = self.detector.update(0 if y_pred == y else 1)
            t4 = now()
            if signal:
                self._on_signal(i, signal, increased)
                t5 = now()
            else:
                t5 = t4
        else:
            t4 = t5 = t3
        if self.learning:
            self._learn(i, x, imputed, scaled, xa if self.active is active else None, y)
            if i == self._warmup - 1:
                self._end_warmup(i)
        t6 = now()
        return y_pred, t6 - t0, (t1 - t0, t2 - t1, t3 - t2, t4 - t3, t5 - t4, t6 - t5)

    def _learn(self, i: int, x: dict, imputed: dict, scaled: dict, xa: dict | None, y) -> None:
        self.pre.learn(x, imputed)
        self.selector.learn(scaled, y)
        if i < self._warmup:
            self._warmup_buffer.append((scaled, y))
        self._labels[y] = self._labels.get(y, 0) + 1
        stride = self.update_stride
        if stride != 1:
            self._stride_count += 1
            if self._stride_count < stride:
                return
            self._stride_count = 0
        active = self.active
        active.model.learn_one(xa if xa is not None else project(scaled, active.features), y)
        active.trained_on += 1
        if self.background is not None:
            self._learn_background(i, scaled, y)

    def _learn_background(self, i: int, scaled: dict, y) -> None:
        bg = self.background
        try:
            bg.model.learn_one(project(scaled, bg.features), y)
        except Exception as exc:  # noqa: BLE001 — a failing replacement must not stop the stream
            self._fail(i, "train_replacement", exc)
            return
        bg.trained_on += 1
        if self.pending_since is not None:
            if bg.trained_on >= self._adapt_cfg.background_min_samples:
                self._promote(i, f"replacement model reached {bg.trained_on} samples", detected_at=self.pending_since)
        elif i - bg.started_at >= self._adapt_cfg.background_timeout:
            self.background = None
            self.emit(i, "background_discarded", reason="no drift confirmed before timeout", model_version=bg.version)

    def _fallback_label(self):
        self.n_fallback_predictions += 1
        return max(self._labels, key=self._labels.get) if self._labels else self._fallback

    # ------------------------------------------------------------------ boundaries
    def _end_warmup(self, i: int) -> None:
        proposed = self.selector.proposed()
        if proposed != self.active.features:
            # Rebuild once on the warm-up samples so the model only ever sees its applied features.
            model = self._new_learner()
            for scaled, y in self._warmup_buffer:
                model.learn_one(project(scaled, proposed), y)
            self.active = ModelSlot(model, proposed, self.active.version, i, trained_on=len(self._warmup_buffer))
        self._warmup_buffer.clear()
        self.emit(
            i,
            "selection_applied",
            selected=list(proposed),
            dropped=[f for f in self._features if f not in proposed],
            ranking=[[f, round(w, 6)] for f, w in self.selector.ranking()],
        )
        if not self.spec.learns_after_warmup:
            self.learning = False
            self.emit(i, "frozen")

    def _on_signal(self, i: int, signal: Signal, increased: bool) -> None:
        bg = self.background
        decision = self.policy.decide(
            signal,
            error_increased=increased,
            sample_index=i,
            last_adaptation=self.last_adaptation,
            background_trained=None if bg is None else bg.trained_on,
            adaptation_pending=self.pending_since is not None,
        )
        if signal is Signal.DRIFT:
            self.emit(
                i,
                "drift_detected",
                error_increased=increased,
                width=self.detector.width,
                error_estimate=round(self.detector.estimation, 6),
            )
        action = decision.action
        if action is Action.NONE:
            return
        if action is Action.IGNORE:
            if signal is Signal.DRIFT:
                self.emit(i, "drift_ignored", reason=decision.reason)
        elif action is Action.START_BACKGROUND:
            self._start_background(i, decision.reason)
        elif action is Action.SWAP:
            self._promote(i, decision.reason, detected_at=i)
        elif action is Action.RESET:
            self._reset_model(i, decision.reason)
        elif action is Action.PREPARE:
            self._prepare(i, decision.reason, "prepare")

    def _prepare(self, i: int, reason: str, action: str) -> None:
        """Keep the current model active while a replacement trains; promote it once it is ready."""
        if self.background is None and not self._start_background(i, reason):
            return
        self.pending_since = i
        if self.detector is not None:
            self.detector.reset()
        self.emit(
            i,
            "adaptation_started",
            action=action,
            reason=reason,
            replacement_version=self.background.version,
            replacement_trained=self.background.trained_on,
            needed=self._adapt_cfg.background_min_samples,
            features=list(self.background.features),
        )

    def _start_background(self, i: int, reason: str) -> bool:
        try:
            model = self._new_learner()
        except Exception as exc:  # noqa: BLE001
            self._fail(i, "start_replacement", exc)
            return False
        self.background = ModelSlot(model, self.selector.proposed(), self.active.version + 1, i)
        self.emit(i, "background_started", reason=reason, features=list(self.background.features))
        return True

    def _promote(self, i: int, reason: str, *, detected_at: int) -> None:
        start = perf_counter_ns()
        previous, new = self.active, self.background
        self.active, self.background, self.pending_since = new, None, None
        if self.detector is not None:
            self.detector.reset()
        self.last_adaptation = i
        self._emit_completed(i, "swap", reason, previous, new, detected_at, start)

    def _reset_model(self, i: int, reason: str, action: str = "reset") -> None:
        start = perf_counter_ns()
        try:
            model = self._new_learner()
        except Exception as exc:  # noqa: BLE001
            self._fail(i, action, exc)
            return
        previous = self.active
        self.active = ModelSlot(model, self.selector.proposed(), previous.version + 1, i)
        self.background, self.pending_since = None, None
        if self.detector is not None:
            self.detector.reset()
        self.last_adaptation = i
        self._emit_completed(i, action, reason, previous, self.active, i, start)

    def _fail(self, i: int, action: str, exc: Exception) -> None:
        self.background, self.pending_since = None, None
        if self.detector is not None:
            self.detector.reset()
        self.last_adaptation = i  # wait out the cooldown before trying again
        self.emit(i, "adaptation_failed", action=action, error=repr(exc), model_version=self.active.version, message=FAILED_MESSAGE)

    def _emit_completed(self, i, action, reason, previous: ModelSlot, new: ModelSlot, detected_at: int, start: int) -> None:
        self.emit(
            i,
            "adaptation_completed",
            action=action,
            reason=reason,
            model_version=new.version,
            trained_on=new.trained_on,
            detected_at=detected_at,
            samples_after_detection=i - detected_at,
            features=list(new.features),
            dropped=[f for f in previous.features if f not in new.features],
            duration_ns=perf_counter_ns() - start,
        )

    def _new_learner(self) -> base.Classifier:
        self._n_learners += 1
        return self._learner_factory(derive_seed(self._seed, f"{self.name}.learner.{self._n_learners}"))

    # ------------------------------------------------------------------ resource governor hooks
    def set_update_stride(self, i: int, stride: int, reason: str) -> None:
        old, self.update_stride, self._stride_count = self.update_stride, stride, 0
        self.emit(i, "config_changed", field="update_stride", old=old, new=stride, reason=reason)

    def reconfigure_features(self, i: int, k: int, reason: str) -> None:
        """Change the number of selected features. The current model cannot drop a feature it splits
        on, so this is a model change: a replacement on the new feature set (promoted when ready), or
        a fresh model when the profile disallows background models."""
        old = len(self.active.features)
        self.selector.k = k
        self.emit(i, "config_changed", field="n_features", old=old, new=k, reason=reason)
        if self.background is not None and self.background.features != self.selector.proposed():
            self.background = None
        if self._adapt_cfg.allow_background:
            self._prepare(i, reason, "reconfigure")
        else:
            self._reset_model(i, reason, action="reconfigure")

    # ------------------------------------------------------------------ reporting
    def emit(self, i: int, kind: str, **fields) -> None:
        self.events.append({"i": i, "method": self.name, "type": kind, **fields})

    def block_extra(self) -> dict:
        return {
            "model_version": self.active.version,
            "n_features": len(self.active.features),
            "model_size_bytes": self.model_size_bytes,
            "background": self.background is not None,
            "adapting": self.pending_since is not None,
            "learning": self.learning,
            "update_stride": self.update_stride,
        }
