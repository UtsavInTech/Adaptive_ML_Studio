"""API tests: real worker processes, results written to a temporary folder."""

import os
import time

import pytest
from fastapi.testclient import TestClient

SMALL = {
    "seed": 1,
    "methods": ["static", "adaptive"],
    "stream": {"length": 3_000, "noise": 0.05, "drifts": [{"position": 2_000, "to_variant": 3}]},
    "evaluation": {"warmup": 500, "block_size": 100},
}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["ADAPTIVEML_RESULTS_DIR"] = str(tmp_path_factory.mktemp("results"))
    from adaptiveml.api.app import app

    with TestClient(app) as c:
        yield c
    del os.environ["ADAPTIVEML_RESULTS_DIR"]


def wait_for(check, timeout=90.0, interval=0.2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("timed out")


def finished_state(client):
    return wait_for(lambda: (s := client.get("/api/live/state").json()).get("final") or s.get("error") and s)


def test_meta_endpoints(client):
    assert client.get("/api/health").json()["status"] == "ok"
    presets = client.get("/api/presets").json()
    assert "demo_abrupt" in presets["live"] and "compare_methods" in presets["experiments"]
    profiles = client.get("/api/profiles").json()
    assert profiles["edge_sim"]["simulated"] and profiles["edge_sim"]["placeholder"]
    scenarios = client.get("/api/scenarios").json()["sea"]
    assert scenarios["label_flip_fraction"]["0->3"] == pytest.approx(0.13125)
    assert client.get("/api/method/traceability").json()["components"]


def test_validate_accepts_and_rejects(client):
    assert client.post("/api/config/validate", json={"config": SMALL}).json()["valid"]
    bad = {**SMALL, "stream": {**SMALL["stream"], "drifts": [{"position": 9_000, "to_variant": 3}]}}
    response = client.post("/api/config/validate", json={"config": bad})
    assert response.status_code == 422 and "beyond stream length" in str(response.json())
    assert client.post("/api/config/validate", json={"preset": "nope"}).status_code == 404


def test_live_run_end_to_end(client):
    config = {**SMALL, "stream": {**SMALL["stream"], "rate": 2_000}}
    assert client.post("/api/live", json={"config": config, "name": "api test"}).status_code == 200
    assert client.post("/api/live", json={"config": config}).status_code == 409
    assert client.post("/api/experiments", json={"config": {"name": "blocked", "base": SMALL}}).status_code == 409
    final = finished_state(client)
    state = client.get("/api/live/state").json()
    assert final["status"] == "completed", state.get("error")
    assert set(state["blocks"]) == {"static", "adaptive"} and state["extras"]["points"]
    assert any(e["type"] == "drift_true" for e in state["events"])
    manifest = client.get(f"/api/experiments/{final['experiment_id']}").json()
    assert manifest["kind"] == "live" and manifest["status"] == "completed"
    series = client.get(f"/api/experiments/{final['experiment_id']}/trials/live/series").json()
    assert len(series["methods"]["adaptive"]["x"]) == 30
    export = client.get(f"/api/experiments/{final['experiment_id']}/export")
    assert export.status_code == 200 and export.headers["content-type"] == "application/zip"


def test_live_injection_and_stop(client):
    endless = {**SMALL, "stream": {"length": 60_000, "noise": 0.05, "rate": 3_000}}
    assert client.post("/api/live", json={"config": endless, "name": "commands"}).status_code == 200
    wait_for(lambda: client.get("/api/live/state").json()["status"]["sample"] > 700)
    assert client.post("/api/live/inject-drift", json={"to_variant": 3}).status_code == 200
    wait_for(lambda: any(e["type"] == "drift_scheduled" for e in client.get("/api/live/state").json()["events"]))
    assert client.post("/api/live/stop").status_code == 200
    final = finished_state(client)
    assert final["status"] == "stopped"
    assert len(final["config"]["stream"]["drifts"]) == 1
    assert client.post("/api/live/pause").status_code == 409


def test_experiment_job_and_rerun_reproduce(client):
    assert client.post("/api/experiments", json={"config": {"name": "api experiment", "base": SMALL}}).status_code == 200
    progress = wait_for(lambda: (j := client.get("/api/experiments/job").json())["progress"]["status"] != "running" and j)["progress"]
    assert progress["status"] == "completed"
    manifest = client.get(f"/api/experiments/{progress['experiment_id']}").json()
    assert len(manifest["trials"]) == 2
    assert client.post(f"/api/experiments/{manifest['id']}/rerun").status_code == 200
    rerun = wait_for(lambda: (j := client.get("/api/experiments/job").json())["progress"]["status"] != "running" and j)["progress"]
    reproduced = client.get(f"/api/experiments/{rerun['experiment_id']}").json()["reproducibility"]
    assert reproduced["identical"] == reproduced["trials_compared"] == 2
    listing = client.get("/api/experiments").json()
    assert {m["kind"] for m in listing} >= {"live", "experiment", "rerun"}


def test_ids_are_validated(client):
    assert client.get("/api/experiments/..%2Fsecret").status_code in (400, 404)
    assert client.get("/api/experiments/not-there").status_code == 404
