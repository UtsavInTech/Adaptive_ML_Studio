import random

import pytest

from adaptiveml.adaptation import Action, AdaptationPolicy
from adaptiveml.config import (
    AdaptationConfig,
    DetectorConfig,
    FeatureSelectionConfig,
    PreprocessingConfig,
    StreamConfig,
)
from adaptiveml.drift import ErrorStreamDetector, Signal
from adaptiveml.features import OnlineFeatureSelector
from adaptiveml.preprocessing import Preprocessor
from adaptiveml.stream import SeaScenario

# ---------------------------------------------------------------- preprocessing


def test_transform_uses_only_previously_learned_statistics():
    pre = Preprocessor(["a"], PreprocessingConfig(scaler="standard", clip=None))
    for v in (1.0, 2.0, 3.0):
        imputed, _ = pre.transform({"a": v})
        pre.learn({"a": v}, imputed)
    first = pre.transform({"a": 10.0})[1]["a"]
    assert pre.transform({"a": 10.0})[1]["a"] == first  # transforming does not learn
    pre.learn({"a": 10.0}, {"a": 10.0})
    assert pre.transform({"a": 10.0})[1]["a"] != first


def test_missing_values_are_imputed_from_observed_values_only():
    pre = Preprocessor(["a"], PreprocessingConfig(scaler="none"))
    for v in (2.0, 4.0):
        imputed, _ = pre.transform({"a": v})
        pre.learn({"a": v}, imputed)
    imputed, _ = pre.transform({"a": None})
    assert imputed["a"] == 3.0
    pre.learn({"a": None}, imputed)  # an imputed value must not move the mean
    assert pre.transform({"a": float("nan")})[0]["a"] == 3.0


def test_clip_bounds_standardised_values():
    pre = Preprocessor(["a"], PreprocessingConfig(scaler="standard", clip=5.0))
    for v in (0.0, 1.0) * 50:
        imputed, _ = pre.transform({"a": v})
        pre.learn({"a": v}, imputed)
    assert pre.transform({"a": 100.0})[1]["a"] == 5.0
    assert pre.transform({"a": -100.0})[1]["a"] == -5.0


def test_clip_is_ignored_without_a_scaler():
    pre = Preprocessor(["a"], PreprocessingConfig(scaler="none", clip=5.0))
    assert pre.transform({"a": 100.0})[1]["a"] == 100.0


# ---------------------------------------------------------------- feature selection


def test_selector_ranks_the_irrelevant_sea_feature_last():
    scenario = SeaScenario(StreamConfig(length=1_000, noise=0.1), seed=3)
    pre = Preprocessor(scenario.feature_names, PreprocessingConfig())
    selector = OnlineFeatureSelector(scenario.feature_names, FeatureSelectionConfig())
    for _, x, y in scenario:
        imputed, scaled = pre.transform(x)
        selector.learn(scaled, y)
        pre.learn(x, imputed)
    assert selector.k == 2
    assert selector.ranking()[-1][0] == "x2"
    assert selector.proposed() == ("x0", "x1")


def test_selector_without_method_keeps_all_features():
    selector = OnlineFeatureSelector(["a", "b"], FeatureSelectionConfig(method="none"))
    assert selector.proposed() == ("a", "b")


# ---------------------------------------------------------------- drift detection


def test_detector_is_silent_on_a_constant_error_stream_and_flags_an_increase():
    detector = ErrorStreamDetector(DetectorConfig())
    assert all(detector.update(0)[0] is not Signal.DRIFT for _ in range(2_000))
    for k in range(2_000):
        signal, increased = detector.update(1)
        if signal is Signal.DRIFT:
            assert increased
            assert k < 200
            return
    pytest.fail("no drift detected after the error rate jumped from 0 to 1")


def test_detector_has_no_error_increase_alarm_on_a_seeded_stationary_stream():
    rng = random.Random(0)
    detector = ErrorStreamDetector(DetectorConfig())
    alarms = [k for k in range(5_000) if detector.update(int(rng.random() < 0.1)) == (Signal.DRIFT, True)]
    assert alarms == []


# ---------------------------------------------------------------- adaptation policy


def decide(policy, signal, **overrides):
    kwargs = {
        "error_increased": True,
        "sample_index": 10_000,
        "last_adaptation": None,
        "background_trained": None,
        "adaptation_pending": False,
    }
    kwargs.update(overrides)
    return policy.decide(signal, **kwargs).action


@pytest.fixture
def policy():
    return AdaptationPolicy(AdaptationConfig(background_min_samples=200, cooldown=300))


def test_no_signal_means_no_action(policy):
    assert decide(policy, Signal.NONE) is Action.NONE


def test_drift_swaps_in_a_ready_replacement(policy):
    assert decide(policy, Signal.DRIFT, background_trained=500) is Action.SWAP


def test_drift_prepares_a_replacement_when_none_is_ready(policy):
    assert decide(policy, Signal.DRIFT) is Action.PREPARE
    assert decide(policy, Signal.DRIFT, background_trained=10) is Action.PREPARE


def test_error_decrease_is_ignored(policy):
    assert decide(policy, Signal.DRIFT, error_increased=False) is Action.IGNORE


def test_cooldown_blocks_repeated_adaptation(policy):
    assert decide(policy, Signal.DRIFT, last_adaptation=9_800) is Action.IGNORE
    assert decide(policy, Signal.DRIFT, last_adaptation=9_700) is Action.PREPARE


def test_drift_during_preparation_is_ignored(policy):
    assert decide(policy, Signal.DRIFT, adaptation_pending=True, background_trained=50) is Action.IGNORE


def test_warning_starts_one_replacement(policy):
    assert decide(policy, Signal.WARNING) is Action.START_BACKGROUND
    assert decide(policy, Signal.WARNING, background_trained=5) is Action.NONE


def test_without_background_models_warnings_do_nothing_and_drift_resets():
    policy = AdaptationPolicy(AdaptationConfig(allow_background=False))
    assert decide(policy, Signal.WARNING) is Action.NONE
    assert decide(policy, Signal.DRIFT) is Action.RESET
