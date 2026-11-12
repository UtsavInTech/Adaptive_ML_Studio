"""Q5: a label-free 'easy row' test usable under label delay: the model's own last k predictions
were identical. Share of rows, error rate there, and share of all errors."""
import numpy as np
from common import outcomes, summary, trial_dirs
for rk, tr, lab in [("p3", "joint__standard__max__s42", "joint std (full)"), ("p2_core", "arf__standard__max__s42", "ARF (full)"),
                    ("q_core", "joint__small_sim__max__s11", "joint small (Wed)"),
                    ("q_labels_delay1000_cov1", "joint__small_sim__max__s11", "joint small d1000 (Wed)"),
                    ("q_labels_delay1000_cov1", "incremental__small_sim__max__s11", "incremental d1000 (Wed)")]:
    t = trial_dirs(rk)[tr]; s = summary(t); m = s["config"]["methods"][0]; w = s["config"]["evaluation"]["warmup"]
    o = outcomes(t); y = o["y_true"].astype(np.int8); p = o[f"{m}_pred"].astype(np.int8)
    err = (y != p)[w:]
    ch = np.ones(len(p), bool); ch[1:] = p[1:] != p[:-1]
    idx = np.arange(len(p)); last = np.maximum.accumulate(np.where(ch, idx, 0)); run = idx - last
    prev_run = np.concatenate([[0], run[:-1]])
    out = []
    for k in (10, 100, 1000):
        easy = (prev_run >= k - 1)[w:] & (idx[w:] >= k)
        # 'easy' and predicting the same as last row
        out.append(f"k={k}: share={easy.mean():.2f} err_easy={err[easy].mean():.4f} err_hard={err[~easy].mean():.4f} errors_in_easy={err[easy].sum() / err.sum():.0%}")
    print(lab, "|", " | ".join(out))
