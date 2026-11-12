"""The budgeted effort controller (method "effort"): each lever and repair on a crafted case, the price
of compute, hard limits, stage times, determinism, and that every other method is unchanged.

As in test_joint_controller.py, the controller's `_step` is often driven directly with chosen costs;
the pipeline is real and has finished its warm-up.
"""
import random

import pytest
import yaml

from adaptiveml.config import (
    ControllerConfig, DriftSpec, EffortConfig, EvaluationConfig, ExperimentConfig, PipelineConfig, PreprocessingConfig,
    ProfileConfig, ResourceBudgets, StreamConfig, TrialConfig,
)
from adaptiveml.config.profiles import BUILTIN_PROFILES
from adaptiveml.controller import PipelineController
from adaptiveml.drift import Signal
from adaptiveml.effort_controller import EffortController
from adaptiveml.engine import build_pipelines, run_trial
from adaptiveml.pipeline import C_TRANSFORM, MethodPipeline, method_spec
from adaptiveml.preprocessing import Preprocessor

FEATURES = [f"f{j}" for j in range(24)]
WARMUP = 50
DRIFT = [{"type": "drift_detected", "error_increased": True}]
ALL_OFF = dict(narrow_preprocessing=False, sample_statistics=False, live_ranking=False, skip_easy_updates=False,
               feature_gate=False, fast_switch=False, damp_realarms=False, delay_aware=False)


def row(rng, label=None):
    x = {f: rng.random() for f in FEATURES}
    return x, (x["f0"] + x["f1"] > 1.0) if label is None else label


def make(budgets=None, cpu_budget_ns=None, effort=None, delay=0, rows=60, seed=7, **cfg):
    """An effort pipeline and controller after warm-up, plus `rows` further rows."""
    rng = random.Random(seed)
    pipe = MethodPipeline(method_spec("effort", PipelineConfig()), FEATURES, warmup=WARMUP, seed=1, label_delay=delay)
    settings = dict(window=10, deadline_window=10, deadline_misses=3, cooldown=0, relax_after=5,
                    memory_check_every=1, retrain_buffer=50, cpu_smoothing=1.0) | cfg
    ctrl = EffortController(pipe, ControllerConfig(effort=EffortConfig(**(effort or {})), **settings),
                            budgets or ResourceBudgets(), cpu_budget_ns)
    for i in range(WARMUP + rows):
        ctrl.process(i, *row(rng))
    return pipe, ctrl, rng


def sea(**kw):
    stream = StreamConfig(length=4000, noise=0.1, drifts=(DriftSpec(position=2000, to_variant=2),))
    return TrialConfig(seed=3, stream=stream, evaluation=EvaluationConfig(warmup=500), **kw)


# ---------------------------------------------------------------- the other methods are unchanged
# Computed on the unchanged code (before "effort" existed), on this exact SEA trial. Static, incremental
# and repeat-last-label never read a timer; joint on the standard tier has no budget, so its rules read
# no timer either (checked: identical over four runs). Adaptive's subset controller compares measured
# time with 15 ms, so its predictions are not bit-stable and only its configuration is compared.
BEFORE = {
    "static": "c8c6616d48d5b0554b950162c1d7ed215bcf7598dda74baf2a4ff0d8810c0ab1",
    "incremental": "954ba76d2131b2ca39461ab48fe60b11af440d4358c6c621db3a982a9c321613",
    "no_change": "8fd3af0feb86d0919fc9b41e88a54cb5cd86b092d4b77c5a62094ebf36134652",
    "joint": "2b493332c7abc511d2ba4d260118d69190e36901f45966b01c904109ab00a729",
}


def test_defaults_leave_other_methods_unchanged():
    result = run_trial(sea(methods=("static", "incremental", "adaptive", "joint", "no_change")))
    for method, digest in BEFORE.items():
        assert result.summaries[method]["predictions_sha256"] == digest, method
    trial = sea(methods=("adaptive", "joint", "incremental", "effort"))
    adaptive, joint, incremental, effort = build_pipelines(trial, ["x0", "x1", "x2"])
    for p in (adaptive, joint, incremental):  # no lever, gate or warm start outside "effort"
        assert p.levers is None and p.drift_gate is None and p._warm_start == 0 and p.pre._ew is None
    assert adaptive.spec.pipeline == joint.spec.pipeline == effort.spec.pipeline == trial.pipeline
    assert "controller" not in result.summaries["adaptive"]
    assert set(result.summaries["joint"]["controller"]) >= {"rules", "actions", "rows_in_lightweight_mode"}
    assert "effort" not in result.summaries["joint"]["controller"]


def test_adaptive_keeps_its_subset_controller():
    captured = {}
    run_trial(sea(methods=("adaptive", "effort")), context_sink=lambda ctx: captured.update(ctx.governors))
    assert type(captured["adaptive"]) is PipelineController and type(captured["effort"]) is EffortController


def test_everything_off_reproduces_joint():
    """With every lever and repair off, "effort" on the standard tier is the joint pipeline, bit for bit."""
    cfg = sea(methods=("effort", "joint"), controller=ControllerConfig(effort=EffortConfig(**ALL_OFF)))
    s = run_trial(cfg).summaries
    assert s["effort"]["predictions_sha256"] == s["joint"]["predictions_sha256"]


# ---------------------------------------------------------------- levers
def test_b1_narrow_preprocessing_from_the_end_of_warmup():
    pipe, ctrl, rng = make(effort={"live_ranking": False})
    needed = pipe._narrowed_effort()
    assert len(needed) < len(FEATURES) and set(pipe.active.features) <= set(needed)
    pipe.process(500, *row(rng))
    assert pipe.row_counts[C_TRANSFORM] == len(needed)
    pipe2, _, rng2 = make(effort={"narrow_preprocessing": False, "live_ranking": False})
    pipe2.process(500, *row(rng2))
    assert pipe2.row_counts[C_TRANSFORM] == len(FEATURES)


def test_b2_statistics_on_one_row_in_s_with_a_scaled_fading_factor():
    pipe, ctrl, rng = make(effort={"live_ranking": False, "levels": [{"name": "only", "stats_every": 4, "rank_every": 1}]}, rows=0)
    for i in range(WARMUP, WARMUP + 400):
        ctrl.process(i, *row(rng))
    assert pipe.levers.stats_rows == 100
    # gap-aware: one update after a gap of g rows weighs like g updates of the same value
    a = 0.01
    pre = Preprocessor(["v"], PreprocessingConfig(fading_factor=a), gap_aware=True)
    pre.learn_at({"v": 0.0}, {"v": 0.0}, 0)
    pre.learn_at({"v": 1.0}, {"v": 1.0}, 4)
    every = Preprocessor(["v"], PreprocessingConfig(fading_factor=a), gap_aware=True)
    every.learn_at({"v": 0.0}, {"v": 0.0}, 0)
    for i in range(1, 5):
        every.learn_at({"v": 1.0}, {"v": 1.0}, i)
    assert pre._ew["v"][0] == pytest.approx(1 - (1 - a) ** 4) == pytest.approx(every._ew["v"][0])


def test_b3_ranking_stays_live_over_all_inputs_while_narrowed():
    pipe, ctrl, rng = make(effort={"gate_rows_per_class": 1}, rows=0)
    outside = [f for f in FEATURES if f not in pipe._narrowed_effort()]
    assert outside
    w0 = dict(pipe.selector._ranker.weights)
    for i in range(WARMUP, WARMUP + 400):
        ctrl.process(i, *row(rng))
    lv = pipe.levers
    assert 0 < lv.rank_rows <= 400 // 10 + 5  # 1 labelled row in r (r = 10 or 20), plus class catch-up
    w1 = pipe.selector._ranker.weights
    assert any(w1.get(f, 0.0) != w0.get(f, 0.0) for f in outside)  # inputs outside the model are still ranked
    frozen, fctrl, frng = make(effort={"live_ranking": False}, rows=0)  # the joint/R3 behaviour: frozen when narrowed
    w0 = dict(frozen.selector._ranker.weights)
    for i in range(WARMUP, WARMUP + 200):
        fctrl.process(i, *row(frng))
    assert dict(frozen.selector._ranker.weights) == w0


def test_b3_ranks_every_row_of_a_class_not_yet_seen_enough():
    pipe, ctrl, rng = make(effort={"gate_rows_per_class": 10_000}, rows=0)
    for i in range(WARMUP, WARMUP + 100):
        ctrl.process(i, *row(rng))
    assert pipe.levers.rank_rows == 100


def test_b4_skips_most_updates_on_easy_rows_only():
    levels = [{"name": "only", "stats_every": 1, "rank_every": 10, "skip_easy": True, "easy_learn_every": 5}]
    pipe, ctrl, rng = make(effort={"levels": levels, "easy_k": 10, "fast_switch": False}, rows=0)
    for i in range(WARMUP, WARMUP + 200):  # teach it that this is always True
        ctrl.process(i, *row(rng, True))
    lv = pipe.levers
    easy0, skipped0, trained0 = lv.easy_rows, lv.skipped_updates, pipe.active.trained_on
    for i in range(WARMUP + 200, WARMUP + 700):
        ctrl.process(i, *row(rng, True))
    easy, skipped = lv.easy_rows - easy0, lv.skipped_updates - skipped0
    assert easy == 500 and skipped == 400  # learns from 1 easy row in 5
    assert pipe.active.trained_on - trained0 == 100
    ctrl.process(WARMUP + 700, *row(rng, False))  # a label switch is never easy
    assert lv.run <= 1 and lv.skipped_updates - skipped0 == 400


def test_b5_features_cut_only_after_both_classes_ranked_and_never_below_floor():
    budgets = ResourceBudgets(latency_deadline_ms=0.1, min_features=2, max_update_stride=4)
    pipe, ctrl, _ = make(budgets, effort={"gate_rows_per_class": 10**9})
    k0, i = len(pipe.active.features), 500
    assert k0 == 16 and ctrl.floor == 8
    for _ in range(3):  # three rows over the deadline, gate closed: thinner updates, not fewer features
        ctrl._step(i, True, 0, [], modelled=5e6)
        i += 1
    assert len(pipe.active.features) == k0 and pipe.update_stride == 2
    pipe.levers.rank_counts = {True: 10**9, False: 10**9}  # both classes seen
    for _ in range(3):
        ctrl._step(i, True, 0, [], modelled=5e6)
        i += 1
    assert len(pipe.active.features) == 8 and ctrl.gate_opened_at is not None
    for _ in range(3):
        ctrl._step(i, True, 0, [], modelled=5e6)
        i += 1
    assert len(pipe.active.features) == 8 and pipe.update_stride == 4  # the floor holds
    off, octrl, _ = make(budgets, effort={"feature_gate": False})
    for j in range(3):
        octrl._step(500 + j, True, 0, [], modelled=5e6)
    assert len(off.active.features) == 8 and octrl.floor == 2  # no gate: cut at once, tier floor only


# ---------------------------------------------------------------- the price of compute
def test_price_rises_over_budget_and_falls_under_it():
    pipe, ctrl, _ = make(cpu_budget_ns=100_000)
    assert ctrl.price == 0.0
    for i in range(500, 600):
        ctrl._step(i, True, 0, [], modelled=200_000)
    assert ctrl.price == pytest.approx(100 * 0.002 * 1.0)
    for i in range(600, 800):
        ctrl._step(i, True, 0, [], modelled=50_000)
    assert ctrl.price == 0.0
    # quiet (activity ~0) and a positive price → the cheapest level; full activity at price 0 → the richest
    ctrl.price = 1.0
    ctrl._step(800, True, 0, [], modelled=100_000)
    assert ctrl.level == 0
    ctrl.price = 0.0
    ctrl.alarm_until = 10**9
    ctrl._step(801, True, 0, [], modelled=100_000)
    assert ctrl.level == len(ctrl.levels) - 1


def test_mean_modelled_cost_converges_near_the_budget_and_effort_goes_to_hard_stretches():
    # statistics made expensive, so the levels differ clearly in cost (rich: every row; cheap: 1 in 16)
    effort = {"cost": {"stats_ns_per_input": 20_000.0}}
    pipe, ctrl, rng = make(effort=effort, rows=0)
    costs = ctrl.level_costs()
    budget = (costs[0] + costs[-1]) / 2
    ctrl.cpu_budget_ns, ctrl.price = budget, 0.0
    by_stretch = {"quiet": [0, 0, 0.0], "active": [0, 0, 0.0]}  # rows, rows at the richest level, modelled ns
    i = WARMUP
    for stretch in range(12):
        active = stretch % 2 == 1
        for _ in range(3_000):
            label = rng.random() < 0.5 if active else True
            before = ctrl.modelled_sum
            ctrl.process(i, *row(rng, label))
            tally = by_stretch["active" if active else "quiet"]
            tally[0] += 1
            tally[1] += ctrl.level == len(ctrl.levels) - 1
            tally[2] += ctrl.modelled_sum - before
            i += 1
    mean = ctrl.modelled_sum / ctrl.rows
    active_mean = by_stretch["active"][2] / by_stretch["active"][0]
    assert costs[0] < mean <= 1.02 * budget  # held on average; quiet stretches leave budget unspent
    assert active_mean == pytest.approx(budget, rel=0.1)  # where the budget binds, spending converges to it
    assert by_stretch["active"][1] / by_stretch["active"][0] > 2 * by_stretch["quiet"][1] / by_stretch["quiet"][0]
    report = ctrl.report()["effort"]
    assert sum(report["rows_per_level"].values()) == ctrl.rows and report["final_price"] == ctrl.price
    # a stream that is hard throughout: the running mean settles at the budget
    pipe2, ctrl2, rng2 = make(effort=effort, rows=0)
    ctrl2.cpu_budget_ns = budget
    for j in range(WARMUP, WARMUP + 20_000):
        if j == WARMUP + 10_000:
            first_half = ctrl2.modelled_sum
        ctrl2.process(j, *row(rng2, rng2.random() < 0.5))
    assert (ctrl2.modelled_sum - first_half) / 10_000 == pytest.approx(budget, rel=0.05)
    assert 0 < ctrl2.price < ctrl2.e.price_max


def test_without_budget_quiet_rows_still_get_the_cheap_levers():
    pipe, ctrl, rng = make(rows=0)
    for i in range(WARMUP, WARMUP + 1_500):
        ctrl.process(i, *row(rng, True))
    assert ctrl.level == 0 and ctrl.price == EffortConfig().free_price
    assert ctrl.report()["effort"]["share_rows_update_skipped"] > 0.5


# ---------------------------------------------------------------- hard limits
def test_memory_limit_wins_over_a_low_price():
    pipe, ctrl, _ = make(ResourceBudgets(min_features=1), cpu_budget_ns=10**9)
    ctrl.memory_budget = 0.001 * 2**20  # set after the setup rows, so R5 acts only on the rows below
    pipe.model_bytes = lambda: 10 * 2**20
    pipe._start_background(500, "test")
    ctrl._step(500, True, 0, [], modelled=1_000)
    assert ctrl.price == 0.0 and pipe.background is None and ctrl.actions["R5_DROP_REPLACEMENT"] == 1
    ctrl._step(501, True, 0, [], modelled=1_000)
    ctrl._step(502, True, 0, [], modelled=1_000)
    assert ctrl.actions["R5_FRESH_MODEL"] == 1 and len(pipe.active.features) == 8  # shrunk, but not below the floor
    assert ctrl.report()["memory_probes_over_budget"] == ctrl.report()["memory_probes"]


def test_deadline_restricts_levels_and_wins_over_the_price():
    pipe, ctrl, _ = make(ResourceBudgets(latency_deadline_ms=0.1), cpu_budget_ns=10**9)
    deadline = ctrl.deadline_ns
    costs = ctrl.level_costs()
    ctrl.deadline_ns = (costs[0] + costs[-1]) / 2  # the richest level no longer fits in one row
    ctrl.alarm_until = 10**9  # full activity, price 0: it would choose the richest level
    ctrl._step(500, True, 0, [], modelled=1_000)
    assert ctrl.levels[ctrl.level].name != "rich"
    ctrl.deadline_ns = deadline


# ---------------------------------------------------------------- repairs
def test_d1_fast_switch_promotes_a_replacement_that_beats_the_active_model():
    pipe, ctrl, rng = make()
    pipe._prepare(500, "test drift", "prepare")
    bg = pipe.background
    bg.model.learn_one({f: 0.0 for f in bg.features}, True)
    bg.trained_on = 1
    bg.model.predict_one = lambda x: True
    version = pipe.active.version
    for i in range(501, 525):
        x, _ = row(rng)
        pipe._learn_background_effort(i, {f: x[f] for f in FEATURES}, True, False)  # active wrong, replacement right
        if pipe.background is None:
            break
    assert pipe.active is bg and pipe.active.version == version + 1 and pipe.levers.fast_promotions == 1
    assert bg.trained_on < 200
    pipe2, _, rng2 = make(effort={"fast_switch": False})
    pipe2._prepare(500, "test drift", "prepare")
    for i in range(501, 525):
        x, _ = row(rng2)
        pipe2._learn_background_effort(i, {f: x[f] for f in FEATURES}, True, False)
    assert pipe2.background is not None  # without D1 it waits for 200 rows


def test_d2_damps_realarms_while_the_label_mix_is_stable():
    pipe, ctrl, rng = make()
    ctrl._step(500, True, 0, [{"type": "adaptation_completed"}], labels=(True,), modelled=1_000)
    pipe.last_adaptation = 500
    assert ctrl._damp(900) is not None
    events = len(pipe.events)
    pipe._on_signal(900, Signal.DRIFT, True)  # after the policy's 300-row cooldown, inside the damping window
    assert any(e["type"] == "drift_ignored" and e.get("damped") for e in pipe.events[events:])
    assert ctrl._damp(500 + ctrl.e.damp_rows + 1) is None  # too long after the adaptation
    for j in range(600):  # the label mix moves
        ctrl._signals(700 + j, (True,), (False,), [])
    assert ctrl._damp(900) is None
    _, off, _ = make(effort={"damp_realarms": False})
    assert off.pipe.drift_gate is None


def test_d3_delay_aware_mutes_old_labels_warm_starts_and_keeps_the_old_model():
    pipe, ctrl, rng = make(delay=30, cpu_budget_ns=10_000, rows=100)
    assert ctrl.delay_aware and pipe._warm_start == 100
    pipe.last_adaptation = WARMUP + 100
    muted = pipe.levers.muted_labels
    for i in range(WARMUP + 100, WARMUP + 120):  # labels arriving now belong to rows before the adaptation
        ctrl.process(i, *row(rng))
    assert pipe.levers.muted_labels - muted == 20
    pipe.policy = type(pipe.policy)(pipe._adapt_cfg.model_copy(update={"allow_background": False, "cooldown": 0}))
    pipe.last_adaptation = None
    pipe._on_signal(400, Signal.DRIFT, True)  # a reset: the fresh model is warm-started
    assert pipe.active.started_at == 400 and pipe.active.trained_on == min(100, len(pipe.recent))
    ctrl.price = ctrl.e.price_max  # tight: the joint controller would switch to lightweight resets
    ctrl._step(401, True, 0, [], labels=(True,), modelled=10**6)
    assert not pipe.lightweight  # D3: a replacement is allowed here, so the old model keeps predicting
    _, imm, _ = make(cpu_budget_ns=10_000)
    assert not imm.delay_aware and imm.pipe._warm_start == 0  # only with delayed labels


# ---------------------------------------------------------------- measurement and determinism
@pytest.mark.parametrize("delay", [0, 25])
def test_stage_times_sum_to_service_time(delay):
    pipe, ctrl, rng = make(delay=delay, cpu_budget_ns=50_000)
    for i in range(WARMUP + 60, WARMUP + 400):
        _, service, stages = ctrl.process(i, *row(rng))
        assert sum(stages) == service


def test_same_config_gives_identical_predictions_with_modelled_cost():
    tight = ProfileConfig(name="tight", simulated=True, placeholder=True,
                          budgets=ResourceBudgets(compute_share=0.02, nominal_rate=1_000, latency_deadline_ms=0.05,
                                                  model_memory_mib=0.05))
    for delay in (0, 200):
        cfg = sea(methods=("effort",), profile=tight).model_copy(
            update={"stream": sea().stream.model_copy(update={"label_delay": delay})})
        a, b = run_trial(cfg), run_trial(cfg)
        assert a.summaries["effort"]["predictions_sha256"] == b.summaries["effort"]["predictions_sha256"]
        ca, cb = a.summaries["effort"]["controller"], b.summaries["effort"]["controller"]
        assert ca["actions"] == cb["actions"] and ca["effort"]["rows_per_level"] == cb["effort"]["rows_per_level"]
        assert ca["effort"]["mean_modelled_us"] == cb["effort"]["mean_modelled_us"]
        assert a.timing["timing_dependent_behaviour"] is False
        assert a.summaries["effort"]["controller"]["effort"]["peak_price"] > 0  # the budget did bind


def test_effort_through_engine_reports_controller_and_cost_terms():
    result = run_trial(sea(methods=("effort",), profile=BUILTIN_PROFILES["small_sim"]))
    s = result.summaries["effort"]
    c = s["controller"]
    for key in ("rules", "actions", "rows_in_lightweight_mode", "final_features", "final_update_stride",
                "final_narrow_processing", "budgets", "memory_probes", "peak_model_bytes"):
        assert key in c
    e = c["effort"]
    for key in ("rows_per_level", "mean_modelled_us", "mean_measured_us", "budget_us_per_row", "final_price",
                "share_rows_update_skipped", "levers", "repairs"):
        assert key in e
    terms = s["cost_terms_us_per_row"]
    parts = sum(v for k, v in terms.items() if k not in ("C_comm", "total", "unattributed"))
    assert parts + terms["unattributed"] == pytest.approx(terms["total"])
    assert all(terms[k] >= 0 for k in ("C_pre", "C_fs", "C_inf", "C_drift", "C_upd", "C_ret", "C_ctrl"))
    assert abs(terms["unattributed"]) < 0.2 * terms["total"]


def test_every_lever_and_repair_switches_from_an_experiment_file():
    text = """
name: effort switches
base:
  methods: [effort]
  controller:
    effort:
      cost_source: measured
      narrow_preprocessing: false
      sample_statistics: false
      live_ranking: false
      skip_easy_updates: false
      feature_gate: false
      budget_control: false
      activity_signal: false
      fast_switch: false
      damp_realarms: false
      delay_aware: false
      levels: [{name: one, stats_every: 2, rank_every: 5}]
"""
    exp = ExperimentConfig.model_validate(yaml.safe_load(text))
    e = exp.base.controller.effort
    assert e.cost_source == "measured" and not any(
        getattr(e, k) for k in ("narrow_preprocessing", "sample_statistics", "live_ranking", "skip_easy_updates",
                                "feature_gate", "budget_control", "activity_signal", "fast_switch", "damp_realarms", "delay_aware"))
    with pytest.raises(ValueError):
        EffortConfig(spare_price=4.0, tight_price=3.0)
    with pytest.raises(ValueError):
        EffortConfig(levels=[])


def test_post_hoc_race_only_keeps_the_old_model_unless_the_replacement_wins():
    pipe, ctrl, rng = make(delay=30, effort={"delay_race_only": True, "fast_switch": False})
    assert pipe.levers.race_only
    pipe._prepare(500, "test drift", "prepare")
    bg = pipe.background
    for i in range(501, 501 + 400):  # past 200 rows, never better than the active model: not promoted
        x, y = row(rng)
        pipe._learn_background_effort(i, {f: x[f] for f in FEATURES}, y, y)
    assert pipe.background is bg and pipe.pending_since == 500
    bg.model.predict_one = lambda x: True
    for i in range(901, 930):  # now it wins the race
        x, _ = row(rng)
        pipe._learn_background_effort(i, {f: x[f] for f in FEATURES}, True, False)
        if pipe.background is None:
            break
    assert pipe.active is bg
    _, imm, _ = make(effort={"delay_race_only": True})
    assert not imm.pipe.levers.race_only  # only with delayed labels
