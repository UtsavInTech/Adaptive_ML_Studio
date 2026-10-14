"""Behavioral regression checks for the root-level local validation harness."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('stress_mvp', Path(__file__).resolve().parents[2] / 'stress_test_mvp.py')
mvp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mvp)


def test_bomb_is_permanent_reproducible_and_exactly_200_flips():
    bomb = mvp.DataBomb(1000, ['sensor'])
    same = mvp.DataBomb(1000, ['sensor'])
    original = {'sensor': 2., 'other': 3.}
    flips = []
    for i in range(2000):
        result = bomb.apply(i, original, True)
        assert result == same.apply(i, original, True)
        x, y, shifted, flipped = result
        assert x == {'sensor': 20. if i >= 1000 else 2., 'other': 3.}
        assert shifted == (i >= 1000)
        assert flipped == (y is False)
        if flipped:
            flips.append(i)
    assert len(flips) == 200
    assert min(flips) >= 1000 and max(flips) < 1500
    assert original == {'sensor': 2., 'other': 3.}
    assert mvp.DataBomb(1000, ['sensor'], enabled=False).apply(1100, original, True) == (original, True, False, False)


class Engine:
    def __init__(self):
        self.features = tuple('abcdefgh')
        self.refreshes = []

    def refresh(self, index, k, reason):
        self.features = self.features[:k]
        self.refreshes.append((index, k, reason))


def test_latency_halves_during_cooldown_and_reports_minimum():
    engine, policy = Engine(), mvp.Controller()
    policy.last_refresh = 100
    for index, expected in enumerate([4, 2, 1, 1], 101):
        actions = policy.step(index, 16., .5, engine, [])
        assert len(engine.features) == expected
        assert actions[0].startswith('R2_')
    assert actions == ['R2_AT_MINIMUM_UNRESOLVED']
    assert len(engine.refreshes) == 3


def test_accuracy_cooldown_and_drift_override():
    engine, policy = Engine(), mvp.Controller()
    assert policy.step(1000, 1., .69, engine, []) == ['R3_LOW_ACCURACY_REFRESH']
    assert policy.step(1001, 1., .69, engine, []) == ['R4_COOLDOWN']
    assert policy.step(1002, 1., .9, engine, [{'type': 'drift_detected', 'error_increased': True}]) == ['R1_DRIFT']
    assert len(engine.refreshes) == 2
    policy.step(1003, 1., .9, engine, [{'type': 'drift_detected', 'error_increased': True}, {'type': 'adaptation_completed'}])
    assert len(engine.refreshes) == 2  # Don't reset a model the native policy already replaced.


@pytest.mark.parametrize('engine_class', [mvp.ProjectEngine, mvp.StandaloneEngine])
def test_actual_engine_reconfiguration_and_stage_accounting(engine_class):
    engine = engine_class(('a', 'b', 'c', 'd'), 10, 500, 42)
    for i in range(30):
        prediction, elapsed, stages = engine.process(i, dict(a=1., b=2., c=3., d=4.), bool(i % 2))
        assert prediction in (True, False)
        assert sum(stages) == elapsed and min(stages) >= 0
    mvp.Controller().step(30, 16., None, engine, [])
    assert len(engine.features) == 2
    engine.process(31, dict(a=1., b=2., c=3., d=4.), True)


def test_csv_rejects_nonfinite_and_unknown_labels(tmp_path):
    path = tmp_path / 'input.csv'
    for value in ('nan,1', '1,unknown'):
        path.write_text('x,y\n' + value + '\n')
        with pytest.raises(ValueError, match='Invalid CSV row 2'):
            list(mvp.rows(path, ['x'], 'y', {'0': 0, '1': 1}))


def test_portable_cli_writes_each_row_and_complete_costs(tmp_path):
    import csv
    import json
    import subprocess
    import sys

    data = tmp_path / 'stream.csv'
    data.write_text('a,b,y\n' + ''.join(f'{i % 7},{i % 3},{i % 2}\n' for i in range(1200)))
    result = subprocess.run([
        sys.executable, str(Path(mvp.__file__)), '--engine', 'standalone',
        '--csv', str(data), '--features', 'a,b', '--target', 'y', '--warmup', '100',
        '--fault-latency-ms', '20', '--log-every', '1200', '--output', str(tmp_path / 'output'),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr + result.stdout
    output = next((tmp_path / 'output').iterdir())
    with (output / 'iterations.csv').open() as handle:
        records = list(csv.DictReader(handle))
    assert len(records) == 1200
    assert sum(r['label_flipped'] == 'True' for r in records) == 200
    assert sum(r['shifted'] == 'True' for r in records) == 600
    assert float(records[600]['C_pre_ms']) >= 20
    assert int(records[600]['active_features']) == 1
    for record in records:
        components = [float(record[k]) for k in ('C_pre_ms', 'C_inf_ms', 'C_upd_ms', 'C_other_ms', 'C_policy_ms')]
        assert min(components) >= 0
        assert sum(components) == pytest.approx(float(record['C_total_ms']))
    summary = json.loads((output / 'summary.json').read_text())
    assert summary['status'] == 'completed'
    assert summary['rows_processed'] == 1200
