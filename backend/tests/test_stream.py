import itertools

import pytest
from pydantic import ValidationError

from adaptiveml.config import DriftSpec, EvaluationConfig, StreamConfig, TrialConfig
from adaptiveml.stream import SeaScenario, label_flip_fraction
from adaptiveml.stream.sea import SEA_THRESHOLDS


def take(scenario, n):
    return list(itertools.islice(scenario, n))


def test_same_seed_gives_identical_stream():
    cfg = StreamConfig(length=500, drifts=(DriftSpec(position=250, to_variant=3),))
    assert take(SeaScenario(cfg, 7), 500) == take(SeaScenario(cfg, 7), 500)


def test_different_seed_gives_different_stream():
    cfg = StreamConfig(length=100)
    assert take(SeaScenario(cfg, 1), 100) != take(SeaScenario(cfg, 2), 100)


def test_length_and_indices():
    rows = list(SeaScenario(StreamConfig(length=321), 0))
    assert [i for i, _, _ in rows] == list(range(321))
    assert list(rows[0][1]) == ["x0", "x1", "x2"]


@pytest.mark.parametrize("position", [300, 1_000])
def test_abrupt_drift_switches_concept_at_the_configured_index(position):
    cfg = StreamConfig(length=position + 500, noise=0.0, drifts=(DriftSpec(position=position, to_variant=3),))
    old, new = SEA_THRESHOLDS[0], SEA_THRESHOLDS[3]
    for i, x, y in SeaScenario(cfg, 11):
        s = x["x0"] + x["x1"]
        a, b = s > old, s > new
        if a == b:
            continue  # this sample has the same label under both concepts
        if i < position - 3:
            assert y == a, i
        elif i > position + 3:
            assert y == b, i


def test_second_drift_in_a_chain_lands_near_its_index():
    # Later drifts in a chain inherit the few-sample jitter of earlier abrupt transitions.
    cfg = StreamConfig(
        length=1_200,
        noise=0.0,
        drifts=(DriftSpec(position=300, to_variant=3), DriftSpec(position=700, to_variant=2)),
    )
    t3, t2 = SEA_THRESHOLDS[3], SEA_THRESHOLDS[2]
    for i, x, y in SeaScenario(cfg, 5):
        s = x["x0"] + x["x1"]
        a, b = s > t3, s > t2
        if a == b:
            continue
        if 306 < i < 694:
            assert y == a, i
        elif i > 706:
            assert y == b, i


def test_label_flip_fraction_closed_form():
    assert label_flip_fraction(0, 3) == pytest.approx(0.13125)
    assert label_flip_fraction(2, 3) == pytest.approx(0.20625)
    assert label_flip_fraction(0, 1) == pytest.approx(0.085)
    assert label_flip_fraction(3, 0) == label_flip_fraction(0, 3)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"length": 0},
        {"length": 100, "drifts": (DriftSpec(position=100, to_variant=1),)},
        {"length": 1_000, "drifts": (DriftSpec(position=500, to_variant=1), DriftSpec(position=400, to_variant=2))},
        {"lenght": 10},
    ],
)
def test_invalid_stream_configs_are_rejected(kwargs):
    with pytest.raises(ValidationError):
        StreamConfig(**kwargs)


def test_drift_inside_warmup_is_rejected():
    with pytest.raises(ValidationError):
        TrialConfig(
            stream=StreamConfig(length=5_000, drifts=(DriftSpec(position=500, to_variant=3),)),
            evaluation=EvaluationConfig(warmup=1_000),
        )
