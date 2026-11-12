"""Calibrate the effort controller's per-row cost model (EffortCostModel) from a short measured run.

    backend/.venv/bin/python research_testbed/scripts/calibrate_effort_cost.py [--rows 20000]

Data: Tuesday's traffic of CIC-IDS2017 (row 371,624 on; FTP-Patator starts 20,401 rows in), so the
Wednesday evaluation slice is not used. The effort pipeline runs with measured stage times at three
feature counts (8, 28, 56) and with the controller choosing levels freely (standard tier), so the
counts vary. Each stage's time per row is regressed on the counts the pipeline records:

    preprocess = a_pre + transform · inputs transformed
    select     = a_sel + select · features projected
    predict    = predict + predict_per_feature · features (naive-Bayes leaves read every feature)
    detect     = detect · labels fed to the detector (mean over rows with one)
    statistics = stats · statistics updated            (the pipeline's own timer around this step)
    ranking    = rank · inputs ranked                  (idem)
    model      = update · models updated + update_per_feature · their features
                 + split · features of an update that split a leaf   (idem, active + replacement)
    update     = a_upd + the three above               (a_upd: the rest of the update stage)

Least squares, then a second fit without the 0.5 % largest residuals (pauses not explained by the
counts). base = the intercepts; controller = the controller's own mean time. Writes the coefficients
to research_testbed/research/effort_cost_calibration.json. Timings depend on the machine and its
load at calibration time; the coefficients are then fixed, which is what makes decisions repeatable.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from adaptiveml.config import (  # noqa: E402
    ControllerConfig, EffortConfig, FeatureSelectionConfig, PipelineConfig, ResourceBudgets, StreamConfig,
)
from adaptiveml.effort_controller import EffortController  # noqa: E402
from adaptiveml.pipeline import (  # noqa: E402
    C_DETECT, C_RANK, C_REPLACEMENT, C_REPLACEMENT_FEATURES, C_SELECT, C_SPLIT_FEATURES, C_STATS, C_TRANSFORM,
    C_UPDATE, C_UPDATE_FEATURES, MethodPipeline, method_spec,
)
from adaptiveml.stream import make_scenario  # noqa: E402

TUESDAY = 371_624
WARMUP = 1_000


def collect(k: int | None, rows: int) -> tuple[np.ndarray, np.ndarray, float]:
    stream = StreamConfig(scenario="csv", dataset="cicids2017", noise=0, start=TUESDAY, length=WARMUP + rows)
    scenario = make_scenario(stream, 1)
    pipe_cfg = PipelineConfig(feature_selection=FeatureSelectionConfig(k=k))
    pipe = MethodPipeline(method_spec("effort", pipe_cfg), scenario.feature_names, warmup=WARMUP, seed=1)
    ctrl = EffortController(pipe, ControllerConfig(effort=EffortConfig(cost_source="measured")), ResourceBudgets(), None)
    counts, stages = [], []
    for i, x, y in scenario:
        before = list(pipe.cost_ns)
        _, _, st = ctrl.process(i, x, y)
        if i >= WARMUP:
            counts.append(list(pipe.row_counts))
            split = [a - b for a, b in zip(pipe.cost_ns, before)] if i > WARMUP else [0, 0, 0, 0]
            stages.append(list(st) + split)  # + statistics, ranking, model update, replacement (ns)
    ctrl_ns = pipe.controller_cost_ns[0] / rows
    return np.asarray(counts, dtype=float), np.asarray(stages, dtype=float), ctrl_ns


def fit(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = np.abs(y - X @ coef)
    keep = resid <= np.quantile(resid, 0.995)
    coef, *_ = np.linalg.lstsq(X[keep], y[keep], rcond=None)
    return coef


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, default=60_000)
    parser.add_argument("--out", type=Path, default=ROOT / "research_testbed" / "research" / "effort_cost_calibration.json")
    args = parser.parse_args()
    started = time.time()
    parts = [collect(k, args.rows) for k in (8, 28, None)]
    C = np.concatenate([p[0] for p in parts])
    S = np.concatenate([p[1] for p in parts])
    ctrl_ns = float(np.mean([p[2] for p in parts]))
    ones = np.ones(len(C))
    a_pre, transform = fit(np.column_stack([ones, C[:, C_TRANSFORM]]), S[:, 0])
    a_sel, select = fit(np.column_stack([ones, C[:, C_SELECT]]), S[:, 1])
    predict, predict_pf = fit(np.column_stack([ones, C[:, C_SELECT]]), S[:, 2])
    det_rows = C[:, C_DETECT] > 0
    detect = float(np.mean(S[det_rows, 3] / C[det_rows, C_DETECT])) if det_rows.any() else 0.0
    valid = np.ones(len(C), dtype=bool)
    valid[[0, args.rows, 2 * args.rows]] = False  # first row of each part: no per-row split
    st_rows = valid & (C[:, C_STATS] > 0)
    stats = float(S[st_rows, 6].sum() / C[st_rows, C_STATS].sum())
    rk_rows = valid & (C[:, C_RANK] > 0)
    rank = float(S[rk_rows, 7].sum() / C[rk_rows, C_RANK].sum())
    model_X = np.column_stack([C[:, C_UPDATE] + C[:, C_REPLACEMENT], C[:, C_UPDATE_FEATURES] + C[:, C_REPLACEMENT_FEATURES],
                               C[:, C_SPLIT_FEATURES]])
    update, update_pf, split = fit(model_X[valid], S[valid, 8] + S[valid, 9])
    a_upd = float(np.mean(S[valid, 5] - S[valid, 6] - S[valid, 7] - S[valid, 8] - S[valid, 9]))
    adapt = float(np.mean(S[:, 4]))
    coefficients = {
        "base_ns": max(0.0, a_pre) + max(0.0, a_sel) + max(0.0, a_upd) + adapt,
        "transform_ns_per_input": max(0.0, transform),
        "stats_ns_per_input": max(0.0, stats),
        "rank_ns_per_input": max(0.0, rank),
        "select_ns_per_feature": max(0.0, select),
        "predict_ns": max(0.0, predict),
        "predict_ns_per_feature": max(0.0, predict_pf),
        "detect_ns_per_label": detect,
        "update_ns": max(0.0, update),
        "update_ns_per_feature": max(0.0, update_pf),
        "split_ns_per_feature": max(0.0, split),
        "controller_ns": ctrl_ns,
    }
    model = (coefficients["base_ns"] + coefficients["controller_ns"] + predict
             + transform * C[:, C_TRANSFORM] + stats * C[:, C_STATS] + rank * C[:, C_RANK] + (select + predict_pf) * C[:, C_SELECT]
             + detect * C[:, C_DETECT] + update * (C[:, C_UPDATE] + C[:, C_REPLACEMENT])
             + update_pf * (C[:, C_UPDATE_FEATURES] + C[:, C_REPLACEMENT_FEATURES]) + split * C[:, C_SPLIT_FEATURES])
    measured = S[:, :6].sum(axis=1) + ctrl_ns
    out = {
        "data": f"CIC-IDS2017 rows {TUESDAY:,}–{TUESDAY + WARMUP + args.rows:,} (Tuesday), warm-up {WARMUP}, "
                f"k = 8, 28, 56, standard tier, levels chosen by the controller",
        "rows": int(len(C)),
        "machine": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}",
        "date_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime()),
        "seconds": round(time.time() - started, 1),
        "coefficients_ns": {k: round(v, 1) for k, v in coefficients.items()},
        "check": {
            "mean_measured_us": float(measured.mean() / 1e3),
            "mean_modelled_us": float(model.mean() / 1e3),
            "per_k_measured_vs_modelled_us": [
                [int(np.median(p[0][:, C_SELECT])), float((p[1][:, :6].sum(axis=1).mean() + p[2]) / 1e3),
                 float(model[sum(len(q[0]) for q in parts[:j]):sum(len(q[0]) for q in parts[:j + 1])].mean() / 1e3)]
                for j, p in enumerate(parts)
            ],
            "corr_per_row": float(np.corrcoef(model, measured)[0, 1]),
        },
    }
    args.out.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
