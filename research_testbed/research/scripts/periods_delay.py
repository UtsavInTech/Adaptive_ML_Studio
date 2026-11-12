"""Q1 per attack period (drift alarms around onsets) and Q4 label delay anatomy."""
from __future__ import annotations

import json
import sys

import numpy as np

from common import CACHE, SCHEDULE, events, outcomes, summary, trial_dirs


def period_table(run_key, trial, label):
    t = trial_dirs(run_key)[trial]
    s = summary(t)
    m = s["config"]["methods"][0]
    start = s["config"]["stream"].get("start") or 0
    ev = events(t)
    drifts = np.array([e["i"] for e in ev if e["type"] == "drift_detected"])
    adapts = np.array([e["i"] for e in ev if e["type"] == "adaptation_completed"])
    o = outcomes(t)
    y, p = o["y_true"], o[f"{m}_pred"]
    rows = []
    for per in s["summaries"][m]["attack_periods"]:
        a = per["start_row"] - start
        b = per["end_row"] - start
        seg_y, seg_p = y[a:b + 1], p[a:b + 1]
        att = np.flatnonzero(seg_y == 1)
        first_att = a + att[0] if len(att) else a
        flag = np.flatnonzero((seg_y == 1) & (seg_p == 1))
        first_flag = a + flag[0] if len(flag) else None
        d_before = int(((drifts >= a - 5000) & (drifts < a)).sum()) if len(drifts) else 0
        d_in = int(((drifts >= a) & (drifts <= b)).sum()) if len(drifts) else 0
        nxt = drifts[drifts >= first_att] if len(drifts) else []
        first_drift_delay = int(nxt[0] - first_att) if len(nxt) else None
        fp_in = int(((seg_y == 0) & (seg_p == 1)).sum())
        rows.append({"run": label, "type": per["attack_type"], "start": per["start_row"], "flows": per["flows"],
                     "recall": per["recall"], "until_first": per["flows_until_first_flagged"],
                     "rows_until_first_flag": None if first_flag is None else int(first_flag - first_att),
                     "first_drift_after_onset_rows": first_drift_delay,
                     "drifts_5k_before": d_before, "drifts_inside": d_in,
                     "adapts_inside": int(((adapts >= a) & (adapts <= b)).sum()) if len(adapts) else 0,
                     "fn": int(((seg_y == 1) & (seg_p == 0)).sum()), "fp_inside": fp_in,
                     "benign_inside": int((seg_y == 0).sum())})
    return rows


def delay_anatomy(run_key, trial, delay, label):
    t = trial_dirs(run_key)[trial]
    s = summary(t)
    m = s["config"]["methods"][0]
    w = s["config"]["evaluation"]["warmup"]
    o = outcomes(t)
    y, p = o["y_true"].astype(np.int8), o[f"{m}_pred"].astype(np.int8)
    n = len(y)
    err = (y != p)
    err[:w] = False
    att = np.flatnonzero(y == 1)
    gap_prev = np.diff(np.concatenate([[-10**6], att]))
    gap_next = np.diff(np.concatenate([att, [n + 10**6]]))
    onsets, ends = att[gap_prev > 1000], att[gap_next > 1000]
    H = max(delay, 1) + 2000  # horizon: the delay plus a short settling time
    on_m = np.zeros(n, bool)
    for r in onsets:
        on_m[r:r + H] = True
    end_m = np.zeros(n, bool)
    for r in ends:
        end_m[r + 1:r + 1 + H] = True
    fn = err & (y == 1)
    fp = err & (y == 0)
    ev = events(t)
    kinds = {}
    for e in ev:
        kinds[e["type"]] = kinds.get(e["type"], 0) + 1
    # adaptations triggered while the stream (true labels) is stable: a 'false' adaptation proxy
    stable = np.zeros(n, bool)
    pos = np.zeros(n, int)
    for i in range(1, n):
        pos[i] = pos[i - 1] + 1 if y[i] == y[i - 1] else 0
    ad = [e["i"] for e in ev if e["type"] == "adaptation_completed"]
    drift_rows = [e["i"] for e in ev if e["type"] == "drift_detected"]
    # attack-period membership of each drift alarm
    in_attack_window = 0
    for d in drift_rows:
        if any(r <= d < r + H for r in onsets) or any(r < d <= r + H for r in ends):
            in_attack_window += 1
    return {"run": label, "delay": delay, "errors": int(err.sum()), "fn": int(fn.sum()), "fp": int(fp.sum()),
            "fn_in_onset_window": int((fn & on_m).sum()), "fp_in_end_window": int((fp & end_m).sum()),
            "fp_in_onset_window": int((fp & on_m).sum()),
            "rows_onset_window": int(on_m[w:].sum()), "rows_end_window": int(end_m[w:].sum()),
            "n_onsets": int(len(onsets)), "n_ends": int(len(ends)),
            "drift_alarms": len(drift_rows), "drift_alarms_near_onset_or_end": in_attack_window,
            "adaptations": len(ad), "kt": s["summaries"][m]["stream_scores_after_warmup"]["kappa_temporal"],
            "recall": s["summaries"][m]["scores_after_warmup"]["recall"],
            "fa": s["summaries"][m]["attack_types_after_warmup"]["BENIGN"]["flagged_share"]}


def main():
    out = {"periods": [], "delay": []}
    for rk, tr, lab in [("p3", "joint__standard__max__s42", "joint std"), ("p3", "joint__gateway_sim__max__s42", "joint gateway"),
                        ("p2_core", "arf__standard__max__s42", "ARF"), ("p2_core", "adaptive__standard__max__s42", "adaptive"),
                        ("p2_core", "no_change__standard__max__s42", "no_change"), ("p3_nor3", "joint__gateway_sim__max__s42", "joint gw -R3")]:
        out["periods"] += period_table(rk, tr, lab)
    for d in ("0", "1000", "10000"):
        for c in ("1", "0.5", "0.1"):
            for m in ("joint", "incremental", "adaptive"):
                rk = f"q_labels_delay{d}_cov{c}"
                out["delay"].append({**delay_anatomy(rk, f"{m}__small_sim__max__s11", int(d), f"{m} d{d} c{c}"), "coverage": c, "method": m})
                print(out["delay"][-1], file=sys.stderr)
    (CACHE / "periods_delay.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
