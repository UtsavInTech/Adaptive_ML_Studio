"""Shared helpers for the results analysis (research_testbed/research).

Reads saved run bundles only. Caches derived arrays in $ANALYSIS_CACHE (default: ./cache next to
this folder) so the 1.1 GB stream file is read once.
"""
from __future__ import annotations

import csv
import gzip
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / "results" / "experiments"
DATA = ROOT / "data" / "cicids2017" / "prepared"
CSV_PATH = DATA / "cicids2017-chronological.csv"
SCHEDULE = json.loads((DATA / "schedule.json").read_text())
CACHE = Path(os.environ.get("ANALYSIS_CACHE", Path(__file__).resolve().parents[1] / "cache"))
FIG = Path(__file__).resolve().parents[1] / "figures"

RUNS = {
    "p2_core": "20261111-145934-568975-experiment-phase-2-core-methods-on-cic-ids2017",
    "p2_srp": "20261111-145938-211780-experiment-phase-2-srp-methods-on-cic-ids2017",
    "p2_levbag": "20261111-145941-337166-experiment-phase-2-levbag-methods-on-cic-ids2017",
    "p3": "20261111-165347-608995-experiment-phase-3-adaptive-vs-joint-standard-and-g",
    "p3_nogating": "20261111-171732-036467-experiment-phase-3-ablation-no-gating",
    "p3_nor2": "20261111-172314-227666-experiment-phase-3-ablation-no-r2",
    "p3_nor3": "20261111-172824-164084-experiment-phase-3-ablation-no-r3",
    "p3_nor5": "20261111-174022-182362-experiment-phase-3-ablation-no-r5",
    "q_core": "20261111-174330-804788-experiment-protocol-v1-quick-core",
    "q_ens": "20261111-175111-293327-experiment-protocol-v1-quick-ensembles",
    "mem_full": "20261111-194052-088567-experiment-protocol-v1-memory-full",
    "mem_nor5": "20261111-195427-125877-experiment-protocol-v1-memory-without-r5",
}
for line in (ROOT / "research_testbed/protocol/generated-quick/runs.txt").read_text().split("\n"):
    if line.strip():
        k, v = line.split("\t")
        RUNS.setdefault("q_" + k, v)


def trial_dirs(run_key: str) -> dict[str, Path]:
    d = EXP / RUNS[run_key] / "trials"
    return {p.name: p for p in sorted(d.iterdir()) if p.is_dir()}


def summary(trial: Path) -> dict:
    return json.loads((trial / "summary.json").read_text())


def outcomes(trial: Path) -> dict[str, np.ndarray]:
    """Columns of outcomes.csv.gz as numpy arrays (cached as .npz)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / ("out_" + trial.parent.parent.name[:40] + "_" + trial.name + ".npz")
    if key.exists():
        z = np.load(key)
        return {k: z[k] for k in z.files}
    with gzip.open(trial / "outcomes.csv.gz", "rt") as f:
        r = csv.reader(f)
        head = next(r)
        cols = [[] for _ in head]
        for row in r:
            for j, v in enumerate(row):
                cols[j].append(v)
    out = {}
    for h, c in zip(head, cols):
        if h.endswith("_service_ns") or h == "i":
            out[h] = np.asarray(c, dtype=np.int64)
        else:
            out[h] = np.asarray([1 if v in ("1", "True", "true") else 0 for v in c], dtype=np.int8)
    np.savez(key, **out)
    return out


def events(trial: Path) -> list[dict]:
    return [json.loads(l) for l in (trial / "events.jsonl").read_text().splitlines() if l.strip()]


def blocks(trial: Path) -> dict[str, np.ndarray]:
    with open(trial / "blocks.csv") as f:
        r = csv.DictReader(f)
        rows = list(r)
    out = {}
    for k in rows[0]:
        vals = [row[k] for row in rows]
        try:
            out[k] = np.asarray([float(v) if v not in ("", "None") else np.nan for v in vals])
        except ValueError:
            out[k] = np.asarray(vals)
    return out


def labels_original() -> tuple[np.ndarray, list[str]]:
    """Original attack_type label code for every stream row (cached)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / "attack_type.npz"
    if f.exists():
        z = np.load(f, allow_pickle=True)
        return z["codes"], list(z["names"])
    names: dict[str, int] = {}
    codes = np.zeros(SCHEDULE["rows"], dtype=np.int16)
    with open(CSV_PATH, newline="") as fh:
        r = csv.reader(fh)
        head = next(r)
        j = head.index("attack_type")
        for n, row in enumerate(r):
            codes[n] = names.setdefault(row[j], len(names))
    inv = [None] * len(names)
    for k, v in names.items():
        inv[v] = k
    np.savez(f, codes=codes, names=np.asarray(inv, dtype=object))
    return codes, inv


def load_features(start: int, length: int, step: int = 1):
    """Numeric model features for rows [start, start+length) every `step` rows (float32), with
    binary labels and original attack types."""
    feats = SCHEDULE["model_features"]
    with open(CSV_PATH, newline="") as fh:
        r = csv.reader(fh)
        head = next(r)
        idx = [head.index(c) for c in feats]
        jl, ja = head.index("label"), head.index("attack_type")
        X, y, at = [], [], []
        for n, row in enumerate(r):
            if n < start:
                continue
            if n >= start + length:
                break
            if (n - start) % step:
                continue
            X.append([float(row[k]) if row[k] not in ("", "nan", "NaN") else np.nan for k in idx])
            y.append(0 if row[jl] == "BENIGN" else 1)
            at.append(row[ja])
    return np.asarray(X, dtype=np.float64), np.asarray(y, dtype=np.int8), np.asarray(at), feats
