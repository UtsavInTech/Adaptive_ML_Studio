import csv
import gzip
import json

import pytest

from adaptiveml.config import (
    DriftSpec,
    EvaluationConfig,
    ExperimentConfig,
    ProfileConfig,
    ResourceBudgets,
    StreamConfig,
    TrialConfig,
)
from adaptiveml.config.profiles import EDGE_SIM, STANDARD
from adaptiveml.engine import run_trial
from adaptiveml.experiments.runner import run_experiment
from adaptiveml.results import list_experiments, load_blocks, load_events, windowed_scores


class ScriptedControl:
    """Returns the commands scripted for the n-th poll."""

    def __init__(self, script: dict[int, list[dict]]):
        self.script, self.calls = script, 0

    def poll(self) -> list[dict]:
        self.calls += 1
        return self.script.get(self.calls, [])


def config(length=3_000, **stream) -> TrialConfig:
    return TrialConfig(
        seed=3,
        methods=("static", "adaptive"),
        stream=StreamConfig(length=length, **stream),
        evaluation=EvaluationConfig(warmup=500, block_size=100),
    )


def test_paced_trial_follows_the_arrival_schedule_and_records_response_times():
    result = run_trial(config(length=800, rate=4_000))
    assert result.timing["total_ms"] >= 800 / 4_000 * 1e3 * 0.95
    assert len(result.response_ns) == 800
    assert result.timing["response_ms"]["mean"] < 5
    assert all(b["backlog"] >= 0 for b in result.engine_blocks)


def test_rate_does_not_change_predictions():
    fast, paced = run_trial(config(length=1_200)), run_trial(config(length=1_200, rate=20_000))
    for method in ("static", "adaptive"):
        assert fast.summaries[method]["predictions_sha256"] == paced.summaries[method]["predictions_sha256"]


def test_stop_command_ends_the_trial_early():
    result = run_trial(config(), control=ScriptedControl({5: [{"type": "stop"}]}))
    assert result.status == "stopped"
    assert result.timing["samples"] == 500


def test_pause_is_excluded_from_timing():
    statuses = []
    result = run_trial(
        config(),
        control=ScriptedControl({2: [{"type": "pause"}], 4: [{"type": "resume"}]}),
        on_status=lambda s: statuses.append(s["lifecycle"]),
    )
    assert result.status == "completed"
    assert result.timing["paused_ms"] >= 90
    assert "paused" in statuses and statuses[-1] == "completed"


def test_injected_drift_is_recorded_and_replays_identically():
    live = run_trial(config(length=4_000), control=ScriptedControl({8: [{"type": "inject_drift", "to_variant": 3}]}))
    (drift,) = live.config.stream.drifts
    assert drift.position == 800 + 176 and drift.to_variant == 3
    assert any(e["type"] == "drift_scheduled" for e in live.events)
    assert any(e["type"] == "drift_true" and e["i"] == drift.position for e in live.events)
    replay = run_trial(live.config)
    for method in ("static", "adaptive"):
        assert live.summaries[method]["predictions_sha256"] == replay.summaries[method]["predictions_sha256"]


def test_rejected_command_is_reported_not_raised():
    pending = config(length=4_000, drifts=(DriftSpec(position=3_000, to_variant=3),))
    result = run_trial(pending, control=ScriptedControl({6: [{"type": "inject_drift", "to_variant": 1}]}))
    assert any(e["type"] == "command_rejected" for e in result.events)


def test_shared_controller_halves_features_per_instance_under_tiny_budget():
    tiny = ProfileConfig(
        name="tiny", simulated=True, placeholder=True,
        budgets=ResourceBudgets(compute_share=0.001, nominal_rate=1_000, allow_background=False,
                                max_update_stride=4, down_blocks=1),
    )
    result = run_trial(config(length=4_000).model_copy(update={"profile": tiny}))
    changes = [e for e in result.events if e["type"] == "config_changed" and e["method"] == "adaptive"]
    assert not [c for c in changes if c["field"] == "update_stride"]
    assert all(c["new"] == max(1, c["old"] // 2) for c in changes if c["field"] == "n_features")
    assert any(c["field"] == "n_features" for c in changes)
    assert any(e["type"] == "controller_action" and e["action"].startswith("R3_") for e in result.events)
    assert result.timing["timing_dependent_behaviour"] is True
    assert result.pipelines["adaptive"].detector is not None


def test_standard_profile_uses_default_shared_controller():
    plain = run_trial(config(length=1_500))
    explicit = run_trial(config(length=1_500).model_copy(update={"profile": STANDARD}))
    assert plain.summaries["adaptive"]["predictions_sha256"] == explicit.summaries["adaptive"]["predictions_sha256"]
    assert plain.timing["timing_dependent_behaviour"] is True


def test_experiment_expands_into_trials_with_unique_ids():
    exp = ExperimentConfig(name="x", base=config(), profiles=(STANDARD, EDGE_SIM), rates=(None, 500.0), seeds=(1, 2))
    ids = [trial_id for trial_id, _ in exp.trials()]
    assert len(ids) == 2 * 2 * 2 * 2 and len(set(ids)) == len(ids)


def test_run_experiment_writes_a_complete_bundle(tmp_path):
    exp = ExperimentConfig(name="bundle test", base=config(length=1_500, drifts=(DriftSpec(position=900, to_variant=3),)))
    manifest = run_experiment(exp, root=tmp_path)
    assert manifest["status"] == "completed" and len(manifest["trials"]) == 2
    folder = tmp_path / manifest["id"]
    for trial in manifest["trials"]:
        tdir = folder / "trials" / trial["trial_id"]
        for name in ("summary.json", "blocks.csv", "engine_blocks.csv", "events.jsonl", "outcomes.csv.gz"):
            assert (tdir / name).exists(), name
        with gzip.open(tdir / "outcomes.csv.gz", "rt") as f:
            rows = list(csv.reader(f))
        assert len(rows) == 1 + 1_500
        blocks = load_blocks(manifest["id"], trial["trial_id"], root=tmp_path)
        assert sum(b["n"] for b in blocks) == 1_500
        assert load_events(manifest["id"], trial["trial_id"], root=tmp_path)
        series = windowed_scores(blocks, 500)
        assert len(series["x"]) == len(blocks)
    assert json.loads((folder / "manifest.json").read_text())["environment"]["cpu"]
    assert (tmp_path / "index.csv").exists()
    assert list_experiments(root=tmp_path)[0]["id"] == manifest["id"]


def test_ids_are_path_safe():
    from adaptiveml.results import check_id

    with pytest.raises(ValueError):
        check_id("../etc")
