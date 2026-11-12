"""Phase 7, on the laptop: bring a device bundle into the Studio.

    backend/.venv/bin/python research_testbed/device/import_bundle.py device-20261112-101500.tar.gz

The bundle is the .tar.gz that run_on_device.py wrote. Its runs are copied into results/experiments,
where the Studio lists them (Testbed → Real device). The calibration, device record and summary go
to research_testbed/results/device/<tag>/. Nothing existing is overwritten.

The archive is treated as untrusted: only plain files with expected names are written, and only
inside those two folders.
"""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from adaptiveml.results import check_id, experiments_dir  # noqa: E402

EXTRAS = {"device.json", "summary.md", "effort_cost_calibration.json"}
SUFFIXES = {".json", ".csv", ".yaml", ".md", ".jsonl", ".gz", ".txt"}
MAX_FILE = 600 * 1024 * 1024


def plan(tar: tarfile.TarFile, runs: Path, extras: Path) -> tuple[str, list[tuple[tarfile.TarInfo, Path]]]:
    """Where each member goes; raises ValueError on anything unexpected."""
    tag, out = None, []
    for member in tar.getmembers():
        parts = PurePosixPath(member.name).parts
        if member.isdir():
            continue
        if not member.isfile() or member.name.startswith("/") or ".." in parts or len(parts) < 2:
            raise ValueError(f"unexpected entry in the bundle: {member.name}")
        if member.size > MAX_FILE or PurePosixPath(member.name).suffix not in SUFFIXES:
            raise ValueError(f"unexpected file in the bundle: {member.name}")
        tag = tag or check_id(parts[0])
        if parts[0] != tag:
            raise ValueError("the bundle has more than one top folder")
        rest = parts[1:]
        if rest[0] == "experiments" and len(rest) >= 3:
            for part in rest[1:]:
                if part.startswith("."):
                    raise ValueError(f"unexpected file in the bundle: {member.name}")
            out.append((member, runs / check_id(rest[1]) / Path(*rest[2:])))
        elif (len(rest) == 1 and rest[0] in EXTRAS) or (len(rest) == 2 and rest[0] == "presets"):
            out.append((member, extras / tag / Path(*rest)))
        else:
            raise ValueError(f"unexpected file in the bundle: {member.name}")
    if tag is None:
        raise ValueError("the bundle is empty")
    return tag, out


def import_bundle(bundle: Path, runs: Path | None = None, extras: Path | None = None) -> dict:
    runs = (runs or experiments_dir()).resolve()
    extras = (extras or ROOT / "research_testbed" / "results" / "device").resolve()
    with tarfile.open(bundle, "r:gz") as tar:
        tag, members = plan(tar, runs, extras)
        ids = sorted({target.relative_to(runs).parts[0] for _, target in members if target.is_relative_to(runs)})
        if not ids:
            raise ValueError("the bundle holds no runs")
        for run_id in ids:
            if (runs / run_id).exists():
                raise ValueError(f"run {run_id} is already here; nothing was imported")
            if not any(t == runs / run_id / "manifest.json" for _, t in members):
                raise ValueError(f"run {run_id} has no manifest.json")
        if (extras / tag).exists():
            raise ValueError(f"{extras / tag} already exists; nothing was imported")
        for member, target in members:
            if not (target.resolve().is_relative_to(runs) or target.resolve().is_relative_to(extras)):
                raise ValueError(f"unexpected entry in the bundle: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            with target.open("xb") as f:
                while chunk := source.read(1 << 20):
                    f.write(chunk)
    device_file = extras / tag / "device.json"
    device = json.loads(device_file.read_text()) if device_file.is_file() else {}
    return {"tag": tag, "runs": ids, "extras": str(extras / tag), "device": device.get("name"),
            "real_device": device.get("real_device")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        done = import_bundle(args.bundle)
    except (ValueError, tarfile.TarError, OSError) as e:
        sys.exit(f"Not imported: {e}")
    kind = "real device" if done["real_device"] else "REHEARSAL, not a device"
    print(f"Imported {len(done['runs'])} run(s) from {done['device']} ({kind}):")
    for run_id in done["runs"]:
        print(f"  results/experiments/{run_id}")
    print(f"Summary, calibration and device record: {done['extras']}")
    print("Open the Studio → Testbed → Real device.")


if __name__ == "__main__":
    main()
