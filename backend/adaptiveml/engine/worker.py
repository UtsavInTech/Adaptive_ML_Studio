"""Live-run worker: runs one trial in its own process and streams bounded, aggregated updates.

The ML loop never waits on the UI. Updates go through a bounded queue: closed blocks are batched to
≈4 Hz and dropped (counted) if the consumer falls behind — the result bundle still has every block.
Status and events are rare and are never dropped. Extras for the UI (data snapshot, feature ranking,
detector state) are built at 1 Hz; their cost is inside the measured callback time.
"""

from __future__ import annotations

import queue
import time
import traceback

from adaptiveml.config import TrialConfig

SNAPSHOT_INTERVAL_S = 0.25
EXTRAS_INTERVAL_S = 1.0
RECENT_SAMPLES = 300


class QueueControl:
    def __init__(self, commands):
        self._commands = commands

    def poll(self) -> list[dict]:
        out = []
        while True:
            try:
                out.append(self._commands.get_nowait())
            except queue.Empty:
                return out


class _Publisher:
    def __init__(self, out):
        self._out = out
        self.dropped = 0

    def put(self, message: dict, *, droppable: bool) -> None:
        try:
            if droppable:
                self._out.put_nowait(message)
            else:
                self._out.put(message, timeout=5)
        except queue.Full:
            self.dropped += 1


def build_extras(ctx) -> dict:
    scenario = ctx.scenario
    fx, fy = scenario.feature_names[:2]
    points = [[round(x[fx], 3), round(x[fy], 3), int(bool(y))] for x, y in list(ctx.recent or ())]
    methods = {}
    for p in ctx.pipelines:
        info = {
            "model_version": p.active.version,
            "features": list(p.active.features),
            "ranking": [[f, round(w, 4)] for f, w in p.selector.ranking()],
            "update_stride": p.update_stride,
            "adapting": p.adaptation_in_progress,
            "replacement_trained": p.background.trained_on if p.background is not None else None,
            "learning": p.learning,
        }
        if p.detector is not None:
            info["detector"] = {"width": p.detector.width, "error_estimate": round(p.detector.estimation, 5)}
        governor = ctx.governors.get(p.name)
        if governor is not None:
            info["governor"] = {"constrained": governor.constrained, "budget_us": round(governor.budget_ns / 1e3, 2)}
        methods[p.name] = info
    variant = scenario.current_variant
    return {
        "type": "extras",
        "sample": scenario.cursor + 1,
        "concept": {"variant": variant, "threshold": scenario.info["thresholds"].get(str(variant))},
        "axes": [fx, fy],
        "points": points,
        "methods": methods,
    }


def live_worker(cfg_json: str, name: str, out, commands) -> None:
    from adaptiveml.engine import run_trial
    from adaptiveml.results import ExperimentBundle, utc_now, write_trial

    publisher = _Publisher(out)
    cfg = TrialConfig.model_validate_json(cfg_json)
    started = utc_now()
    holder: dict = {}
    pending_blocks: dict[str, list] = {}
    pending_engine: list[dict] = []
    last = {"snapshot": 0.0, "extras": 0.0}

    def flush(now: float) -> None:
        if pending_engine:
            publisher.put({"type": "blocks", "blocks": dict(pending_blocks), "engine": list(pending_engine)}, droppable=True)
            pending_blocks.clear()
            pending_engine.clear()
        last["snapshot"] = now

    def on_block(index: int, records: dict, engine: dict) -> None:
        for method, record in records.items():
            pending_blocks.setdefault(method, []).append(record)
        pending_engine.append(engine)
        now = time.monotonic()
        if now - last["snapshot"] >= SNAPSHOT_INTERVAL_S:
            flush(now)
        if now - last["extras"] >= EXTRAS_INTERVAL_S and "ctx" in holder:
            last["extras"] = now
            publisher.put(build_extras(holder["ctx"]), droppable=True)

    try:
        result = run_trial(
            cfg,
            on_block=on_block,
            on_events=lambda batch: publisher.put({"type": "events", "events": batch}, droppable=False),
            on_status=lambda status: publisher.put({"type": "status", **status}, droppable=False),
            control=QueueControl(commands),
            keep_recent=RECENT_SAMPLES,
            context_sink=lambda ctx: holder.__setitem__("ctx", ctx),
        )
        flush(time.monotonic())
        publisher.put(build_extras(holder["ctx"]), droppable=True)
        bundle = ExperimentBundle("live", name, result.config.model_dump(mode="json"))
        bundle.created = started
        payload = write_trial(result, bundle.trial_dir("live"))
        bundle.record_trial("live", payload)
        bundle.finish(result.status)
        publisher.put(
            {
                "type": "final",
                "experiment_id": bundle.id,
                "status": result.status,
                "config": payload["config"],
                "summaries": result.summaries,
                "timing": result.timing,
                "dropped_snapshots": publisher.dropped,
            },
            droppable=False,
        )
    except Exception as exc:  # noqa: BLE001 — the server must learn why the run failed
        detail = traceback.format_exc()
        experiment_id = None
        try:
            bundle = ExperimentBundle("live", name, cfg.model_dump(mode="json"))
            bundle.finish("error", error=detail)
            experiment_id = bundle.id
        except Exception:  # noqa: BLE001
            pass
        publisher.put({"type": "error", "message": repr(exc), "traceback": detail, "experiment_id": experiment_id}, droppable=False)
