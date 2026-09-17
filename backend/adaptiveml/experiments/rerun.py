"""Re-run an existing experiment or live run from its resolved configs and check reproducibility.

Every trial is re-run in a fresh process at max speed (the stream rate does not change predictions,
by design and by test). Predictions are compared by hash; timings are expected to differ. Trials that
ran under a measured-time resource budget are flagged, since their behaviour may legitimately differ.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from adaptiveml.config import TrialConfig
from adaptiveml.experiments.runner import run_isolated
from adaptiveml.results import ExperimentBundle, load_manifest, load_trial_summary


def rerun_experiment(
    original_id: str,
    *,
    root: Path | None = None,
    on_progress: Callable[[dict], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict:
    original = load_manifest(original_id, root)
    trials = []
    for entry in original["trials"]:
        summary = load_trial_summary(original_id, entry["trial_id"], root)
        cfg = TrialConfig.model_validate(summary["config"])
        cfg = cfg.model_copy(update={"stream": cfg.stream.model_copy(update={"rate": None})})
        trials.append((entry, cfg))

    payload = {"rerun_of": original_id, "trials": {e["trial_id"]: c.model_dump(mode="json") for e, c in trials}}
    bundle = ExperimentBundle("rerun", f"rerun of {original['name']}", payload, root=root)
    compared, status = [], "completed"
    for k, (entry, cfg) in enumerate(trials):
        if should_stop is not None and should_stop():
            status = "stopped"
            break
        if on_progress is not None:
            on_progress({"experiment_id": bundle.id, "done": k, "total": len(trials), "trial": entry["trial_id"]})
        (result,) = run_isolated([cfg], [bundle.trial_dir(entry["trial_id"])])
        bundle.record_trial(entry["trial_id"], result)
        before = {m: s["predictions_sha256"] for m, s in entry["methods"].items()}
        after = {m: s["predictions_sha256"] for m, s in result["summaries"].items()}
        compared.append({
            "trial_id": entry["trial_id"],
            "identical_predictions": before == after,
            "timing_dependent": bool(entry["timing"].get("timing_dependent_behaviour")),
        })
    manifest = bundle.finish(status)
    manifest["reproducibility"] = {
        "rerun_of": original_id,
        "trials_compared": len(compared),
        "identical": sum(c["identical_predictions"] for c in compared),
        "per_trial": compared,
        "note": "Re-run at max speed in fresh processes. Timings are expected to differ; predictions should be "
        "identical unless a measured-time resource budget made behaviour timing-dependent.",
    }
    (bundle.dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    if on_progress is not None:
        on_progress({"experiment_id": bundle.id, "done": len(compared), "total": len(trials), "trial": None})
    return manifest
