#!/usr/bin/env bash
# Phase 7, on the device: create the Python environment. Run once, from the unpacked kit folder:
#
#   bash research_testbed/device/setup.sh
#
# Uses python3; to use another interpreter:  PYTHON=python3.12 bash research_testbed/device/setup.sh
set -euo pipefail
PYTHON="${PYTHON:-python3}"
cd "$(dirname "$0")/../.."

"$PYTHON" - <<'EOF' || { echo "Python 3.11 or newer on a 64-bit system is needed (Raspberry Pi OS 64-bit, Bookworm or later)." >&2; exit 1; }
import struct, sys
assert sys.version_info >= (3, 11) and struct.calcsize("P") == 8
EOF

"$PYTHON" -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -e backend

backend/.venv/bin/python - <<'EOF'
import sys
sys.path.insert(0, "backend")
from adaptiveml.experiments.environment import capture_environment
import adaptiveml.stream.static as static
env = capture_environment()
print("\nDevice:   ", env["device_model"] or "not a single-board computer (runs here are rehearsals)")
print("CPU:      ", env["cpu"], "·", env["ram_gb"], "GB RAM")
print("Governor: ", env["cpu_governor"] or "not reported")
entry = next((e for e in static.catalog() if e["id"] == "cicids2017"), None)
print("Dataset:  ", "found" if entry and entry["available"] else "MISSING: copy data/cicids2017/prepared/ from the laptop")
EOF
echo
echo "Ready. Next:  backend/.venv/bin/python research_testbed/device/run_on_device.py --quick"
