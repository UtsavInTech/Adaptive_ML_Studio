"""Raw-engine benchmark: no pacing, no IPC, no UI.

Each method runs alone in a fresh process; the live-mode pairing (static + adaptive in one process)
is measured too. Repetitions use different seeds and a rotated group order to spread scheduling and
thermal effects. Reported values are medians across repetitions with [min, max] ranges.

Run from backend/:  .venv/bin/python -m adaptiveml.experiments.benchmark --reps 5
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

from adaptiveml.experiments.environment import capture_environment
from adaptiveml.experiments.runner import RESULTS_DIR, run_isolated, sea_config

DEFAULT_GROUPS = (("static",), ("incremental",), ("adaptive",), ("arf",), ("static", "adaptive"))


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _range(values):
    values = [v for v in values if v is not None]
    return [min(values), max(values)] if values else None


def _method_stats(summaries: list[dict]) -> dict:
    acc = [s["scores_after_warmup"]["accuracy"] for s in summaries]
    f1 = [s["scores_after_warmup"]["f1"] for s in summaries]
    refs = [s["stability_reference"] or {} for s in summaries]
    recovery = [r.get("recovery_samples") for r in refs]
    return {
        "latency_us": {k: _median([s["latency_us"][k] for s in summaries]) for k in ("mean", "p50", "p95", "p99", "max")},
        "stage_mean_us": {k: _median([s["stage_mean_us"][k] for s in summaries]) for k in summaries[0]["stage_mean_us"]},
        "accuracy": {"median": _median(acc), "range": _range(acc)},
        "f1": {"median": _median(f1), "range": _range(f1)},
        "adaptations": _median([s["adaptations"]["count"] for s in summaries]),
        "adaptation_duration_us_mean": _median([s["adaptations"]["duration_us_mean"] for s in summaries]),
        "model_size_kb": _median([(s["final_model"]["size_bytes"] or 0) / 1024 for s in summaries]),
        "stability_reference": {
            "pre_drift_accuracy": _median([(r.get("pre_drift") or {}).get("accuracy") for r in refs]),
            "min_windowed_accuracy": _median([r.get("min_windowed_accuracy") for r in refs]),
            "post_drift_late_accuracy": _median([(r.get("post_drift_late") or {}).get("accuracy") for r in refs]),
            "detection_delay_samples": _median([r.get("detection_delay_samples") for r in refs]),
            "recovery_samples": _median(recovery),
            "recovered_runs": sum(1 for v in recovery if v is not None),
        },
    }


def run_benchmark(groups=DEFAULT_GROUPS, *, reps: int = 5, length: int = 20_000, drift_at: int = 10_000, seed: int = 42) -> dict:
    groups = list(groups)
    plan = []
    for rep in range(reps):
        k = rep % len(groups)
        for group in groups[k:] + groups[:k]:
            plan.append((group, sea_config(group, seed + rep, length=length, drift_at=drift_at)))
    raw = run_isolated([cfg for _, cfg in plan])

    runs_by_group: dict[str, list[dict]] = {}
    for (group, _), result in zip(plan, raw):
        runs_by_group.setdefault("+".join(group), []).append(result)

    out = {}
    for name, runs in runs_by_group.items():
        timing = [r["timing"] for r in runs]
        throughput = [t["engine_throughput_per_s"] for t in timing]
        out[name] = {
            "runs": len(runs),
            "engine_throughput_per_s": {"median": _median(throughput), "range": _range(throughput)},
            "cpu_us_per_sample": _median([t["cpu_us_per_sample"] for t in timing]),
            "stream_us_per_sample": _median([t["stream_us_per_sample"] for t in timing]),
            "monitor_us_per_sample": _median([t["monitor_us_per_sample"] for t in timing]),
            "monitor_share_of_total": _median([t["monitor_share_of_total"] for t in timing]),
            "peak_rss_mb": _median([t["peak_rss_mb"] for t in timing]),
            "timer_overhead_ns": _median([t["timer_overhead_ns"] for t in timing]),
            "methods": {m: _method_stats([r["summaries"][m] for r in runs]) for m in runs[0]["summaries"]},
        }
    return {
        "parameters": {
            "scenario": "SEA 0→3 abrupt, noise 0.1",
            "length": length,
            "drift_at": drift_at,
            "warmup": 1_000,
            "reps": reps,
            "seeds": [seed + r for r in range(reps)],
            "mode": "max speed, one fresh process per trial, trials sequential",
        },
        "environment": capture_environment(),
        "groups": out,
    }


def _fmt(v, digits=1):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.{digits}f}"
    return f"{v:,}"


def to_markdown(report: dict) -> str:
    p, env = report["parameters"], report["environment"]
    lines = [
        "# Raw engine benchmark",
        "",
        f"- Measured on: {env['cpu']} ({env['cores_performance']}P + {env['cores_efficiency']}E cores), "
        f"{env['ram_gb']} GB RAM, {env['os']}, power: {env['power_source']}",
        f"- Python {env['python']}, river {env['packages']['river']}, numpy {env['packages']['numpy']}",
        f"- Scenario: {p['scenario']}; {p['length']:,} samples, drift at {p['drift_at']:,}, warm-up {p['warmup']:,}; "
        f"{p['reps']} repetitions (seeds {p['seeds'][0]}–{p['seeds'][-1]}); {p['mode']}",
        "- Values are medians across repetitions; [min – max] where shown. Latency statistics exclude warm-up.",
        "",
        "## Engine (per trial process)",
        "",
        "| Group | Throughput (samples/s) | CPU µs/sample | Monitor µs/sample (share) | Stream µs/sample | Peak RSS MB |",
        "|---|---|---|---|---|---|",
    ]
    for name, g in report["groups"].items():
        t = g["engine_throughput_per_s"]
        lines.append(
            f"| {name} | {_fmt(t['median'], 0)} [{_fmt(t['range'][0], 0)} – {_fmt(t['range'][1], 0)}] | "
            f"{_fmt(g['cpu_us_per_sample'])} | {_fmt(g['monitor_us_per_sample'], 2)} ({_fmt(100 * g['monitor_share_of_total'])} %) | "
            f"{_fmt(g['stream_us_per_sample'], 2)} | {_fmt(g['peak_rss_mb'])} |"
        )
    lines += [
        "",
        "## Per method — service time per sample (µs, after warm-up)",
        "",
        "| Group · method | mean | p50 | p95 | p99 | max | preprocess | select | predict | detect | adapt | update |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, g in report["groups"].items():
        for m, s in g["methods"].items():
            lat, st = s["latency_us"], s["stage_mean_us"]
            lines.append(
                f"| {name} · {m} | {_fmt(lat['mean'])} | {_fmt(lat['p50'])} | {_fmt(lat['p95'])} | {_fmt(lat['p99'])} | "
                f"{_fmt(lat['max'], 0)} | {_fmt(st['preprocess'], 2)} | {_fmt(st['select'], 2)} | {_fmt(st['predict'], 2)} | "
                f"{_fmt(st['detect'], 2)} | {_fmt(st['adapt'], 2)} | {_fmt(st['update'], 2)} |"
            )
    lines += [
        "",
        "## Per method — predictive measurements (factual; interpretation belongs to the research workstream)",
        "",
        "| Group · method | Accuracy | F1 | Adaptations | Adapt. µs (mean) | Model KB | Pre-drift acc | Min windowed acc | Late post-drift acc | Detection delay | Recovery samples (runs) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, g in report["groups"].items():
        for m, s in g["methods"].items():
            ref = s["stability_reference"]
            lines.append(
                f"| {name} · {m} | {_fmt(s['accuracy']['median'], 4)} | {_fmt(s['f1']['median'], 4)} | {_fmt(s['adaptations'])} | "
                f"{_fmt(s['adaptation_duration_us_mean'], 0)} | {_fmt(s['model_size_kb'])} | {_fmt(ref['pre_drift_accuracy'], 4)} | "
                f"{_fmt(ref['min_windowed_accuracy'], 4)} | {_fmt(ref['post_drift_late_accuracy'], 4)} | "
                f"{_fmt(ref['detection_delay_samples'])} | {_fmt(ref['recovery_samples'])} ({ref['recovered_runs']}/{g['runs']}) |"
            )
    lines += ["", "Stability columns are reference computations (docs/architecture.md §4.8); the formula is a team decision."]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--length", type=int, default=20_000)
    parser.add_argument("--drift-at", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "benchmarks")
    args = parser.parse_args()

    report = run_benchmark(reps=args.reps, length=args.length, drift_at=args.drift_at, seed=args.seed)
    out = args.out / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps(report, indent=2))
    md = to_markdown(report)
    (out / "benchmark.md").write_text(md)
    print(md)
    print(f"\nWritten to {out}")


if __name__ == "__main__":
    main()
