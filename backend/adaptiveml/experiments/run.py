"""Run an experiment from a YAML file.

    .venv/bin/python -m adaptiveml.experiments.run presets/experiments/compare_methods.yaml

Profiles may be given by name (`standard`, `edge_sim`) or as full profile objects.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from adaptiveml.config import ExperimentConfig
from adaptiveml.config.profiles import BUILTIN_PROFILES
from adaptiveml.experiments.runner import run_experiment


def resolve_profiles(data: dict) -> dict:
    profiles = data.get("profiles")
    if profiles:
        data = dict(data, profiles=[BUILTIN_PROFILES[p].model_dump() if isinstance(p, str) else p for p in profiles])
    return data


def load_experiment(path: Path) -> ExperimentConfig:
    return ExperimentConfig.model_validate(resolve_profiles(yaml.safe_load(path.read_text())))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    exp = load_experiment(args.config)
    print(f"{exp.name}: {len(exp.trials())} trials")
    manifest = run_experiment(exp, on_progress=lambda p: p["trial"] and print(f"  [{p['done'] + 1}/{p['total']}] {p['trial']}", flush=True))
    print(f"\nstatus: {manifest['status']} — results/experiments/{manifest['id']}")
    def fmt(value, spec):
        return "—" if value is None else format(value, spec)

    for t in manifest["trials"]:
        for method, s in t["methods"].items():
            print(
                f"  {t['trial_id']:<44} acc {fmt(s['accuracy'], '.4f')}  f1 {fmt(s['f1'], '.4f')}  "
                f"mean {fmt(s['latency_us']['mean'], '.1f')} µs  adaptations {s['adaptations']}"
            )


if __name__ == "__main__":
    main()
