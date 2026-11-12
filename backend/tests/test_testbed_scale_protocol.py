"""Phases 4-5: start offset, recorded arrival rate, delayed/partial labels, device tiers, fleet runner,
protocol statistics, protocol expansion and the report generator."""
import hashlib
import importlib.util
import json
import random
from pathlib import Path

import numpy as np
import pytest
from scipy import stats as sstats

from adaptiveml.analysis import block_counts, bootstrap_ci, friedman, metrics, nemenyi_cd
from adaptiveml.config import (
    EvaluationConfig, ExperimentConfig, PipelineConfig, ResourceBudgets, StreamConfig, TrialConfig,
)
from adaptiveml.config.profiles import BUILTIN_PROFILES, TESTBED_TIERS, per_sample_budget_ns
from adaptiveml.engine import run_trial
from adaptiveml.joint_controller import JointController
from adaptiveml.pipeline import MethodPipeline, method_spec
from adaptiveml.stream import make_scenario, static

REPO = Path(__file__).resolve().parents[2]


def _sha(b):
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def timed(tmp_path, monkeypatch):
    """60 rows, one per second until row 30, then ten per second (a burst); attacks at rows 40-49."""
    lines, t = ["row,ts_end,attack_type,label,a,b"], 0.0
    for i in range(60):
        t += 1.0 if i < 30 else 0.1
        sec, frac = int(t), round(t - int(t), 6)
        ts = f"2017-07-04 10:{sec // 60:02d}:{sec % 60:02d}.{int(frac * 1e6):06d}"
        attack = 40 <= i < 50
        lines.append(f"{i},{ts},{'DoS' if attack else 'BENIGN'},{'ATTACK' if attack else 'BENIGN'},{i},{-i}")
    raw = ("\n".join(lines) + "\n").encode()
    schedule = json.dumps({"rows": 60, "day_start_rows": {"monday": 0, "tuesday": 20}, "episode_gap_seconds": 600,
                           "attack_periods": [{"attack_type": "DoS", "start_row": 40, "end_row": 49, "flows": 10}]}).encode()
    (tmp_path / "t.csv").write_bytes(raw)
    (tmp_path / "s.json").write_bytes(schedule)
    entry = dict(id="timed", file="t.csv", schedule="s.json", streaming=True, name="Timed", rows=60, features=["a", "b"],
                 target="label", labels={"BENIGN": 0, "ATTACK": 1}, sha256=_sha(raw), schedule_sha256=_sha(schedule),
                 source="https://example.org", license="test", order="end time")
    (tmp_path / "catalog.json").write_text(json.dumps([entry]))
    monkeypatch.setattr(static, "DATA_ROOT", tmp_path)
    return tmp_path


def scfg(**kw):
    return StreamConfig(scenario="csv", dataset="timed", noise=0, **({"length": 60} | kw))


# ---------------------------------------------------------------- phase 4: stream scheduling
def test_start_offset_shifts_rows_and_schedule(timed):
    s = make_scenario(scfg(start=15, length=40), 1)
    rows = list(s)
    assert len(rows) == 40 and rows[0][1] == {"a": 15.0, "b": -15.0} and rows[0][0] == 0
    assert [(p["start_row"], p["end_row"]) for p in s.periods()] == [(25, 34)]
    assert s.info["schedule"]["day_start_rows"] == {"tuesday": 5}
    assert make_scenario(scfg(start=45, length=15), 1).periods() == []  # under way at the start: left out
    with pytest.raises(ValueError, match="from row 30"):
        make_scenario(scfg(start=30, length=40), 1)


def test_recorded_arrival_rate_follows_timestamps(timed, monkeypatch):
    from adaptiveml.stream import streaming
    monkeypatch.setattr(streaming, "ARRIVAL_WINDOW", 10)  # the fixture has 60 rows, not thousands
    s = make_scenario(scfg(arrival="recorded", rate_scale=2.0), 1)
    rates = {}
    for i, _, _ in s:
        rates[i] = s.arrival_rate()
    assert rates[0] is None
    assert rates[20] == pytest.approx(2.0, rel=1e-6)  # one row per second, doubled
    assert rates[59] > 5 * rates[20]  # the burst
    assert make_scenario(scfg(), 1).arrival_rate() is None


def test_start_and_arrival_rejected_where_unsupported():
    with pytest.raises(ValueError, match="dataset replay"):
        StreamConfig(start=5)
    with pytest.raises(ValueError, match="dataset replay"):
        StreamConfig(arrival="recorded")


def test_device_tiers_are_simulated_placeholders():
    for name in TESTBED_TIERS[1:]:
        p = BUILTIN_PROFILES[name]
        assert p.simulated and p.placeholder and p.budgets.latency_deadline_ms and p.budgets.model_memory_mib
    assert per_sample_budget_ns(BUILTIN_PROFILES["micro_sim"], None) < per_sample_budget_ns(BUILTIN_PROFILES["small_sim"], None)


def test_joint_controller_follows_a_changing_cpu_budget():
    pipe = MethodPipeline(method_spec("joint", PipelineConfig()), ["f0", "f1"], warmup=5, seed=1)
    rng = random.Random(1)
    for i in range(5):
        pipe.process(i, {"f0": rng.random(), "f1": rng.random()}, rng.random() > 0.5)
    budget = [100_000.0]
    ctrl = JointController(pipe, __import__("adaptiveml.config", fromlist=["ControllerConfig"]).ControllerConfig(cpu_smoothing=1.0),
                           ResourceBudgets(compute_share=0.5), 100_000.0, cpu_budget_now=lambda: budget[0])
    ctrl._step(10, True, 50_000, [])
    assert not pipe.lightweight  # 50 % of the budget: spare
    budget[0] = 20_000.0  # a burst: the budget per row shrinks
    ctrl._step(11, True, 50_000, [])
    assert pipe.lightweight and ctrl.report()["budgets"]["cpu_us_per_row_lowest"] == pytest.approx(20.0)


# ---------------------------------------------------------------- phase 4: labels
def _pipe(delay, coverage):
    p = MethodPipeline(method_spec("incremental", PipelineConfig()), ["f0", "f1"], warmup=10, seed=1,
                       label_delay=delay, label_coverage=coverage, label_seed=5)
    return p


def test_label_delay_learns_only_arrived_labels():
    p, rng = _pipe(5, 1.0), random.Random(2)
    for i in range(10):
        p.process(i, {"f0": rng.random(), "f1": rng.random()}, True)
    trained = p.active.trained_on
    for i in range(10, 30):
        _, service, stages = p.process(i, {"f0": rng.random(), "f1": rng.random()}, True)
        assert sum(stages) == service
        assert len(p.revealed) == (1 if i >= 15 else 0)
    assert p.active.trained_on == trained + 15  # rows 10-24 have arrived by row 29
    assert len(p._pending) == 5


def test_label_coverage_is_shared_by_methods_and_close_to_target():
    picks = []
    for _ in range(2):
        p, rng = _pipe(0, 0.3), random.Random(3)
        got = []
        for i in range(2010):
            p.process(i, {"f0": rng.random(), "f1": rng.random()}, rng.random() > 0.5)
            if i >= 10:
                got.append(len(p.revealed))
        picks.append(got)
    assert picks[0] == picks[1]  # the same rows get labels for every method of a trial
    assert 0.25 < np.mean(picks[0]) < 0.35


def test_delayed_labels_through_engine():
    trial = TrialConfig(stream=StreamConfig(length=3000, noise=0.0, label_delay=200, label_coverage=0.5),
                        methods=("adaptive", "joint"), evaluation=EvaluationConfig(warmup=500))
    r = run_trial(trial)
    assert r.summaries["joint"]["scores_after_warmup"]["n"] == 2500


# ---------------------------------------------------------------- phase 4: fleet runner
def test_fleet_runner_runs_trials_in_parallel(tmp_path):
    from adaptiveml.experiments.runner import run_experiment
    exp = ExperimentConfig(name="fleet", base=TrialConfig(stream=StreamConfig(length=1500, noise=0.0),
                           methods=("static", "adaptive"), evaluation=EvaluationConfig(warmup=300)), seeds=(1, 2))
    manifest = run_experiment(exp, root=tmp_path, workers=3)
    assert manifest["status"] == "completed" and len(manifest["trials"]) == 4
    assert manifest["parallel_workers"] == 3


# ---------------------------------------------------------------- phase 5: statistics
def test_metrics_and_bootstrap():
    y = np.array([0, 0, 1, 1, 0, 1, 1, 1, 0, 0] * 50, dtype=np.int8)
    p = y.copy()
    p[::7] ^= 1
    c = block_counts(y, p, 10, 40)
    m = metrics(c.sum(axis=0))
    rows = slice(10, 10 + 40 * len(c))
    assert m["accuracy"] == pytest.approx(np.mean(y[rows] == p[rows]))
    ci = bootstrap_ci(c, n_boot=300, seed=1)
    for k in ("accuracy", "kappa_temporal"):
        assert ci[k]["low"] <= ci[k]["value"] <= ci[k]["high"]
    with pytest.raises(ValueError):
        block_counts(y, p, 0, 40)


def test_friedman_matches_scipy_and_nemenyi_matches_demsar():
    rng = np.random.default_rng(0)
    scores = rng.random((14, 4)) + np.array([0.0, 0.1, 0.2, 0.3])
    ours = friedman(scores)
    ref = sstats.friedmanchisquare(*scores.T)
    assert ours["chi2"] == pytest.approx(ref.statistic) and ours["p_value"] == pytest.approx(ref.pvalue)
    assert ours["average_ranks"][3] < ours["average_ranks"][0]  # the highest scores rank best
    assert nemenyi_cd(4, 14) == pytest.approx(1.25, abs=0.01)  # Demšar (2006), worked example


# ---------------------------------------------------------------- phase 5: protocol and report
def _script(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "research_testbed" / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_protocol_expands_to_valid_experiments():
    import yaml
    proto = _script("protocol")
    protocol = yaml.safe_load(proto.PROTOCOL.read_text())
    for quick, expected in ((True, 105), (False, 333)):  # v2: + effort in core and labels, + effort_ablations
        total = 0
        for grid, stem, exp in proto.expand(protocol, quick):
            total += len(ExperimentConfig.model_validate(
                exp | {"profiles": [BUILTIN_PROFILES[p].model_dump() for p in exp["profiles"]]}).trials())
            if quick:
                assert "srp" not in exp["base"]["methods"] and exp["base"]["stream"]["start"] == 693702
        assert total == expected


def test_report_builds_from_a_small_run(tmp_path):
    from adaptiveml.experiments.runner import run_experiment
    exp = ExperimentConfig(name="report", base=TrialConfig(stream=StreamConfig(length=6000, noise=0.05),
                           methods=("no_change", "static", "incremental", "adaptive"),
                           evaluation=EvaluationConfig(warmup=500)), seeds=(1,))
    manifest = run_experiment(exp, root=tmp_path)
    report = _script("report")
    out = tmp_path / "rep"
    import sys
    argv = sys.argv
    sys.argv = ["report.py", "--runs", str(tmp_path / manifest["id"]), "--out", str(out),
                "--block-rows", "500", "--segment-blocks", "2", "--n-boot", "50"]
    try:
        report.main()
    finally:
        sys.argv = argv
    text = (out / "report.md").read_text()
    assert "## Core methods" in text and "Friedman" in text
    assert (out / "tables" / "settings.csv").exists() and (out / "figures" / "fig2_accuracy_vs_cost.png").exists()
    assert (out / "figures" / "fig7_critical_difference.svg").exists()
