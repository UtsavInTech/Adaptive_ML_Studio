"""Q1 + Q5: where are errors made? Position in label runs, attack onsets/ends, attack types, and the
share of 'easy' rows. Reads saved outcomes only. Writes tables to stdout (markdown) and JSON."""
from __future__ import annotations

import json
import sys

import numpy as np

from common import CACHE, SCHEDULE, labels_original, outcomes, summary, trial_dirs

FULL = [  # (label, run key, trial)
    ("Repeat last label", "p2_core", "no_change__standard__max__s42"),
    ("Static", "p2_core", "static__standard__max__s42"),
    ("Incremental", "p2_core", "incremental__standard__max__s42"),
    ("Adaptive (old ctrl)", "p2_core", "adaptive__standard__max__s42"),
    ("ARF", "p2_core", "arf__standard__max__s42"),
    ("SRP", "p2_srp", "srp__standard__max__s42"),
    ("LevBag", "p2_levbag", "lev_bag__standard__max__s42"),
    ("Joint std", "p3", "joint__standard__max__s42"),
    ("Joint gateway", "p3", "joint__gateway_sim__max__s42"),
    ("Joint gateway −R3", "p3_nor3", "joint__gateway_sim__max__s42"),
    ("Joint memory 256K", "mem_full", None),
    ("Joint memory −R5", "mem_nor5", None),
]
QUICK = [(f"{m} {t}", "q_core", f"{m}__{t}__max__s11") for m in ("no_change", "incremental", "adaptive", "joint")
         for t in ("standard", "small_sim", "micro_sim")] + [("arf standard", "q_ens", "arf__standard__max__s11")]

BUCKETS = [(0, 1), (1, 10), (10, 100), (100, 1000), (1000, 10**9)]


def run_position(y: np.ndarray) -> np.ndarray:
    """Rows since the binary label last changed (0 = this row differs from the previous)."""
    change = np.ones(len(y), dtype=bool)
    change[1:] = y[1:] != y[:-1]
    idx = np.arange(len(y))
    last = np.maximum.accumulate(np.where(change, idx, 0))
    return idx - last


def onset_rows(y: np.ndarray, gap: int = 1000) -> np.ndarray:
    """Indices of attack rows preceded by >= gap benign rows (an 'attack onset')."""
    att = np.flatnonzero(y == 1)
    if len(att) == 0:
        return att
    prev_gap = np.diff(np.concatenate([[-gap - 1], att]))
    return att[prev_gap > gap]


def analyse(label, run_key, trial, offset_hint=None):
    trials = trial_dirs(run_key)
    tname = trial or sorted(trials)[0]
    tdir = trials[tname]
    s = summary(tdir)
    cfg = s["config"]
    start = cfg["stream"].get("start") or 0
    warm = cfg["evaluation"]["warmup"]
    method = cfg["methods"][0]
    o = outcomes(tdir)
    y = o["y_true"][warm:].astype(np.int8)
    p = o[f"{method}_pred"][warm:].astype(np.int8)
    rows = np.arange(len(o["y_true"]))[warm:] + start
    codes, names = labels_original()
    at = codes[rows]
    err = y != p
    fn = err & (y == 1)
    fp = err & (y == 0)
    pos = run_position(o["y_true"].astype(np.int8))[warm:]
    out = {"label": label, "run": run_key, "trial": tname, "rows": int(len(y)), "errors": int(err.sum()),
           "fn": int(fn.sum()), "fp": int(fp.sum()), "acc": float(1 - err.mean())}
    out["err_by_runpos"] = {f"{a}-{b - 1}" if b < 10**9 else f">={a}": int(err[(pos >= a) & (pos < b)].sum()) for a, b in BUCKETS}
    out["rows_by_runpos"] = {f"{a}-{b - 1}" if b < 10**9 else f">={a}": int(((pos >= a) & (pos < b)).sum()) for a, b in BUCKETS}
    # FN by attack type, FP by attempted vs benign
    out["fn_by_type"] = {names[c]: int(fn[at == c].sum()) for c in np.unique(at[fn])}
    out["fp_by_type"] = {names[c]: int(fp[at == c].sum()) for c in np.unique(at[fp])}
    # onset: first N attack rows after >=1000 benign rows
    yy = o["y_true"].astype(np.int8)
    ons = onset_rows(yy)
    ons = ons[ons >= warm]
    for N in (10, 100, 1000):
        mask = np.zeros(len(yy), dtype=bool)
        for r in ons:
            seg = np.flatnonzero(yy[r:r + 20 * N] == 1)[:N] + r  # first N attack rows of the episode
            mask[seg] = True
        m = mask[warm:]
        out[f"fn_first{N}_after_onset"] = int(fn[m].sum())
        out[f"rows_first{N}_after_onset"] = int(m.sum())
    out["n_onsets"] = int(len(ons))
    # attack end: benign rows within 1000 / 5000 rows after the last attack row of an episode
    att = np.flatnonzero(yy == 1)
    if len(att):
        nxt_gap = np.diff(np.concatenate([att, [len(yy) + 10**6]]))
        ends = att[nxt_gap > 1000]
        for W in (1000, 5000):
            mask = np.zeros(len(yy), dtype=bool)
            for r in ends:
                mask[r + 1:r + 1 + W] = True
            m = mask[warm:] & (y == 0)
            out[f"fp_within{W}_after_end"] = int(fp[m].sum())
            out[f"benign_within{W}_after_end"] = int(m.sum())
    # inside / outside scheduled attack period ranges
    inper = np.zeros(len(yy), dtype=bool)
    for per in SCHEDULE["attack_periods"]:
        a, b = per["start_row"] - start, per["end_row"] - start
        if b < 0 or a >= len(yy):
            continue
        inper[max(a, 0):b + 1] = True
    out["fp_inside_periods"] = int(fp[inper[warm:]].sum())
    out["fn_inside_periods"] = int(fn[inper[warm:]].sum())
    out["rows_inside_periods"] = int(inper[warm:].sum())
    # Q5: easy rows = last k labels identical and the model correct on the last k rows
    e_all = (o["y_true"] != o[f"{method}_pred"]).astype(np.int32)
    ce = np.concatenate([[0], np.cumsum(e_all)])
    pos_all = run_position(yy)
    for k in (10, 100, 1000):
        idx = np.arange(len(yy))
        recent_err = ce[idx] - ce[np.maximum(idx - k, 0)]
        # label history: previous k labels all equal to each other  <=> run position of row t-1 >= k-1
        prev_pos = np.concatenate([[0], pos_all[:-1]])
        easy = (idx >= k) & (recent_err == 0) & (prev_pos >= k - 1)
        easy = easy[warm:]
        out[f"easy{k}_share"] = float(easy.mean())
        out[f"easy{k}_err_rate"] = float(err[easy].mean()) if easy.any() else None
        out[f"hard{k}_err_rate"] = float(err[~easy].mean())
        out[f"easy{k}_share_of_errors"] = float(err[easy].sum() / max(err.sum(), 1))
        # predicting the previous label on easy rows (a free cheap path) — its errors there:
        prevlab = np.concatenate([[0], yy[:-1]])[warm:]
        out[f"easy{k}_prevlabel_err_rate"] = float((prevlab[easy] != y[easy]).mean()) if easy.any() else None
    # per-row service time on easy vs hard rows (k=100)
    svc = o[f"{method}_service_ns"][warm:]
    idx = np.arange(len(yy))
    recent_err = ce[idx] - ce[np.maximum(idx - 100, 0)]
    prev_pos = np.concatenate([[0], pos_all[:-1]])
    easy = ((idx >= 100) & (recent_err == 0) & (prev_pos >= 99))[warm:]
    out["svc_us_mean"] = float(svc.mean() / 1e3)
    out["svc_us_easy100"] = float(svc[easy].mean() / 1e3)
    return out


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    res = []
    sets = (FULL if which in ("all", "full") else []) + (QUICK if which in ("all", "quick") else [])
    for lab, rk, tr in sets:
        r = analyse(lab, rk, tr)
        res.append(r)
        print(lab, r["errors"], r["fn"], r["fp"], r["err_by_runpos"], file=sys.stderr)
    (CACHE / f"error_structure_{which}.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
