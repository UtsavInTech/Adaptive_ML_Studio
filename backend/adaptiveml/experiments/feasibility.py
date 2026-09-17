"""Stage 4 feasibility spike — the seven go/no-go checks of docs/architecture.md §12.

Pass criteria are fixed in CRITERIA before any result is seen; results are reported as measured,
failures included. Run from backend/:
    .venv/bin/python -m adaptiveml.experiments.feasibility            # all checks
    .venv/bin/python -m adaptiveml.experiments.feasibility --only 7   # a subset
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import multiprocessing as mp
import platform
import queue
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from statistics import median

import river
from river.datasets import synth

from adaptiveml.config import DriftSpec, StreamConfig, TrialConfig
from adaptiveml.engine import run_trial
from adaptiveml.experiments.environment import capture_environment
from adaptiveml.experiments.runner import RESULTS_DIR, run_isolated, sea_config
from adaptiveml.stream import SeaScenario, label_flip_fraction
from adaptiveml.stream.sea import SEA_THRESHOLDS

DEMO_RATE = 100  # samples/s — live-demo default (docs/product_definition.md §11)
SNAPSHOT_INTERVAL_S = 0.25  # designed UI cadence ≈ 4 Hz (docs/architecture.md §8.1)
IPC_REPS = 9

CRITERIA = {
    1: "Python ≥ 3.11 and river 0.26.1 importable in the project venv",
    2: "Same seed → identical stream, different seed → different stream; with noise 0, no sample more than "
    "3 positions from the drift centre follows the wrong concept; empirical label-flip fraction within 3σ of "
    "the closed form for SEA pairs 0→1, 0→3, 2→3",
    3: f"static + adaptive in one process at max speed ≥ {10 * DEMO_RATE:,} samples/s (10 × the {DEMO_RATE}/s "
    "demo rate); median of 5 isolated runs",
    4: "SEA 0→3 abrupt drift (noise 0.1) detected within 2,000 samples in ≥ 9 of 10 seeds; delays and false "
    "alarms reported as measured",
    5: "x2 ranked last by the feature selector at the end of warm-up in ≥ 9 of 10 seeds",
    6: "Model-size probe on the final Hoeffding tree, amortised over 2,000 samples, < 1 % of the mean "
    "per-sample service time",
    7: "Snapshot emission through a multiprocessing queue at the designed ≈4 Hz cadence: direct cost ≤ 2 % of "
    f"engine time and total-time increase ≤ 5 % (median of {IPC_REPS} interleaved runs each, with an A/A "
    "baseline reported as the noise floor); per-block emission reported as a stress case only. Protocol revised "
    "from 3 runs after the first run (20260911-233051), where the stress case with ≈90× more snapshots showed a "
    "smaller increase than the designed case — i.e. run-to-run noise at the threshold; thresholds unchanged",
}


# ---------------------------------------------------------------- 1 · install
def check_install() -> dict:
    return {
        "passed": sys.version_info >= (3, 11) and river.__version__ == "0.26.1",
        "measured": {"python": platform.python_version(), "river": river.__version__},
    }


# ---------------------------------------------------------------- 2 · stream
def check_stream() -> dict:
    cfg = StreamConfig(length=5_000, drifts=(DriftSpec(position=2_500, to_variant=3),))
    first, again, other = (list(SeaScenario(cfg, s)) for s in (42, 42, 43))
    deterministic = first == again and first != other

    position = 5_000
    cfg0 = StreamConfig(length=10_000, noise=0.0, drifts=(DriftSpec(position=position, to_variant=3),))
    t_old, t_new = SEA_THRESHOLDS[0], SEA_THRESHOLDS[3]
    wrong, informative, transition = 0, 0, []
    for i, x, y in SeaScenario(cfg0, 42):
        s = x["x0"] + x["x1"]
        old, new = s > t_old, s > t_new
        if old == new:
            continue
        informative += 1
        if abs(i - position) <= 3:
            transition.append([i, "new" if y == new else "old"])
        elif y != (old if i < position else new):
            wrong += 1

    flips, n = [], 200_000
    for va, vb in ((0, 1), (0, 3), (2, 3)):
        ta, tb = SEA_THRESHOLDS[va], SEA_THRESHOLDS[vb]
        mismatches = sum(
            (x[0] + x[1] > ta) != (x[0] + x[1] > tb) for x, _ in itertools.islice(synth.SEA(variant=va, seed=7), n)
        )
        empirical, analytical = mismatches / n, label_flip_fraction(va, vb)
        z = (empirical - analytical) / math.sqrt(analytical * (1 - analytical) / n)
        flips.append({"pair": f"{va}→{vb}", "analytical": analytical, "empirical": empirical, "z": round(z, 3)})

    return {
        "passed": deterministic and wrong == 0 and all(abs(f["z"]) <= 3 for f in flips),
        "measured": {
            "deterministic": deterministic,
            "informative_samples": informative,
            "wrong_concept_outside_transition": wrong,
            "transition_zone_samples": transition,
            "label_flip_fraction": flips,
        },
    }


# ---------------------------------------------------------------- 3 · throughput
def check_throughput() -> dict:
    runs = run_isolated([sea_config(("static", "adaptive"), 42 + k) for k in range(5)])
    throughput = [r["timing"]["engine_throughput_per_s"] for r in runs]
    med = median(throughput)
    return {
        "passed": med >= 10 * DEMO_RATE,
        "measured": {
            "throughput_per_s": [round(t) for t in throughput],
            "median_throughput_per_s": round(med),
            "headroom_vs_demo_rate": round(med / DEMO_RATE, 1),
            "mean_service_us": {
                m: round(median(r["summaries"][m]["latency_us"]["mean"] for r in runs), 2) for m in ("static", "adaptive")
            },
            "p95_service_us": {
                m: round(median(r["summaries"][m]["latency_us"]["p95"] for r in runs), 2) for m in ("static", "adaptive")
            },
        },
    }


# ---------------------------------------------------------------- 4 · detection
def check_detection() -> dict:
    drift, warmup, rows = 5_000, 1_000, []
    for seed in range(1, 11):
        r = run_trial(sea_config(("static", "adaptive"), seed))
        adaptive_events = [e for e in r.events if e["method"] == "adaptive"]
        detections = [e["i"] for e in adaptive_events if e["type"] == "drift_detected" and e["error_increased"]]
        first = next((i for i in detections if i >= drift), None)
        ref = {m: r.summaries[m]["stability_reference"] for m in ("static", "adaptive")}
        rows.append(
            {
                "seed": seed,
                "detection_delay": None if first is None else first - drift,
                "false_alarms_before_drift": [i for i in detections if warmup <= i < drift],
                "adaptations": [[e["i"], e["action"]] for e in adaptive_events if e["type"] == "adaptation_completed"],
                "pre_drift_accuracy": {m: ref[m]["pre_drift"]["accuracy"] for m in ref},
                "min_windowed_accuracy": {m: ref[m]["min_windowed_accuracy"] for m in ref},
                "post_drift_late_accuracy": {m: ref[m]["post_drift_late"]["accuracy"] for m in ref},
                "recovery_samples": {m: ref[m]["recovery_samples"] for m in ref},
            }
        )
    detected = sum(1 for row in rows if row["detection_delay"] is not None and row["detection_delay"] <= 2_000)
    delays = [row["detection_delay"] for row in rows if row["detection_delay"] is not None]
    return {
        "passed": detected >= 9,
        "measured": {
            "detected_within_2000": f"{detected}/10",
            "delay_median": median(delays) if delays else None,
            "delay_range": [min(delays), max(delays)] if delays else None,
            "seeds_with_false_alarms": sum(1 for row in rows if row["false_alarms_before_drift"]),
            "per_seed": rows,
        },
    }


# ---------------------------------------------------------------- 5 · feature selection
def check_feature_selection() -> dict:
    rows = []
    for seed in range(1, 11):
        r = run_trial(TrialConfig(seed=seed, methods=("adaptive",), stream=StreamConfig(length=1_100)))
        applied = next(e for e in r.events if e["type"] == "selection_applied")
        rows.append({"seed": seed, "ranking": applied["ranking"], "last": applied["ranking"][-1][0]})
    hits = sum(1 for row in rows if row["last"] == "x2")
    return {"passed": hits >= 9, "measured": {"x2_ranked_last": f"{hits}/10", "per_seed": rows}}


# ---------------------------------------------------------------- 6 · memory probe
def _probe_cost(model, repeats: int = 21) -> tuple[int, int]:
    times, size = [], 0
    for _ in range(repeats):
        t = time.perf_counter_ns()
        size = model._raw_memory_usage
        times.append(time.perf_counter_ns() - t)
    return int(median(times)), size


def check_memory_probe() -> dict:
    measured = {}
    for method in ("adaptive", "arf"):
        r = run_trial(sea_config((method,), 42, length=20_000, drift_at=10_000))
        probe_ns, size = _probe_cost(r.pipelines[method].active.model)
        service_ns = r.summaries[method]["latency_us"]["mean"] * 1_000
        measured[method] = {
            "model_size_kb": round(size / 1024, 1),
            "probe_us": round(probe_ns / 1_000, 1),
            "amortised_ns_per_sample": round(probe_ns / 2_000, 1),
            "mean_service_us": round(service_ns / 1_000, 2),
            "share_of_service": probe_ns / 2_000 / service_ns,
        }
    return {
        "passed": measured["adaptive"]["share_of_service"] < 0.01,
        "measured": measured,
        "note": "ARF is informational; the criterion applies to the Hoeffding tree of the adaptive pipeline.",
    }


# ---------------------------------------------------------------- 7 · IPC
def _drain(q, ready) -> None:
    ready.set()
    while q.get() is not None:
        pass


class _Emitter:
    """Batches closed blocks and puts one snapshot on the queue per interval (0 = every block)."""

    def __init__(self, q, interval_s: float):
        self.q, self.interval_ns = q, int(interval_s * 1e9)
        self.last, self.pending, self.sent, self.dropped = 0, [], 0, 0

    def __call__(self, index: int, records: dict, engine: dict) -> None:
        self.pending.append(records)
        now = time.perf_counter_ns()
        if now - self.last >= self.interval_ns:
            try:
                self.q.put_nowait({"blocks": self.pending, "engine": engine})
                self.sent += 1
            except queue.Full:
                self.dropped += 1
            self.pending, self.last = [], now


def _timed_run(cfg: TrialConfig, ctx, interval_s: float | None) -> dict:
    if interval_s is None:
        t = run_trial(cfg).timing
        return {"total_ms": t["total_ms"], "cpu_s": t["cpu_s"], "callback_share": 0.0, "sent": 0, "dropped": 0}
    q, ready = ctx.Queue(maxsize=64), ctx.Event()
    consumer = ctx.Process(target=_drain, args=(q, ready), daemon=True)
    consumer.start()
    ready.wait(timeout=30)  # the server-side consumer is always running before a live trial starts
    emitter = _Emitter(q, interval_s)
    t = run_trial(cfg, on_block=emitter).timing
    q.put(None)
    consumer.join(timeout=10)
    return {
        "total_ms": t["total_ms"],
        "cpu_s": t["cpu_s"],
        "callback_share": t["block_callback_ms"] / t["total_ms"],
        "sent": emitter.sent,
        "dropped": emitter.dropped,
    }


def check_ipc() -> dict:
    ctx = mp.get_context("spawn")
    cfg = sea_config(("static", "adaptive"), 42, length=30_000, drift_at=15_000, block_size=25)
    variants = {"baseline": None, "baseline_repeat": None, "designed_4hz": SNAPSHOT_INTERVAL_S, "stress_every_block": 0.0}
    names = list(variants)
    runs = {name: [] for name in names}
    for rep in range(IPC_REPS):
        k = rep % len(names)
        for name in names[k:] + names[:k]:  # rotate the order so no variant always runs first or last
            runs[name].append(_timed_run(cfg, ctx, variants[name]))
    base_wall = median(r["total_ms"] for r in runs["baseline"])
    base_cpu = median(r["cpu_s"] for r in runs["baseline"])
    summary = {
        name: {
            "total_ms_median": round(median(r["total_ms"] for r in rs), 1),
            "wall_increase_vs_baseline": median(r["total_ms"] for r in rs) / base_wall - 1,
            "cpu_increase_vs_baseline": median(r["cpu_s"] for r in rs) / base_cpu - 1,
            "direct_share_median": median(r["callback_share"] for r in rs),
            "snapshots_sent_median": median(r["sent"] for r in rs),
            "dropped_total": sum(r["dropped"] for r in rs),
        }
        for name, rs in runs.items()
    }
    designed = summary["designed_4hz"]
    return {
        "passed": designed["direct_share_median"] <= 0.02 and designed["wall_increase_vs_baseline"] <= 0.05,
        "measured": summary,
        "note": "baseline_repeat is an A/A comparison: its 'increase' is the protocol's noise floor.",
    }


CHECKS = {
    1: ("Install", check_install),
    2: ("Stream determinism and drift placement", check_stream),
    3: ("Throughput headroom", check_throughput),
    4: ("ADWIN drift detection", check_detection),
    5: ("Feature selection ranks x2 last", check_feature_selection),
    6: ("Model-size probe cost", check_memory_probe),
    7: ("IPC snapshot overhead", check_ipc),
}


def run_checks(only: set[int] | None = None) -> dict:
    results = {}
    for number, (title, fn) in CHECKS.items():
        if only and number not in only:
            continue
        started = time.perf_counter()
        try:
            outcome = fn()
        except Exception:  # noqa: BLE001 — a crashing check is a failed check, reported in full
            outcome = {"passed": False, "error": traceback.format_exc()}
        outcome.update(title=title, criterion=CRITERIA[number], seconds=round(time.perf_counter() - started, 1))
        results[number] = outcome
        print(f"[{'PASS' if outcome['passed'] else 'FAIL'}] {number}. {title} ({outcome['seconds']} s)", flush=True)
    return {
        "environment": capture_environment(),
        "checks_run": sorted(results),
        "all_passed": all(r["passed"] for r in results.values()),
        "checks": results,
    }


def to_markdown(report: dict) -> str:
    env = report["environment"]
    subset = len(report["checks_run"]) < len(CHECKS)
    verdict = "all checks run passed" if report["all_passed"] else "see failed checks"
    lines = [
        "# Stage 4 feasibility checks" + (f" — subset {report['checks_run']}" if subset else ""),
        "",
        f"- Measured on: {env['cpu']} ({env['cores_performance']}P + {env['cores_efficiency']}E), {env['ram_gb']} GB, "
        f"{env['os']}, power: {env['power_source']}; Python {env['python']}, river {env['packages']['river']}",
        f"- Result: **{'PASS' if report['all_passed'] else 'FAIL'} — {verdict}**",
        "",
        "| # | Check | Result | Criterion |",
        "|---|---|---|---|",
    ]
    for number, r in report["checks"].items():
        lines.append(f"| {number} | {r['title']} | {'PASS' if r['passed'] else '**FAIL**'} | {r['criterion']} |")
    lines += ["", "## Measurements", ""]
    for number, r in report["checks"].items():
        lines += [f"### {number}. {r['title']}", "", "```json", json.dumps(r.get("measured", r.get("error")), indent=2, default=str), "```", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", type=str, default="", help="comma-separated check numbers, e.g. 4,7")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "feasibility")
    args = parser.parse_args()
    only = {int(n) for n in args.only.split(",") if n.strip()} or None
    report = run_checks(only)
    out = args.out / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "feasibility.json").write_text(json.dumps(report, indent=2, default=str))
    (out / "feasibility.md").write_text(to_markdown(report))
    print(f"\nResult: {'PASS' if report['all_passed'] else 'FAIL'} — written to {out}")


if __name__ == "__main__":
    main()
