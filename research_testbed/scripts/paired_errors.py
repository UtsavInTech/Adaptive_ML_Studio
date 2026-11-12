"""Paired block bootstrap of the difference in errors between two methods on the same rows.

    backend/.venv/bin/python research_testbed/scripts/paired_errors.py A_trial_dir:method B_trial_dir:method [...]

Each argument pair is compared; rows after warm-up (1,000) are cut into 10,000-row blocks, blocks are
resampled with replacement (2,000 resamples, seed 0), and the 95 % interval of errors(A) − errors(B) is
printed. Negative = A makes fewer errors. Used for research/effort_results.md.
"""
import csv, gzip, sys
import numpy as np

def errors(arg):
    folder, method = arg.rsplit(":", 1)
    with gzip.open(f"{folder}/outcomes.csv.gz", "rt") as f:
        r = csv.reader(f); h = next(r); jt, jp = h.index("y_true"), h.index(f"{method}_pred")
        e = np.array([row[jt] != row[jp] for row in r], dtype=np.int64)
    e = e[1000:]
    n = len(e) // 10_000
    return e[: n * 10_000].reshape(n, -1).sum(axis=1)

rng = np.random.default_rng(0)
args = sys.argv[1:]
for a, b in zip(args[::2], args[1::2]):
    ea, eb = errors(a), errors(b)
    d = ea - eb
    boots = d[rng.integers(0, len(d), size=(2000, len(d)))].sum(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print(f"{a.split('/')[-1]} − {b.split('/')[-1]}: {d.sum():+,} errors [95 % {lo:+,.0f}, {hi:+,.0f}]; "
          f"A better in {int((d < 0).sum())} of {len(d)} blocks, worse in {int((d > 0).sum())}")
