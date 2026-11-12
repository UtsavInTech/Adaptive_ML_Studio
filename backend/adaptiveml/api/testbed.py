"""Research testbed screen: what the setup form offers, and the generated reports.

The form itself posts an ordinary ExperimentConfig to /api/experiments; nothing here runs anything.
Reports are files written by research_testbed/scripts/report.py. They are served read-only, and only
from inside the reports folder.
"""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from adaptiveml.config.profiles import BUILTIN_PROFILES, per_sample_budget_ns
from adaptiveml.results import REPO_ROOT
import adaptiveml.stream.static as static

router = APIRouter(prefix="/api/testbed")

TIERS = ("standard", "small_sim", "micro_sim", "memory_sim")
TIER_NOTES = {
    "standard": "No budget: the method may use as much of this computer as it needs.",
    "small_sim": "Budgets meant to resemble a Raspberry Pi class device.",
    "micro_sim": "Budgets meant to resemble an IoT gateway. No replacement model may train alongside.",
    "memory_sim": "Only a model-memory budget, so memory rule R5 is the one resource rule that can act.",
}

# Mean µs per row measured in earlier whole-stream runs on an 8 GB Apple Silicon Mac (research_testbed
# README, phases 2-3), plus reading the file. Used only for a rough duration estimate in the form.
METHODS = [
    {"id": "no_change", "said": "Repeats the previous row's label and never looks at the inputs. The reference to beat.", "us_per_row": 90},
    {"id": "static", "said": "Learns once from the warm-up rows, then never changes.", "us_per_row": 30},
    {"id": "incremental", "said": "Keeps learning from every labelled row, but never checks for drift.", "us_per_row": 200},
    {"id": "adaptive", "said": "Keeps learning, watches its own errors, and trains a replacement model when they rise (the earlier controller).", "us_per_row": 125},
    {"id": "joint", "said": "The adaptive pipeline under the joint controller: rules R1–R5 read drift, accuracy, deadlines, CPU and memory together.", "us_per_row": 210},
    {"id": "effort", "said": "The proposed method: the same pipeline, with more work on rows in hard stretches and less on easy ones, holding the CPU budget on average (research testbed; under evaluation).", "us_per_row": 100},
    {"id": "arf", "said": "Adaptive Random Forest: ten trees that each watch for drift and are replaced one at a time.", "us_per_row": 660},
    {"id": "srp", "said": "Streaming Random Patches: ten trees, each on a random subset of the inputs.", "us_per_row": 4_800, "slow": True},
    {"id": "lev_bag", "said": "Leveraging bagging: ten trees, each on a reweighted copy of the rows.", "us_per_row": 5_750, "slow": True},
]
READ_US_PER_ROW = 15

RULES = [
    {"id": "R1", "title": "Drift, resources spare",
     "said": "When the detector confirms drift and there is spare CPU and memory, train a replacement model in the background and swap it in once it is ready."},
    {"id": "R2", "title": "Drift, resources tight",
     "said": "When drift is confirmed but resources are tight, adapt cheaply: reset the model at once instead of training a replacement alongside."},
    {"id": "R3", "title": "Deadline misses",
     "said": "When too many rows take longer than the per-row deadline, halve the features, process only the features in use, then learn from fewer rows. Steps back up when calm."},
    {"id": "R4", "title": "Low accuracy",
     "said": "When recent accuracy falls below 70 % and resources are spare, retrain a fresh model on the last 2,000 labelled rows."},
    {"id": "R5", "title": "Memory over budget",
     "said": "When the model grows past the memory budget, drop the replacement model, then start a fresh model, then halve the features."},
]
RESOURCE_CHECK = {
    "id": "resource_gating", "title": "Resource checks",
    "said": "R1, R2 and R4 look at CPU and memory before acting. Switched off, they act as if resources were always spare (an ablation).",
}

# A slice that the research protocol uses for its quick runs: Wednesday's denial-of-service attacks.
WEDNESDAY_DOS = {"id": "wednesday_dos", "label": "Wednesday DoS attacks", "start": 693_702, "length": 300_000,
                 "said": "Slowloris, Slowhttptest, Hulk and GoldenEye. The protocol's quick slice."}


def reports_dir() -> Path:
    return Path(os.environ.get("ADAPTIVEML_REPORTS_DIR", REPO_ROOT / "research_testbed" / "reports")).resolve()


def _schedule(entry: dict) -> dict | None:
    root = static.DATA_ROOT.resolve()
    path = (root / entry.get("schedule", "")).resolve()
    if not entry.get("schedule") or not path.is_relative_to(root) or not path.is_file():
        return None
    data = json.loads(path.read_text())
    return {k: data.get(k) for k in ("day_start_rows", "attack_periods", "first_flow_end", "last_flow_end")}


def _slices(rows: int, schedule: dict | None) -> list[dict]:
    out = [{"id": "week", "label": "Whole week", "start": 0, "length": rows, "said": "All five days in one stream."}]
    if schedule and schedule.get("day_start_rows"):
        days = sorted(schedule["day_start_rows"].items(), key=lambda kv: kv[1])
        for k, (day, start) in enumerate(days):
            end = days[k + 1][1] if k + 1 < len(days) else rows
            out.append({"id": day, "label": day.capitalize(), "start": start, "length": end - start,
                        "said": "One day of traffic, as recorded."})
    if rows >= WEDNESDAY_DOS["start"] + WEDNESDAY_DOS["length"]:
        out.append(dict(WEDNESDAY_DOS))
    return out


def _tier(name: str) -> dict:
    p = BUILTIN_PROFILES[name]
    b = p.budgets
    cpu = per_sample_budget_ns(p, None)
    return {
        "name": p.name, "label": p.label, "simulated": p.simulated, "placeholder": p.placeholder,
        "note": TIER_NOTES.get(name, ""),
        "budgets": {
            "cpu_us_per_row": None if cpu is None else cpu / 1e3,
            "deadline_ms": b.latency_deadline_ms,
            "model_memory_mib": b.model_memory_mib,
            "background_replacement": b.allow_background,
            "max_update_stride": b.max_update_stride,
            "min_features": b.min_features,
        },
    }


@router.get("/options")
def options() -> dict:
    datasets = []
    for entry in static.catalog():
        if not entry.get("streaming"):
            continue
        schedule = _schedule(entry)
        datasets.append({
            "id": entry["id"], "name": entry["name"], "rows": entry["rows"], "available": entry["available"],
            "sha256": entry["sha256"], "n_features": len(entry.get("features", [])),
            "schedule": schedule, "slices": _slices(entry["rows"], schedule),
        })
    return {
        "datasets": datasets,
        "tiers": [_tier(name) for name in TIERS if name in BUILTIN_PROFILES],
        "methods": METHODS,
        "read_us_per_row": READ_US_PER_ROW,
        "rules": RULES,
        "resource_check": RESOURCE_CHECK,
        "defaults": {"warmup": 1_000, "seeds": [11], "slice": WEDNESDAY_DOS["id"], "large_rows": 300_000},
    }


# ---------------------------------------------------------------- reports
SERVED = {".md": "text/markdown; charset=utf-8", ".csv": "text/csv; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml"}


def _report_folder(name: str) -> Path:
    root = reports_dir()
    folder = (root / name).resolve()
    if "/" in name or "\\" in name or name.startswith(".") or folder.parent != root:
        raise HTTPException(400, "invalid report name")
    if not (folder / "report.md").is_file():
        raise HTTPException(404, "not found")
    return folder


def _files(folder: Path, sub: str, suffixes: tuple[str, ...]) -> list[str]:
    path = folder / sub
    if not path.is_dir():
        return []
    return sorted(f"{sub}/{p.name}" for p in path.iterdir() if p.is_file() and p.suffix in suffixes)


@router.get("/reports")
def reports() -> list[dict]:
    root = reports_dir()
    if not root.is_dir():
        return []
    out = []
    for folder in sorted(root.iterdir()):
        md = folder / "report.md"
        if folder.is_dir() and not folder.name.startswith(".") and md.is_file():
            title = next((line[2:].strip() for line in md.read_text().splitlines() if line.startswith("# ")), folder.name)
            out.append({
                "name": folder.name, "title": title, "modified": md.stat().st_mtime,
                "figures": len(_files(folder, "figures", (".png",))), "tables": len(_files(folder, "tables", (".csv",))),
            })
    return sorted(out, key=lambda r: -r["modified"])


@router.get("/reports/{name}")
def report(name: str) -> dict:
    folder = _report_folder(name)
    tables = []
    for rel in _files(folder, "tables", (".csv",)):
        with (folder / rel).open(newline="") as f:
            rows = list(csv.reader(io.StringIO(f.read())))
        tables.append({"path": rel, "columns": rows[0] if rows else [], "rows": rows[1:]})
    return {
        "name": name,
        "markdown": (folder / "report.md").read_text(),
        "figures": [{"path": rel, "svg": rel[:-4] + ".svg" if (folder / (rel[:-4] + ".svg")).is_file() else None}
                    for rel in _files(folder, "figures", (".png",))],
        "tables": tables,
    }


@router.get("/reports/{name}/files/{path:path}")
def report_file(name: str, path: str, download: bool = False) -> FileResponse:
    folder = _report_folder(name)
    target = (folder / path).resolve()
    if not target.is_relative_to(folder) or target.suffix not in SERVED:
        raise HTTPException(400, "invalid file path")
    if not target.is_file():
        raise HTTPException(404, "not found")
    # An SVG served from this origin could carry script; it is only ever offered as a download.
    attach = download or target.suffix == ".svg"
    return FileResponse(
        target, media_type=SERVED[target.suffix],
        filename=f"{name}-{target.name}" if attach else None,
        content_disposition_type="attachment" if attach else "inline",
        headers={"Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'",
                 "X-Content-Type-Options": "nosniff"},
    )
