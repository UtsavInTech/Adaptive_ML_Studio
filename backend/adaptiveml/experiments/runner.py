"""Shared experiment helpers: the SEA demo configuration, isolated (fresh-process) trial runs and
multi-trial experiments with result bundles.

Isolated trials run one at a time, each in a new spawned process, so timing and memory are never
shared between trials (docs/architecture.md §3.3).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

from adaptiveml.config import DriftSpec, EvaluationConfig, ExperimentConfig, StreamConfig, TrialConfig

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


def run_experiment(
    exp: ExperimentConfig,
    *,
    root: Path | None = None,
    on_progress: Callable[[dict], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict:
    """Run every trial of an experiment in sequence (fresh process each) and write its bundle."""
    from adaptiveml.results import ExperimentBundle

    bundle = ExperimentBundle("experiment", exp.name, exp.model_dump(mode="json"), root=root)
    trials = exp.trials()
    status, error = "completed", None

    def progress(done: int, trial: str | None) -> None:
        if on_progress is not None:
            on_progress({"experiment_id": bundle.id, "done": done, "total": len(trials), "trial": trial})

    try:
        for k, (trial_id, cfg) in enumerate(trials):
            if should_stop is not None and should_stop():
                status = "stopped"
                break
            progress(k, trial_id)
            (payload,) = run_isolated([cfg], [bundle.trial_dir(trial_id)])
            bundle.record_trial(trial_id, payload)
    except Exception as exc:  # noqa: BLE001 — record the failure in the manifest instead of losing the bundle
        status, error = "error", repr(exc)
    manifest = bundle.finish(status, error)
    progress(len(bundle.trials), None)
    return manifest
