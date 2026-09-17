import math
import random

import pytest

from adaptiveml.engine import run_trial
from adaptiveml.experiments.runner import sea_config
from adaptiveml.metrics import MethodRecorder
from adaptiveml.pipeline import STAGE_NAMES


def test_block_aggregation_matches_brute_force():
    rng = random.Random(0)
    rec = MethodRecorder("m", positive_class=True)
    rows = []
    for _ in range(137):
        y, y_pred = rng.random() < 0.6, rng.random() < 0.5
        stages = tuple(rng.randrange(0, 5_000) for _ in STAGE_NAMES)
        rec.add(y, y_pred, sum(stages), stages)
        rows.append((y, y_pred, stages))
    block = rec.close_block(0, 0, {"extra": 1})

    n = len(rows)
    service = sorted(sum(s) for _, _, s in rows)
    assert block["n"] == n and block["extra"] == 1
    assert block["tp"] == sum(1 for y, p, _ in rows if y and p)
    assert block["fp"] == sum(1 for y, p, _ in rows if not y and p)
    assert block["tn"] == sum(1 for y, p, _ in rows if not y and not p)
    assert block["fn"] == sum(1 for y, p, _ in rows if y and not p)
    assert block["service_mean_ns"] == pytest.approx(sum(service) / n)
    assert block["service_p95_ns"] == service[math.ceil(0.95 * n) - 1]
    assert block["service_max_ns"] == service[-1]
    for k, name in enumerate(STAGE_NAMES):
        assert block[f"{name}_mean_ns"] == pytest.approx(sum(s[k] for _, _, s in rows) / n)


def test_consecutive_blocks_do_not_mix_and_empty_blocks_are_skipped():
    rec = MethodRecorder("m", positive_class=True)
    rec.add(True, True, 6, (1, 1, 1, 1, 1, 1))
    first = rec.close_block(0, 0, {})
    rec.add(False, True, 12, (2, 2, 2, 2, 2, 2))
    second = rec.close_block(1, 1, {})
    assert (first["tp"], first["fp"]) == (1, 0) and (second["tp"], second["fp"]) == (0, 1)
    assert second["preprocess_mean_ns"] == 2
    assert rec.close_block(2, 2, {}) is None
    assert list(rec.service_ns) == [6, 12]


TIMING_FIELDS = {"service_mean_ns", "service_p95_ns", "service_max_ns", "duration_ns"} | {
    f"{name}_mean_ns" for name in STAGE_NAMES
}
# River's `_raw_memory_usage` is an estimate that varies by ~0.1 % between identical runs
# (docs/performance.md), so it is a resource measurement, not a reproducible output.
MEASUREMENT_FIELDS = TIMING_FIELDS | {"model_size_bytes"}


def _strip(records):
    return [{k: v for k, v in r.items() if k not in MEASUREMENT_FIELDS} for r in records]


def test_identical_runs_give_identical_non_measurement_records():
    cfg = sea_config(("static", "adaptive"), 5, length=6_000, drift_at=3_000, block_size=25)
    a, b = run_trial(cfg), run_trial(cfg)
    for method in cfg.methods:
        assert _strip(a.blocks[method]) == _strip(b.blocks[method])
    assert _strip(a.events) == _strip(b.events)


def test_pipeline_stages_add_up_to_the_service_time():
    result = run_trial(sea_config(("static", "adaptive"), 3, length=3_000, drift_at=2_000, block_size=100))
    for blocks in result.blocks.values():
        for b in blocks:
            stage_sum = sum(b[f"{name}_mean_ns"] for name in STAGE_NAMES)
            assert stage_sum == pytest.approx(b["service_mean_ns"])
