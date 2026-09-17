import itertools

import pytest
from river.datasets import synth

from adaptiveml.config import DriftSpec, StreamConfig, derive_seed
from adaptiveml.stream import SeaScenario
from adaptiveml.stream.sea import FEATURES, injection_margin
from adaptiveml.stream.transition import ConceptTransition


def nested_reference(cfg: StreamConfig, seed: int):
    """The previous construction: one nested ConceptTransition per drift (validated in check 4b)."""
    variants = [cfg.initial_variant] + [d.to_variant for d in cfg.drifts]
    concepts = [
        synth.SEA(variant=v, noise=cfg.noise, seed=derive_seed(seed, f"sea.concept.{k}")) for k, v in enumerate(variants)
    ]
    stream = concepts[-1]
    for k in reversed(range(len(cfg.drifts))):
        drift = cfg.drifts[k]
        previous = cfg.drifts[k - 1].position if k else 0
        stream = ConceptTransition(
            concepts[k], stream, position=drift.position - previous + 1, width=drift.width,
            seed=derive_seed(seed, f"sea.transition.{k}"),
        )
    a, b, c = FEATURES
    return [(i, {a: x[0], b: x[1], c: x[2]}, y) for i, (x, y) in enumerate(itertools.islice(stream, cfg.length))]


@pytest.mark.parametrize(
    "cfg",
    [
        StreamConfig(length=2_000),
        StreamConfig(length=6_000, noise=0.05, drifts=(DriftSpec(position=3_000, to_variant=3),)),
        StreamConfig(length=6_000, drifts=(DriftSpec(position=2_500, width=800, to_variant=1),)),
        StreamConfig(
            length=9_000,
            initial_variant=2,
            drifts=(DriftSpec(position=3_000, to_variant=3), DriftSpec(position=6_000, width=300, to_variant=0)),
        ),
    ],
)
def test_flat_chain_is_draw_for_draw_identical_to_nested_transitions(cfg):
    assert list(SeaScenario(cfg, 17)) == nested_reference(cfg, 17)


def run_with_injections(cfg: StreamConfig, seed: int, plan: dict[int, int]) -> tuple[list, SeaScenario]:
    scenario, rows = SeaScenario(cfg, seed), []
    for row in scenario:
        rows.append(row)
        if row[0] in plan:
            scenario.inject(plan[row[0]])
    return rows, scenario


def test_injected_drift_reproduces_exactly_from_the_resolved_config():
    cfg = StreamConfig(length=8_000, noise=0.05)
    live, scenario = run_with_injections(cfg, 9, {2_999: 3})
    (spec,) = scenario.drifts
    assert spec.position == 3_000 + injection_margin(1)
    replay = list(SeaScenario(cfg.model_copy(update={"drifts": scenario.drifts}), 9))
    assert live == replay


def test_two_injections_in_a_row_also_reproduce():
    cfg = StreamConfig(length=12_000)
    live, scenario = run_with_injections(cfg, 4, {1_999: 3, 5_999: 2})
    assert [d.to_variant for d in scenario.drifts] == [3, 2]
    replay = list(SeaScenario(cfg.model_copy(update={"drifts": scenario.drifts}), 4))
    assert live == replay


def test_injection_is_refused_while_a_scheduled_drift_is_pending():
    scenario = SeaScenario(StreamConfig(length=8_000, drifts=(DriftSpec(position=5_000, to_variant=3),)), 1)
    it = iter(scenario)
    next(it)
    with pytest.raises(ValueError, match="pending"):
        scenario.inject(1)


def test_injection_is_refused_near_the_end_or_to_the_current_concept_or_when_idle():
    scenario = SeaScenario(StreamConfig(length=150), 1)  # shorter than the 177-sample injection margin
    with pytest.raises(RuntimeError):
        scenario.inject(3)
    it = iter(scenario)
    next(it)
    with pytest.raises(ValueError, match="already"):
        scenario.inject(0)
    with pytest.raises(ValueError, match="not enough stream"):
        scenario.inject(3)
