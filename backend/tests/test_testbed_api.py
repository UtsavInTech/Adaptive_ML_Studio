"""Testbed screen API: setup options, reports served only from their folder, and a small testbed run."""

import os
import time

import pytest
from fastapi.testclient import TestClient

from adaptiveml.stream.static import catalog


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["ADAPTIVEML_RESULTS_DIR"] = str(tmp_path_factory.mktemp("results"))
    reports = tmp_path_factory.mktemp("reports")
    os.environ["ADAPTIVEML_REPORTS_DIR"] = str(reports)
    folder = reports / "demo"
    (folder / "figures").mkdir(parents=True)
    (folder / "tables").mkdir()
    (folder / "report.md").write_text("# Demo report\n\nSome text.\n")
    (folder / "figures" / "fig1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (folder / "figures" / "fig1.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (folder / "tables" / "settings.csv").write_text("method,tier,kappa_temporal\njoint,small_sim,0.65\n")
    (folder / "secret.txt").write_text("not served")
    (reports / "no-report-here").mkdir()
    (reports.parent / "outside.csv").write_text("a\n1\n")
    from adaptiveml.api.app import app

    with TestClient(app) as c:
        yield c
    del os.environ["ADAPTIVEML_RESULTS_DIR"]
    del os.environ["ADAPTIVEML_REPORTS_DIR"]


def test_options_describe_tiers_rules_and_methods(client):
    body = client.get("/api/testbed/options").json()
    tiers = {t["name"]: t for t in body["tiers"]}
    assert set(tiers) == {"standard", "small_sim", "micro_sim", "memory_sim"}
    assert not tiers["standard"]["simulated"] and tiers["standard"]["budgets"]["cpu_us_per_row"] is None
    for name in ("small_sim", "micro_sim", "memory_sim"):
        assert tiers[name]["simulated"] and tiers[name]["placeholder"]
    assert tiers["small_sim"]["budgets"]["cpu_us_per_row"] == pytest.approx(100)
    assert tiers["micro_sim"]["budgets"]["cpu_us_per_row"] == pytest.approx(50)
    assert tiers["memory_sim"]["budgets"]["model_memory_mib"] == 0.25
    assert [r["id"] for r in body["rules"]] == ["R1", "R2", "R3", "R4", "R5"]
    assert all(r["said"] for r in body["rules"]) and body["resource_check"]["id"] == "resource_gating"
    methods = {m["id"]: m for m in body["methods"]}
    assert {"no_change", "static", "incremental", "adaptive", "joint", "arf", "srp", "lev_bag"} <= set(methods)
    assert methods["srp"].get("slow") and methods["lev_bag"].get("slow") and not methods["joint"].get("slow")


def test_options_list_only_streaming_datasets_with_their_slices(client):
    datasets = client.get("/api/testbed/options").json()["datasets"]
    streaming = {e["id"] for e in catalog() if e.get("streaming")}
    assert {d["id"] for d in datasets} == streaming
    for d in datasets:
        slices = {s["id"]: s for s in d["slices"]}
        assert slices["week"] == {**slices["week"], "start": 0, "length": d["rows"]}
        assert all(s["start"] + s["length"] <= d["rows"] for s in d["slices"])
        if d["id"] == "cicids2017" and d["schedule"]:
            assert slices["wednesday_dos"]["start"] == 693_702 and slices["wednesday_dos"]["length"] == 300_000
            assert slices["wednesday"]["start"] == d["schedule"]["day_start_rows"]["wednesday"]
            assert slices["monday"]["length"] == slices["tuesday"]["start"]


def test_reports_are_listed_and_parsed(client):
    listed = client.get("/api/testbed/reports").json()
    assert [r["name"] for r in listed] == ["demo"]
    assert listed[0]["title"] == "Demo report" and listed[0]["figures"] == 1 and listed[0]["tables"] == 1
    report = client.get("/api/testbed/reports/demo").json()
    assert report["markdown"].startswith("# Demo report")
    assert report["figures"] == [{"path": "figures/fig1.png", "svg": "figures/fig1.svg"}]
    assert report["tables"] == [{"path": "tables/settings.csv", "columns": ["method", "tier", "kappa_temporal"],
                                 "rows": [["joint", "small_sim", "0.65"]]}]


def test_report_files_are_served_safely(client):
    png = client.get("/api/testbed/reports/demo/files/figures/fig1.png")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert "attachment" not in png.headers.get("content-disposition", "")
    svg = client.get("/api/testbed/reports/demo/files/figures/fig1.svg")
    assert svg.status_code == 200 and svg.headers["content-disposition"].startswith("attachment")
    csv_file = client.get("/api/testbed/reports/demo/files/tables/settings.csv?download=true")
    assert csv_file.status_code == 200 and csv_file.headers["content-disposition"].startswith("attachment")
    assert client.get("/api/testbed/reports/demo/files/report.md").text.startswith("# Demo")
    # Outside the report folder, an unserved type, or not a report at all.
    assert client.get("/api/testbed/reports/demo/files/..%2F..%2Foutside.csv").status_code == 400
    assert client.get("/api/testbed/reports/demo/files/%2Fetc%2Fhosts").status_code == 400
    assert client.get("/api/testbed/reports/demo/files/secret.txt").status_code == 400
    assert client.get("/api/testbed/reports/demo/files/figures/missing.png").status_code == 404
    assert client.get("/api/testbed/reports/..%2F..").status_code in (400, 404)
    assert client.get("/api/testbed/reports/..").status_code in (400, 404)
    assert client.get("/api/testbed/reports/no-report-here").status_code == 404
    assert client.get("/api/testbed/reports/nope/files/report.md").status_code == 404


CICIDS = next((e for e in catalog() if e["id"] == "cicids2017"), None)


@pytest.mark.skipif(not (CICIDS and CICIDS["available"]), reason="CIC-IDS2017 stream not prepared")
def test_small_testbed_experiment_runs_and_reports_stream_scores(client):
    config = {
        "name": "testbed api check",
        "base": {
            "methods": ["no_change", "joint"],
            "stream": {"scenario": "csv", "dataset": "cicids2017", "noise": 0, "start": 693_702, "length": 3_000,
                       "label_delay": 100, "label_coverage": 0.5},
            "evaluation": {"warmup": 500},
            "controller": {"rules": ["R1", "R2", "R3", "R5"], "resource_gating": True},
        },
        "profiles": ["small_sim"],
        "seeds": [11],
    }
    assert client.post("/api/config/validate", json={"kind": "experiment", "config": config}).json()["trials"] == 2
    assert client.post("/api/experiments", json={"config": config}).status_code == 200
    deadline = time.monotonic() + 240
    while (job := client.get("/api/experiments/job").json())["active"] and time.monotonic() < deadline:
        time.sleep(0.5)
    progress = job["progress"]
    assert progress["status"] == "completed", progress
    manifest = client.get(f"/api/experiments/{progress['experiment_id']}").json()
    trial = next(t for t in manifest["trials"] if t["trial_id"].startswith("joint"))
    summary = client.get(f"/api/experiments/{manifest['id']}/trials/{trial['trial_id']}/summary").json()
    joint = summary["summaries"]["joint"]
    assert "kappa_temporal" in joint["stream_scores_after_warmup"]
    assert "C_pre" in joint["cost_terms_us_per_row"]
    assert joint["controller"]["rules"] == ["R1", "R2", "R3", "R5"]
    assert summary["config"]["stream"]["label_delay"] == 100
