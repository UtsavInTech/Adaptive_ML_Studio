"""Large datasets read row by row (`StreamingScenario`) and the CIC-IDS2017 preparation script."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest

from adaptiveml.config import EvaluationConfig, StreamConfig, TrialConfig
from adaptiveml.engine import run_trial
from adaptiveml.stream import StreamingScenario, make_scenario, static

REPO = Path(__file__).resolve().parents[2]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def large(tmp_path, monkeypatch):
    rows = ['row,attack_type,label,a,b']
    for i in range(40):
        attack = 10 <= i < 20
        rows.append(f"{i},{'DoS' if attack else 'BENIGN'},{'ATTACK' if attack else 'BENIGN'},{i},{'' if i == 3 else -i}")
    raw = ('\n'.join(rows) + '\n').encode()
    schedule = json.dumps({
        'rows': 40, 'day_start_rows': {'monday': 0, 'tuesday': 25}, 'episode_gap_seconds': 600,
        'attack_periods': [{'attack_type': 'DoS', 'start_row': 10, 'end_row': 19, 'flows': 10}],
    }).encode()
    (tmp_path / 'big.csv').write_bytes(raw)
    (tmp_path / 'schedule.json').write_bytes(schedule)
    entry = dict(id='big', file='big.csv', schedule='schedule.json', streaming=True, name='Big fixture', rows=40,
                 features=['a', 'b'], target='label', labels={'BENIGN': 0, 'ATTACK': 1}, sha256=_sha(raw),
                 schedule_sha256=_sha(schedule), source='https://example.org', license='test', order='end time')
    (tmp_path / 'catalog.json').write_text(json.dumps([entry]))
    monkeypatch.setattr(static, 'DATA_ROOT', tmp_path)
    return tmp_path, entry


def cfg(**kw):
    return StreamConfig(scenario='csv', dataset='big', noise=0, length=kw.pop('length', 40), **kw)


def test_rows_labels_and_blanks(large):
    s = make_scenario(cfg(), 1)
    assert isinstance(s, StreamingScenario)
    rows = list(s)
    assert [i for i, _, _ in rows] == list(range(40))
    assert [y for _, _, y in rows] == [10 <= i < 20 for i in range(40)]
    assert rows[5][1] == {'a': 5.0, 'b': -5.0}
    assert math.isnan(rows[3][1]['b'])  # a blank field becomes NaN for the pipeline's imputation
    assert s.attack_type == 'BENIGN' and s.cursor == 39


def test_length_limits_rows_and_schedule(large):
    s = make_scenario(cfg(length=8), 1)
    assert len(list(s)) == 8
    info = s.info
    assert info['drift_ground_truth'] == 'schedule' and info['schedule']['attack_periods'] == []
    assert info['schedule']['day_start_rows'] == {'monday': 0}
    assert make_scenario(cfg(length=15), 1).info['schedule']['attack_periods'][0]['start_row'] == 10


def test_checksums_and_injection_refused(large):
    path, _ = large
    with pytest.raises(ValueError, match='checksum'):
        make_scenario(cfg(dataset_sha256='bad'), 1)
    with pytest.raises(ValueError, match='contains 40'):
        make_scenario(cfg(length=41), 1)
    with pytest.raises(ValueError, match='real, dated changes'):
        make_scenario(cfg(injection={'kind': 'abrupt', 'start': 20, 'swap': ['a', 'b']}), 1)
    with pytest.raises(ValueError, match='disabled'):
        make_scenario(cfg(), 1).inject(1)
    (path / 'schedule.json').write_text('{}')
    with pytest.raises(ValueError, match='schedule checksum'):
        make_scenario(cfg(), 1)
    (path / 'big.csv').write_text('row,attack_type,label,a,b\n0,BENIGN,BENIGN,1,2\n')
    with pytest.raises(ValueError, match='checksum'):
        make_scenario(cfg(), 1)


def test_bad_value_reports_line(large, monkeypatch):
    path, entry = large
    raw = (path / 'big.csv').read_bytes().replace(b'\n7,BENIGN,BENIGN,7,-7\n', b'\n7,BENIGN,BENIGN,x,-7\n')
    (path / 'big.csv').write_bytes(raw)
    entry['sha256'] = _sha(raw)
    (path / 'catalog.json').write_text(json.dumps([entry]))
    with pytest.raises(ValueError, match='CSV line 9'):
        list(make_scenario(cfg(), 1))


def test_runs_through_the_engine(large):
    trial = TrialConfig(stream=cfg(), methods=('static', 'adaptive'), evaluation=EvaluationConfig(warmup=5))
    result = run_trial(trial)
    assert result.status == 'completed' and result.timing['samples'] == 40
    assert set(result.summaries) == {'static', 'adaptive'}
    assert result.scenario['drift_ground_truth'] == 'schedule'
    assert result.config.stream.dataset_sha256 == make_scenario(cfg(), 1).sha256


# ---------------------------------------------------------------- preparation script

def _prepare_module():
    spec = importlib.util.spec_from_file_location('prepare_cicids2017', REPO / 'scripts' / 'prepare_cicids2017.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HEADER = ('id,Flow ID,Src IP,Src Port,Dst IP,Dst Port,Protocol,Timestamp,Flow Duration,'
          'Flow Bytes/s,Const,Label,Attempted Category')


def _day(rows):
    return '\n'.join([HEADER, *rows]) + '\n'


def test_prepare_orders_by_end_time_and_keeps_labels(tmp_path):
    prep = _prepare_module()
    raw, out = tmp_path / 'raw', tmp_path / 'out'
    raw.mkdir(), out.mkdir()
    days = {
        # id 1 starts first but ends last (30 s long); id 2 ends first.
        'monday': ['1,f,1.1.1.1,1,2.2.2.2,80,6,2017-07-03 10:00:00.000000,30000000,inf,0,BENIGN,-1',
                   '2,f,1.1.1.1,2,2.2.2.2,80,6,2017-07-03 10:00:05.000000,1000000,5.5,0,BENIGN,-1'],
        'tuesday': ['1,f,6.6.6.6,3,2.2.2.2,21,6,2017-07-04 10:00:00.000000,0,1,0,FTP-Patator,-1',
                    '2,f,6.6.6.6,4,2.2.2.2,21,6,2017-07-04 10:00:01.000000,0,1,0,FTP-Patator - Attempted,1',
                    '3,f,6.6.6.6,5,2.2.2.2,21,6,2017-07-04 10:30:00.000000,0,1,0,FTP-Patator,-1'],
        'wednesday': [], 'thursday': [], 'friday': [],
    }
    for day, rows in days.items():
        (raw / f'{day}.csv').write_text(_day(rows))
    header, arrays, order = prep.index_rows(raw)
    path, schedule = prep.write_stream(raw, out, header, arrays, order)
    lines = path.read_text().splitlines()
    assert lines[0].split(',')[:7] == ['row', 'source_day', 'source_id', 'ts_start', 'ts_end', 'attack_type', 'label']
    body = [line.split(',') for line in lines[1:]]
    assert [r[2] for r in body] == ['2', '1', '1', '2', '3']  # monday id 2 ends before id 1
    assert [r[6] for r in body] == ['BENIGN', 'BENIGN', 'ATTACK', 'BENIGN', 'ATTACK']  # "Attempted" → BENIGN
    assert body[3][5] == 'FTP-Patator - Attempted'  # the original label is kept
    assert body[1][9:11] == ['30000000', '']  # Flow Duration as written; inf Flow Bytes/s as blank
    assert schedule['blank_values'] == {'Flow Bytes/s': 1}
    assert schedule['columns_written'] == ['Dst Port', 'Protocol', 'Flow Duration', 'Flow Bytes/s', 'Const']
    assert schedule['constant_columns'] == ['Protocol', 'Const']
    assert schedule['labels_binary'] == {'BENIGN': 3, 'ATTACK': 2}
    # 30 minutes apart > the 10-minute gap: two separate attack periods.
    assert [(p['start_row'], p['flows']) for p in schedule['attack_periods']] == [(2, 1), (4, 1)]
    assert schedule['day_start_rows'] == {'monday': 0, 'tuesday': 2}
