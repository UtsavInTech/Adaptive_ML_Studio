"""Immutable, registered Kaggle files replayed in their documented order.

Only numeric binary-classification datasets are supported. File bytes are pinned by
SHA-256; labels are mapped explicitly, never inferred from truthiness. No shuffle,
resampling or fitted global preprocessing is applied.

By default the rows are replayed untouched ("natural replay"), and nothing is known about
where the data's own drift lies. A run may instead ask for one *controlled* change
(`StreamConfig.injection`): from a known row onward the values of two input columns are
exchanged. Rows, order and labels stay as recorded. That gives a ground-truth position, so
scores before, during and after the change become measurable. Such a run is real data plus an
injected change, and its scenario record says so.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

from adaptiveml.config import StreamConfig

DATA_ROOT = Path(__file__).resolve().parents[3] / "data"


def catalog() -> list[dict]:
    path = DATA_ROOT / "catalog.json"
    if not path.exists():
        return []
    entries = json.loads(path.read_text())
    return [dict(entry, available=_path(entry).is_file()) for entry in entries]


def _path(entry: dict) -> Path:
    path = (DATA_ROOT / entry["file"]).resolve()
    if not path.is_relative_to(DATA_ROOT.resolve()):
        raise ValueError("dataset file must be inside the data directory")
    return path


DRIFT_KINDS = {
    "abrupt": {
        "label": "Sudden",
        "also": "abrupt drift",
        "said": "The data changes all at once, at one row.",
        "example": "A sensor is replaced overnight, or a pricing rule changes on a set date.",
    },
    "gradual": {
        "label": "Gradual",
        "also": "gradual drift",
        "said": "Old and new behaviour are mixed for a while. New-style rows become more frequent until only they remain.",
        "example": "Customers move to a new app version over several weeks; both versions are in use meanwhile.",
    },
    "incremental": {
        "label": "Incremental",
        "also": "incremental drift",
        "said": "Every row shifts a little further from the old behaviour towards the new one, in small steps.",
        "example": "A sensor slowly loses calibration, reading slightly more wrong each day.",
    },
    "recurring": {
        "label": "Recurring",
        "also": "recurring / reoccurring concepts",
        "said": "The data switches to the new behaviour, then back to the old one, and repeats.",
        "example": "Weekday and weekend patterns, or seasons that come round again.",
    },
}


@dataclass(frozen=True)
class InjectedChange:
    """Ground truth for one controlled change: where it starts and how long it takes."""

    index: int  # first row the change can affect
    width: int  # rows until the change is complete
    kind: str
    from_variant: int  # 0 = columns as recorded, 1 = columns exchanged
    to_variant: int
    label_flip_fraction: float | None = None  # not defined for a column exchange

    @property
    def start(self) -> int:
        return self.index

    @property
    def end(self) -> int:
        return self.index + self.width


def _injection_rng(injection) -> random.Random:
    """A fixed stream of draws per injection, independent of the trial seed.

    Gradual drift decides row by row whether a row is old-style or new-style. Tying that to the
    model seed would give different seeds different data; this keeps "model seeds never change
    the data" true for injected runs as well.
    """
    key = f"csv.injection:{injection.kind}:{injection.start}:{injection.width}:{injection.swap[0]}:{injection.swap[1]}"
    return random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big"))


class StaticScenario:
    is_synthetic = False
    drifts = ()

    def __init__(self, cfg: StreamConfig):
        self.cfg = cfg
        self.cursor = -1
        self.injection = cfg.injection
        self.entry = next((e for e in catalog() if e["id"] == cfg.dataset), None)
        if self.entry is None:
            raise ValueError(f"unknown dataset: {cfg.dataset}")
        entry = self.entry
        if not entry["available"]:
            raise ValueError(f"dataset file is missing: {entry['file']}")
        raw = _path(entry).read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        if self.sha256 != entry["sha256"] or (cfg.dataset_sha256 and self.sha256 != cfg.dataset_sha256):
            raise ValueError("dataset checksum differs from the registered or recorded snapshot")
        self._text = raw.decode("utf-8-sig")
        self.feature_names = tuple(entry["features"])
        if len(self.feature_names) < 2 or entry["target"] in self.feature_names:
            raise ValueError("dataset needs at least two features and must exclude the target")
        if set(entry["labels"].values()) != {0, 1} or len(entry["labels"]) != 2:
            raise ValueError("dataset needs an explicit binary label mapping")
        if cfg.length > entry["rows"]:
            raise ValueError(f"requested {cfg.length} rows; dataset contains {entry['rows']}")
        if self.injection is not None:
            unknown = [f for f in self.injection.swap if f not in self.feature_names]
            if unknown:
                raise ValueError(f"cannot exchange unknown column(s): {', '.join(unknown)}")
        # Validate the entire source before a run can produce a misleading partial result.
        count = sum(1 for _ in self._rows())
        if count != entry["rows"]:
            raise ValueError(f"dataset row count differs from catalog: {count}")

    def _rows(self):
        reader = csv.DictReader(io.StringIO(self._text))
        needed = {*self.feature_names, self.entry["target"]}
        if not reader.fieldnames or not needed.issubset(reader.fieldnames):
            raise ValueError("dataset columns do not match the catalog")
        for line, row in enumerate(reader, 2):
            try:
                x = {f: float(row[f]) for f in self.feature_names}
                if not all(math.isfinite(v) for v in x.values()):
                    raise ValueError("non-finite feature")
                y = bool(self.entry["labels"][row[self.entry["target"]].strip()])
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"invalid dataset value at CSV line {line}: {exc}") from exc
            yield x, y

    def _share(self, i: int, rng: random.Random | None) -> float:
        """How much of row `i` uses the exchanged arrangement: 0 = as recorded, 1 = fully exchanged."""
        inj = self.injection
        if i < inj.start:
            return 0.0
        if inj.kind == "abrupt":
            return 1.0
        if inj.kind == "recurring":
            return 1.0 if ((i - inj.start) // inj.period) % 2 == 0 else 0.0
        progress = min(1.0, (i - inj.start + 1) / inj.width)
        if inj.kind == "incremental":
            return progress
        # gradual: the row is either old-style or new-style; the chance of new-style rises to 1
        return 1.0 if progress >= 1.0 or rng.random() < progress else 0.0

    def __iter__(self):
        inj = self.injection
        if inj is None:
            for i, (x, y) in enumerate(self._rows()):
                if i >= self.cfg.length:
                    break
                self.cursor = i
                yield i, x, y
            return
        a, b = inj.swap
        rng = _injection_rng(inj) if inj.kind == "gradual" else None
        for i, (x, y) in enumerate(self._rows()):
            if i >= self.cfg.length:
                break
            share = self._share(i, rng)
            if share >= 1.0:
                # An exact exchange: blending with share 1.0 is not bit-identical in floating point.
                x[a], x[b] = x[b], x[a]
            elif share > 0.0:
                xa, xb = x[a], x[b]
                x[a] = (1.0 - share) * xa + share * xb
                x[b] = (1.0 - share) * xb + share * xa
            self.cursor = i
            yield i, x, y

    @property
    def ground_truth_drifts(self) -> tuple[InjectedChange, ...]:
        inj = self.injection
        if inj is None:
            return ()
        if inj.kind != "recurring":
            return (InjectedChange(inj.start, inj.width, inj.kind, 0, 1),)
        switches = range(inj.start, self.cfg.length, inj.period)
        return tuple(InjectedChange(at, 1, inj.kind, k % 2, (k + 1) % 2) for k, at in enumerate(switches))

    @property
    def current_variant(self) -> int | None:
        """0 while the columns are as recorded, 1 while they are exchanged; None without an injection."""
        if self.injection is None:
            return None
        return int(self._share(max(self.cursor, 0), None) >= 0.5) if self.injection.kind != "gradual" else int(
            self.cursor >= self.injection.end
        )

    def inject(self, *args, **kwargs):
        raise ValueError("drift injection is disabled for real dataset replay")

    @property
    def info(self):
        inj = self.injection
        changes = [
            {"index": c.index, "width": c.width, "kind": c.kind, "start": c.start, "end": c.end,
             "from_variant": c.from_variant, "to_variant": c.to_variant, "label_flip_fraction": None}
            for c in self.ground_truth_drifts
        ]
        injected = None if inj is None else {
            **inj.model_dump(mode="json"),
            "end": inj.end,
            "label": DRIFT_KINDS[inj.kind]["label"],
            "what": f"The values of the columns {inj.swap[0]} and {inj.swap[1]} are exchanged. "
                    "Rows, order and labels are unchanged.",
        }
        return {
            "name": self.entry["name"], "real": True, "dataset": self.entry["id"],
            "source": self.entry["source"], "sha256": self.sha256,
            "license": self.entry["license"], "order": self.entry["order"],
            "target": self.entry["target"], "labels": self.entry["labels"],
            "feature_names": list(self.feature_names), "n_features": len(self.feature_names),
            "length": self.cfg.length, "available_rows": self.entry["rows"],
            "noise": None, "drifts": changes,
            "drift_ground_truth": "unavailable" if inj is None else "injected",
            "injection": injected,
            "notes": self.entry.get("notes", ""),
        }
