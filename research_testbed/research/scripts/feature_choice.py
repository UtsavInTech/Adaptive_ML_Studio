"""Q2 (EXPLORATORY): were the 4–8 features R3 kept informative, and would another 4–8 have kept
quality? Offline, ≤300k rows per pass, no SRP/lev_bag.

1. Per-feature univariate AUC (attack vs benign) on Tuesday (rows 371,624–671,623: FTP/SSH-Patator)
   and on Wednesday (693,702–993,701: DoS), plus the selector's own ranking (|w| of an online
   logistic regression, lr 0.05, on standardised inputs) when it is fed Tuesday's labelled rows.
2. Prequential test on Wednesday: a plain Hoeffding tree (grace 200, learns every row, no detector)
   on fixed feature sets. Raw features (trees are invariant to monotone scaling; the pipeline's
   clipping at ±5σ is not reproduced).
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np
from river import linear_model, optim, preprocessing, tree
from scipy.stats import rankdata

from common import CACHE, load_features

TUE, WED, N = 371_624, 693_702, 300_000
FEATS56_EXCLUDED = None


def auc(x, y):
    ok = ~np.isnan(x)
    x, y = x[ok], y[ok]
    n1, n0 = y.sum(), len(y) - y.sum()
    if n1 == 0 or n0 == 0:
        return 0.5
    r = rankdata(x)
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def lr_ranking(X, y, names):
    sc = preprocessing.StandardScaler()
    lr = linear_model.LogisticRegression(optimizer=optim.SGD(0.05))
    for i in range(len(y)):
        x = {f: (0.0 if np.isnan(v) else float(v)) for f, v in zip(names, X[i])}
        sc.learn_one(x)
        z = sc.transform_one(x)
        z = {k: max(-5.0, min(5.0, v)) for k, v in z.items()}
        lr.learn_one(z, int(y[i]))
    w = lr.weights
    return sorted(((f, abs(w.get(f, 0.0))) for f in names), key=lambda t: -t[1])


def prequential(X, y, names, feats, warm=1000):
    idx = [names.index(f) for f in feats]
    m = tree.HoeffdingTreeClassifier(grace_period=200)
    pred = np.zeros(len(y), dtype=np.int8)
    t0 = time.perf_counter()
    for i in range(len(y)):
        x = {f: (0.0 if np.isnan(v) else float(v)) for f, v in zip(feats, X[i, idx])}
        p = m.predict_one(x)
        pred[i] = 0 if p is None else int(p)
        m.learn_one(x, int(y[i]))
    us = (time.perf_counter() - t0) / len(y) * 1e6
    yy, pp = y[warm:], pred[warm:]
    err = (yy != pp)
    nc = (yy[1:] != yy[:-1]).mean()
    acc = 1 - err.mean()
    p_nc = 1 - nc
    return {"features": feats, "k": len(feats), "errors": int(err.sum()), "acc": float(acc),
            "recall": float(pp[yy == 1].mean()), "false_alarm": float(pp[yy == 0].mean()),
            "kappa_temporal": float((acc - p_nc) / (1 - p_nc)), "us_per_row_tree": us}


def main():
    t = time.time()
    Xt, yt, _, names = load_features(TUE, N)
    print("tuesday loaded", Xt.shape, yt.mean(), time.time() - t, file=sys.stderr)
    auc_t = {f: auc(Xt[:, j], yt) for j, f in enumerate(names)}
    lr_t = lr_ranking(Xt, yt, names)
    print("lr ranking done", time.time() - t, file=sys.stderr)
    del Xt
    Xw, yw, atw, _ = load_features(WED, N)
    auc_w = {f: auc(Xw[:, j], yw) for j, f in enumerate(names)}
    sep = lambda d: sorted(d, key=lambda f: -abs(d[f] - 0.5))
    top_t, top_w, top_lr = sep(auc_t), sep(auc_w), [f for f, _ in lr_t]
    sets = {
        "R3 kept, full-stream gateway (frozen benign-only ranking)": ["Dst Port", "Flow Packets/s", "Fwd Packets/s", "FIN Flag Count"],
        "R3 kept, Wed micro_sim final 2": ["Flow Bytes/s", "Fwd Bulk Rate Avg"],
        "R3 kept, Wed micro_sim at 7": ["Flow Bytes/s", "Flow Packets/s", "Fwd Packets/s", "Packet Length Min", "Packet Length Variance", "Fwd Bulk Rate Avg", "Subflow Fwd Packets"],
        "selector LR fed Tuesday labels, top 4": top_lr[:4],
        "selector LR fed Tuesday labels, top 8": top_lr[:8],
        "univariate AUC on Tuesday, top 4": top_t[:4],
        "univariate AUC on Tuesday, top 8": top_t[:8],
        "hindsight: univariate AUC on Wednesday, top 4": top_w[:4],
        "hindsight: univariate AUC on Wednesday, top 8": top_w[:8],
        "all 83 inputs": list(names),
    }
    res = {"auc_tuesday": auc_t, "auc_wednesday": auc_w, "lr_tuesday": lr_t, "runs": {}}
    for k, fs in sets.items():
        r = prequential(Xw, yw, names, fs)
        res["runs"][k] = r
        print(f"{k}: err={r['errors']} rec={r['recall']:.3f} fa={r['false_alarm']:.4f} kt={r['kappa_temporal']:.2f} us={r['us_per_row_tree']:.1f} {fs}", file=sys.stderr)
        (CACHE / "feature_choice.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
