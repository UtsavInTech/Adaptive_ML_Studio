"""Capture the measurement environment so every timing result states where it was measured."""

from __future__ import annotations

import importlib.metadata
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

import psutil


def _run(*cmd: str) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _power_source() -> str | None:
    if sys.platform != "darwin":
        return None
    out = _run("pmset", "-g", "batt")
    if not out or "'" not in out:
        return None
    return out.split("'")[1]  # e.g. "AC Power" / "Battery Power"


def capture_environment() -> dict:
    darwin = sys.platform == "darwin"
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "os": platform.platform(),
        "machine": platform.machine(),
        "cpu": (_run("sysctl", "-n", "machdep.cpu.brand_string") if darwin else None) or platform.processor(),
        "cores_logical": os.cpu_count(),
        "cores_performance": _run("sysctl", "-n", "hw.perflevel0.physicalcpu") if darwin else None,
        "cores_efficiency": _run("sysctl", "-n", "hw.perflevel1.physicalcpu") if darwin else None,
        "ram_gb": round(psutil.virtual_memory().total / 1e9, 1),
        "python": platform.python_version(),
        "packages": {p: importlib.metadata.version(p) for p in ("river", "numpy", "scipy", "pydantic", "psutil")},
        "power_source": _power_source(),
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "cpu_affinity_supported": hasattr(psutil.Process(), "cpu_affinity"),
    }
