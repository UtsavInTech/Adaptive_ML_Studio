import hashlib
import json

import pytest
from pydantic import ValidationError

from adaptiveml.config import EvaluationConfig, StreamConfig, TrialConfig
from adaptiveml.engine import run_trial
from adaptiveml.engine.worker import build_extras
from adaptiveml.stream import make_scenario
from adaptiveml.stream import static


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    raw = b'a,b,target\n1,2,no\n3,4,yes\n5,6,no\n7,8,yes\n9,10,no\n11,12,yes\n'
    (tmp_path / 'sample.csv').write_bytes(raw)
    entry = dict(id='sample', file='sample.csv', name='Fixture', rows=6, features=['a', 'b'],
                 target='target', labels={'no': 0, 'yes': 1}, sha256=hashlib.sha256(raw).hexdigest(),
                 source='https://www.kaggle.com/datasets/example', license='test', order='file order')
    (tmp_path / 'catalog.json').write_text(json.dumps([entry]))
    monkeypatch.setattr(static, 'DATA_ROOT', tmp_path)
    return tmp_path, entry


def config(**kwargs):
    return StreamConfig(scenario='csv', dataset='sample', noise=0, length=6, **kwargs)


def test_replay_order_labels_and_seed_independence(snapshot):
    a, b = make_scenario(config(), 1), make_scenario(config(), 999)
    assert list(a) == list(b)
    assert [row[2] for row in a] == [False, True, False, True, False, True]
    assert next(iter(a))[1] == {'a': 1.0, 'b': 2.0}
    assert a.info['real'] and a.ground_truth_drifts == ()
    with pytest.raises(ValueError, match='disabled'):
        a.inject(3)


def test_tampered_and_mismatched_snapshot_rejected(snapshot):
    path, _ = snapshot
    with pytest.raises(ValueError, match='checksum'):
        make_scenario(config(dataset_sha256='bad'), 1)
    (path / 'sample.csv').write_text('a,b,target\n99,2,yes\n')
    with pytest.raises(ValueError, match='checksum'):
        make_scenario(config(), 1)


def test_no_synthetic_mutations_or_oversized_replay(snapshot):
    with pytest.raises(ValidationError, match='noise=0'):
        StreamConfig(scenario='csv', dataset='sample')
    with pytest.raises(ValueError, match='contains 6'):
        make_scenario(config().model_copy(update={'length': 7}), 1)


@pytest.mark.parametrize('replacement', ['nan', '', 'infinity'])
def test_invalid_numeric_data_rejected_before_run(snapshot, replacement):
    path, entry = snapshot
    raw = (path / 'sample.csv').read_bytes().replace(b'1,2,no', f'{replacement},2,no'.encode())
    (path / 'sample.csv').write_bytes(raw)
    entry['sha256'] = hashlib.sha256(raw).hexdigest()
    (path / 'catalog.json').write_text(json.dumps([entry]))
    with pytest.raises(ValueError, match='CSV line 2'):
        make_scenario(config(), 1)


def test_engine_records_real_provenance_without_invented_drift(snapshot):
    contexts = []
    cfg = TrialConfig(stream=config(), evaluation=EvaluationConfig(warmup=2, block_size=2))
    first = run_trial(cfg, keep_recent=6, context_sink=contexts.append)
    second = run_trial(cfg)
    assert first.status == 'completed'
    assert first.config.stream.dataset_sha256 == snapshot[1]['sha256']
    assert first.scenario['real']
    assert not any(e['type'] == 'drift_true' for e in first.events)
    for method, summary in first.summaries.items():
        assert summary['scores_after_warmup']['n'] == 4
        assert summary['stability_reference'] is None
        assert summary['predictions_sha256'] == second.summaries[method]['predictions_sha256']
    extras = build_extras(contexts[0])
    assert extras['real_data'] and extras['concept']['threshold'] is None
    assert {p[2] for p in extras['points']} == {0, 1}


# ---------------------------------------------------------------- controlled drift on real rows
from adaptiveml.config import ExperimentConfig, InjectedDrift, PhaseConfig  # noqa: E402
from adaptiveml.metrics import drift_phases  # noqa: E402


@pytest.fixture
def long_snapshot(tmp_path, monkeypatch):
    """200 rows: a rises 0..199, b is constant 1000, label is `a` odd."""
    raw = ('a,b,target\n' + ''.join(f'{i},1000,{"yes" if i % 2 else "no"}\n' for i in range(200))).encode()
    (tmp_path / 'long.csv').write_bytes(raw)
    entry = dict(id='long', file='long.csv', name='Fixture', rows=200, features=['a', 'b'],
                 target='target', labels={'no': 0, 'yes': 1}, sha256=hashlib.sha256(raw).hexdigest(),
                 source='https://www.kaggle.com/datasets/example', license='test', order='file order')
    (tmp_path / 'catalog.json').write_text(json.dumps([entry]))
    monkeypatch.setattr(static, 'DATA_ROOT', tmp_path)
    return entry


def injected(kind, **extra):
    drift = InjectedDrift(kind=kind, start=100, swap=('a', 'b'), **extra)
    return StreamConfig(scenario='csv', dataset='long', noise=0, length=200, injection=drift)


def test_injection_leaves_earlier_rows_labels_and_order_untouched(long_snapshot):
    natural = list(make_scenario(StreamConfig(scenario='csv', dataset='long', noise=0, length=200), 1))
    for stream in (injected('abrupt'), injected('gradual', width=40), injected('incremental', width=40), injected('recurring', period=30)):
        rows = list(make_scenario(stream, 1))
        assert rows[:100] == natural[:100]
        assert [(i, y) for i, _, y in rows] == [(i, y) for i, _, y in natural]
        assert rows == list(make_scenario(stream, 999))  # a model seed never changes the data


def test_each_drift_kind_has_its_shape(long_snapshot):
    def a_values(stream):
        return [x['a'] for _, x, _ in make_scenario(stream, 1)]

    abrupt = a_values(injected('abrupt'))
    assert abrupt[99] == 99 and all(v == 1000 for v in abrupt[100:])  # an exact exchange, at once

    gradual = a_values(injected('gradual', width=40))
    window = gradual[100:140]
    assert set(window) <= {1000.0, *map(float, range(100, 140))}  # every row is fully old or fully new
    assert 0 < sum(v == 1000 for v in window) < 40 and all(v == 1000 for v in gradual[140:])
    assert sum(v == 1000 for v in window[20:]) > sum(v == 1000 for v in window[:20])  # new rows become more common

    incremental = a_values(injected('incremental', width=40))
    assert all(100 < v < 1000 for v in incremental[100:139])  # every row is a blend
    assert incremental[100:140] == sorted(incremental[100:140]) and all(v == 1000 for v in incremental[139:])

    recurring = a_values(injected('recurring', period=30))
    assert all(v == 1000 for v in recurring[100:130]) and recurring[130:160] == list(map(float, range(130, 160)))
    assert all(v == 1000 for v in recurring[160:190])


def test_ground_truth_and_scenario_record_say_the_change_was_injected(long_snapshot):
    scenario = make_scenario(injected('recurring', period=30), 1)
    assert [(c.index, c.from_variant, c.to_variant) for c in scenario.ground_truth_drifts] == [
        (100, 0, 1), (130, 1, 0), (160, 0, 1), (190, 1, 0)]
    info = make_scenario(injected('gradual', width=40), 1).info
    assert info['real'] and info['drift_ground_truth'] == 'injected'
    assert info['injection']['swap'] == ['a', 'b'] and info['drifts'][0]['start'] == 100 and info['drifts'][0]['end'] == 140
    assert make_scenario(StreamConfig(scenario='csv', dataset='long', noise=0, length=200), 1).info['injection'] is None


def test_injection_is_validated(long_snapshot):
    with pytest.raises(ValidationError, match='width must be 1'):
        InjectedDrift(kind='abrupt', start=100, width=5, swap=('a', 'b'))
    with pytest.raises(ValidationError, match='period is required'):
        InjectedDrift(kind='recurring', start=100, swap=('a', 'b'))
    with pytest.raises(ValidationError, match='must be different'):
        InjectedDrift(kind='abrupt', start=100, swap=('a', 'a'))
    with pytest.raises(ValidationError, match='finish before the replay ends'):
        injected('gradual', width=100)
    with pytest.raises(ValidationError, match='only valid for CSV replay'):
        StreamConfig(injection=InjectedDrift(kind='abrupt', start=100, swap=('a', 'b')))
    with pytest.raises(ValidationError, match='after the warm-up'):
        TrialConfig(stream=injected('abrupt'), evaluation=EvaluationConfig(warmup=150))
    with pytest.raises(ValueError, match='unknown column'):
        make_scenario(StreamConfig(scenario='csv', dataset='long', noise=0, length=200,
                                   injection=InjectedDrift(kind='abrupt', start=100, swap=('a', 'zzz'))), 1)


def test_phase_scores_cover_the_documented_rows():
    import numpy as np
    y_true = np.array([True, False] * 50)
    y_pred = y_true.copy()
    y_pred[40:60] = ~y_pred[40:60]  # wrong for 20 rows from the change
    events = [{'i': 45, 'type': 'drift_detected', 'error_increased': True}, {'i': 52, 'type': 'adaptation_completed'},
              {'i': 10, 'type': 'drift_detected', 'error_increased': True}]
    out = drift_phases(y_true, y_pred, 40, 41, PhaseConfig(before=20, settle=19, after=30), events=events)
    assert [out[k]['range'] for k in ('before', 'during', 'after')] == [[20, 40], [40, 60], [60, 90]]
    assert [out[k]['accuracy'] for k in ('before', 'during', 'after')] == [1.0, 0.0, 1.0]
    assert out['during']['precision'] == 0.0 and out['before']['precision'] == 1.0
    assert (out['during']['detector_alerts'], out['during']['adaptations'], out['before']['detector_alerts']) == (1, 1, 0)
    assert (out['first_alert_after_start'], out['first_adaptation_after_start']) == (5, 12)
    clipped = drift_phases(y_true, y_pred, 40, 41, PhaseConfig(before=20, settle=19, after=30), limit=70)
    assert clipped['after']['range'] == [60, 70]  # a recurring drift's next switch ends the window


def test_engine_scores_phases_and_control_over_identical_rows(long_snapshot):
    evaluation = EvaluationConfig(warmup=20, block_size=10, phases=PhaseConfig(before=40, settle=10, after=30))
    drifted = run_trial(TrialConfig(stream=injected('abrupt'), evaluation=evaluation))
    exp = ExperimentConfig(name='t', control=True, base=TrialConfig(stream=injected('abrupt'), evaluation=evaluation, methods=('static',)))
    (trial_id, _), (control_id, control_cfg) = exp.trials()
    assert control_id == trial_id + '__control' and control_cfg.stream.injection is None
    assert control_cfg.evaluation.phase_anchor == (100, 101)
    control = run_trial(control_cfg)
    truth = [e for e in drifted.events if e['type'] == 'drift_true']
    assert [(e['i'], e['drift_kind'], e['injected']) for e in truth] == [(100, 'abrupt', True)]
    assert not any(e['type'] == 'drift_true' for e in control.events)
    a, b = drifted.summaries['static']['drift_phases'], control.summaries['static']['drift_phases']
    assert [a[k]['range'] for k in ('before', 'during', 'after')] == [[60, 100], [100, 111], [111, 141]]
    assert [b[k]['range'] for k in ('before', 'during', 'after')] == [a[k]['range'] for k in ('before', 'during', 'after')]
    assert a['before'] == b['before']  # identical rows before the change give identical scores
    assert b['source'].startswith('control')
