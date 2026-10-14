"""Shared experiment helpers: the SEA demo configuration, isolated (fresh-process) trial runs and
multi-trial experiments with result bundles.

Isolated trials run one at a time, each in a new spawned process, so timing and memory are never
shared between trials (docs/architecture.md §3.3).
"""

from __future__ import annotations

import os
import queue
import time
import traceback
from collections import deque
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

from adaptiveml.config import (
    CONTROL_SUFFIX, DriftSpec, EvaluationConfig, ExperimentConfig, StreamConfig, TrialConfig,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = REPO_ROOT / "results"


def sea_config(
    methods: tuple[str, ...],
    seed: int,
    *,
    length: int = 12_000,
    drift_at: int = 5_000,
    to_variant: int = 3,
    noise: float = 0.1,
    block_size: int = 100,
) -> TrialConfig:
    return TrialConfig(
        seed=seed,
        methods=methods,
        stream=StreamConfig(length=length, noise=noise, drifts=(DriftSpec(position=drift_at, to_variant=to_variant),)),
        evaluation=EvaluationConfig(block_size=block_size),
    )


def _run_serialised(cfg_json: str, trial_dir: str | None = None) -> dict:
    from adaptiveml.engine import run_trial
    from adaptiveml.results import write_trial

    result = run_trial(TrialConfig.model_validate_json(cfg_json))
    if trial_dir is not None:
        write_trial(result, Path(trial_dir))
    return {
        "config": result.config.model_dump(mode="json"),
        "status": result.status,
        "scenario": result.scenario,
        "summaries": result.summaries,
        "timing": result.timing,
        "events": result.events,
    }


def run_isolated(configs: list[TrialConfig], trial_dirs: list[Path] | None = None) -> list[dict]:
    os.environ.setdefault("PYTHONHASHSEED", "0")  # inherited by spawned workers
    ctx = get_context("spawn")
    results = []
    for k, cfg in enumerate(configs):
        target = None if trial_dirs is None else str(trial_dirs[k])
        with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as pool:
            results.append(pool.submit(_run_serialised, cfg.model_dump_json(), target).result())
    return results


PROGRESS_INTERVAL_S = 0.2  # a running trial reports at most five times a second
RECENT_BLOCKS = 10  # "recent accuracy" covers this many blocks (1,000 rows at the default block size)
FEED_LENGTH = 14


def _run_streaming(cfg_json: str, trial_dir: str | None, out) -> None:
    """Child process: run one trial and say what it is doing while it runs.

    The reports exist so that a person watching an experiment can see it working: rows processed,
    accuracy so far, and the events of the adaptive pipeline. They are sent between blocks, at most
    five times a second; the per-row processing times are measured inside the pipeline and are not
    affected. The cost of sending them is part of the separately reported monitoring time.
    """
    from adaptiveml.engine import run_trial
    from adaptiveml.results import write_trial

    try:
        cfg = TrialConfig.model_validate_json(cfg_json)
        warmup = cfg.evaluation.warmup
        totals: dict[str, list[int]] = {}
        recent: dict[str, deque] = {}
        state: dict = {"sent": 0.0, "lifecycle": "loading", "sample": 0, "methods": {}}
        began = time.monotonic()

        def send() -> None:
            state["sent"] = time.monotonic()
            methods = {}
            for name, info in state["methods"].items():
                tp, fp, tn, fn = totals.get(name, (0, 0, 0, 0))
                scored = tp + fp + tn + fn
                window = recent.get(name, ())
                rows = sum(n for _, n in window)
                methods[name] = info | {
                    "scored": scored,
                    "accuracy": (tp + tn) / scored if scored else None,
                    "precision": tp / (tp + fp) if tp + fp else None,
                    "recent_accuracy": sum(c for c, _ in window) / rows if rows else None,
                }
            out.put({
                "type": "progress", "lifecycle": state["lifecycle"], "sample": state["sample"],
                "total": cfg.stream.length, "elapsed_s": round(time.monotonic() - began, 2), "methods": methods,
            })

        def on_block(index: int, records: dict, engine: dict) -> None:
            for name, block in records.items():
                if block["start"] >= warmup:
                    t = totals.setdefault(name, [0, 0, 0, 0])
                    for k, key in enumerate(("tp", "fp", "tn", "fn")):
                        t[k] += block[key]
                    recent.setdefault(name, deque(maxlen=RECENT_BLOCKS)).append((block["tp"] + block["tn"], block["n"]))
                state["methods"][name] = {
                    "model_version": block["model_version"], "adapting": block["adapting"],
                    "background": block["background"], "learning": block["learning"],
                    "n_features": block["n_features"],
                }
            state["sample"] = engine["start"] + engine["n"]
            if time.monotonic() - state["sent"] >= PROGRESS_INTERVAL_S:
                send()

        def on_status(status: dict) -> None:
            state["lifecycle"], state["sample"] = status["lifecycle"], status["sample"]
            send()

        result = run_trial(
            cfg, on_block=on_block, on_status=on_status,
            on_events=lambda batch: out.put({"type": "events", "events": batch}),
        )
        if trial_dir is not None:
            write_trial(result, Path(trial_dir))
        send()
        out.put({"type": "done", "payload": {
            "config": result.config.model_dump(mode="json"),
            "status": result.status,
            "scenario": result.scenario,
            "summaries": result.summaries,
            "timing": result.timing,
            "events": result.events,
        }})
    except Exception as exc:  # noqa: BLE001 — the parent must learn why the trial failed
        out.put({"type": "error", "message": repr(exc), "traceback": traceback.format_exc()})


def run_isolated_streaming(cfg: TrialConfig, trial_dir: Path | None, on_message: Callable[[dict], None]) -> dict:
    """Run one trial alone in a fresh process, forwarding its progress reports; return its payload."""
    os.environ.setdefault("PYTHONHASHSEED", "0")  # inherited by the spawned worker
    ctx = get_context("spawn")
    out = ctx.Queue()
    target = None if trial_dir is None else str(trial_dir)
    process = ctx.Process(target=_run_streaming, args=(cfg.model_dump_json(), target, out), daemon=True)
    process.start()
    try:
        while True:
            try:
                message = out.get(timeout=0.5)
            except queue.Empty:
                if process.is_alive():
                    continue
                try:  # the process has gone: take anything it managed to send first
                    message = out.get(timeout=0.5)
                except queue.Empty:
                    raise RuntimeError(f"the trial process ended unexpectedly (exit code {process.exitcode})") from None
            if message["type"] == "done":
                return message["payload"]
            if message["type"] == "error":
                raise RuntimeError(f"{message['message']}\n{message['traceback']}")
            on_message(message)
    finally:
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()


def run_experiment(
    exp: ExperimentConfig,
    *,
    root: Path | None = None,
    on_progress: Callable[[dict], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict:
    """Run every trial of an experiment in sequence (fresh process each) and write its bundle."""
    from adaptiveml.results import ExperimentBundle
    from adaptiveml.stream.static import StaticScenario

    if exp.base.stream.scenario == "csv":
        source = StaticScenario(exp.base.stream)
        stream = exp.base.stream.model_copy(update={"dataset_sha256": source.sha256})
        exp = exp.model_copy(update={"base": exp.base.model_copy(update={"stream": stream})})

    bundle = ExperimentBundle("experiment", exp.name, exp.model_dump(mode="json"), root=root)
    trials = exp.trials()
    status, error = "completed", None
    stream, evaluation = exp.base.stream, exp.base.evaluation
    injection = stream.injection
    # What the run is, in the terms a person watching it needs: which data, which change, which windows.
    context = {
        "scenario": stream.scenario,
        "dataset": stream.dataset,
        "length": stream.length,
        "warmup": evaluation.warmup,
        "injection": None if injection is None else injection.model_dump(mode="json") | {"end": injection.end},
        "phases": evaluation.phases.model_dump(),
        "control": exp.control and injection is not None,
    }
    plan = [
        {
            "trial_id": trial_id, "method": cfg.methods[0], "profile": cfg.profile.label, "seed": cfg.seed,
            "control": trial_id.endswith(CONTROL_SUFFIX), "status": "waiting",
            "accuracy": None, "precision": None, "seconds": None, "detections": None, "adaptations": None,
        }
        for trial_id, cfg in trials
    ]
    feed: deque = deque(maxlen=FEED_LENGTH)

    def progress(done: int, trial: str | None, current: dict | None = None) -> None:
        if on_progress is not None:
            on_progress({
                "experiment_id": bundle.id, "done": done, "total": len(trials), "trial": trial,
                "context": context, "plan": plan, "current": current, "feed": list(feed),
            })

    try:
        for k, (trial_id, cfg) in enumerate(trials):
            if should_stop is not None and should_stop():
                status = "stopped"
                break
            entry, method = plan[k], cfg.methods[0]
            entry["status"] = "running"
            progress(k, trial_id, {"lifecycle": "starting", "sample": 0, "total": stream.length, "methods": {}})
            began = time.monotonic()

            def on_message(message: dict, k=k, trial_id=trial_id, entry=entry) -> None:
                if message["type"] == "events":
                    for event in message["events"]:
                        feed.append({"trial_id": trial_id, "control": entry["control"], **event})
                    return
                progress(k, trial_id, {key: message[key] for key in ("lifecycle", "sample", "total", "elapsed_s", "methods")})

            payload = run_isolated_streaming(cfg, bundle.trial_dir(trial_id), on_message)
            bundle.record_trial(trial_id, payload)
            summary = payload["summaries"].get(method)
            entry.update(status="done", seconds=round(time.monotonic() - began, 1))
            if summary is not None:
                entry.update(
                    accuracy=summary["scores_after_warmup"]["accuracy"],
                    precision=summary["scores_after_warmup"]["precision"],
                    detections=summary["drift_detections_error_increase"],
                    adaptations=summary["adaptations"]["count"],
                )
    except Exception as exc:  # noqa: BLE001 — record the failure in the manifest instead of losing the bundle
        status, error = "error", repr(exc).split("\\n")[0][:600]
        for entry in plan:
            if entry["status"] == "running":
                entry["status"] = "failed"
    manifest = bundle.finish(status, error)
    progress(len(bundle.trials), None)
    return manifest
