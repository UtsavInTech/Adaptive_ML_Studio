import itertools

import pytest
from river.datasets import synth

from adaptiveml.stream.transition import ConceptTransition, transition_probability


def test_matches_river_draw_for_draw_where_river_does_not_overflow():
    # width 2,000 keeps River's exponent small, so its implementation is usable for comparison.
    kwargs = dict(position=1_000, width=2_000, seed=3)
    ours = ConceptTransition(synth.SEA(variant=0, seed=1), synth.SEA(variant=3, seed=2), **kwargs)
    river_stream = synth.ConceptDriftStream(
        stream=synth.SEA(variant=0, seed=1), drift_stream=synth.SEA(variant=3, seed=2), **kwargs
    )
    assert list(itertools.islice(ours, 3_000)) == list(itertools.islice(river_stream, 3_000))


def test_river_overflows_for_an_abrupt_distant_drift_but_ours_does_not():
    far = dict(position=5_000, width=1, seed=0)
    with pytest.raises(OverflowError):
        list(itertools.islice(synth.ConceptDriftStream(synth.SEA(seed=1), synth.SEA(variant=3, seed=2), **far), 10))
    assert len(list(itertools.islice(ConceptTransition(synth.SEA(seed=1), synth.SEA(variant=3, seed=2), **far), 10))) == 10


def test_probability_is_clamped_and_monotonic():
    assert transition_probability(1, 5_000, 1) == 0.0
    assert transition_probability(10_000, 5_000, 1) == 1.0
    assert transition_probability(5_000, 5_000, 1) == 0.5
    values = [transition_probability(k, 100, 50) for k in range(0, 200, 10)]
    assert values == sorted(values)
