"""AdaptiveML Studio HTTP API: REST for control and results, Server-Sent Events for live updates.

Run from backend/:  .venv/bin/uvicorn adaptiveml.api.app:app --port 8000
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import io
import json
import os
import platform
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from adaptiveml.api.jobs import ExperimentJobs
from adaptiveml.api.live import Hub, LiveRunManager
from adaptiveml.config import ExperimentConfig, TrialConfig
from adaptiveml.config.profiles import BUILTIN_PROFILES
from adaptiveml.experiments.run import resolve_profiles
from adaptiveml.results import (
    REPO_ROOT,
    experiment_path,
    list_experiments,
    load_blocks,
    load_events,
    load_manifest,
    load_trial_summary,
    windowed_scores,
)
from adaptiveml.stream.sea import SEA_THRESHOLDS, label_flip_fraction

PRESETS_DIR = Path(__file__).resolve().parents[2] / "presets"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
TRACEABILITY = REPO_ROOT / "docs" / "traceability.yaml"

hub = Hub()
live = LiveRunManager(hub)
jobs = ExperimentJobs(hub.publish)


@asynccontextmanager
async def lifespan(_: FastAPI):
    os.environ.setdefault("PYTHONHASHSEED", "0")
    hub.loop = asyncio.get_running_loop()
    yield
    live.shutdown()


app = FastAPI(title="AdaptiveML Studio API", version="0.1.0", lifespan=lifespan)


def _load_presets(kind: str) -> dict[str, dict]:
    presets = {}
    for path in sorted((PRESETS_DIR / kind).glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        presets[path.stem] = data
    return presets


def _validation_error(exc: ValidationError) -> HTTPException:
    return HTTPException(422, [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()])


def _trial_config(body: dict) -> tuple[TrialConfig, str]:
    if "preset" in body:
        preset = _load_presets("live").get(body["preset"])
        if preset is None:
            raise HTTPException(404, f"unknown live preset: {body['preset']}")
        data, name = dict(preset["config"]), preset["name"]
        if body.get("profile"):
            data["profile"] = BUILTIN_PROFILES[body["profile"]].model_dump()
    else:
        data, name = body.get("config", {}), body.get("name") or "custom live run"
    if isinstance(data.get("profile"), str):
        data = dict(data, profile=BUILTIN_PROFILES[data["profile"]].model_dump())
    try:
        return TrialConfig.model_validate(data), name
    except ValidationError as exc:
        raise _validation_error(exc) from exc


def _experiment_config(body: dict) -> ExperimentConfig:
    if "preset" in body:
        preset = _load_presets("experiments").get(body["preset"])
        if preset is None:
            raise HTTPException(404, f"unknown experiment preset: {body['preset']}")
        data = preset["config"]
    else:
        data = body.get("config", {})
    try:
        return ExperimentConfig.model_validate(resolve_profiles(data))
    except ValidationError as exc:
        raise _validation_error(exc) from exc


def _guard_idle(for_live: bool) -> None:
    if live.active:
        raise HTTPException(409, "a live run is in progress; stop it first (runs never share the CPU)")
    if jobs.active:
        raise HTTPException(409, "an experiment is running; wait for it or stop it (runs never share the CPU)")


# ---------------------------------------------------------------- meta
@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "python": platform.python_version(),
        "river": importlib.metadata.version("river"),
        "live_active": live.active,
        "experiment_active": jobs.active,
    }


@app.get("/api/presets")
def presets() -> dict:
    return {"live": _load_presets("live"), "experiments": _load_presets("experiments")}


@app.get("/api/profiles")
def profiles() -> dict:
    return {name: p.model_dump() for name, p in BUILTIN_PROFILES.items()}


@app.get("/api/scenarios")
def scenarios() -> dict:
    variants = sorted(SEA_THRESHOLDS)
    return {
        "sea": {
            "thresholds": {str(v): SEA_THRESHOLDS[v] for v in variants},
            "label_flip_fraction": {f"{a}->{b}": label_flip_fraction(a, b) for a in variants for b in variants if a != b},
        }
    }


@app.post("/api/config/validate")
def validate(body: dict = Body(...)) -> dict:
    if body.get("kind") == "experiment":
        exp = _experiment_config(body)
        return {"valid": True, "trials": len(exp.trials()), "config": exp.model_dump(mode="json")}
    cfg, _ = _trial_config(body)
    return {"valid": True, "config": cfg.model_dump(mode="json")}


@app.get("/api/method/traceability")
def traceability() -> dict:
    return yaml.safe_load(TRACEABILITY.read_text()) if TRACEABILITY.exists() else {"components": []}


# ---------------------------------------------------------------- live
@app.post("/api/live")
def start_live(body: dict = Body(...)) -> dict:
    cfg, name = _trial_config(body)
    _guard_idle(for_live=True)
    return live.start(cfg, name)


@app.post("/api/live/{command}")
def live_command(command: str, body: dict | None = Body(None)) -> dict:
    kinds = {"pause": "pause", "resume": "resume", "stop": "stop", "inject-drift": "inject_drift"}
    if command not in kinds:
        raise HTTPException(404, f"unknown command: {command}")
    message = {"type": kinds[command], **(body or {})}
    try:
        live.command(message)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"sent": message}


@app.get("/api/live/state")
def live_state() -> dict:
    return live.snapshot() or {"active": False}


@app.get("/api/live/stream")
async def live_stream(request: Request) -> StreamingResponse:
    q = hub.subscribe()

    async def events():
        try:
            yield f"event: hello\ndata: {json.dumps({'seq': hub.seq})}\n\n"
            while not await request.is_disconnected():
                try:
                    message = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if message is None:  # dropped as too slow: the client reconnects and resyncs
                    break
                yield f"id: {message['seq']}\nevent: {message['type']}\ndata: {json.dumps(message, default=str)}\n\n"
        finally:
            hub.unsubscribe(q)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------- experiments
@app.post("/api/experiments")
def start_experiment(body: dict = Body(...)) -> dict:
    exp = _experiment_config(body)
    _guard_idle(for_live=False)
    jobs.start(exp)
    return {"started": exp.name, "trials": len(exp.trials())}


@app.get("/api/experiments/job")
def experiment_job() -> dict:
    return {"active": jobs.active, "progress": jobs.progress}


@app.post("/api/experiments/job/stop")
def stop_experiment() -> dict:
    jobs.stop()
    return {"stopping": jobs.active}


@app.get("/api/experiments")
def experiments() -> list[dict]:
    return [
        {k: m.get(k) for k in ("id", "kind", "name", "status", "created_utc", "finished_utc", "provenance", "config_hash", "reproducibility")}
        | {"trials": [{k: t[k] for k in ("trial_id", "profile", "rate", "seed", "methods", "scenario")} for t in m["trials"]]}
        for m in list_experiments()
    ]


def _safe(call, *args):
    try:
        return call(*args)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, "not found") from exc


@app.get("/api/experiments/{experiment_id}")
def experiment(experiment_id: str) -> dict:
    return _safe(load_manifest, experiment_id)


@app.get("/api/experiments/{experiment_id}/trials/{trial_id}/summary")
def trial_summary(experiment_id: str, trial_id: str) -> dict:
    return _safe(load_trial_summary, experiment_id, trial_id)


@app.get("/api/experiments/{experiment_id}/trials/{trial_id}/events")
def trial_events(experiment_id: str, trial_id: str) -> list[dict]:
    return _safe(load_events, experiment_id, trial_id)


@app.get("/api/experiments/{experiment_id}/trials/{trial_id}/series")
def trial_series(experiment_id: str, trial_id: str, window: int = 500, max_points: int = 2_000) -> dict:
    """Per method: windowed accuracy/F1 and per-block cost series, aggregated into ≤ max_points buckets
    (latency p95 keeps the bucket maximum so spikes survive)."""
    blocks = _safe(load_blocks, experiment_id, trial_id)
    out = {}
    for method in sorted({b["method"] for b in blocks}):
        rows = [b for b in blocks if b["method"] == method]
        scores = windowed_scores(rows, window)
        step = max(1, -(-len(rows) // max_points))
        series = {k: [] for k in ("x", "accuracy", "f1", "service_mean_us", "service_p95_us", "model_size_kb",
                                  "n_features", "update_stride", "model_version")}
        stages = {k[:-8]: [] for k in rows[0] if k.endswith("_mean_ns") and k != "service_mean_ns"}
        for lo in range(0, len(rows), step):
            chunk, end = rows[lo:lo + step], min(lo + step, len(rows)) - 1
            series["x"].append(scores["x"][end])
            series["accuracy"].append(scores["accuracy"][end])
            series["f1"].append(scores["f1"][end])
            series["service_mean_us"].append(sum(b["service_mean_ns"] for b in chunk) / len(chunk) / 1e3)
            series["service_p95_us"].append(max(b["service_p95_ns"] for b in chunk) / 1e3)
            size = chunk[-1].get("model_size_bytes")
            series["model_size_kb"].append(None if size is None else size / 1024)
            for key in ("n_features", "update_stride", "model_version"):
                series[key].append(chunk[-1].get(key))
            for stage in stages:
                stages[stage].append(sum(b[f"{stage}_mean_ns"] for b in chunk) / len(chunk) / 1e3)
        out[method] = series | {"stage_mean_us": stages}
    return {"window": window, "methods": out}


@app.post("/api/experiments/{experiment_id}/rerun")
def rerun(experiment_id: str) -> dict:
    _safe(load_manifest, experiment_id)
    _guard_idle(for_live=False)
    jobs.rerun(experiment_id)
    return {"rerun_of": experiment_id}


@app.get("/api/experiments/{experiment_id}/export")
def export(experiment_id: str) -> StreamingResponse:
    folder = _safe(experiment_path, experiment_id)
    if not folder.is_dir():
        raise HTTPException(404, "not found")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zf.write(path, Path(experiment_id) / path.relative_to(folder))
    buffer.seek(0)
    return StreamingResponse(
        buffer, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{experiment_id}.zip"'}
    )


# ---------------------------------------------------------------- frontend (built bundle, if present)
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        # An unmatched /api path is a client error, not a page: never answer it with the SPA shell.
        if path.startswith("api/") or path == "api":
            raise HTTPException(404, "not found")
        return FileResponse(FRONTEND_DIST / "index.html")
