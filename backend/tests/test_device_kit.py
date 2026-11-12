"""Phase 7 device kit: the device record, the budget rule, and importing a bundle safely."""

import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

from adaptiveml.config import ProfileConfig
from adaptiveml.config.profiles import per_sample_budget_ns
from adaptiveml.experiments import environment
from adaptiveml.results import ExperimentBundle

DEVICE = Path(__file__).resolve().parents[2] / "research_testbed" / "device"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, DEVICE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_on_device = load("run_on_device")
import_bundle = load("import_bundle")


def test_device_model_is_read_from_the_board_and_absent_elsewhere(monkeypatch):
    monkeypatch.setattr(environment, "_read", lambda path: None)
    assert environment.device_model() is None
    assert environment.capture_environment()["device_model"] is None
    monkeypatch.setattr(environment, "_read", lambda path: "Raspberry Pi 4 Model B Rev 1.4" if "model" in path else None)
    env = environment.capture_environment()
    assert env["device_model"] == "Raspberry Pi 4 Model B Rev 1.4"
    assert env["cpu"]  # never empty, so "measured on" always names something


def test_manifest_provenance_names_the_device(tmp_path, monkeypatch):
    monkeypatch.setattr(environment, "_read", lambda path: "Raspberry Pi 5 Model B Rev 1.0" if "model" in path else None)
    manifest = ExperimentBundle("experiment", "x", {}, root=tmp_path).write_manifest("completed")
    assert manifest["provenance"]["device_model"] == "Raspberry Pi 5 Model B Rev 1.0"


def test_device_budgets_keep_the_laptop_tiers_relative_tightness():
    real = {p["name"]: p for p in run_on_device.profiles(800.0, True, "Raspberry Pi 4")}
    small = ProfileConfig.model_validate(real["device_small"])
    micro = ProfileConfig.model_validate(real["device_micro"])
    # 100 and 50 µs against 80.07 µs on the laptop; here against 800 µs.
    assert per_sample_budget_ns(small, None) / 1e3 == pytest.approx(800 * 100 / 80.07)
    assert per_sample_budget_ns(micro, None) / 1e3 == pytest.approx(800 * 50 / 80.07)
    assert small.budgets.latency_deadline_ms == pytest.approx(5 * 800 * 100 / 80.07 / 1e3)
    assert not small.simulated and small.placeholder  # real timings, but budgets set by a rule
    assert micro.budgets.model_memory_mib == 1.0 and not micro.budgets.allow_background


def test_a_rehearsal_is_never_labelled_as_a_device():
    for p in run_on_device.profiles(80.0, False, "a laptop"):
        assert p["simulated"] and "REHEARSAL" in p["label"]


def test_presets_carry_the_device_calibration_to_the_effort_controller():
    cost = {"base_ns": 99_000.0}
    made = run_on_device.presets(run_on_device.SLICES["quick"], [11, 23], cost, ["standard"], "device-x")
    assert made["controllers"]["base"]["controller"]["effort"]["cost"] == cost
    assert made["controllers"]["base"]["methods"] == ["joint", "effort"]
    assert made["references"]["seeds"] == [11, 23]


def bundle(path: Path, files: dict[str, bytes], links: dict[str, str] | None = None) -> Path:
    with tarfile.open(path, "w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.SYMTYPE, target
            tar.addfile(info)
    return path


GOOD = {
    "device-1/experiments/run-a/manifest.json": b'{"id": "run-a"}',
    "device-1/experiments/run-a/trials/t1/outcomes.csv.gz": b"x",
    "device-1/device.json": json.dumps({"name": "Raspberry Pi 4", "real_device": True}).encode(),
    "device-1/summary.md": b"# s\n",
    "device-1/presets/controllers.yaml": b"name: x\n",
}


def test_import_copies_runs_and_extras_and_refuses_a_second_time(tmp_path):
    runs, extras = tmp_path / "runs", tmp_path / "extras"
    tar = bundle(tmp_path / "b.tar.gz", GOOD)
    done = import_bundle.import_bundle(tar, runs, extras)
    assert done == {"tag": "device-1", "runs": ["run-a"], "extras": str(extras.resolve() / "device-1"),
                    "device": "Raspberry Pi 4", "real_device": True}
    assert (runs / "run-a" / "trials" / "t1" / "outcomes.csv.gz").read_bytes() == b"x"
    assert (extras / "device-1" / "presets" / "controllers.yaml").is_file()
    with pytest.raises(ValueError, match="already here"):
        import_bundle.import_bundle(tar, runs, extras)


@pytest.mark.parametrize("extra, links", [
    ({"device-1/experiments/run-a/../../../escape.json": b"{}"}, None),
    ({"/abs/evil.json": b"{}"}, None),
    ({"device-1/experiments/run-a/tool.sh": b"#!/bin/sh"}, None),
    ({"device-1/notes.json": b"{}"}, None),
    ({"other-top/device.json": b"{}"}, None),
    ({}, {"device-1/experiments/run-a/link.json": "/etc/passwd"}),
])
def test_import_refuses_anything_unexpected_and_writes_nothing(tmp_path, extra, links):
    runs, extras = tmp_path / "runs", tmp_path / "extras"
    tar = bundle(tmp_path / "b.tar.gz", {**GOOD, **extra}, links)
    with pytest.raises(ValueError):
        import_bundle.import_bundle(tar, runs, extras)
    assert not runs.exists() and not extras.exists()
    assert not (tmp_path / "escape.json").exists()


def test_import_needs_a_manifest_for_every_run(tmp_path):
    files = {k: v for k, v in GOOD.items() if not k.endswith("manifest.json")}
    with pytest.raises(ValueError, match="manifest"):
        import_bundle.import_bundle(bundle(tmp_path / "b.tar.gz", files), tmp_path / "runs", tmp_path / "extras")
