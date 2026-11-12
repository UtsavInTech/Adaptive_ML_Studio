"""Large registered datasets, read from disk one row at a time.

`StaticScenario` loads a whole file into memory, which suits the Kaggle snapshots (a few MB) but
not a stream of millions of rows. This scenario keeps memory flat: it checks the file's SHA-256
in chunks, then parses each row only when the engine asks for it.

The file is prepared once by a script (e.g. `scripts/prepare_cicids2017.py`) and pinned in
`data/catalog.json` with `"streaming": true`. It must carry a binary `target` column, an
`attack_type` column with the original label, and the catalog's feature columns. Empty feature
fields become NaN, which the pipeline's running-mean imputation fills in.

These datasets have real, dated changes of their own (listed in the schedule file), so the
column-exchange injection used for the Kaggle snapshots is not offered.
"""
from __future__ import annotations

import csv
from array import array
from collections import deque
from datetime import datetime
import hashlib
import json
from pathlib import Path

import numpy as np

from adaptiveml.config import StreamConfig
import adaptiveml.stream.static as static
from adaptiveml.stream.static import _path, catalog

NAN = float("nan")
ARRIVAL_WINDOW = 1_000  # rows over which the recorded arrival rate is measured
MAX_RATE = 1e7  # rows/s cap where many rows share one timestamp
EPOCH = datetime(1970, 1, 1)
_hash_cache: dict[tuple[str, int, int], str] = {}


def file_sha256(path: Path) -> str:
    """SHA-256 of a file, read in 8 MiB chunks; cached per process while size and mtime stay the same."""
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _hash_cache:
        h = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(1 << 23):
                h.update(chunk)
        _hash_cache[key] = h.hexdigest()
    return _hash_cache[key]


class StreamingScenario:
    is_synthetic = False
    drifts = ()
    ground_truth_drifts = ()  # real changes are reported as `schedule`, not as injected ground truth
    current_variant = None

    def __init__(self, cfg: StreamConfig):
        self.cfg = cfg
        self.cursor = -1
        self.attack_type: str | None = None
        entry = next((e for e in catalog() if e["id"] == cfg.dataset), None)
        if entry is None:
            raise ValueError(f"unknown dataset: {cfg.dataset}")
        if not entry.get("streaming"):
            raise ValueError(f"{cfg.dataset} is not a streaming dataset")
        if not entry["available"]:
            raise ValueError(f"dataset file is missing: {entry['file']}; run its preparation script")
        if cfg.injection is not None:
            raise ValueError(f"{entry['name']} has real, dated changes; an added column exchange is not offered")
        if set(entry["labels"].values()) != {0, 1} or len(entry["labels"]) != 2:
            raise ValueError("dataset needs an explicit binary label mapping")
        if cfg.start + cfg.length > entry["rows"]:
            raise ValueError(
                f"requested {cfg.length:,} rows from row {cfg.start:,}; dataset contains {entry['rows']:,}"
            )
        self.entry = entry
        self.path = _path(entry)
        self.sha256 = file_sha256(self.path)
        if self.sha256 != entry["sha256"] or (cfg.dataset_sha256 and self.sha256 != cfg.dataset_sha256):
            raise ValueError("dataset checksum differs from the registered or recorded snapshot")
        root = static.DATA_ROOT.resolve()
        schedule_path = (root / entry["schedule"]).resolve()
        if not schedule_path.is_relative_to(root) or not schedule_path.is_file():
            raise ValueError(f"schedule file is missing: {entry['schedule']}")
        if file_sha256(schedule_path) != entry["schedule_sha256"]:
            raise ValueError("schedule checksum differs from the catalog")
        self.schedule = json.loads(schedule_path.read_text())
        self.feature_names = tuple(entry["features"])
        if len(self.feature_names) < 2 or entry["target"] in self.feature_names:
            raise ValueError("dataset needs at least two features and must exclude the target")
        with self.path.open(newline="") as f:
            header = next(csv.reader(f))
        missing = {*self.feature_names, entry["target"], "attack_type"} - set(header)
        if cfg.arrival == "recorded" and "ts_end" not in header:
            missing.add("ts_end")
        if missing:
            raise ValueError(f"dataset columns do not match the catalog: missing {', '.join(sorted(missing))}")
        self._header = header
        self._times: deque | None = None  # arrival times of recent rows (s), for the recorded rate

    def arrival_rate(self) -> float | None:
        """Rows per second arriving now: the recorded rate over the last ARRIVAL_WINDOW rows, times
        `rate_scale`. None for constant arrival, or before two rows have been read."""
        t = self._times
        if t is None or len(t) < 2:
            return None
        span = t[-1] - t[0]
        rate = (len(t) - 1) / span if span > 0 else MAX_RATE
        return min(MAX_RATE, rate * self.cfg.rate_scale)

    def __iter__(self):
        h = self._header
        fi = [h.index(f) for f in self.feature_names]
        names = self.feature_names
        ti, ai = h.index(self.entry["target"]), h.index("attack_type")
        labels = self.entry["labels"]
        length, width, start = self.cfg.length, len(h), self.cfg.start
        recorded = self.cfg.arrival == "recorded"
        if recorded:
            tsi = h.index("ts_end")
            self._times = times = deque(maxlen=ARRIVAL_WINDOW)
            parse = datetime.fromisoformat
        # The original label of every row read, as small integer codes (2 bytes per row).
        self._codes, self._type_index = array("h"), {}
        add_code, type_index = self._codes.append, self._type_index
        i = -1
        with self.path.open(newline="") as f:
            next(f)
            for _ in range(start):  # skip to the first requested row without parsing it
                next(f)
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i >= length:
                    return
                try:
                    if len(row) != width:
                        raise ValueError(f"expected {width} columns, found {len(row)}")
                    x = {n: (float(row[c]) if row[c] else NAN) for n, c in zip(names, fi)}
                    y = bool(labels[row[ti]])
                except (ValueError, KeyError) as exc:
                    raise ValueError(f"invalid dataset value at CSV line {start + i + 2}: {exc}") from exc
                if recorded:
                    times.append((parse(row[tsi]) - EPOCH).total_seconds())  # naive: no time-zone lookup
                self.cursor = i
                kind = self.attack_type = row[ai]
                code = type_index.get(kind)
                if code is None:
                    code = type_index[kind] = len(type_index)
                add_code(code)
                yield i, x, y
        if i + 1 < length:
            raise ValueError(f"dataset ended after {i + 1:,} rows; {length:,} were requested")

    def inject(self, *args, **kwargs):
        raise ValueError("drift injection is disabled for this dataset; it has real, dated changes")

    def row_types(self) -> tuple[np.ndarray, list[str]] | None:
        """Codes of the original label of each row read so far, and the label each code stands for."""
        if not hasattr(self, "_codes"):
            return None
        return np.frombuffer(self._codes, dtype=np.int16), list(self._type_index)

    def periods(self) -> list[dict]:
        """The dataset's attack periods that start inside the requested rows, in replay row numbers.
        A period already under way at `start` is left out: its beginning is not in the replay."""
        lo, hi = self.cfg.start, self.cfg.start + self.cfg.length
        return [
            p | {"start_row": p["start_row"] - lo, "end_row": p["end_row"] - lo}
            for p in self.schedule["attack_periods"] if lo <= p["start_row"] < hi
        ]

    @property
    def info(self):
        e = self.entry
        return {
            "name": e["name"], "real": True, "dataset": e["id"],
            "source": e["source"], "sha256": self.sha256,
            "license": e["license"], "order": e["order"],
            "target": e["target"], "labels": e["labels"],
            "feature_names": list(self.feature_names), "n_features": len(self.feature_names),
            "length": self.cfg.length, "available_rows": e["rows"], "start": self.cfg.start,
            "arrival": self.cfg.arrival, "rate_scale": self.cfg.rate_scale,
            "noise": None, "drifts": [],
            "drift_ground_truth": "schedule",
            "injection": None,
            "schedule": {
                "attack_periods": self.periods(),
                "day_start_rows": {
                    d: r - self.cfg.start for d, r in self.schedule["day_start_rows"].items()
                    if self.cfg.start <= r < self.cfg.start + self.cfg.length
                },
                "episode_gap_seconds": self.schedule["episode_gap_seconds"],
            },
            "notes": e.get("notes", ""),
        }
