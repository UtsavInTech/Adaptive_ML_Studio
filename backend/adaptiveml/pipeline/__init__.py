"""One complete pipeline instance per compared method.

Per sample, in prequential test-then-train order (docs/architecture.md §3.1):
    preprocess → select → predict → [label revealed] → detect → decide/adapt → learn
A decision taken on sample i takes effect before sample i+1 is predicted — the activity diagram's
"detect/adapt before predict" order, viewed from the next sample.
"""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
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


# Work recorded per row by the effort path (`row_counts`), read by the effort controller's cost model.
(C_TRANSFORM, C_STATS, C_RANK, C_SELECT, C_DETECT, C_UPDATE, C_UPDATE_FEATURES, C_SPLIT_FEATURES,
 C_REPLACEMENT, C_REPLACEMENT_FEATURES, C_REPLACEMENT_PREDICT) = range(11)
N_COUNTS = 11


@dataclass
class Levers:
    """Pipeline-side state of the effort levers (method "effort"). The controller sets the rates
    each row from the chosen effort level; sampling uses deterministic credit counters, not random
    draws, so a run is repeatable."""

    narrow: bool = False            # B1
    sample_stats: bool = False      # B2
    live_ranking: bool = False      # B3
    skip_easy: bool = False         # B4
    easy_k: int = 100
    fast_switch: bool = False       # D1
    switch_window: int = 20
    delay_aware: bool = False       # D3 (detector mute)
    race_only: bool = False         # D3 variant (post hoc): a replacement must beat the old model
    stats_rate: float = 1.0         # 1/s
    rank_rate: float = 1.0          # 1/r
    easy_rate: float = 1.0          # 1/m
    stats_credit: float = 0.0
    rank_credit: float = 0.0
    easy_credit: float = 0.0
    rank_version: int = 0
    rank_min_per_class: int = 0     # B3: rank every row of a class seen fewer times than this
    rank_counts: dict = field(default_factory=dict)
    run: int = 0
    last_label: object = None
    race_slot: object = None
    race: deque = field(default_factory=deque)
    # tallies (after warm-up)
    stats_rows: int = 0
    rank_rows: int = 0
    easy_rows: int = 0
    skipped_updates: int = 0
    fast_promotions: int = 0
    muted_labels: int = 0
    warm_starts: int = 0


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
    if name in ("adaptive", "joint", "effort"):
        # "joint" is the same pipeline under the joint drift-and-resource controller (R1-R5);
        # "effort" is the same pipeline under the budgeted effort controller, which switches on the
        # effort levers (enable_effort) before the first row.
        return MethodSpec(name, learns_after_warmup=True, detects=True, pipeline=base_cfg)
    if name in ("arf", "srp", "lev_bag"):
        # Literature ensembles: each manages drift inside its own members, so no pipeline detector.
        cfg = base_cfg.model_copy(update={"learner": base_cfg.learner.model_copy(update={"type": name})})
        return MethodSpec(name, learns_after_warmup=True, detects=False, pipeline=cfg)
    if name == "no_change":
        # Repeats the previous row's label. Same preprocessing path as the others, so its cost is
        # measured the same way, but the learner never looks at a feature.
        cfg = non_adaptive.model_copy(update={"learner": base_cfg.learner.model_copy(update={"type": "no_change"})})
        return MethodSpec(name, learns_after_warmup=True, detects=False, pipeline=cfg)
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
        label_delay: int = 0,
        label_coverage: float = 1.0,
        label_seed: int = 0,
    ):
        cfg = spec.pipeline
        # Delayed / partial labels (after warm-up): a row's label reaches the pipeline `label_delay`
        # rows after its prediction, and only for a `label_coverage` share of rows. Which rows get a
        # label is drawn from `label_seed`, the same for every method of a trial.
        self.delayed = label_delay > 0 or label_coverage < 1.0
        self._delay, self._coverage = label_delay, label_coverage
        self._label_rng = random.Random(label_seed)
        self._pending: deque = deque()
        self.revealed: list[bool] = []  # delayed mode: was each label that arrived this row predicted right?
        self.name = spec.name
        self.spec = spec
        self._features = tuple(features)
        self._warmup = warmup
        self._seed = seed
        self._learner_factory = learner_factory or (lambda s: make_learner(cfg.learner, s))
        self._n_learners = 0
        self._adapt_cfg = self._base_adapt_cfg = cfg.adaptation
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
        # Time spent inside the "update" stage, split by the review's cost terms (ns, after warm-up):
        # [preprocessing statistics, feature-selection statistics, model update, replacement training]
        self.cost_ns = [0, 0, 0, 0]
        self.lightweight = False  # set by the joint controller (R2): adapt by reset, no replacement model
        self.recent: deque | None = None  # recent (scaled row, label) pairs, kept only for R4 retraining
        self.narrow = False  # R3: preprocess and rank only the features the models use
        self._narrow_key = None
        self._narrow_features: tuple[str, ...] | None = None
        self.respond_to_drift = True  # the joint controller turns this off when the matching rule is ablated
        # Controller time after warm-up (ns): [decisions and measurements, R4 retraining]
        self.controller_cost_ns = [0, 0]
        # Method "effort" only (all off otherwise, so every other method runs the code paths above).
        self.levers: Levers | None = None
        self.drift_gate: Callable[[int], str | None] | None = None  # D2: may veto a drift alarm
        self._warm_start = 0  # D3: rows of the recent labelled buffer a new model first learns from

    @property
    def adaptation_in_progress(self) -> bool:
        return self.pending_since is not None

    # ------------------------------------------------------------------ per-sample path
    def process(self, i: int, x: dict, y) -> tuple[object, int, tuple[int, int, int, int, int, int]]:
        """Return (prediction, service ns, per-stage ns). Stages are contiguous intervals, so their sum
        is exactly the service time, and no timer is read that is not a stage boundary."""
        if self.levers is not None:
            return self._process_effort(i, x, y)
        if self.delayed and i >= self._warmup:
            return self._process_delayed(i, x, y)
        now = perf_counter_ns
        t0 = now()
        imputed, scaled = self.pre.transform(x, self._narrowed()) if self.narrow else self.pre.transform(x)
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

    def _process_delayed(self, i: int, x: dict, y):
        """Predict row i now; detect, adapt and learn on the labels that arrive this row.

        The label `y` of row i is held back: it is used only once `label_delay` rows have passed, and
        only if the row was drawn as labelled. Detection and adaptation run on arriving labels, so a
        drift is noticed no earlier than its labels arrive. Stages stay contiguous: detect and adapt
        sum over the arriving labels, and update is the rest of the row's time.
        """
        now = perf_counter_ns
        t0 = now()
        imputed, scaled = self.pre.transform(x, self._narrowed()) if self.narrow else self.pre.transform(x)
        t1 = now()
        active = self.active
        xa = {f: scaled[f] for f in active.features}
        t2 = now()
        y_pred = active.model.predict_one(xa)
        if y_pred is None:
            y_pred = self._fallback_label()
        t3 = now()
        pending = self._pending
        if self._label_rng.random() < self._coverage:
            pending.append((i, x, imputed, scaled, y_pred, y))
        revealed = self.revealed = []
        detect = adapt = 0
        due = i - self._delay
        while pending and pending[0][0] <= due:
            j, xj, imputed_j, scaled_j, pred_j, y_j = pending.popleft()
            a = now()
            if self.detector is not None:
                signal, increased = self.detector.update(0 if pred_j == y_j else 1)
                b = now()
                detect += b - a
                if signal:
                    self._on_signal(i, signal, increased)
                    adapt += now() - b
            revealed.append(pred_j == y_j)
            if self.learning:
                self._learn(j, xj, imputed_j, scaled_j, None, y_j)
        t4 = now()
        return y_pred, t4 - t0, (t1 - t0, t2 - t1, t3 - t2, detect, adapt, t4 - t3 - detect - adapt)

    def _learn(self, i: int, x: dict, imputed: dict, scaled: dict, xa: dict | None, y) -> None:
        now, cost = perf_counter_ns, self.cost_ns
        t0 = now()
        self.pre.learn(x, imputed)
        t1 = now()
        if not self.narrow:  # narrowed: the ranking is frozen; it would see only the kept features
            self.selector.learn(scaled, y)
        t2 = now()
        cost[0] += t1 - t0
        cost[1] += t2 - t1
        if i < self._warmup:
            self._warmup_buffer.append((scaled, y))
        if self.recent is not None:
            self.recent.append((scaled, y))
        self._labels[y] = self._labels.get(y, 0) + 1
        stride = self.update_stride
        if stride != 1:
            self._stride_count += 1
            if self._stride_count < stride:
                return
            self._stride_count = 0
        active = self.active
        t3 = now()
        active.model.learn_one(xa if xa is not None else project(scaled, active.features), y)
        t4 = now()
        cost[2] += t4 - t3
        active.trained_on += 1
        if self.background is not None:
            self._learn_background(i, scaled, y)
            cost[3] += now() - t4

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
        self.cost_ns = [0, 0, 0, 0]  # cost terms are reported after warm-up only
        self.controller_cost_ns = [0, 0]
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
        if not self.respond_to_drift:
            if signal is Signal.DRIFT:
                self.emit(i, "drift_ignored", reason="the controller rule for this resource state is switched off")
            return
        if self.drift_gate is not None and signal is Signal.DRIFT and action is not Action.IGNORE:
            veto = self.drift_gate(i)
            if veto is not None:
                self.emit(i, "drift_ignored", reason=veto, damped=True)
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
        if self._warm_start:
            if action is Action.RESET:
                self._warm(i, self.active)
            elif action in (Action.START_BACKGROUND, Action.PREPARE) and self.background is not None and self.background.trained_on == 0:
                self._warm(i, self.background)

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

    def reconfigure_features(self, i: int, k: int, reason: str, *, immediate: bool = False) -> None:
        """Change the number of selected features. The current model cannot drop a feature it splits
        on, so this is a model change: a replacement on the new feature set (promoted when ready), or
        a fresh model when the profile disallows background models."""
        old = len(self.active.features)
        self.selector.k = k
        self.emit(i, "config_changed", field="n_features", old=old, new=k, reason=reason)
        if self.background is not None and self.background.features != self.selector.proposed():
            self.background = None
        if self._adapt_cfg.allow_background and not immediate:
            self._prepare(i, reason, "reconfigure")
        else:
            self._reset_model(i, reason, action="reconfigure")

    # ------------------------------------------------------------------ joint controller hooks
    def set_lightweight(self, i: int, on: bool, reason: str) -> None:
        """R2 on: adapt by an immediate reset, with no replacement model training alongside.
        R1 (off): the normal path — a replacement trains in the background and is swapped in."""
        if on == self.lightweight:
            return
        self.lightweight = on
        base = self._base_adapt_cfg
        self._adapt_cfg = base.model_copy(update={"allow_background": base.allow_background and not on})
        self.policy = AdaptationPolicy(self._adapt_cfg)
        self.emit(i, "config_changed", field="adaptation_mode", old="lightweight" if not on else "standard",
                  new="lightweight" if on else "standard", reason=reason)
        if on and self.background is not None:
            pending = self.pending_since is not None
            self.background, self.pending_since = None, None
            self.emit(i, "background_discarded", reason="lightweight adaptation: no replacement model while resources are tight")
            if pending:  # a drift was confirmed and is waiting on the replacement: adapt the cheap way now
                self._reset_model(i, "drift confirmed earlier; resources are now tight, so a fresh model replaces the current one")
                if self._warm_start:
                    self._warm(i, self.active)

    def retrain(self, i: int, reason: str) -> int:
        """R4: a fresh model trained now on the recent labelled rows, then swapped in. Returns ns spent."""
        start = perf_counter_ns()
        rows = list(self.recent or ())
        if not rows:
            return 0
        features = self.selector.proposed()
        try:
            model = self._new_learner()
            for scaled, y in rows:
                model.learn_one(project(scaled, features), y)
        except Exception as exc:  # noqa: BLE001
            self._fail(i, "retrain", exc)
            return perf_counter_ns() - start
        previous = self.active
        self.active = ModelSlot(model, features, previous.version + 1, i, trained_on=len(rows))
        self.background, self.pending_since = None, None
        if self.detector is not None:
            self.detector.reset()
        self.last_adaptation = i
        self._emit_completed(i, "retrain", reason, previous, self.active, i, start)
        return perf_counter_ns() - start

    def drop_background(self, i: int, reason: str) -> bool:
        if self.background is None:
            return False
        pending = self.pending_since is not None
        self.background, self.pending_since = None, None
        self.emit(i, "background_discarded", reason=reason)
        if pending:
            self._reset_model(i, f"{reason}; the confirmed drift is handled by a fresh model instead")
        return True

    def _narrowed(self) -> tuple[str, ...]:
        # Keep what the active model, a replacement, or a model started this row would need. The
        # ranking is frozen while narrowed, so the selector's choice only changes with k.
        bg = self.background
        key = (id(self.active), None if bg is None else id(bg), self.selector.k)
        if key != self._narrow_key:
            keep = set(self.active.features) | set(self.selector.proposed())
            if bg is not None:
                keep |= set(bg.features)
            self._narrow_features = tuple(f for f in self._features if f in keep)
            self._narrow_key = key
        return self._narrow_features

    def set_narrow(self, i: int, on: bool, reason: str) -> None:
        if on != self.narrow:
            self.narrow = on
            self.emit(i, "config_changed", field="narrow_processing", old=not on, new=on, reason=reason)

    def model_bytes(self) -> int:
        """River's estimate of the active model's size, plus the replacement's if one is training."""
        size = self.active.model._raw_memory_usage
        if self.background is not None:
            size += self.background.model._raw_memory_usage
        return size


    # ------------------------------------------------------------------ method "effort": levers
    def enable_effort(self, levers: Levers) -> None:
        """Switch on the effort levers (budgeted effort controller). Must be called before the first
        row: the scaler becomes gap-aware so sampled statistics keep their memory in rows."""
        if self.events or self._labels:
            raise RuntimeError("effort levers must be enabled before the first row")
        self.levers = levers
        self.pre = Preprocessor(self._features, self.spec.pipeline.preprocessing, gap_aware=True)
        self.row_counts = [0] * N_COUNTS

    def _narrowed_effort(self) -> tuple[str, ...]:
        """Inputs a row needs when processing is narrowed: the active model's, a replacement's, and
        those a model started this row would get (the live ranking's current choice)."""
        bg = self.background
        lv = self.levers
        key = (id(self.active), None if bg is None else id(bg), self.selector.k, lv.rank_version)
        if key != self._narrow_key:
            keep = set(self.active.features) | set(self.selector.proposed())
            if bg is not None:
                keep |= set(bg.features)
            self._narrow_features = tuple(f for f in self._features if f in keep)
            self._narrow_key = key
        return self._narrow_features

    def _process_effort(self, i: int, x: dict, y):
        """The same stages as `process` / `_process_delayed`, with the effort levers applied after
        warm-up: narrowed preprocessing (B1) and `_learn_effort` for the update. `row_counts` records
        the work done, for the controller's cost model."""
        lv, now = self.levers, perf_counter_ns
        post = i >= self._warmup
        counts = self.row_counts
        for j in range(N_COUNTS):
            counts[j] = 0
        t0 = now()
        only = self._narrowed_effort() if post and lv.narrow else None
        imputed, scaled = self.pre.transform(x, only)
        t1 = now()
        active = self.active
        xa = {f: scaled[f] for f in active.features}
        t2 = now()
        y_pred = active.model.predict_one(xa)
        if y_pred is None:
            y_pred = self._fallback_label()
        t3 = now()
        counts[C_TRANSFORM] = len(imputed)
        counts[C_SELECT] = len(xa)
        if self.delayed and post:
            pending = self._pending
            if self._label_rng.random() < self._coverage:
                pending.append((i, x, imputed, scaled, y_pred, y))
            revealed = self.revealed = []
            labels = self.revealed_labels = []
            detect = adapt = 0
            due = i - self._delay
            mute_before = self.last_adaptation if lv.delay_aware and self.last_adaptation is not None else -1
            while pending and pending[0][0] <= due:
                j, xj, imputed_j, scaled_j, pred_j, y_j = pending.popleft()
                a = now()
                if self.detector is not None:
                    if j < mute_before:
                        lv.muted_labels += 1  # D3: predicted by the model an adaptation replaced
                    else:
                        signal, increased = self.detector.update(0 if pred_j == y_j else 1)
                        counts[C_DETECT] += 1
                        b = now()
                        detect += b - a
                        if signal:
                            self._on_signal(i, signal, increased)
                            adapt += now() - b
                        if lv.delay_aware and self.last_adaptation is not None:
                            mute_before = self.last_adaptation
                revealed.append(pred_j == y_j)
                labels.append(y_j)
                if self.learning:
                    self._learn_effort(j, xj, imputed_j, scaled_j, None, y_j, pred_j)
            t4 = now()
            return y_pred, t4 - t0, (t1 - t0, t2 - t1, t3 - t2, detect, adapt, t4 - t3 - detect - adapt)
        if self.detector is not None and post:
            signal, increased = self.detector.update(0 if y_pred == y else 1)
            counts[C_DETECT] = 1
            t4 = now()
            if signal:
                self._on_signal(i, signal, increased)
                t5 = now()
            else:
                t5 = t4
        else:
            t4 = t5 = t3
        if self.learning:
            self._learn_effort(i, x, imputed, scaled, xa if self.active is active else None, y, y_pred)
            if i == self._warmup - 1:
                self._end_warmup(i)
        t6 = now()
        return y_pred, t6 - t0, (t1 - t0, t2 - t1, t3 - t2, t4 - t3, t5 - t4, t6 - t5)

    def _learn_effort(self, i: int, x: dict, imputed: dict, scaled: dict, xa: dict | None, y, pred) -> None:
        """`_learn` with the levers, once the row's label is known:
        - B3 ranking rows: 1 labelled row in r, and every row of a class the ranker has seen fewer
          than `rank_min_per_class` times. On such a row all inputs are preprocessed from the raw row
          (kept with the label), so the ranking stays live over all inputs while processing is narrowed;
        - B2 statistics on 1 row in s (inputs in use), and on every ranking row (all inputs);
        - B4 no model update on most easy rows."""
        lv, now, cost, counts = self.levers, perf_counter_ns, self.cost_ns, self.row_counts
        post = i >= self._warmup
        stats_row = rank_row = True
        if post:
            if lv.sample_stats:
                lv.stats_credit += lv.stats_rate
                stats_row = lv.stats_credit >= 1.0
                if stats_row:
                    lv.stats_credit -= 1.0
            if lv.live_ranking:
                lv.rank_credit += lv.rank_rate
                rank_row = lv.rank_credit >= 1.0
                if rank_row:
                    lv.rank_credit -= 1.0
                elif lv.rank_counts.get(y, 0) < lv.rank_min_per_class:
                    rank_row = True
            else:
                rank_row = not lv.narrow  # as the joint controller: ranks while processing all inputs, frozen when narrowed
        t0 = now()
        rank_imputed, rank_scaled = imputed, scaled
        if post and rank_row and lv.narrow and len(imputed) < len(self._features):
            rank_imputed, rank_scaled = self.pre.transform(x)
            counts[C_TRANSFORM] += len(rank_imputed)
        if rank_row and lv.live_ranking or not post:
            self.pre.learn_at(x, rank_imputed, i)
            counts[C_STATS] += len(rank_imputed)
            lv.stats_rows += post
        elif stats_row:
            self.pre.learn_at(x, imputed, i)
            counts[C_STATS] += len(imputed)
            lv.stats_rows += post
        t1 = now()
        if rank_row:
            self.selector.learn(rank_scaled, y)
            lv.rank_counts[y] = lv.rank_counts.get(y, 0) + 1
            if post:
                lv.rank_version += 1
                lv.rank_rows += 1
                counts[C_RANK] += len(rank_scaled)
        t2 = now()
        cost[0] += t1 - t0
        cost[1] += t2 - t1
        if i < self._warmup:
            self._warmup_buffer.append((scaled, y))
        if self.recent is not None:
            self.recent.append((scaled, y))
        self._labels[y] = self._labels.get(y, 0) + 1
        # easy rows (B4): the last k arrived labels agree and were all predicted right
        correct = pred == y
        if correct and y == lv.last_label:
            lv.run += 1
        else:
            lv.run = 1 if correct else 0
        lv.last_label = y
        stride = self.update_stride
        if stride != 1:
            self._stride_count += 1
            if self._stride_count < stride:
                return
            self._stride_count = 0
        learn_active = True
        if post and lv.skip_easy and lv.run >= lv.easy_k:
            lv.easy_rows += 1
            lv.easy_credit += lv.easy_rate
            if lv.easy_credit >= 1.0:
                lv.easy_credit -= 1.0
            else:
                learn_active = False
                lv.skipped_updates += 1
        t3 = now()
        if learn_active:
            active = self.active
            model = active.model
            leaves = getattr(model, "_n_active_leaves", 0) + getattr(model, "_n_inactive_leaves", 0)
            model.learn_one(xa if xa is not None else {f: scaled.get(f, 0.0) for f in active.features}, y)
            active.trained_on += 1
            counts[C_UPDATE] += 1
            k = len(active.features)
            counts[C_UPDATE_FEATURES] += k
            if getattr(model, "_n_active_leaves", 0) + getattr(model, "_n_inactive_leaves", 0) > leaves:
                counts[C_SPLIT_FEATURES] += k
        t4 = now()
        cost[2] += t4 - t3
        if self.background is not None:
            self._learn_background_effort(i, scaled, y, pred)
            cost[3] += now() - t4

    def _learn_background_effort(self, i: int, scaled: dict, y, pred) -> None:
        """`_learn_background`, plus the D1 race: while a drift waits on the replacement, promote it
        as soon as it beats the active model on the last `switch_window` arrived labels."""
        bg, lv, counts = self.background, self.levers, self.row_counts
        xb = {f: scaled.get(f, 0.0) for f in bg.features}
        try:
            if (lv.fast_switch or lv.race_only) and bg.trained_on > 0:
                if lv.race_slot is not bg:
                    lv.race_slot, lv.race = bg, deque(maxlen=lv.switch_window)
                guess = bg.model.predict_one(xb)
                counts[C_REPLACEMENT_PREDICT] += 1
                lv.race.append((guess == y, pred == y))
            bg.model.learn_one(xb, y)
        except Exception as exc:  # noqa: BLE001 — a failing replacement must not stop the stream
            self._fail(i, "train_replacement", exc)
            return
        bg.trained_on += 1
        counts[C_REPLACEMENT] += 1
        counts[C_REPLACEMENT_FEATURES] += len(bg.features)
        if self.pending_since is not None:
            if lv.race_only and bg.trained_on >= self._adapt_cfg.background_timeout:
                self.background, self.pending_since = None, None
                self.emit(i, "background_discarded", reason="the replacement never beat the active model", model_version=bg.version)
            elif not lv.race_only and bg.trained_on >= self._adapt_cfg.background_min_samples:
                self._promote(i, f"replacement model reached {bg.trained_on} samples", detected_at=self.pending_since)
            elif (lv.fast_switch or lv.race_only) and lv.race_slot is bg and len(lv.race) == lv.switch_window:
                won = sum(r[0] for r in lv.race)
                held = sum(r[1] for r in lv.race)
                if won > held:
                    lv.fast_promotions += 1
                    self._promote(i, f"replacement beat the active model on the last {lv.switch_window} labels "
                                     f"({won} vs {held} right)", detected_at=self.pending_since)
        elif i - bg.started_at >= self._adapt_cfg.background_timeout:
            self.background = None
            self.emit(i, "background_discarded", reason="no drift confirmed before timeout", model_version=bg.version)

    def _warm(self, i: int, slot: ModelSlot) -> None:
        """D3: a new model first learns from the last `_warm_start` labelled rows."""
        rows = list(self.recent or ())[-self._warm_start:]
        if not rows:
            return
        counts = self.row_counts
        for scaled, y in rows:
            slot.model.learn_one({f: scaled.get(f, 0.0) for f in slot.features}, y)
        slot.trained_on += len(rows)
        counts[C_REPLACEMENT] += len(rows)
        counts[C_REPLACEMENT_FEATURES] += len(rows) * len(slot.features)
        if self.levers is not None:
            self.levers.warm_starts += 1
        self.emit(i, "warm_start", rows=len(rows), model_version=slot.version)

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
