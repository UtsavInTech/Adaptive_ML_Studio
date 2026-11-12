"""Phase 3: each rule of the joint controller fires on a crafted case, and the cost terms add up.

The controller's `_step` is driven directly with chosen service times, accuracy and detector events,
on a real pipeline that has finished its warm-up, so every rule is checked without relying on timing.
"""
import random

import pytest

from adaptiveml.config import ControllerConfig, EvaluationConfig, PipelineConfig, ResourceBudgets, StreamConfig, TrialConfig
from adaptiveml.engine import run_trial
from adaptiveml.joint_controller import JointController
from adaptiveml.pipeline import MethodPipeline, method_spec

FEATURES = [f"f{j}" for j in range(8)]
WARMUP = 50
MS = 1_000_000  # ns
DRIFT = [{"type": "drift_detected", "error_increased": True}]


def row(rng):
    x = {f: rng.random() for f in FEATURES}
    return x, x["f0"] + x["f1"] > 1.0


def make(budgets=None, cpu_budget_ns=None, **cfg):
    rng = random.Random(7)
    pipe = MethodPipeline(method_spec("joint", PipelineConfig()), FEATURES, warmup=WARMUP, seed=1)
    for i in range(WARMUP):
        pipe.process(i, *row(rng))
    settings = dict(window=10, deadline_window=10, deadline_misses=3, cooldown=0, relax_after=5,
                    memory_check_every=1, retrain_buffer=50, cpu_smoothing=1.0) | cfg
    ctrl = JointController(pipe, ControllerConfig(**settings), budgets or ResourceBudgets(), cpu_budget_ns)
    for i in range(WARMUP, WARMUP + 60):  # fills the retraining buffer with real rows
        pipe.process(i, *row(rng))
    return pipe, ctrl


def actions(ctrl):
    return dict(ctrl.actions)


def test_r3_narrows_halves_then_thins_updates_and_relaxes():
    pipe, ctrl = make(ResourceBudgets(latency_deadline_ms=0.1, min_features=2, max_update_stride=4))
    k0, i = len(pipe.active.features), 200
    for _ in range(3):  # three rows over the 0.1 ms deadline
        ctrl._step(i, True, 5 * MS, [])
        i += 1
    assert pipe.narrow and len(pipe.active.features) == max(2, k0 // 2)
    assert any(a.startswith("R3_HALVE_FEATURES") for a in ctrl.actions)
    while len(pipe.active.features) > 2:
        for _ in range(3):
            ctrl._step(i, True, 5 * MS, [])
            i += 1
    for _ in range(3):
        ctrl._step(i, True, 5 * MS, [])
        i += 1
    assert pipe.update_stride == 2 and "R3_UPDATE_EVERY_2" in ctrl.actions
    for _ in range(10):  # calm: fast rows, nothing tight
        ctrl._step(i, True, 1_000, [])
        i += 1
    assert pipe.update_stride == 1 and "R3_RELAX_UPDATE_EVERY_1" in ctrl.actions


def test_r5_escalates_replacement_then_fresh_model_then_fewer_features():
    pipe, ctrl = make(ResourceBudgets(model_memory_mib=0.001, min_features=1))
    pipe._start_background(200, "test")
    pipe.model_bytes = lambda: 10 * 2**20  # far over the 1 KiB budget
    ctrl._step(200, True, 1_000, [])
    assert pipe.background is None and ctrl.actions["R5_DROP_REPLACEMENT"] == 1
    k, version = len(pipe.active.features), pipe.active.version
    ctrl._step(201, True, 1_000, [])  # no replacement left: a fresh model, same features
    assert ctrl.actions["R5_FRESH_MODEL"] == 1 and len(pipe.active.features) == k and pipe.active.version == version + 1
    ctrl._step(202, True, 1_000, [])  # over budget again soon after: fewer features
    assert len(pipe.active.features) == max(1, k // 2) and ctrl.k_ceiling == max(1, k // 2)
    assert any(a.startswith("R5_SHRINK_MODEL") for a in ctrl.actions)
    report = ctrl.report()
    assert report["memory_probes_over_budget"] == report["memory_probes"] and report["peak_model_bytes"] == 10 * 2**20


def test_r5_cut_is_not_undone_by_r3_relaxing():
    pipe, ctrl = make(ResourceBudgets(model_memory_mib=0.001, min_features=1))
    pipe.model_bytes = lambda: 10 * 2**20
    ctrl._step(200, True, 1_000, [])
    ctrl._step(201, True, 1_000, [])
    cut = len(pipe.active.features)
    assert cut < pipe.selector.k_initial
    pipe.model_bytes = lambda: 100  # memory fine from now on; long calm stretch
    for i in range(202, 260):
        ctrl._step(i, True, 1_000, [])
    assert len(pipe.active.features) == cut and not any("RELAX" in a for a in ctrl.actions)


def test_joint_alone_leaves_rivers_memory_cap_to_r5():
    from adaptiveml.config.profiles import BUILTIN_PROFILES
    from adaptiveml.engine import build_pipelines
    trial = TrialConfig(methods=("joint", "adaptive"), profile=BUILTIN_PROFILES["memory_sim"])
    joint, adaptive = build_pipelines(trial, FEATURES)
    assert joint.spec.pipeline.learner.max_size_mib == 100.0  # not capped: R5 enforces the budget
    assert adaptive.spec.pipeline.learner.max_size_mib == 0.25  # capped by River, as before


def test_r2_when_tight_and_r1_when_spare():
    pipe, ctrl = make(cpu_budget_ns=10_000)  # 10 µs per row
    ctrl._step(200, True, 50_000, DRIFT)  # 5× the budget: tight
    assert pipe.lightweight and not pipe._adapt_cfg.allow_background
    assert ctrl.actions["R2_DRIFT"] == 1
    ctrl._step(201, True, 1_000, DRIFT)  # 10 % of the budget: spare again
    assert not pipe.lightweight and pipe._adapt_cfg.allow_background
    assert ctrl.actions["R1_DRIFT"] == 1
    # between the thresholds the mode holds (hysteresis)
    ctrl._step(202, True, 50_000, [])
    ctrl._step(203, True, 8_000, [])  # 80 %: neither tight nor spare
    assert pipe.lightweight


def test_r2_drops_a_replacement_and_handles_pending_drift_by_reset():
    pipe, ctrl = make(cpu_budget_ns=10_000)
    pipe._prepare(200, "test drift", "prepare")
    version = pipe.active.version
    ctrl._step(200, True, 50_000, [])
    assert pipe.background is None and pipe.pending_since is None and pipe.active.version == version + 1


def test_r4_retrains_when_spare_and_defers_when_tight():
    pipe, ctrl = make(cpu_budget_ns=10_000, accuracy_floor=0.9)
    version = pipe.active.version
    for i in range(200, 210):  # ten wrong predictions: rolling accuracy 0
        ctrl._step(i, False, 1_000, [])
    assert ctrl.actions["R4_RETRAIN"] == 1 and pipe.active.version == version + 1
    assert pipe.active.trained_on == len(pipe.recent) > 0
    pipe2, ctrl2 = make(cpu_budget_ns=10_000, accuracy_floor=0.9)
    for i in range(200, 210):
        ctrl2._step(i, False, 50_000, [])  # tight: no retraining
    assert ctrl2.actions["R4_DEFERRED_RESOURCES_TIGHT"] == 1 and "R4_RETRAIN" not in ctrl2.actions


def test_ablations_switch_rules_off():
    pipe, ctrl = make(cpu_budget_ns=10_000, rules=("R2", "R3", "R4", "R5"))  # no R1
    assert pipe.respond_to_drift is False  # standard mode, and R1 is off
    ctrl._step(200, True, 1_000, DRIFT)
    assert ctrl.actions["R1_OFF_DRIFT_IGNORED"] == 1
    ctrl._step(201, True, 50_000, [])
    assert pipe.lightweight and pipe.respond_to_drift  # R2 handles drift while tight
    pipe3, ctrl3 = make(cpu_budget_ns=10_000, resource_gating=False)
    ctrl3._step(200, True, 50_000, DRIFT)
    assert not pipe3.lightweight and ctrl3.actions["R1_DRIFT"] == 1  # never switches without gating
    pipe4, ctrl4 = make(ResourceBudgets(latency_deadline_ms=0.1), rules=("R1", "R2", "R4", "R5"))
    for i in range(200, 210):
        ctrl4._step(i, True, 5 * MS, [])
    assert not any(a.startswith("R3") for a in ctrl4.actions) and not pipe4.narrow


def test_narrow_processing_keeps_needed_features_only():
    pipe, _ = make()
    pipe.reconfigure_features(300, 2, "test", immediate=True)
    pipe.set_narrow(300, True, "test")
    assert set(pipe._narrowed()) == set(pipe.active.features) | set(pipe.selector.proposed())
    x, y = row(random.Random(1))
    pred, service, stages = pipe.process(301, x, y)
    assert sum(stages) == service


def test_joint_through_engine_reports_controller_and_cost_terms():
    from adaptiveml.config import ProfileConfig
    profile = ProfileConfig(name="tight", simulated=True, placeholder=True,
                            budgets=ResourceBudgets(compute_share=0.01, nominal_rate=10_000, latency_deadline_ms=0.001))
    trial = TrialConfig(stream=StreamConfig(length=3_000, noise=0.0), methods=("joint", "adaptive"),
                        evaluation=EvaluationConfig(warmup=500), profile=profile)
    result = run_trial(trial)
    joint = result.summaries["joint"]
    assert joint["controller"]["decisions"] > 0 and joint["controller"]["rows_in_lightweight_mode"] > 0
    for s in result.summaries.values():
        terms = s["cost_terms_us_per_row"]
        assert terms["C_comm"] is None
        parts = sum(v for k, v in terms.items() if k not in ("C_comm", "total", "unattributed"))
        assert parts + terms["unattributed"] == pytest.approx(terms["total"])
        assert all(terms[k] >= 0 for k in ("C_pre", "C_fs", "C_inf", "C_drift", "C_upd", "C_ret", "C_ctrl"))
    assert "controller" not in result.summaries["adaptive"]  # the earlier controller is unchanged
