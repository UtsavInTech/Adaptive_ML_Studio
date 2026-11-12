"""Phase 7: run the testbed on a real small device (e.g. a Raspberry Pi) and pack the results.

    backend/.venv/bin/python research_testbed/device/run_on_device.py            # full run
    backend/.venv/bin/python research_testbed/device/run_on_device.py --quick    # ~10x shorter

What it does, in order:

1. Records the device (board model, CPU, governor, temperature).
2. Calibrates the effort controller's cost model ON THIS DEVICE (Tuesday rows, not the evaluation
   slice). The laptop's coefficients would be wrong here: a small device is several times slower.
3. Sets two time budgets from that measurement, with the same relative tightness as the laptop's
   simulated tiers (see BUDGET_RULE). They are still chosen by a rule, not by an application
   requirement, so they stay marked as placeholder budgets.
4. Runs the reference methods without a budget, then `joint` (rules R1-R5) and `effort` under both
   budgets, one trial at a time, each in a fresh process.
5. Writes a summary table and packs everything into one .tar.gz, in the same bundle format the
   Studio reads. Copy that file to the laptop and run import_bundle.py there.

On a machine that does not name itself as a single-board computer the run is a REHEARSAL: the
profiles stay marked as simulated and the bundle says so. Nothing here measures energy.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from adaptiveml.experiments.environment import capture_environment, cpu_temperature_c  # noqa: E402
import adaptiveml.stream.static as static  # noqa: E402

DATASET = "cicids2017"
SLICES = {
    # Same rows as the laptop runs, so the two can be set side by side.
    "full": {"start": 693_702, "length": 300_000, "said": "Wednesday DoS attacks (the protocol's quick slice)"},
    "quick": {"start": 730_000, "length": 40_000, "said": "40,000 Wednesday rows with two attacks (the Studio's demo slice)"},
}
# The laptop's simulated tiers allow 100 and 50 µs per row, where the same calibration run measured
# 80.07 µs per row (research/effort_cost_calibration.json). The device budgets keep those ratios.
# The calibration must use the same rows as the laptop's did (60,000 Tuesday rows per feature count,
# which include the FTP-Patator attack): on fewer rows the stream is all quiet and the cost per row
# comes out far lower, so the ratios above would give budgets that are much too tight.
CALIBRATION_ROWS = 60_000
BUDGET_RULE = {
    "device_small": {"times_calibrated_cost": 100 / 80.07, "deadline_times_budget": 5, "model_memory_mib": 8.0,
                     "allow_background": True, "max_update_stride": 4, "min_features": 4, "like": "small_sim"},
    "device_micro": {"times_calibrated_cost": 50 / 80.07, "deadline_times_budget": 4, "model_memory_mib": 1.0,
                     "allow_background": False, "max_update_stride": 8, "min_features": 2, "like": "micro_sim"},
}


def profiles(calibrated_us: float, real_device: bool, where: str) -> list[dict]:
    out = []
    for name, rule in BUDGET_RULE.items():
        budget_us = calibrated_us * rule["times_calibrated_cost"]
        kind = "measured on the device" if real_device else f"REHEARSAL on {where}, not a device"
        out.append({
            "name": name,
            "label": f"{name.split('_')[1].capitalize()} budget, {budget_us:.0f} µs per row ({kind})",
            "simulated": not real_device,
            "placeholder": True,  # set by BUDGET_RULE, not by an application requirement
            "budgets": {
                "compute_share": 1.0, "nominal_rate": 1e6 / budget_us,
                "latency_deadline_ms": budget_us * rule["deadline_times_budget"] / 1e3,
                "model_memory_mib": rule["model_memory_mib"], "allow_background": rule["allow_background"],
                "max_update_stride": rule["max_update_stride"], "min_features": rule["min_features"],
            },
        })
    return out


def presets(slice_: dict, seeds: list[int], cost: dict, device_profiles: list[dict], tag: str) -> dict[str, dict]:
    base = {
        "seed": seeds[0],
        "stream": {"scenario": "csv", "dataset": DATASET, "noise": 0, "start": slice_["start"], "length": slice_["length"]},
        "evaluation": {"warmup": 1000},
    }
    return {
        "references": {
            "name": f"Device run {tag} — references, no budget",
            "base": dict(base, methods=["no_change", "incremental", "adaptive"]),
            "profiles": ["standard"], "seeds": seeds,
        },
        "controllers": {
            "name": f"Device run {tag} — rules (R1–R5) vs effort controller",
            "base": dict(base, methods=["joint", "effort"], controller={"effort": {"cost": cost}}),
            "profiles": device_profiles, "seeds": seeds,
        },
    }


def run(cmd: list[str], env: dict) -> None:
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, env=env, cwd=ROOT / "backend")


def summary(results: Path, device: dict) -> str:
    lines = [
        f"# Device run — {device['name']}", "",
        f"- Measured on: {device['name']} ({device['environment']['cpu']}, {device['environment']['ram_gb']} GB RAM, "
        f"{device['environment']['os']})",
        f"- Real device: {'yes' if device['real_device'] else 'NO — rehearsal on a machine that is not a single-board computer'}",
        f"- Slice: {device['slice']['said']}, rows {device['slice']['start']:,} + {device['slice']['length']:,}; seeds {device['seeds']}",
        f"- Cost of a row in the calibration run on this machine: {device['calibrated_us_per_row']:.1f} µs",
        f"- CPU governor: {device['environment'].get('cpu_governor') or 'not reported'}; "
        f"temperature before {device['temperature_c']['before']} °C, after {device['temperature_c']['after']} °C",
        "- Budgets are set by a rule from the calibration run (placeholder budgets). Energy was not measured.", "",
        "| Method | Budget | Seed | Accuracy | κ-temporal | Mean µs/row | p95 µs/row | Budget µs | Mean vs budget |",
        "|---|---|--:|--:|--:|--:|--:|--:|--:|",
    ]
    budgets_us = {p["name"]: 1e6 * p["budgets"]["compute_share"] / p["budgets"]["nominal_rate"] for p in device["profiles"]}
    for path in sorted(results.glob("experiments/*/manifest.json")):
        for t in json.loads(path.read_text())["trials"]:
            budget = budgets_us.get(t["profile"]["name"])
            for method, s in t["methods"].items():
                mean = s["latency_us"]["mean"]
                kt = s.get("kappa_temporal")
                lines.append(
                    f"| {method} | {t['profile']['name']} | {t['seed']} | {s['accuracy'] * 100:.2f} % | "
                    f"{'—' if kt is None else format(kt, '.2f')} | {mean:.0f} | {s['latency_us']['p95']:.0f} | "
                    f"{'none' if budget is None else format(budget, '.0f')} | "
                    f"{'—' if budget is None else format((mean / budget - 1) * 100, '+.0f') + ' %'} |"
                )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="40,000-row slice instead of 300,000 (the calibration is the same)")
    parser.add_argument("--seeds", default="11", help="comma-separated, e.g. 11,23,37")
    parser.add_argument("--out", type=Path, default=ROOT / "research_testbed" / "device" / "out")
    args = parser.parse_args()
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    slice_ = SLICES["quick" if args.quick else "full"]

    entry = next((e for e in static.catalog() if e["id"] == DATASET), None)
    if not entry or not entry["available"]:
        sys.exit(f"The dataset file is missing: data/{entry['file'] if entry else DATASET}. Copy it from the laptop (see README).")

    env_record = capture_environment()
    real = bool(env_record["device_model"])
    name = env_record["device_model"] or f"{platform.system()} {platform.machine()} ({socket.gethostname().split('.')[0]})"
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    tag = f"{'device' if real else 'rehearsal'}-{stamp}"
    out = args.out / tag
    (out / "presets").mkdir(parents=True)
    print(f"Device: {name}" + ("" if real else "\n  This machine does not name itself as a single-board computer: REHEARSAL only."))
    if env_record.get("cpu_governor") not in (None, "performance"):
        print(f"  Note: CPU governor is '{env_record['cpu_governor']}'. Timings are steadier with 'performance' (see README).")
    temp_before = cpu_temperature_c()

    env = dict(os.environ, PYTHONHASHSEED="0", ADAPTIVEML_RESULTS_DIR=str(out))
    print("\n1/3 Calibrating the cost model on this machine")
    calibration = out / "effort_cost_calibration.json"
    run([sys.executable, str(ROOT / "research_testbed" / "scripts" / "calibrate_effort_cost.py"),
         "--rows", str(CALIBRATION_ROWS), "--out", str(calibration)], dict(env, PYTHONHASHSEED="0"))
    cal = json.loads(calibration.read_text())
    calibrated_us = cal["check"]["mean_measured_us"]
    device_profiles = profiles(calibrated_us, real, name)

    print("\n2/3 Running the trials (one at a time)")
    for key, preset in presets(slice_, seeds, cal["coefficients_ns"], device_profiles, tag).items():
        path = out / "presets" / f"{key}.yaml"
        path.write_text(yaml.safe_dump(preset, sort_keys=False, allow_unicode=True))
        run([sys.executable, "-m", "adaptiveml.experiments.run", str(path)], env)

    device = {
        "name": name, "real_device": real, "tag": tag, "environment": env_record, "slice": slice_, "seeds": seeds,
        "calibrated_us_per_row": calibrated_us, "budget_rule": BUDGET_RULE, "profiles": device_profiles,
        "temperature_c": {"before": temp_before, "after": cpu_temperature_c()},
        "note": "Budgets follow a rule from the calibration run; they are placeholders. Energy not measured.",
    }
    (out / "device.json").write_text(json.dumps(device, indent=2) + "\n")
    text = summary(out, device)
    (out / "summary.md").write_text(text)

    print("\n3/3 Packing the bundle")
    bundle = args.out / f"{tag}.tar.gz"
    with tarfile.open(bundle, "w:gz") as tar:
        for path in sorted(out.rglob("*")):
            if path.is_file() and path.name != "index.csv":
                tar.add(path, arcname=str(Path(tag) / path.relative_to(out)))
    print("\n" + text)
    print(f"Bundle: {bundle} ({bundle.stat().st_size / 1e6:.1f} MB)")
    print("Copy it to the laptop, then:  backend/.venv/bin/python research_testbed/device/import_bundle.py <file>")


if __name__ == "__main__":
    main()
