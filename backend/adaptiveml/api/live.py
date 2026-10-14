"""Live runs: one worker process at a time, its state, and fan-out of its updates to SSE clients.

Resources (CPU %, RSS) are sampled by the server from the worker's PID at 1 Hz, so the observer adds
nothing to the measured process.
"""

from __future__ import annotations

import asyncio
import csv
import multiprocessing as mp
import os
import queue
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

import psutil

from adaptiveml.config import TrialConfig
from adaptiveml.engine.worker import live_worker
from adaptiveml.results import experiment_path


class Hub:
    """Thread-safe fan-out of messages to SSE subscribers running on the asyncio loop."""

    QUEUE_SIZE = 1_000

    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.subscribers: set[asyncio.Queue] = set()
        self.seq = 0
        self._lock = threading.Lock()

    def publish(self, message: dict) -> None:
        with self._lock:
            self.seq += 1
            message = {**message, "seq": self.seq}
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self._deliver, message)

    def _deliver(self, message: dict) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:  # a slow client: drop it; it reconnects and resyncs from /state
                self.subscribers.discard(q)
                while not q.empty():
                    q.get_nowait()
                q.put_nowait(None)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self.QUEUE_SIZE)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)


class LiveState:
    MAX_BLOCKS, MAX_EVENTS, MAX_RESOURCES = 4_000, 2_000, 3_600

    def __init__(self, name: str, config: dict):
        self.name, self.config = name, config
        self.started = time.time()
        self.status: dict = {"lifecycle": "starting", "sample": 0, "total": config["stream"]["length"]}
        self.blocks: dict[str, deque] = defaultdict(lambda: deque(maxlen=self.MAX_BLOCKS))
        self.engine: deque = deque(maxlen=self.MAX_BLOCKS)
        self.events: deque = deque(maxlen=self.MAX_EVENTS)
        self.resources: deque = deque(maxlen=self.MAX_RESOURCES)
        self.extras: dict | None = None
        self.final: dict | None = None
        self.error: dict | None = None
        self._lock = threading.Lock()

    def apply(self, message: dict) -> None:
        kind = message["type"]
        with self._lock:
            if kind == "status":
                self.status = {k: message[k] for k in ("lifecycle", "sample", "total")}
            elif kind == "blocks":
                for method, records in message["blocks"].items():
                    self.blocks[method].extend(records)
                self.engine.extend(message["engine"])
                if message["engine"]:
                    last = message["engine"][-1]
                    self.status["sample"] = last["start"] + last["n"]
            elif kind == "events":
                self.events.extend(message["events"])
            elif kind == "extras":
                self.extras = message
            elif kind == "resources":
                self.resources.append(message)
            elif kind == "final":
                self.final = message
            elif kind == "error":
                self.error = message
                self.status["lifecycle"] = "error"

    @property
    def finished(self) -> bool:
        return self.final is not None or self.error is not None

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "config": self.config,
                "started": self.started,
                "status": dict(self.status),
                "blocks": {m: list(b) for m, b in self.blocks.items()},
                "engine": list(self.engine),
                "events": list(self.events),
                "resources": list(self.resources),
                "extras": self.extras,
                "final": self.final,
                "error": self.error,
            }


@dataclass
class _Run:
    process: mp.Process
    out: object
    commands: object
    state: LiveState


class LiveRunManager:
    def __init__(self, hub: Hub):
        self.hub = hub
        self.run: _Run | None = None
        self._lock = threading.Lock()

    @property
    def active(self) -> bool:
        run = self.run
        return run is not None and not run.state.finished and run.process.is_alive()

    def start(self, cfg: TrialConfig, name: str) -> dict:
        with self._lock:
            if self.active:
                raise RuntimeError("a live run is already in progress")
            os.environ.setdefault("PYTHONHASHSEED", "0")
            ctx = mp.get_context("spawn")
            out, commands = ctx.Queue(maxsize=512), ctx.Queue()
            process = ctx.Process(target=live_worker, args=(cfg.model_dump_json(), name, out, commands), daemon=True)
            process.start()
            self.run = _Run(process, out, commands, LiveState(name, cfg.model_dump(mode="json")))
        threading.Thread(target=self._consume, args=(self.run,), daemon=True).start()
        threading.Thread(target=self._sample_resources, args=(self.run,), daemon=True).start()
        self.hub.publish({"type": "run_started", "name": name, "config": self.run.state.config})
        return {"name": name, "pid": process.pid}

    def command(self, command: dict) -> None:
        if not self.active:
            raise RuntimeError("no live run is in progress")
        if command.get("type") == "inject_drift" and self.run.state.config["stream"]["scenario"] == "csv":
            raise RuntimeError("drift injection is disabled for real dataset replay")
        self.run.commands.put(command)

    def snapshot(self) -> dict | None:
        return None if self.run is None else self.run.state.snapshot() | {"active": self.active}

    def _consume(self, run: _Run) -> None:
        while True:
            try:
                message = run.out.get(timeout=0.5)
            except queue.Empty:
                if run.process.is_alive():
                    continue
                if not run.state.finished:
                    message = {"type": "error", "message": f"engine process exited unexpectedly (exit code {run.process.exitcode})"}
                else:
                    return
            run.state.apply(message)
            self.hub.publish(message)
            if message["type"] == "final":
                self._write_resources(run, message["experiment_id"])
            if message["type"] in ("final", "error"):
                return

    def _sample_resources(self, run: _Run) -> None:
        try:
            proc = psutil.Process(run.process.pid)
            proc.cpu_percent(None)  # the first reading is always 0.0
        except psutil.Error:
            return
        t0 = time.monotonic()
        while not run.state.finished and run.process.is_alive():
            time.sleep(1.0)
            try:
                message = {
                    "type": "resources",
                    "t": round(time.monotonic() - t0, 2),
                    "cpu_percent": proc.cpu_percent(None),
                    "rss_mb": round(proc.memory_info().rss / 1e6, 1),
                }
            except psutil.Error:
                return
            run.state.apply(message)
            self.hub.publish(message)

    @staticmethod
    def _write_resources(run: _Run, experiment_id: str) -> None:
        folder = experiment_path(experiment_id)
        with (folder / "resources.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["t", "cpu_percent", "rss_mb"], extrasaction="ignore")
            writer.writeheader()
            writer.writerows(run.state.resources)

    def shutdown(self) -> None:
        run = self.run
        if run is not None and run.process.is_alive():
            run.commands.put({"type": "stop"})
            run.process.join(timeout=5)
            if run.process.is_alive():
                run.process.terminate()
