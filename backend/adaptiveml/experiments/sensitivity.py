"""Detection sensitivity of the error-stream ADWIN detector — exploratory measurement for team decisions.

This is not tuning: no default changes as a result of running it. For every configuration, ten seeds
report how often the adaptive pipeline detects the drift within 2,000 samples, the median delay,
false alarms before the drift, and the late post-drift accuracy. No-drift control streams report the
false-alarm rate on their own. Runs execute in parallel because no timing is measured here.

Run from backend/:  .venv/bin/python -m adaptiveml.experiments.sensitivity
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from multiprocessing import get_context
from pathlib import Path
from statistics import median

from adaptiveml.config import DetectorConfig, DriftSpec, PipelineConfig, StreamConfig, TrialConfig
from adaptiveml.experiments.runner import RESULTS_DIR

SEEDS = range(1, 11)
INTENSITIES = {"medium 0→3 (13.1 %)": (0, 3), "high 2→3 (20.6 %)": (2, 3)}
NOISE = (0.05, 0.1)
DELTAS = (0.002, 0.01)
DRIFT_AT = (5_000, 10_000)
POST_DRIFT = 5_000
WARMUP = 1_000
CONTROL_LENGTH = 15_000


def _trial_config(seed: int, variants: tuple[int, int], noise: float, delta: float, drift_at: int | None) -> TrialConfig:
    start, end = variants
    drifts = () if drift_at is None else (DriftSpec(position=drift_at, to_variant=end),)
    length = CONTROL_LENGTH if drift_at is None else drift_at + POST_DRIFT
    return TrialConfig(
        seed=seed,
        methods=("adaptive",),
        stream=StreamConfig(length=length, noise=noise, initial_variant=start, drifts=drifts),
        pipeline=PipelineConfig(detector=DetectorConfig(delta_drift=delta)),
    )


def _run_one(cfg_json: str) -> dict:
    from adaptiveml.engine import run_trial

    cfg = TrialConfig.model_validate_json(cfg_json)
    r = run_trial(cfg)
    drift = cfg.stream.drifts[0].position if cfg.stream.drifts else None
    alarms = [e["i"] for e in r.events if e["type"] == "drift_detected" and e["error_increased"]]
    first = next((i for i in alarms if drift is not None and i >= drift), None)
    ref = r.summaries["adaptive"]["stability_reference"]
    return {
        "detection_delay": None if first is None else first - drift,
        "false_alarms": [i for i in alarms if WARMUP <= i < (drift if drift is not None else cfg.stream.length)],
        "late_accuracy": None if ref is None else ref["post_drift_late"]["accuracy"],
        "samples_monitored": (drift if drift is not None else cfg.stream.length) - WARMUP,
    }


def run_sensitivity(workers: int = 4) -> dict:
    os.environ.setdefault("PYTHONHASHSEED", "0")
    drift_cells = list(itertools.product(INTENSITIES.items(), NOISE, DELTAS, DRIFT_AT))
    control_cells = list(itertools.product(INTENSITIES.items(), NOISE, DELTAS))
    jobs = []
    for (label, variants), noise, delta, drift_at in drift_cells:
        jobs += [(("drift", label, noise, delta, drift_at), _trial_config(s, variants, noise, delta, drift_at)) for s in SEEDS]
    for (label, variants), noise, delta in control_cells:
        jobs += [(("control", label, noise, delta, None), _trial_config(s, variants, noise, delta, None)) for s in SEEDS]

    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as pool:
        outputs = list(pool.map(_run_one, [cfg.model_dump_json() for _, cfg in jobs]))

    cells: dict[tuple, list[dict]] = {}
    for (key, _), out in zip(jobs, outputs):
        cells.setdefault(key, []).append(out)

    rows = []
    for (kind, label, noise, delta, drift_at), outs in cells.items():
        delays = [o["detection_delay"] for o in outs if o["detection_delay"] is not None]
        alarms = sum(len(o["false_alarms"]) for o in outs)
        monitored = sum(o["samples_monitored"] for o in outs)
        row = {
            "kind": kind,
            "intensity": label,
            "noise": noise,
            "delta_drift": delta,
            "drift_at": drift_at,
            "false_alarms_total": alarms,
            "false_alarms_per_10k_samples": round(alarms / monitored * 10_000, 2),
            "seeds_with_false_alarm": sum(1 for o in outs if o["false_alarms"]),
        }
        if kind == "drift":
            row |= {
                "detected_within_2000": sum(1 for d in delays if d <= 2_000),
                "detected_at_all": len(delays),
                "delay_median": median(delays) if delays else None,
                "late_accuracy_median": median(o["late_accuracy"] for o in outs),
            }
        rows.append(row)
    return {
        "note": "Exploratory sensitivity measurement; defaults are unchanged. Adaptive pipeline only; 10 seeds per cell.",
        "seeds": list(SEEDS),
        "rows": rows,
    }


def to_markdown(report: dict) -> str:
    lines = [
        "# Detection sensitivity (exploratory — defaults unchanged)",
        "",
        report["note"],
        "",
        "## Drift streams",
        "",
        "| Intensity | Noise | δ drift | Drift at | Detected ≤ 2,000 | Detected at all | Median delay | False alarms before drift (seeds) | Late post-drift acc (median) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in (r for r in report["rows"] if r["kind"] == "drift"):
        lines.append(
            f"| {r['intensity']} | {r['noise']} | {r['delta_drift']} | {r['drift_at']:,} | {r['detected_within_2000']}/10 | "
            f"{r['detected_at_all']}/10 | {r['delay_median'] if r['delay_median'] is not None else '—'} | "
            f"{r['false_alarms_total']} ({r['seeds_with_false_alarm']}/10) | {r['late_accuracy_median']:.3f} |"
        )
    lines += [
        "",
        f"## No-drift controls ({CONTROL_LENGTH:,} samples; alarms counted after warm-up)",
        "",
        "| Concept | Noise | δ drift | False alarms | per 10k samples | Seeds with ≥ 1 alarm |",
        "|---|---|---|---|---|---|",
    ]
    for r in (r for r in report["rows"] if r["kind"] == "control"):
        concept = r["intensity"].split(" ")[1].split("→")[0]
        lines.append(
            f"| SEA variant {concept} | {r['noise']} | {r['delta_drift']} | {r['false_alarms_total']} | "
            f"{r['false_alarms_per_10k_samples']} | {r['seeds_with_false_alarm']}/10 |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "sensitivity")
    args = parser.parse_args()
    report = run_sensitivity(args.workers)
    out = args.out / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "sensitivity.json").write_text(json.dumps(report, indent=2))
    md = to_markdown(report)
    (out / "sensitivity.md").write_text(md)
    print(md)
    print(f"\nWritten to {out}")


if __name__ == "__main__":
    main()
