#!/usr/bin/env bash
# Phase 7, on the laptop: pack what a device needs into one file.
#
#   research_testbed/device/pack.sh             # code + the prepared dataset (about 1.1 GB before compression)
#   research_testbed/device/pack.sh --no-data   # code only; copy the dataset yourself
#
# Writes research_testbed/device/out/adaptiveml-device-kit.tar.gz. No results, no virtual environment
# and no frontend are included: the device only runs trials.
set -euo pipefail
cd "$(dirname "$0")/../.."

files=(backend/adaptiveml backend/pyproject.toml data/catalog.json
       research_testbed/scripts/calibrate_effort_cost.py
       research_testbed/device/run_on_device.py research_testbed/device/setup.sh research_testbed/device/README.md)
if [[ "${1:-}" != "--no-data" ]]; then
  for f in data/cicids2017/prepared/cicids2017-chronological.csv data/cicids2017/prepared/schedule.json; do
    [[ -f "$f" ]] || { echo "Missing $f. Prepare the dataset first (scripts/prepare_cicids2017.py)." >&2; exit 1; }
    files+=("$f")
  done
fi

mkdir -p research_testbed/device/out
out=research_testbed/device/out/adaptiveml-device-kit.tar.gz
COPYFILE_DISABLE=1 tar --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' -czf "$out" "${files[@]}"
echo "Wrote $out ($(du -h "$out" | cut -f1))"
echo "Copy it to the device, for example:  scp $out pi@raspberrypi.local:~"
