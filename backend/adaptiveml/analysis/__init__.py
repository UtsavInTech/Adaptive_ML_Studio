"""Evaluation protocol statistics for stream experiments (research testbed, phase 5).

- Confidence intervals: a non-overlapping block bootstrap over the stream's rows. Rows next to each
  other are not independent (labels arrive in runs), so whole blocks of consecutive rows are
  resampled, never single rows. Every metric is recomputed from the resampled blocks' counts.
- Many methods over many blocks (Demšar, 2006): the Friedman test on per-block ranks, then the
  Nemenyi critical difference between average ranks.

These describe the uncertainty of measured runs; which comparisons go into the paper, and how they
are read, is the research workstream's decision.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import stats as _stats

# Critical values q_alpha of the Nemenyi test (studentized range / sqrt 2), Demšar 2006, Table 5(a).
NEMENYI_Q = {
    0.05: {2: 1.960, 3: 2.343, 4: 2.569, 5: 2.728, 6: 2.850, 7: 2.949, 8: 3.031, 9: 3.102, 10: 3.164},
    0.10: {2: 1.645, 3: 2.052, 4: 2.291, 5: 2.459, 6: 2.589, 7: 2.693, 8: 2.780, 9: 2.855, 10: 2.920},
}
COUNTS = ("n", "tp", "fp", "tn", "fn", "nc")  # nc: rows whose label equals the previous row's


def block_counts(y_true: np.ndarray, y_pred: np.ndarray, lo: int, block: int) -> np.ndarray:
    """Per block of `block` consecutive rows from `lo`: the counts every metric below needs."""
    t = y_true.astype(bool)
    p = y_pred.astype(bool)
    hi = len(t)
    if lo < 1 or hi - lo < block:
        raise ValueError("need a previous row and at least one full block")
    rows = []
    for a in range(lo, hi - block + 1, block):
        tt, pp = t[a:a + block], p[a:a + block]
        rows.append((block, np.sum(tt & pp), np.sum(~tt & pp), np.sum(~tt & ~pp), np.sum(tt & ~pp),
                     np.sum(t[a - 1:a + block - 1] == tt)))
    return np.asarray(rows, dtype=np.int64)


def metrics(c: np.ndarray) -> dict:
    """Metrics from summed counts (one row of COUNTS). None where undefined."""
    n, tp, fp, tn, fn, nc = (int(v) for v in c)
    acc = (tp + tn) / n if n else None
    p_nc = nc / n if n else None
    chance = ((tp + fn) * (tp + fp) + (tn + fp) * (tn + fn)) / (n * n) if n else None
    f1p = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else None
    f1n = 2 * tn / (2 * tn + fn + fp) if (2 * tn + fn + fp) else None
    return {
        "accuracy": acc,
        "kappa": None if acc is None or chance is None or chance >= 1 else (acc - chance) / (1 - chance),
        "kappa_temporal": None if acc is None or p_nc is None or p_nc >= 1 else (acc - p_nc) / (1 - p_nc),
        "macro_f1": None if f1p is None or f1n is None else (f1p + f1n) / 2,
        "recall": tp / (tp + fn) if tp + fn else None,
        "false_alarm_rate": fp / (fp + tn) if fp + tn else None,
    }


def bootstrap_ci(counts: np.ndarray, *, n_boot: int = 1000, alpha: float = 0.05, seed: int = 0) -> dict:
    """Point estimate and percentile interval of every metric, resampling whole blocks.

    Returns {metric: {"value", "low", "high"}}. With fewer than two blocks the interval is None.
    """
    point = metrics(counts.sum(axis=0))
    out = {k: {"value": v, "low": None, "high": None} for k, v in point.items()}
    m = len(counts)
    if m < 2:
        return out
    rng = np.random.default_rng(seed)
    draws = {k: [] for k in point}
    for _ in range(n_boot):
        sample = counts[rng.integers(0, m, size=m)].sum(axis=0)
        for k, v in metrics(sample).items():
            if v is not None:
                draws[k].append(v)
    for k, values in draws.items():
        if len(values) >= n_boot // 2:
            lo, hi = np.percentile(values, [100 * alpha / 2, 100 * (1 - alpha / 2)])
            out[k]["low"], out[k]["high"] = float(lo), float(hi)
    return out


def average_ranks(scores: np.ndarray, higher_is_better: bool = True) -> np.ndarray:
    """scores: blocks × methods. Rank 1 is best in each block; ties share the mean rank."""
    data = -scores if higher_is_better else scores
    return np.vstack([_stats.rankdata(row) for row in data]).mean(axis=0)


def friedman(scores: np.ndarray, higher_is_better: bool = True) -> dict:
    """Friedman test over blocks (rows) and methods (columns), with Iman-Davenport's F version."""
    n, k = scores.shape
    if n < 2 or k < 3:
        return {"blocks": n, "methods": k, "chi2": None, "p_value": None, "iman_davenport_f": None,
                "p_value_f": None, "average_ranks": average_ranks(scores, higher_is_better).tolist() if n else None}
    ranks = average_ranks(scores, higher_is_better)
    chi2 = 12 * n / (k * (k + 1)) * (np.sum(ranks ** 2) - k * (k + 1) ** 2 / 4)
    p = float(_stats.chi2.sf(chi2, k - 1))
    denom = n * (k - 1) - chi2
    f = (n - 1) * chi2 / denom if denom > 0 else math.inf
    p_f = float(_stats.f.sf(f, k - 1, (k - 1) * (n - 1))) if math.isfinite(f) else 0.0
    return {"blocks": n, "methods": k, "chi2": float(chi2), "p_value": p, "iman_davenport_f": float(f),
            "p_value_f": p_f, "average_ranks": ranks.tolist()}


def nemenyi_cd(k: int, n: int, alpha: float = 0.05) -> float:
    """Critical difference of average ranks for k methods over n blocks (Nemenyi)."""
    q = NEMENYI_Q[alpha].get(k)
    if q is None:
        raise ValueError(f"no Nemenyi critical value for {k} methods (supported: 2-10)")
    return q * math.sqrt(k * (k + 1) / (6 * n))
