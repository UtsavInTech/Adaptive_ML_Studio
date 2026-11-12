"""Q4: errors in the D rows after each model replacement (adaptation_completed) under label delay D."""
import sys
import numpy as np
from common import events, outcomes, summary, trial_dirs
for d in ("0", "1000", "10000"):
    for c in ("1", "0.1"):
        for m in ("joint", "adaptive"):
            t = trial_dirs(f"q_labels_delay{d}_cov{c}")[f"{m}__small_sim__max__s11"]
            s = summary(t); w = s["config"]["evaluation"]["warmup"]
            o = outcomes(t); y = o["y_true"]; p = o[f"{m}_pred"]
            err = (y != p); err[:w] = False
            D = max(int(d), 500)
            ev = events(t)
            ad = sorted(e["i"] for e in ev if e["type"] == "adaptation_completed")
            mask = np.zeros(len(y), bool)
            for a in ad: mask[a:a + D] = True
            acts = {}
            for e in ev:
                if e["type"] == "adaptation_completed": acts[e.get("action")] = acts.get(e.get("action"), 0) + 1
            # alarms while true labels had been stable for >= 2D rows (no label change in the window the detector sees)
            yy = y.astype(np.int8); ch = np.flatnonzero(np.diff(yy) != 0) + 1
            dr = [e["i"] for e in ev if e["type"] == "drift_detected"]
            def stable(i):
                lo = i - int(d) - 2000; hi = i - int(d)
                k = np.searchsorted(ch, lo); return not (k < len(ch) and ch[k] <= hi)
            n_st = sum(stable(i) for i in dr)
            print(f"{m} d{d} c{c}: errors={err.sum()} adapt={len(ad)} {acts} rows_after_adapt={mask[w:].sum()} err_after_adapt={(err & mask).sum()} ({(err & mask).sum()/max(err.sum(),1):.0%}) alarms={len(dr)} alarms_with_no_label_change_in_seen_window={n_st}")
