"""Phase 2: the "repeat last label" baseline, literature ensembles, and stream-aware scores."""
import numpy as np
import pytest

from adaptiveml.config import EvaluationConfig, StreamConfig, TrialConfig
from adaptiveml.engine import run_trial
from adaptiveml.metrics import attack_period_scores, attack_type_scores, stream_scores
from adaptiveml.models import NoChangeClassifier
from adaptiveml.stream import make_scenario

from test_streaming_data import large, cfg  # noqa: F401 — the fixture is reused


def arr(*v):
    return np.array(v, dtype=bool)


def test_no_change_classifier_repeats_previous_label():
    m = NoChangeClassifier()
    assert m.predict_one({}) is None and m.predict_proba_one({}) == {}
    seen = []
    for y in [True, True, False, True]:
        seen.append(m.predict_one({'a': 1}))
        m.learn_one({'a': 1}, y)
    assert seen == [None, True, True, False]


def test_stream_scores_by_hand():
    s = stream_scores(arr(0, 0, 1, 1, 0), arr(0, 1, 1, 0, 0), lo=1)
    # rows 1-4: one each of TP, FP, FN, TN; labels match the previous row in 2 of 4
    assert s['kappa'] == pytest.approx(0.0)
    assert s['no_change_accuracy'] == 0.5 and s['kappa_temporal'] == pytest.approx(0.0)
    assert s['macro_f1'] == pytest.approx(0.5)
    perfect = stream_scores(arr(0, 0, 1, 1, 0), arr(0, 0, 1, 1, 0), lo=1)
    assert perfect['kappa'] == pytest.approx(1.0) and perfect['kappa_temporal'] == pytest.approx(1.0)
    # labels that never change: copying the previous label is perfect, so kappa-temporal is undefined
    assert stream_scores(arr(1, 1, 1), arr(1, 1, 1), lo=1)['kappa_temporal'] is None
    assert stream_scores(arr(1, 0), arr(1, 0), lo=0) is None  # row 0 has no previous label


def test_attack_type_and_period_scores():
    names = ['BENIGN', 'DoS', 'DoS - Attempted']
    codes = np.array([0, 0, 1, 1, 1, 2, 0, 1], dtype=np.int16)
    y_true = arr(0, 0, 1, 1, 1, 0, 0, 1)
    y_pred = arr(0, 1, 0, 1, 1, 1, 0, 0)
    by_type = attack_type_scores(y_true, y_pred, codes, names, lo=0)
    assert by_type['DoS'] == {'rows': 4, 'counted_as_attack': True, 'flagged': 2, 'flagged_share': 0.5}
    assert by_type['BENIGN']['flagged_share'] == pytest.approx(1 / 3)  # false-alarm rate
    assert by_type['DoS - Attempted']['counted_as_attack'] is False
    periods = [{'attack_type': 'DoS', 'start_row': 2, 'end_row': 4}, {'attack_type': 'DoS', 'start_row': 0, 'end_row': 1}]
    events = [{'i': 3, 'type': 'drift_detected', 'error_increased': True}, {'i': 4, 'type': 'adaptation_completed'}]
    (p,) = attack_period_scores(y_true, y_pred, codes, names, periods, events, warmup=1)  # second period is in warm-up
    assert p['flows'] == 3 and p['recall'] == pytest.approx(2 / 3) and p['flows_until_first_flagged'] == 1
    assert p['false_alarm_rate'] is None  # no benign rows inside rows 2-4
    assert p['detector_alerts'] == 1 and p['adaptations'] == 1


def test_baselines_through_engine_on_streaming_data(large):  # noqa: F811
    trial = TrialConfig(stream=cfg(), methods=('no_change', 'adaptive'), evaluation=EvaluationConfig(warmup=5))
    result = run_trial(trial)
    nc = result.summaries['no_change']
    s = nc['stream_scores_after_warmup']
    # the baseline *is* the no-change classifier, so it scores exactly p_nc and kappa-temporal 0
    assert nc['scores_after_warmup']['accuracy'] == pytest.approx(s['no_change_accuracy'])
    assert s['kappa_temporal'] == pytest.approx(0.0)
    # labels 10-19 are attacks: the baseline misses only the first attack row
    assert nc['attack_types_after_warmup']['DoS'] == {'rows': 10, 'counted_as_attack': True, 'flagged': 9, 'flagged_share': 0.9}
    (period,) = nc['attack_periods']
    assert period['flows_until_first_flagged'] == 1 and period['recall'] == pytest.approx(0.9)
    assert set(result.summaries['adaptive']) >= {'stream_scores_after_warmup', 'attack_periods'}


def test_row_types_follow_the_rows_read(large):  # noqa: F811
    s = make_scenario(cfg(length=12), 1)
    assert s.row_types() is None
    list(s)
    codes, names = s.row_types()
    assert names == ['BENIGN', 'DoS'] and codes.tolist() == [0] * 10 + [1, 1]


@pytest.mark.parametrize('method', ['srp', 'lev_bag'])
def test_literature_ensembles_run(method):
    trial = TrialConfig(stream=StreamConfig(length=600, noise=0.0), methods=(method,), evaluation=EvaluationConfig(warmup=100))
    trial = trial.model_copy(update={'pipeline': trial.pipeline.model_copy(
        update={'learner': trial.pipeline.learner.model_copy(update={'n_models': 3})})})
    s = run_trial(trial).summaries[method]
    assert s['scores_after_warmup']['n'] == 500 and s['final_model']['size_bytes'] > 0
    assert s['attack_periods'] is None  # synthetic data has no per-row labels
