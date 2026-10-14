"""Trial loop: one stream, one or more method pipelines, at max speed or paced at a stream rate.

Every method sees the identical sample sequence. Pacing sleeps, command handling and pauses happen
between samples and are excluded from every timing. "monitor" time is the loop time that is neither
a pipeline stage nor stream generation: outcome recording, block closing and probes.
"""

from __future__ import annotations

import resource
import sys
import time
from array import array
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import median
from typing import Protocol

import numpy as np

from adaptiveml.adaptation.resources import ResourceGovernor
from adaptiveml.config import TrialConfig, derive_seed
from adaptiveml.config.profiles import apply_profile, per_sample_budget_ns
from adaptiveml.metrics import MethodRecorder, summarize_method
from adaptiveml.pipeline import MethodPipeline, method_spec
from adaptiveml.stream import make_scenario

BlockCallback = Callable[[int, dict[str, dict], dict], None]
PROBE_BUDGET = 0.005  # model-size probes may use at most 0.5 % of a method's service time
PAUSE_POLL_S = 0.05


class Control(Protocol):
    def poll(self) -> list[dict]:
        """Commands received since the last call: {"type": "pause"|"resume"|"stop"|"inject_drift", ...}."""


def calibrate_timer_overhead(n: int = 20_000) -> int:
    """Median cost (ns) of one back-to-back `perf_counter_ns` pair on this machine."""
    now = time.perf_counter_ns
    diffs = []
    for _ in range(n):
        a = now()
        diffs.append(now() - a)
    return int(median(diffs))


def peak_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / 1e6 if sys.platform == "darwin" else rss / 1e3  # bytes on macOS, KiB on Linux


@dataclass
class TrialContext:
    """Live objects of a running trial, for observers that build UI snapshots (same thread)."""

    scenario: object
    pipelines: list[MethodPipeline]
    recorders: list[MethodRecorder]
    recent: deque | None
    governors: dict[str, ResourceGovernor]
    lifecycle: dict


@dataclass
class TrialResult:
    config: TrialConfig  # resolved: includes drifts injected during the run
    status: str
    scenario: dict
    summaries: dict[str, dict]
    blocks: dict[str, list[dict]]
    engine_blocks: list[dict]
    events: list[dict]
    timing: dict
    pipelines: dict[str, MethodPipeline] = field(repr=False)
    recorders: dict[str, MethodRecorder] = field(repr=False)
    response_ns: array | None = field(default=None, repr=False)


def build_pipelines(cfg: TrialConfig, features) -> list[MethodPipeline]:
    pipeline_cfg = apply_profile(cfg.pipeline, cfg.profile)
    return [
        MethodPipeline(
            method_spec(name, pipeline_cfg),
            features,
            warmup=cfg.evaluation.warmup,
            seed=derive_seed(cfg.seed, f"method.{name}"),
        )
        for name in cfg.methods
    ]


class _Commands:
    """Applies control commands between samples; returns (stop requested, paused ns)."""

    def __init__(self, control: Control, scenario, emit, notify):
        self.control, self.scenario, self.emit, self.notify = control, scenario, emit, notify

    def handle(self, sample: int) -> tuple[bool, int]:
        stop, paused = False, 0
        for cmd in self.control.poll():
            kind = cmd.get("type")
            if kind == "stop":
                stop = True
            elif kind == "inject_drift":
                self._inject(sample, cmd)
            elif kind == "pause" and not stop:
                stop, dt = self._pause(sample)
                paused += dt
        return stop, paused

    def _pause(self, sample: int) -> tuple[bool, int]:
        resume_state = self.notify("paused", sample)
        start = time.perf_counter_ns()
        while True:
            time.sleep(PAUSE_POLL_S)
            for cmd in self.control.poll():
                kind = cmd.get("type")
                if kind == "stop":
                    return True, time.perf_counter_ns() - start
                if kind == "inject_drift":
                    self._inject(sample, cmd)
                if kind == "resume":
                    self.notify(resume_state, sample)
                    return False, time.perf_counter_ns() - start

    def _inject(self, sample: int, cmd: dict) -> None:
        try:
            spec = self.scenario.inject(int(cmd["to_variant"]), width=int(cmd.get("width", 1)))
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            self.emit(sample, "command_rejected", command="inject_drift", reason=str(exc))
            return
        self.emit(sample, "drift_scheduled", position=spec.position, width=spec.width, to_variant=spec.to_variant)


def run_trial(
    cfg: TrialConfig,
    *,
    on_block: BlockCallback | None = None,
    on_events: Callable[[list[dict]], None] | None = None,
    on_status: Callable[[dict], None] | None = None,
    control: Control | None = None,
    keep_recent: int = 0,
    context_sink: Callable[[TrialContext], None] | None = None,
) -> TrialResult:
    ev = cfg.evaluation
    lifecycle = {"state": "loading"}

    def notify(state: str, sample: int = -1) -> str:
        previous, lifecycle["state"] = lifecycle["state"], state
        if on_status is not None:
            on_status({"lifecycle": state, "sample": sample + 1, "total": cfg.stream.length})
        return previous

    notify("loading")
    scenario = make_scenario(cfg.stream, derive_seed(cfg.seed, "stream"))
    pipelines = build_pipelines(cfg, scenario.feature_names)
    recorders = [MethodRecorder(p.name, ev.positive_class) for p in pipelines]
    pairs = list(zip(pipelines, recorders))
    hot = [(p.process, *rec.sinks) for p, rec in pairs]
    positive = ev.positive_class

    budget_ns = per_sample_budget_ns(cfg.profile, cfg.stream.rate)
    governors = {p.name: ResourceGovernor(cfg.profile.budgets, budget_ns) for p in pipelines if budget_ns and p.spec.detects}
    recent = deque(maxlen=keep_recent) if keep_recent else None
    engine_events: list[dict] = []

    def emit(i: int, kind: str, **fields) -> None:
        engine_events.append({"i": i, "method": None, "type": kind, **fields})

    commands = _Commands(control, scenario, emit, notify) if control is not None else None
    if context_sink is not None:
        context_sink(TrialContext(scenario, pipelines, recorders, recent, governors, lifecycle))

    timer_overhead = calibrate_timer_overhead()
    now = time.perf_counter_ns
    block_size, warmup = ev.block_size, ev.warmup
    rate = cfg.stream.rate
    interval = 1e9 / rate if rate else 0.0
    response = array("q") if rate else None
    block_response: list[int] = []
    stream_ns = loop_ns = probe_ns = callback_ns = paused_ns = 0
    n_probes = 0
    probe_state = [[ev.model_size_every, ev.model_size_every] for _ in pairs]  # [next count, interval]
    next_probe = ev.model_size_every
    engine_blocks: list[dict] = []
    event_offsets = [0] * (len(pipelines) + 1)
    reported_drifts: set[int] = set()
    block_index = block_start = 0
    n = 0

    def probe_models(count: int) -> int:
        """Probe model sizes that are due; halve a method's probe rate while a probe costs more than
        PROBE_BUDGET of its service time over the interval (large ensembles, e.g. ARF)."""
        nonlocal probe_ns, n_probes
        for (p, rec), state in zip(pairs, probe_state):
            if count < state[0]:
                continue
            t = now()
            p.model_size_bytes = p.active.model._raw_memory_usage
            cost = now() - t
            probe_ns += cost
            n_probes += 1
            if rec.blocks and cost > PROBE_BUDGET * state[1] * rec.blocks[-1]["service_mean_ns"]:
                state[1] *= 2
            state[0] = count + state[1]
        return min(state[0] for state in probe_state)

    def new_events() -> list[dict]:
        batch = []
        for k, source in enumerate([p.events for p in pipelines] + [engine_events]):
            if len(source) > event_offsets[k]:
                batch.extend(source[event_offsets[k]:])
                event_offsets[k] = len(source)
        batch.sort(key=lambda e: e["i"])
        return batch

    def close_blocks(end: int) -> None:
        nonlocal block_index, block_start, cpu_mark, wall_mark, callback_ns
        cpu_now, wall_now = time.process_time(), now()
        for gt in scenario.ground_truth_drifts:  # ground truth reached in this block (scheduled or injected)
            if block_start <= gt.index < end and gt.index not in reported_drifts:
                reported_drifts.add(gt.index)
                emit(gt.index, "drift_true", from_variant=gt.from_variant, to_variant=gt.to_variant,
                     width=gt.width, label_flip_fraction=gt.label_flip_fraction, drift_kind=gt.kind,
                     injected=not scenario.is_synthetic)
        records = {}
        for p, rec in pairs:
            record = rec.close_block(block_index, block_start, p.block_extra())
            if record is None:
                continue
            governor = governors.get(p.name)
            if governor is not None and block_start >= warmup:
                governor.check(p, record, end - 1)
                record["over_budget"] = governor.constrained
            records[p.name] = record
        engine = {
            "block": block_index,
            "start": block_start,
            "n": end - block_start,
            "cpu_ms": (cpu_now - cpu_mark) * 1e3,
            "wall_ms": (wall_now - wall_mark) / 1e6,
            "lifecycle": lifecycle["state"],
        }
        if rate:
            engine["response_mean_ms"] = sum(block_response) / len(block_response) / 1e6 if block_response else None
            engine["response_max_ms"] = max(block_response) / 1e6 if block_response else None
            engine["backlog"] = max(0, int((wall_now - origin) // interval) + 1 - end)
            block_response.clear()
        engine_blocks.append(engine)
        batch = new_events()
        tc = now()
        if on_events is not None and batch:
            on_events(batch)
        if on_block is not None and records:
            on_block(block_index, records, engine)
        callback_ns += now() - tc
        cpu_mark, wall_mark = cpu_now, wall_now
        block_index += 1
        block_start = end

    it = iter(scenario)
    stop = False
    cpu_start = cpu_mark = time.process_time()
    t_begin = wall_mark = t_mark = origin = now()
    notify("warming_up")
    while True:
        if rate:
            due = origin + round(n * interval)  # integer ns, so response times fit the int64 array
            if commands is not None:
                stop, dt = commands.handle(n - 1)
                if dt:
                    origin += dt
                    due += dt
                    wall_mark += dt
                    paused_ns += dt
                if stop:
                    break
            wait = due - now()
            if wait > 0:
                time.sleep(wait / 1e9)
            t_mark = now()
        item = next(it, None)
        t1 = now()
        stream_ns += t1 - t_mark
        if item is None:
            break
        i, x, y = item
        for process, record_outcome, record_service, record_stages in hot:
            y_pred, service, stages = process(i, x, y)
            record_outcome(((y == positive) << 1) | (y_pred == positive))
            record_service(service)
            record_stages(stages)
        if rate:
            r = now() - due
            response.append(r)
            block_response.append(r)
        if recent is not None:
            recent.append((x, y))
        n = i + 1
        if n == warmup:
            notify("running", i)
        if n >= next_probe:
            next_probe = probe_models(n)
        if n - block_start == block_size:
            close_blocks(n)
        t_mark = now()
        loop_ns += t_mark - t1
        if not rate and commands is not None and n == block_start:  # max speed: commands at block boundaries
            stop, dt = commands.handle(i)
            paused_ns += dt
            wall_mark += dt
            if stop:
                break
            t_mark = now()
    t_end = now() if stop else t1
    it.close()
    if n > block_start:
        close_blocks(n)
    cpu_total = time.process_time() - cpu_start
    status = "stopped" if stop else "completed"
    notify("summarizing", n - 1)

    for p, _ in pairs:  # final size probe, outside the timed loop
        p.model_size_bytes = p.active.model._raw_memory_usage

    stream_updates = {"drifts": scenario.drifts}
    if not scenario.is_synthetic:
        stream_updates["dataset_sha256"] = scenario.sha256
    resolved = cfg.model_copy(update={"stream": cfg.stream.model_copy(update=stream_updates)})
    drifts = scenario.ground_truth_drifts
    drift_index = drifts[0].index if drifts and drifts[0].index < n else None
    # Before / during / after windows: around the first known change, or — for a control trial that
    # has no change of its own — around the rows of the trial it is the control for.
    phase_window = None
    if ev.phase_anchor is not None:
        phase_window = (ev.phase_anchor[0], ev.phase_anchor[1], None, "control: no change in these rows")
    elif drift_index is not None:
        first = drifts[0]
        following = drifts[1].index if len(drifts) > 1 else None
        phase_window = (first.start, first.end, following, "first known change")
    summaries = {
        rec.method: summarize_method(
            rec, p, warmup=min(warmup, n), drift_index=drift_index, stability=ev.stability,
            phases=ev.phases, phase_window=phase_window,
        )
        for p, rec in pairs
        if len(rec.outcomes) > 0
    }
    total_ns = t_end - t_begin - paused_ns
    service_total = sum(sum(rec.service_ns) for rec in recorders)
    monitor_ns = loop_ns - service_total
    events = sorted((e for source in [p.events for p in pipelines] + [engine_events] for e in source), key=lambda e: e["i"])
    response_stats = None
    if response is not None and len(response):
        r_ms = np.frombuffer(response, dtype=np.int64) / 1e6
        response_stats = {"mean": float(r_ms.mean()), "p95": float(np.percentile(r_ms, 95)), "max": float(r_ms.max())}
    timing = {
        "samples": n,
        "methods": len(pipelines),
        "rate": rate,
        "total_ms": total_ns / 1e6,
        "paused_ms": paused_ns / 1e6,
        "engine_throughput_per_s": n / (total_ns / 1e9) if total_ns > 0 else None,
        "stream_us_per_sample": stream_ns / n / 1e3 if n else None,
        "monitor_us_per_sample": monitor_ns / n / 1e3 if n else None,
        "monitor_share_of_total": monitor_ns / total_ns if total_ns > 0 else None,
        "response_ms": response_stats,
        "model_size_probe": {
            "count": n_probes,
            "total_ms": probe_ns / 1e6,
            "final_interval": {p.name: state[1] for (p, _), state in zip(pairs, probe_state)},
        },
        "block_callback_ms": callback_ns / 1e6,
        "cpu_s": cpu_total,
        "cpu_us_per_sample": cpu_total / n * 1e6 if n else None,
        "peak_rss_mb": peak_rss_mb(),
        "timer_overhead_ns": timer_overhead,
        "budget_us_per_sample": budget_ns / 1e3 if budget_ns else None,
        "governor_decisions": {name: g.decisions for name, g in governors.items()},
        # A measured-time budget makes behaviour depend on timing, so such trials are not bit-reproducible.
        "timing_dependent_behaviour": bool(governors),
    }
    notify(status, n - 1)
    return TrialResult(
        config=resolved,
        status=status,
        scenario=scenario.info,
        summaries=summaries,
        blocks={rec.method: rec.blocks for rec in recorders},
        engine_blocks=engine_blocks,
        events=events,
        timing=timing,
        pipelines={p.name: p for p in pipelines},
        recorders={rec.method: rec for rec in recorders},
        response_ns=response,
    )
