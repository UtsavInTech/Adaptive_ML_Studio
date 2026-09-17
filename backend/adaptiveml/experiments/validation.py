"""Check 4b — held-out validation of the recommended demo scenario (pre-registered).

Registered on 2026-09-11, before any held-out run, from docs/stage4_feasibility.md §5.
The scenario, seeds and target are fixed below, and nothing is tuned on these results. The
original check-4 FAIL (results/feasibility/20260911-233051) stays permanently recorded; this check
concerns a different, explicitly chosen configuration.

Run from backend/:  .venv/bin/python -m adaptiveml.experiments.validation
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

from adaptiveml.config import DetectorConfig
from adaptiveml.experiments.environment import capture_environment
from adaptiveml.experiments.runner import RESULTS_DIR, run_isolated, sea_config

# ---------------------------------------------------------------- pre-registration (do not edit after running)
SEEDS = tuple(range(11, 31))  # held out: seeds 1–10 were used to choose the configuration
DRIFT_AT = 10_000
LENGTH = 16_000
NOISE = 0.05
FROM_VARIANT, TO_VARIANT = 0, 3  # medium intensity, 13.1 % label-flip fraction
WARMUP = 1_000
DETECTION_WINDOW = 2_000
TARGET_DETECTED = 18  # ≥ 90 % of 20 seeds
TARGET = f"drift detected within {DETECTION_WINDOW:,} samples of the true drift in ≥ {TARGET_DETECTED} of {len(SEEDS)} held-out seeds"
REPORTED_WITHOUT_BAR = (
    "detection-delay distribution; false alarms; pre/post-drift accuracy and F1; adaptation success/failure; "
    "prediction reproducibility (second isolated run per seed); throughput and latency"
)
assert DetectorConfig().delta_drift == 0.002, "the registered configuration uses River's default ADWIN δ"


def _config(seed: int):
    cfg = sea_config(("static", "adaptive"), seed, length=LENGTH, drift_at=DRIFT_AT, to_variant=TO_VARIANT, noise=NOISE)
    assert cfg.stream.initial_variant == FROM_VARIANT and cfg.evaluation.warmup == WARMUP
    return cfg


# ---------------------------------------------------------------- analysis
def _quantiles(values: list[float]) -> dict | None:
    if not values:
        return None
    ordered = sorted(values)
    q = statistics.quantiles(ordered, n=4, method="inclusive") if len(ordered) > 1 else [ordered[0]] * 3
    return {"min": ordered[0], "p25": q[0], "median": q[1], "p75": q[2], "max": ordered[-1], "n": len(ordered)}


def _spread(values: list) -> dict | None:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {"median": statistics.median(values), "min": min(values), "max": max(values)}


def _per_seed(seed: int, run: dict) -> dict:
    events = [e for e in run["events"] if e["method"] == "adaptive"]
    detections = [e["i"] for e in events if e["type"] == "drift_detected" and e["error_increased"]]
    first = next((i for i in detections if i >= DRIFT_AT), None)
    completed = [e for e in events if e["type"] == "adaptation_completed"]
    first_after = next((e for e in completed if e["i"] >= DRIFT_AT), None)
    after_completion = first_after["i"] if first_after else None
    segments = {}
    for method in ("static", "adaptive"):
        s = run["summaries"][method]
        ref = s["stability_reference"]
        segments[method] = {
            "overall_after_warmup": {k: s["scores_after_warmup"][k] for k in ("accuracy", "f1")},
            "pre_drift": ref["pre_drift"],
            "post_drift_early": ref["post_drift_early"],
            "post_drift_late": ref["post_drift_late"],
            "post_adaptation": ref["post_adaptation"],
            "min_windowed_accuracy": ref["min_windowed_accuracy"],
        }
    timing = run["timing"]
    return {
        "seed": seed,
        "detection_delay": None if first is None else first - DRIFT_AT,
        "false_alarms_before_drift": [i for i in detections if WARMUP <= i < DRIFT_AT],
        "warnings_before_drift": sum(1 for e in events if e["type"] == "background_started" and e["i"] < DRIFT_AT),
        "drift_signals_ignored": sum(1 for e in events if e["type"] == "drift_ignored"),
        "adaptations_completed": [[e["i"], e["action"], e["trained_on"], e["samples_after_detection"]] for e in completed],
        "adaptations_before_drift": sum(1 for e in completed if e["i"] < DRIFT_AT),
        "adaptations_failed": sum(1 for e in events if e["type"] == "adaptation_failed"),
        "detections_after_adaptation": sum(1 for i in detections if after_completion is not None and i > after_completion),
        "segments": segments,
        "predictions_sha256": {m: run["summaries"][m]["predictions_sha256"] for m in ("static", "adaptive")},
        "timing": {
            "engine_throughput_per_s": timing["engine_throughput_per_s"],
            "monitor_share_of_total": timing["monitor_share_of_total"],
            "latency_us": {m: run["summaries"][m]["latency_us"] for m in ("static", "adaptive")},
        },
    }


def run_validation() -> dict:
    configs = [_config(seed) for seed in SEEDS]
    first_pass = run_isolated(configs)
    second_pass = run_isolated(configs)  # reproducibility: fresh processes, same configs
    rows = [_per_seed(seed, run) for seed, run in zip(SEEDS, first_pass)]
    for row, rerun in zip(rows, second_pass):
        row["reproduced"] = all(
            row["predictions_sha256"][m] == rerun["summaries"][m]["predictions_sha256"] for m in ("static", "adaptive")
        )

    delays = [r["detection_delay"] for r in rows if r["detection_delay"] is not None]
    detected = sum(1 for d in delays if d <= DETECTION_WINDOW)

    def segment(method: str, name: str, metric: str):
        return _spread([(r["segments"][method][name] or {}).get(metric) for r in rows])

    accuracy = {
        method: {
            name: {"accuracy": segment(method, name, "accuracy"), "f1": segment(method, name, "f1")}
            for name in ("pre_drift", "post_drift_early", "post_drift_late", "post_adaptation")
        }
        | {
            "overall_after_warmup": {
                "accuracy": _spread([r["segments"][method]["overall_after_warmup"]["accuracy"] for r in rows]),
                "f1": _spread([r["segments"][method]["overall_after_warmup"]["f1"] for r in rows]),
            },
            "min_windowed_accuracy": _spread([r["segments"][method]["min_windowed_accuracy"] for r in rows]),
        }
        for method in ("static", "adaptive")
    }
    lat = lambda m, k: _spread([r["timing"]["latency_us"][m][k] for r in rows])  # noqa: E731
    return {
        "registration": {
            "seeds": list(SEEDS),
            "scenario": f"SEA {FROM_VARIANT}→{TO_VARIANT} abrupt, noise {NOISE}, drift at {DRIFT_AT:,}, length {LENGTH:,}, warm-up {WARMUP:,}",
            "detector": "ADWIN, River default δ = 0.002 (warning δ 0.01, clock 32)",
            "target": TARGET,
            "reported_without_bar": REPORTED_WITHOUT_BAR,
        },
        "environment": capture_environment(),
        "passed": detected >= TARGET_DETECTED,
        "detection": {
            "detected_within_window": detected,
            "detected_at_all": len(delays),
            "seeds": len(SEEDS),
            "delay_distribution": _quantiles(delays),
            "delays_by_seed": {r["seed"]: r["detection_delay"] for r in rows},
        },
        "false_alarms": {
            "error_increase_detections_before_drift": sum(len(r["false_alarms_before_drift"]) for r in rows),
            "seeds_with_false_alarm": sum(1 for r in rows if r["false_alarms_before_drift"]),
            "warnings_before_drift": sum(r["warnings_before_drift"] for r in rows),
            "adaptations_before_drift": sum(r["adaptations_before_drift"] for r in rows),
            "detections_after_adaptation": sum(r["detections_after_adaptation"] for r in rows),
            "drift_signals_ignored": sum(r["drift_signals_ignored"] for r in rows),
        },
        "adaptation": {
            "seeds_with_completed_adaptation_after_drift": sum(
                1 for r in rows if any(a[0] >= DRIFT_AT for a in r["adaptations_completed"])
            ),
            "failed": sum(r["adaptations_failed"] for r in rows),
            "actions": sorted({a[1] for r in rows for a in r["adaptations_completed"]}),
            "samples_from_detection_to_promotion": _spread(
                [next((a[3] for a in r["adaptations_completed"] if a[0] >= DRIFT_AT), None) for r in rows]
            ),
        },
        "accuracy_f1": accuracy,
        "reproducibility": {"identical_predictions": sum(1 for r in rows if r["reproduced"]), "seeds": len(SEEDS)},
        "performance": {
            "engine_throughput_per_s": _spread([r["timing"]["engine_throughput_per_s"] for r in rows]),
            "monitor_share_of_total": _spread([r["timing"]["monitor_share_of_total"] for r in rows]),
            "latency_us": {m: {k: lat(m, k) for k in ("mean", "p50", "p95", "p99", "max")} for m in ("static", "adaptive")},
        },
        "per_seed": rows,
    }


# ---------------------------------------------------------------- report
def _f(v, d=3):
    return "—" if v is None else f"{v:,.{d}f}" if isinstance(v, float) else f"{v:,}"


def _sp(s, d=3):
    return "—" if s is None else f"{_f(s['median'], d)} [{_f(s['min'], d)} – {_f(s['max'], d)}]"


def to_markdown(r: dict) -> str:
    reg, det, fa, ad = r["registration"], r["detection"], r["false_alarms"], r["adaptation"]
    dist = det["delay_distribution"] or {}
    env = r["environment"]
    lines = [
        "# Check 4b — held-out validation of the demo scenario (pre-registered)",
        "",
        f"- Scenario: {reg['scenario']}; detector: {reg['detector']}; seeds {reg['seeds'][0]}–{reg['seeds'][-1]} (held out)",
        f"- Target (registered before running): {reg['target']}",
        f"- Measured on: {env['cpu']}, {env['ram_gb']} GB, power: {env['power_source']}; Python {env['python']}, river {env['packages']['river']}",
        f"- **Result: {'PASS' if r['passed'] else 'FAIL'} — {det['detected_within_window']}/{det['seeds']} detected within 2,000 samples**",
        "- The original check-4 configuration (noise 0.1, drift at 5,000) remains recorded as FAIL (1/10).",
        "",
        "## 1–2. Detection",
        "",
        f"- Detected within 2,000 samples: {det['detected_within_window']}/{det['seeds']}; detected at all: {det['detected_at_all']}/{det['seeds']}",
        f"- Delay (samples): min {_f(dist.get('min'))} · p25 {_f(dist.get('p25'), 0)} · median {_f(dist.get('median'), 0)} · "
        f"p75 {_f(dist.get('p75'), 0)} · max {_f(dist.get('max'))}",
        f"- By seed: {det['delays_by_seed']}",
        "",
        "## 3. False alarms",
        "",
        f"- Error-increase detections before the drift (after warm-up): {fa['error_increase_detections_before_drift']} "
        f"({fa['seeds_with_false_alarm']}/{det['seeds']} seeds)",
        f"- Warnings (replacement model started) before the drift: {fa['warnings_before_drift']}; adaptations before the drift: {fa['adaptations_before_drift']}",
        f"- Detections after the post-drift adaptation: {fa['detections_after_adaptation']}; drift signals ignored by policy: {fa['drift_signals_ignored']}",
        "",
        "## 4. Accuracy / F1 — median [min – max] across seeds",
        "",
        "| Segment | Static accuracy | Static F1 | Adaptive accuracy | Adaptive F1 |",
        "|---|---|---|---|---|",
    ]
    acc = r["accuracy_f1"]
    for name, label in (
        ("pre_drift", "Pre-drift [9,000, 10,000)"),
        ("post_drift_early", "Post-drift early [10,000, 11,000)"),
        ("post_drift_late", "Post-drift late [12,000, 13,000)"),
        ("post_adaptation", "Post-adaptation (1,000 samples after promotion)"),
        ("overall_after_warmup", "Whole stream after warm-up"),
    ):
        lines.append(
            f"| {label} | {_sp(acc['static'][name]['accuracy'])} | {_sp(acc['static'][name]['f1'])} | "
            f"{_sp(acc['adaptive'][name]['accuracy'])} | {_sp(acc['adaptive'][name]['f1'])} |"
        )
    lines += [
        f"| Min windowed accuracy (500-sample window) | {_sp(acc['static']['min_windowed_accuracy'])} | — | {_sp(acc['adaptive']['min_windowed_accuracy'])} | — |",
        "",
        "Segments are reference computations (docs/architecture.md §4.8); interpretation belongs to the research workstream.",
        "",
        "## 5. Adaptation",
        "",
        f"- Seeds with a completed adaptation after the drift: {ad['seeds_with_completed_adaptation_after_drift']}/{det['seeds']}; failed adaptations: {ad['failed']}; actions used: {ad['actions']}",
        f"- Samples from detection to promotion: {_sp(ad['samples_from_detection_to_promotion'], 0)}",
        "",
        "## 6. Reproducibility",
        "",
        f"- Identical predictions (static and adaptive) in a second isolated run: {r['reproducibility']['identical_predictions']}/{r['reproducibility']['seeds']} seeds",
        "",
        "## 7. Throughput / latency (static + adaptive in one process, max speed, isolated trials)",
        "",
        f"- Engine throughput (samples/s): {_sp(r['performance']['engine_throughput_per_s'], 0)}",
        f"- Monitoring share of engine time: {_sp(r['performance']['monitor_share_of_total'], 3)}",
        "",
        "| Method | mean µs | p50 | p95 | p99 | max |",
        "|---|---|---|---|---|---|",
    ]
    for m in ("static", "adaptive"):
        l = r["performance"]["latency_us"][m]
        lines.append(f"| {m} | {_sp(l['mean'], 1)} | {_sp(l['p50'], 1)} | {_sp(l['p95'], 1)} | {_sp(l['p99'], 1)} | {_sp(l['max'], 0)} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "validation")
    args = parser.parse_args()
    report = run_validation()
    out = args.out / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "check4b.json").write_text(json.dumps(report, indent=2, default=str))
    md = to_markdown(report)
    (out / "check4b.md").write_text(md)
    print(md)
    print(f"\nWritten to {out}")


if __name__ == "__main__":
    main()
