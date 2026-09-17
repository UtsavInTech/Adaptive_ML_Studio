import numpy as np
import pytest
from river import tree

from adaptiveml.config import (
    AdaptationConfig,
    DriftSpec,
    EvaluationConfig,
    PipelineConfig,
    StabilityConfig,
    StreamConfig,
    TrialConfig,
)
from adaptiveml.engine import run_trial
from adaptiveml.metrics import classification_scores, rolling_accuracy, stability_reference
from adaptiveml.pipeline import MethodPipeline, method_spec
from adaptiveml.stream import SeaScenario

DRIFT = DriftSpec(position=3_000, to_variant=3)
# Noise-free, highest-intensity SEA change (θ 7 → 9.5): an unambiguous drift for failure-path tests.
CLEAR_DRIFT_STREAM = StreamConfig(length=6_000, noise=0.0, initial_variant=2, drifts=(DRIFT,))


def small_config(methods, length=6_000, **evaluation) -> TrialConfig:
    return TrialConfig(
        seed=7,
        methods=methods,
        stream=StreamConfig(length=length, drifts=(DRIFT,)),
        evaluation=EvaluationConfig(**evaluation),
    )


def run_pipeline(pipe: MethodPipeline, stream: StreamConfig, seed: int = 1) -> MethodPipeline:
    for i, x, y in SeaScenario(stream, seed=seed):
        pipe.process(i, x, y)
    return pipe


@pytest.fixture(scope="module")
def trial():
    return run_trial(small_config(("static", "incremental", "adaptive")))


# ---------------------------------------------------------------- pipelines


def test_static_baseline_is_frozen_after_warmup(trial):
    static = trial.pipelines["static"]
    assert static.learning is False
    assert static.active.trained_on == 1_000
    assert any(e["type"] == "frozen" and e["method"] == "static" for e in trial.events)


def test_incremental_keeps_learning_without_adapting(trial):
    incremental = trial.pipelines["incremental"]
    assert incremental.active.trained_on == 6_000
    assert incremental.active.version == 1


def test_adaptive_promotes_a_replacement_trained_after_the_drift(trial):
    completed = [e for e in trial.events if e["method"] == "adaptive" and e["type"] == "adaptation_completed"]
    assert completed and completed[0]["i"] >= DRIFT.position
    first = completed[0]
    assert first["action"] == "swap" and first["trained_on"] >= 200
    assert trial.pipelines["adaptive"].active.version >= 2


def test_selection_drops_x2_after_warmup(trial):
    applied = [e for e in trial.events if e["type"] == "selection_applied"]
    assert applied and all(e["dropped"] == ["x2"] for e in applied)


def test_failed_adaptation_keeps_the_previous_model_and_the_stream_continues():
    calls = {"n": 0}

    def flaky_factory(seed):
        calls["n"] += 1
        if calls["n"] > 2:  # 1 = initial model, 2 = warm-up rebuild on the selected features
            raise RuntimeError("simulated learner failure")
        return tree.HoeffdingTreeClassifier()

    pipe = MethodPipeline(
        method_spec("adaptive", PipelineConfig()), ("x0", "x1", "x2"), warmup=1_000, seed=1, learner_factory=flaky_factory
    )
    run_pipeline(pipe, CLEAR_DRIFT_STREAM)
    failed = [e for e in pipe.events if e["type"] == "adaptation_failed"]
    assert failed and failed[0]["message"] == "Adaptation failed — continuing with previous model"
    assert not any(e["type"] == "adaptation_completed" for e in pipe.events)
    assert pipe.active.version == 1
    assert pipe.active.trained_on == 6_000  # the previous model kept learning to the end of the stream


def test_profile_without_background_models_resets_on_drift():
    cfg = PipelineConfig(adaptation=AdaptationConfig(allow_background=False))
    pipe = run_pipeline(MethodPipeline(method_spec("adaptive", cfg), ("x0", "x1", "x2"), warmup=1_000, seed=1), CLEAR_DRIFT_STREAM)
    completed = [e for e in pipe.events if e["type"] == "adaptation_completed"]
    assert completed and completed[0]["action"] == "reset" and completed[0]["trained_on"] == 0
    assert not any(e["type"] == "background_started" for e in pipe.events)


def test_untrained_model_falls_back_to_a_label(trial):
    assert trial.summaries["adaptive"]["fallback_predictions"] >= 1


# ---------------------------------------------------------------- engine


def test_identical_configs_give_identical_predictions():
    cfg = small_config(("static", "adaptive"), length=4_000)
    a, b = run_trial(cfg), run_trial(cfg)
    for method in cfg.methods:
        assert a.summaries[method]["predictions_sha256"] == b.summaries[method]["predictions_sha256"]


def test_blocks_cover_the_stream_and_match_outcomes():
    result = run_trial(small_config(("adaptive",), length=4_050, block_size=100))
    blocks = result.blocks["adaptive"]
    assert len(blocks) == 41 and sum(b["n"] for b in blocks) == 4_050
    rec = result.recorders["adaptive"]
    y_true = rec.true_labels().astype(bool)
    y_pred = rec.predicted_labels().astype(bool)
    assert sum(b["tp"] for b in blocks) == int(np.sum(y_true & y_pred))
    assert sum(b["fn"] for b in blocks) == int(np.sum(y_true & ~y_pred))


def test_block_callback_sees_every_block():
    seen = []
    run_trial(small_config(("static",), length=4_000, block_size=250), on_block=lambda i, r, e: seen.append(i))
    assert seen == list(range(16))


# ---------------------------------------------------------------- metrics


def test_classification_scores():
    s = classification_scores(tp=3, fp=1, tn=4, fn=2)
    assert s["accuracy"] == pytest.approx(0.7)
    assert s["precision"] == pytest.approx(0.75)
    assert s["recall"] == pytest.approx(0.6)
    assert s["f1"] == pytest.approx(2 / 3)
    assert classification_scores(0, 0, 0, 0)["accuracy"] is None


def test_rolling_accuracy():
    assert rolling_accuracy(np.array([1, 1, 0, 0]), 2).tolist() == [1.0, 0.5, 0.0]


def test_stability_reference_on_a_synthetic_curve():
    n, drift = 4_000, 2_000
    y_true = np.ones(n, dtype=bool)
    y_pred = y_true.copy()
    y_pred[2_000:2_500] = False  # 500 errors right after the drift
    events = [
        {"i": 2_100, "type": "drift_detected", "error_increased": True},
        {"i": 2_100, "type": "adaptation_completed"},
    ]
    cfg = StabilityConfig(pre_window=1_000, horizon=1_500, window=100, tolerance=0.025, sustain=100)
    ref = stability_reference(y_true, y_pred, drift, events, cfg)
    assert ref["pre_drift"]["accuracy"] == 1.0
    assert ref["min_windowed_accuracy"] == 0.0
    assert ref["detection_delay_samples"] == 100
    assert ref["post_adaptation"]["accuracy"] == pytest.approx(601 / 1_000)
    assert ref["recovery_samples"] == 598  # first window with ≤ 2 errors starts at 2,498
