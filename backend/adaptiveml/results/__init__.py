"""Result bundles: plain files, one folder per experiment, one sub-folder per trial.

Layout (docs/architecture.md §5.5), under <results>/experiments/:
    index.csv                        one row per trial × method across experiments
    <experiment_id>/manifest.json    ids, status, environment, provenance, per-trial headline numbers
    <experiment_id>/config.resolved.yaml
    <experiment_id>/trials/<trial_id>/{summary.json, blocks.csv, engine_blocks.csv, events.jsonl, outcomes.csv.gz}

<results> is the repository's results/ folder unless ADAPTIVEML_RESULTS_DIR is set (tests use this).
Everything here records measurements; nothing interprets them.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

from adaptiveml.experiments.environment import capture_environment

REPO_ROOT = Path(__file__).resolve().parents[3]
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,160}$")
INDEX_FIELDS = [
    "experiment_id", "trial_id", "kind", "created_utc", "name", "status", "scenario", "real_data", "method",
    "profile", "simulated_profile", "placeholder_budgets", "rate", "seed", "accuracy", "f1",
    "latency_mean_us", "latency_p95_us", "adaptations", "timing_dependent", "config_hash",
]
NOTE = "Measurements only; interpretation belongs to the research workstream. y_true / *_pred are 1 for the positive class."


def experiments_dir() -> Path:
    return Path(os.environ.get("ADAPTIVEML_RESULTS_DIR", REPO_ROOT / "results")) / "experiments"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def config_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def app_version() -> dict:
    def git(*args):
        try:
            out = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=5)
            return out.stdout.strip() if out.returncode == 0 else None
        except OSError:
            return None

    return {"commit": git("rev-parse", "--short", "HEAD"), "uncommitted_changes": bool(git("status", "--porcelain"))}


def new_experiment_id(kind: str, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "run"
    return f"{datetime.now():%Y%m%d-%H%M%S-%f}-{kind}-{slug}"


def check_id(value: str) -> str:
    if not SAFE_ID.match(value) or ".." in value:
        raise ValueError(f"invalid id: {value!r}")
    return value


# ---------------------------------------------------------------- writing
def _write_csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        fields.extend(k for k in row if k not in fields)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_outcomes(path: Path, result) -> None:
    recorders = result.recorders
    first = next(iter(recorders.values()))
    columns = {"i": np.arange(len(first.outcomes)), "y_true": first.true_labels()}
    for method, rec in recorders.items():
        columns[f"{method}_pred"] = rec.predicted_labels()
        columns[f"{method}_service_ns"] = np.frombuffer(rec.service_ns, dtype=np.int64)
    if result.response_ns is not None:
        columns["response_ns"] = np.frombuffer(result.response_ns, dtype=np.int64)
    with gzip.open(path, "wt", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(zip(*(c.tolist() for c in columns.values())))


def write_trial(result, trial_dir: Path) -> dict:
    """Write one trial's files and return its summary payload."""
    trial_dir.mkdir(parents=True, exist_ok=True)
    resolved = result.config.model_dump(mode="json")
    summary = {
        "status": result.status,
        "config": resolved,
        "config_hash": config_hash(resolved),
        "scenario": result.scenario,
        "timing": result.timing,
        "summaries": result.summaries,
    }
    (trial_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    _write_csv(trial_dir / "blocks.csv", [r for blocks in result.blocks.values() for r in blocks])
    _write_csv(trial_dir / "engine_blocks.csv", result.engine_blocks)
    with (trial_dir / "events.jsonl").open("w") as f:
        for event in result.events:
            f.write(json.dumps(event, default=str) + "\n")
    if any(len(r.outcomes) for r in result.recorders.values()):
        _write_outcomes(trial_dir / "outcomes.csv.gz", result)
    return summary


def _trial_entry(trial_id: str, payload: dict) -> dict:
    cfg, timing = payload["config"], payload["timing"]
    return {
        "trial_id": trial_id,
        "status": payload.get("status", "completed"),
        "seed": cfg["seed"],
        "rate": cfg["stream"]["rate"],
        "profile": {k: cfg["profile"][k] for k in ("name", "label", "simulated", "placeholder")},
        "config_hash": config_hash(cfg),
        "scenario": {k: payload["scenario"].get(k) for k in ("name", "real", "length", "noise", "drifts")},
        "timing": {
            k: timing.get(k)
            for k in ("samples", "engine_throughput_per_s", "cpu_us_per_sample", "peak_rss_mb",
                      "monitor_share_of_total", "response_ms", "timing_dependent_behaviour", "governor_decisions")
        },
        "methods": {
            m: {
                "accuracy": s["scores_after_warmup"]["accuracy"],
                "f1": s["scores_after_warmup"]["f1"],
                "latency_us": s["latency_us"],
                "adaptations": s["adaptations"]["count"],
                "predictions_sha256": s["predictions_sha256"],
            }
            for m, s in payload["summaries"].items()
        },
    }


class ExperimentBundle:
    def __init__(self, kind: str, name: str, config_payload: dict, *, root: Path | None = None):
        self.kind, self.name = kind, name
        self.root = root or experiments_dir()
        self.id = new_experiment_id(kind, name)
        self.dir = self.root / self.id
        self.dir.mkdir(parents=True, exist_ok=False)
        self.created = utc_now()
        self.config_payload = config_payload
        self.environment = capture_environment()
        self.trials: list[dict] = []
        (self.dir / "config.resolved.yaml").write_text(yaml.safe_dump(config_payload, sort_keys=False))
        self.write_manifest("running")

    def trial_dir(self, trial_id: str) -> Path:
        return self.dir / "trials" / check_id(trial_id)

    def record_trial(self, trial_id: str, payload: dict) -> None:
        self.trials.append(_trial_entry(trial_id, payload))
        self.write_manifest("running")

    def write_manifest(self, status: str, error: str | None = None, finished: str | None = None) -> dict:
        env = self.environment
        profiles = {t["profile"]["name"]: t["profile"] for t in self.trials}
        manifest = {
            "schema_version": 1,
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "status": status,
            "error": error,
            "created_utc": self.created,
            "finished_utc": finished,
            "app_version": app_version(),
            "config_hash": config_hash(self.config_payload),
            "environment": env,
            "provenance": {
                "measured_on": f"{env['cpu']}, {env['ram_gb']} GB RAM, {env['os']}, power: {env['power_source']}",
                "simulated_profiles": sorted(n for n, p in profiles.items() if p["simulated"]),
                "placeholder_budgets": any(p["placeholder"] for p in profiles.values()),
                "real_data": any(t["scenario"]["real"] for t in self.trials),
            },
            "timing_valid": True,  # trials run one at a time, each in a fresh process
            "trials": self.trials,
            "note": NOTE,
        }
        (self.dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        return manifest

    def finish(self, status: str, error: str | None = None) -> dict:
        manifest = self.write_manifest(status, error, finished=utc_now())
        index = self.root / "index.csv"
        new_file = not index.exists()
        with index.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
            if new_file:
                writer.writeheader()
            for t in self.trials:
                for method, s in t["methods"].items():
                    writer.writerow({
                        "experiment_id": self.id, "trial_id": t["trial_id"], "kind": self.kind,
                        "created_utc": self.created, "name": self.name, "status": t["status"],
                        "scenario": t["scenario"]["name"], "real_data": t["scenario"]["real"], "method": method,
                        "profile": t["profile"]["name"], "simulated_profile": t["profile"]["simulated"],
                        "placeholder_budgets": t["profile"]["placeholder"], "rate": t["rate"], "seed": t["seed"],
                        "accuracy": s["accuracy"], "f1": s["f1"], "latency_mean_us": s["latency_us"]["mean"],
                        "latency_p95_us": s["latency_us"]["p95"], "adaptations": s["adaptations"],
                        "timing_dependent": t["timing"]["timing_dependent_behaviour"], "config_hash": t["config_hash"],
                    })
        return manifest


# ---------------------------------------------------------------- reading
def list_experiments(root: Path | None = None) -> list[dict]:
    manifests = []
    for path in (root or experiments_dir()).glob("*/manifest.json"):
        try:
            manifests.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(manifests, key=lambda m: m.get("id") or "", reverse=True)


def experiment_path(experiment_id: str, root: Path | None = None) -> Path:
    return (root or experiments_dir()) / check_id(experiment_id)


def load_manifest(experiment_id: str, root: Path | None = None) -> dict:
    return json.loads((experiment_path(experiment_id, root) / "manifest.json").read_text())


def trial_path(experiment_id: str, trial_id: str, root: Path | None = None) -> Path:
    return experiment_path(experiment_id, root) / "trials" / check_id(trial_id)


def load_trial_summary(experiment_id: str, trial_id: str, root: Path | None = None) -> dict:
    return json.loads((trial_path(experiment_id, trial_id, root) / "summary.json").read_text())


def load_events(experiment_id: str, trial_id: str, root: Path | None = None) -> list[dict]:
    path = trial_path(experiment_id, trial_id, root) / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _number(value: str):
    if value in ("", "None"):
        return None
    if value in ("True", "False"):
        return value == "True"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def load_blocks(experiment_id: str, trial_id: str, root: Path | None = None) -> list[dict]:
    with (trial_path(experiment_id, trial_id, root) / "blocks.csv").open() as f:
        return [{k: _number(v) for k, v in row.items()} for row in csv.DictReader(f)]


def windowed_scores(blocks: list[dict], window: int) -> dict[str, list]:
    """Accuracy/F1 over a sliding window of whole blocks ending at each block (from confusion counts)."""
    ends, acc, f1 = [], [], []
    tp = fp = tn = fn = n = 0
    queue: list[dict] = []
    for b in blocks:
        queue.append(b)
        tp, fp, tn, fn, n = tp + b["tp"], fp + b["fp"], tn + b["tn"], fn + b["fn"], n + b["n"]
        while n - queue[0]["n"] >= window:
            old = queue.pop(0)
            tp, fp, tn, fn, n = tp - old["tp"], fp - old["fp"], tn - old["tn"], fn - old["fn"], n - old["n"]
        ends.append(b["start"] + b["n"])
        acc.append((tp + tn) / n if n else None)
        f1.append(2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else None)
    return {"x": ends, "accuracy": acc, "f1": f1}
