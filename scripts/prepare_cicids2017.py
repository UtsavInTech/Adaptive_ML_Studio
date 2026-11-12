"""Rebuild the chronological CIC-IDS2017 stream from the corrected release.

Source: the improved CIC-IDS2017 of Liu, Engelen et al. (IEEE CNS 2022), published by
KU Leuven DistriNet. The archive is checked against a pinned SHA-256 before anything is read.

    backend/.venv/bin/python scripts/prepare_cicids2017.py            # download, then prepare
    backend/.venv/bin/python scripts/prepare_cicids2017.py --archive /path/CICIDS2017_improved.zip

What preparation does, and nothing else:
- Puts all five days in one stream, ordered by the time each flow *ends* (start + duration). A
  detector can only score a flow once its features are complete, so this is the order in which a
  gateway would see them. Ties keep a fixed order (start time, day, original id).
- Writes a binary label: attack = ATTACK. Flows the authors mark "Attempted" are BENIGN, as the
  authors instruct. The original label is kept, unchanged, in `attack_type`.
- Keeps every feature value as the original text. Infinite or NaN rates (zero-duration flows) are
  written as empty fields, which the pipeline's running-mean imputation fills in.
- Lists the attack periods (the dataset's own, dated drift points) in a schedule file.
No row is dropped, resampled or shuffled, and no label is changed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = "cicids2017"
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")
# Columns that identify a host or connection, or that carry the label. Never model inputs.
NOT_FEATURES = {"id", "Flow ID", "Src IP", "Src Port", "Dst IP", "Timestamp", "Label", "Attempted Category"}
EPISODE_GAP_S = 600  # a new attack period starts after 10 minutes without that attack type
EPOCH = datetime(1970, 1, 1)


def entry() -> dict:
    catalog = json.loads((ROOT / "data/catalog.json").read_text())
    return next(e for e in catalog if e["id"] == DATASET_ID)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 23):
            h.update(chunk)
    return h.hexdigest()


def micros(ts: str) -> int:
    return (datetime.fromisoformat(ts) - EPOCH) // _US


_US = datetime(1970, 1, 1, 0, 0, 0, 1) - EPOCH


def iso(us: int) -> str:
    return (EPOCH + us * _US).isoformat(sep=" ", timespec="microseconds")


def fetch(e: dict, archive: Path | None, raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / "CICIDS2017_improved.zip"
    if archive is not None:
        if archive.resolve() != target.resolve():
            shutil.copyfile(archive, target)
    elif not target.exists():
        print(f"Downloading {e['download_url']} …", flush=True)
        with urlopen(e["download_url"]) as response, target.open("wb") as out:
            shutil.copyfileobj(response, out, 1 << 23)
    if sha256(target) != e["archive_sha256"]:
        raise SystemExit("Archive checksum differs from the catalog; inspect upstream changes before replacing data")
    with ZipFile(target) as z:
        for day in DAYS:
            dest = raw_dir / f"{day}.csv"
            if not dest.exists() or dest.stat().st_size != z.getinfo(f"{day}.csv").file_size:
                z.extract(f"{day}.csv", raw_dir)
    return target


def index_rows(raw_dir: Path):
    """Pass 1: per row, its end time, start time, day, original id and byte offset."""
    cols = {k: [] for k in ("end", "start", "day", "id", "offset")}
    header = None
    for d, day in enumerate(DAYS):
        with (raw_dir / f"{day}.csv").open("rb") as f:
            first = f.readline().decode()
            h = next(csv.reader([first]))
            if header is None:
                header = h
            elif h != header:
                raise SystemExit(f"{day}.csv has a different header")
            ti, di, ii = h.index("Timestamp"), h.index("Flow Duration"), h.index("id")
            offset = f.tell()
            for line in f:
                row = line.decode().rstrip("\r\n").split(",")
                if len(row) != len(h):
                    raise SystemExit(f"{day}.csv: unexpected column count at byte {offset}")
                start = micros(row[ti])
                cols["start"].append(start)
                cols["end"].append(start + int(row[di]))
                cols["day"].append(d)
                cols["id"].append(int(row[ii]))
                cols["offset"].append(offset)
                offset += len(line)
        print(f"  indexed {day}: {len(cols['day']):,} rows so far", flush=True)
    arrays = {k: np.asarray(v, dtype=np.int64) for k, v in cols.items()}
    order = np.lexsort((arrays["id"], arrays["day"], arrays["start"], arrays["end"]))
    return header, arrays, order


def write_stream(raw_dir: Path, out_dir: Path, header, arrays, order):
    """Pass 2: write rows in end-time order; collect constant columns and attack periods."""
    features = [c for c in header if c not in NOT_FEATURES]
    fi = [header.index(c) for c in features]
    li, ai = header.index("Label"), header.index("Attempted Category")
    seen = [set() for _ in features]
    blanks = {}
    labels, binary = {}, {"BENIGN": 0, "ATTACK": 0}
    episodes, open_ep = [], {}
    day_starts = {}
    files = [(raw_dir / f"{day}.csv").open("rb") for day in DAYS]
    out_path = out_dir / "cicids2017-chronological.csv"
    try:
        with out_path.open("w", newline="") as out:
            w = csv.writer(out, lineterminator="\n")
            w.writerow(["row", "source_day", "source_id", "ts_start", "ts_end", "attack_type", "label", *features])
            for row_no, k in enumerate(order):
                d = int(arrays["day"][k])
                f = files[d]
                f.seek(int(arrays["offset"][k]))
                row = f.readline().decode().rstrip("\r\n").split(",")
                original = row[li]
                attempted = row[ai] != "-1"
                label = "BENIGN" if original == "BENIGN" or attempted or original.endswith(" - Attempted") else "ATTACK"
                labels[original] = labels.get(original, 0) + 1
                binary[label] += 1
                day_starts.setdefault(DAYS[d], row_no)
                end_us = int(arrays["end"][k])
                values = []
                for j, c in enumerate(fi):
                    v = row[c]
                    x = float(v)
                    if not math.isfinite(x):
                        blanks[features[j]] = blanks.get(features[j], 0) + 1
                        v = ""
                    elif len(seen[j]) < 2:
                        seen[j].add(x)
                    values.append(v)
                if label == "ATTACK":
                    ep = open_ep.get(original)
                    if ep is None or (end_us - ep["_last"]) > EPISODE_GAP_S * 1_000_000:
                        ep = {"attack_type": original, "start_row": row_no, "start": iso(end_us), "flows": 0}
                        episodes.append(ep)
                        open_ep[original] = ep
                    ep["end_row"], ep["end"], ep["_last"] = row_no, iso(end_us), end_us
                    ep["flows"] += 1
                w.writerow([row_no, DAYS[d], int(arrays["id"][k]), iso(int(arrays["start"][k])), iso(end_us),
                            original, label, *values])
                if (row_no + 1) % 500_000 == 0:
                    print(f"  wrote {row_no + 1:,} rows", flush=True)
    finally:
        for f in files:
            f.close()
    for ep in episodes:
        del ep["_last"]
    constant = [c for c, s in zip(features, seen) if len(s) < 2]
    return out_path, {
        "rows": len(order),
        "columns_written": features,
        "constant_columns": constant,
        "model_features": [c for c in features if c not in constant],
        "blank_values": blanks,
        "labels_original": dict(sorted(labels.items())),
        "labels_binary": binary,
        "day_start_rows": day_starts,
        "first_flow_end": iso(int(arrays["end"][order[0]])),
        "last_flow_end": iso(int(arrays["end"][order[-1]])),
        "episode_gap_seconds": EPISODE_GAP_S,
        "attack_periods": sorted(episodes, key=lambda e: e["start_row"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", type=Path, help="a CICIDS2017_improved.zip downloaded by hand")
    args = parser.parse_args()
    e = entry()
    folder = ROOT / "data" / DATASET_ID
    raw_dir = folder / "raw"
    fetch(e, args.archive, raw_dir)
    print("Indexing rows …", flush=True)
    header, arrays, order = index_rows(raw_dir)
    out_dir = folder / "prepared"
    out_dir.mkdir(parents=True, exist_ok=True)
    print("Writing the chronological stream …", flush=True)
    out_path, schedule = write_stream(raw_dir, out_dir, header, arrays, order)
    schedule_path = out_dir / "schedule.json"
    schedule_path.write_text(json.dumps(schedule, indent=1) + "\n")
    got = {"sha256": sha256(out_path), "schedule_sha256": sha256(schedule_path)}
    print(f"Prepared {schedule['rows']:,} rows → {out_path}")
    for key, value in got.items():
        pinned = e.get(key)
        status = "matches catalog" if pinned == value else ("NOT IN CATALOG YET" if not pinned else "DIFFERS FROM CATALOG")
        print(f"  {key}: {value} ({status})")
    if any(e.get(k) and e[k] != v for k, v in got.items()):
        sys.exit(1)


if __name__ == "__main__":
    main()
