"""Expand and run the fixed evaluation protocol (research_testbed/protocol/protocol.yaml).

    backend/.venv/bin/python research_testbed/scripts/protocol.py expand [--quick]
    backend/.venv/bin/python research_testbed/scripts/protocol.py run [--quick] [--grid core] [--workers 4]

`expand` writes one experiment file per setting into research_testbed/protocol/generated[-quick]/.
`run` executes them with the Studio's experiment runner, one fresh process per trial, and appends each
finished experiment's ID to runs.txt in the same folder; `report.py` reads that list. With --workers
above 1, trials run in parallel and their timings include contention (recorded in each manifest).
"""
from __future__ import annotations

import argparse
import itertools
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "research_testbed" / "protocol" / "protocol.yaml"
PYTHON = ROOT / "backend" / ".venv" / "bin" / "python"


def _seeds(spec, all_seeds):
    if spec == "all":
        return all_seeds
    if isinstance(spec, str) and spec.startswith("first"):
        return all_seeds[: int(spec[5:])]
    return list(spec)


def expand(protocol: dict, quick: bool) -> list[tuple[str, str, dict]]:
    """Return (grid, file stem, experiment config) for every setting of every grid."""
    stream_base = {"scenario": "csv", "dataset": protocol["dataset"], "noise": 0, **protocol["stream"]}
    all_seeds = protocol["seeds"]
    drop = set()
    if quick:
        q = protocol["quick"]
        stream_base |= q["stream"]
        all_seeds = q["seeds"]
        drop = set(q.get("drop_methods", ()))
    out = []
    for grid, g in protocol["grids"].items():
        methods = [m for m in g["methods"] if m not in drop]
        if not methods:
            continue
        seeds = _seeds(g["seeds"], all_seeds)
        variants = [("", {})]
        if "controller" in g:
            variants = [(f"_{name}", {"controller": c}) for name, c in g["controller"].items()]
        streams = [("", {})]
        if "label_delay" in g:
            streams = [(f"_delay{d}_cov{c:g}", {"label_delay": d, "label_coverage": c})
                       for d, c in itertools.product(g["label_delay"], g["label_coverage"])]
        if "rate_scale" in g:
            streams = [(f"_{g['arrival']}x{r:g}", {"arrival": g["arrival"], "rate_scale": r}) for r in g["rate_scale"]]
        for (vname, extra), (sname, stream_extra) in itertools.product(variants, streams):
            stem = f"{grid}{vname}{sname}"
            exp = {
                "name": f"Protocol v{protocol['version']}{' quick' if quick else ''} — {stem}",
                "base": {
                    "seed": seeds[0],
                    "methods": methods,
                    "stream": stream_base | stream_extra,
                    "evaluation": {"warmup": protocol["warmup"]},
                    **extra,
                },
                "profiles": list(g["profiles"]),
                "seeds": seeds,
            }
            out.append((grid, stem, exp))
    return out


def folder(quick: bool) -> Path:
    return PROTOCOL.parent / ("generated-quick" if quick else "generated")


def write(quick: bool) -> list[Path]:
    protocol = yaml.safe_load(PROTOCOL.read_text())
    target = folder(quick)
    target.mkdir(parents=True, exist_ok=True)
    paths = []
    for grid, stem, exp in expand(protocol, quick):
        path = target / f"{stem}.yaml"
        header = (f"# Generated from protocol.yaml v{protocol['version']} ({'quick' if quick else 'full'}), "
                  f"grid '{grid}'. Do not edit; edit the protocol and re-expand.\n")
        path.write_text(header + yaml.safe_dump(exp, sort_keys=False, allow_unicode=True))
        paths.append(path)
    return paths


def run(quick: bool, grid: str | None, workers: int) -> None:
    paths = [p for p in write(quick) if grid is None or p.stem == grid or p.stem.startswith(grid + "_")]
    runs_file = folder(quick) / "runs.txt"
    env = os.environ | {"PYTHONHASHSEED": "0"}
    for k, path in enumerate(paths, 1):
        print(f"[{k}/{len(paths)}] {path.name}", flush=True)
        proc = subprocess.run(
            [str(PYTHON), "-m", "adaptiveml.experiments.run", str(path), "--workers", str(workers)],
            cwd=ROOT / "backend", env=env, capture_output=True, text=True,
        )
        status = next((line for line in proc.stdout.splitlines() if line.startswith("status:")), None)
        if proc.returncode != 0 or status is None:
            print(proc.stdout[-2000:], proc.stderr[-2000:], file=sys.stderr)
            raise SystemExit(f"{path.name} failed")
        run_id = status.split("results/experiments/")[1].strip()
        with runs_file.open("a") as f:
            f.write(f"{path.stem}\t{run_id}\n")
        print(f"    {status}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["expand", "run"])
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--grid", choices=["core", "ensembles", "ablations", "effort_ablations", "memory", "labels", "rates"])
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.action == "expand":
        for p in write(args.quick):
            print(p.relative_to(ROOT))
    else:
        run(args.quick, args.grid, args.workers)


if __name__ == "__main__":
    main()
