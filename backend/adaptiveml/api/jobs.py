"""Background experiment jobs: one at a time, never concurrently with a live run (shared CPU would
invalidate both sets of timings)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from adaptiveml.config import ExperimentConfig
from adaptiveml.experiments.rerun import rerun_experiment
from adaptiveml.experiments.runner import run_experiment


class ExperimentJobs:
    def __init__(self, publish: Callable[[dict], None]):
        self._publish = publish
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.progress: dict | None = None

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, exp: ExperimentConfig) -> None:
        self._launch(exp.name, len(exp.trials()), lambda **kw: run_experiment(exp, **kw))

    def rerun(self, experiment_id: str) -> None:
        self._launch(f"rerun of {experiment_id}", None, lambda **kw: rerun_experiment(experiment_id, **kw))

    def stop(self) -> None:
        self._stop.set()

    def _launch(self, name: str, total: int | None, target: Callable[..., dict]) -> None:
        if self.active:
            raise RuntimeError("an experiment is already running")
        self._stop.clear()
        self.progress = {
            "name": name, "status": "running", "done": 0, "total": total, "trial": None, "experiment_id": None,
            "started_at": time.time(), "finished_at": None, "context": None, "plan": None, "current": None, "feed": [],
        }
        self._publish({"type": "experiment_progress", **self.progress})

        def on_progress(p: dict) -> None:
            self.progress.update(p)
            self._publish({"type": "experiment_progress", **self.progress})

        def work() -> None:
            try:
                manifest = target(on_progress=on_progress, should_stop=self._stop.is_set)
                self.progress.update(status=manifest["status"], experiment_id=manifest["id"], error=manifest.get("error"))
            except Exception as exc:  # noqa: BLE001
                self.progress.update(status="error", error=repr(exc))
            self.progress.update(finished_at=time.time(), current=None)
            self._publish({"type": "experiment_progress", **self.progress})

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
