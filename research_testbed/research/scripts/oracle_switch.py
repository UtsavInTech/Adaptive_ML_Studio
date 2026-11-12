"""§6.3 'search over configurations': an oracle that picks, per 10,000-row block, the saved run
(configuration θ) with the fewest errors whose measured mean service time in that block meets the
tier's CPU budget — versus the configuration the rule ladder actually ran.

ROUGH UPPER BOUND. It assumes switching is free and that a configuration's errors in a block do not
depend on which configuration ran before (each saved run carries its own model history). Times were
measured under machine contention, so which blocks 'meet the budget' is itself noisy.
Also reports a Lagrangian version (budget on the stream mean, not on every block), i.e. minimising
J = errors + λ·cost with λ chosen so the mean cost meets the budget."""
from __future__ import annotations

import json
import sys

import numpy as np

from common import CACHE, RUNS, outcomes, summary, trial_dirs

BLOCK = 10_000


def load(run_key, trial):
    t = trial_dirs(run_key)[trial]
    s = summary(t)
    m = s["config"]["methods"][0]
    w = s["config"]["evaluation"]["warmup"]
    o = outcomes(t)
    err = (o["y_true"] != o[f"{m}_pred"])[w:]
    svc = o[f"{m}_service_ns"][w:] / 1e3
    n = len(err) // BLOCK * BLOCK
    return err[:n].reshape(-1, BLOCK).sum(1), svc[:n].reshape(-1, BLOCK).mean(1), int(err.sum()), float(svc.mean())


def oracle(cands: dict, budget: float, actual: str, tag: str):
    names = list(cands)
    E = np.stack([cands[k][0] for k in names])  # configs x blocks
    C = np.stack([cands[k][1] for k in names])
    nb = E.shape[1]
    ok = C <= budget
    feas_err = np.where(ok, E, np.inf)
    pick = feas_err.argmin(0)
    none_ok = ~ok.any(0)
    # where nothing meets the budget, take the cheapest
    pick[none_ok] = C[:, none_ok].argmin(0)
    o_err = E[pick, np.arange(nb)].sum()
    o_cost = C[pick, np.arange(nb)].mean()
    # Lagrangian: per block min E + lam*C*BLOCK/1e3 ; bisection on lam so mean cost <= budget
    lo, hi = 0.0, 1e4
    for _ in range(60):
        lam = (lo + hi) / 2
        pk = (E + lam * C).argmin(0)
        if C[pk, np.arange(nb)].mean() > budget:
            lo = lam
        else:
            hi = lam
    pk = (E + hi * C).argmin(0)
    l_err, l_cost = E[pk, np.arange(nb)].sum(), C[pk, np.arange(nb)].mean()
    a = names.index(actual)
    print(f"\n### {tag}: budget {budget} µs/row, {nb} blocks of {BLOCK}, {len(names)} configurations")
    print("| configuration | errors (block-aligned) | mean µs | blocks within budget |")
    print("|---|--:|--:|--:|")
    for i, k in enumerate(names):
        print(f"| {k} | {int(E[i].sum()):,} | {C[i].mean():.0f} | {int(ok[i].sum())}/{nb} |")
    print(f"| **rules as run ({actual})** | {int(E[a].sum()):,} | {C[a].mean():.0f} | {int(ok[a].sum())}/{nb} |")
    print(f"| **oracle, budget met in every block** | {int(o_err):,} | {o_cost:.0f} | {nb - int(none_ok.sum())}/{nb} |")
    print(f"| **oracle, budget met on average (Lagrangian)** | {int(l_err):,} | {l_cost:.0f} | — |")
    used = {names[i]: int((pick == i).sum()) for i in np.unique(pick)}
    usedl = {names[i]: int((pk == i).sum()) for i in np.unique(pk)}
    print(f"\nPer-block oracle used: {used}. Lagrangian used: {usedl}. Blocks where nothing met the budget: {int(none_ok.sum())}.")
    return {"tag": tag, "actual_err": int(E[a].sum()), "oracle_err": int(o_err), "lagr_err": int(l_err),
            "oracle_cost": float(o_cost), "lagr_cost": float(l_cost), "used": used, "used_lagr": usedl}


def main():
    res = []
    full = {
        "joint gateway (R3: 4 feat, narrow, stride 4)": ("p3", "joint__gateway_sim__max__s42"),
        "joint gateway −gating": ("p3_nogating", "joint__gateway_sim__max__s42"),
        "joint gateway −R2": ("p3_nor2", "joint__gateway_sim__max__s42"),
        "joint gateway −R5 (4 feat, stride 2)": ("p3_nor5", "joint__gateway_sim__max__s42"),
        "joint gateway −R3 (56 feat, lightweight)": ("p3_nor3", "joint__gateway_sim__max__s42"),
        "joint standard (56 feat, R1)": ("p3", "joint__standard__max__s42"),
        "joint memory 256K (R5: 14 feat)": ("mem_full", "joint__memory_sim__max__s11"),
        "joint memory −R5 (56 feat)": ("mem_nor5", "joint__memory_sim__max__s11"),
        "adaptive (old ctrl)": ("p3", "adaptive__standard__max__s42"),
        "adaptive gateway": ("p3", "adaptive__gateway_sim__max__s42"),
    }
    extra = {
        "incremental": ("p2_core", "incremental__standard__max__s42"),
        "repeat last label": ("p2_core", "no_change__standard__max__s42"),
        "ARF": ("p2_core", "arf__standard__max__s42"),
    }
    F = {k: load(*v) for k, v in {**full, **extra}.items()}
    res.append(oracle({k: F[k] for k in full}, 100.0, "joint gateway (R3: 4 feat, narrow, stride 4)", "Full stream, gateway_sim, joint-pipeline configurations only"))
    res.append(oracle(F, 100.0, "joint gateway (R3: 4 feat, narrow, stride 4)", "Full stream, gateway_sim, all saved methods"))

    q = {}
    for t in ("small_sim", "micro_sim"):
        q[f"joint {t} (as run)"] = ("q_core", f"joint__{t}__max__s11")
        for ab in ("without_resource_checks", "without_R1", "without_R2", "without_R3", "without_R4", "without_R5"):
            q[f"joint {t} {ab}"] = ("q_ablations_" + ab, f"joint__{t}__max__s11")
        for rate in ("x10", "x100", "x1000"):
            q[f"joint {t} recorded{rate}"] = ("q_rates_recorded" + rate, f"joint__{t}__max__s11")
    q["joint standard"] = ("q_core", "joint__standard__max__s11")
    for cov in ("0.5", "0.1"):
        q[f"joint small, learn on {cov} of rows"] = (f"q_labels_delay0_cov{cov}", "joint__small_sim__max__s11")
    qx = {"incremental": ("q_core", "incremental__standard__max__s11"),
          "adaptive": ("q_core", "adaptive__standard__max__s11"),
          "repeat last label": ("q_core", "no_change__standard__max__s11"),
          "ARF": ("q_ens", "arf__standard__max__s11")}
    Q = {}
    for k, v in {**q, **qx}.items():
        if v[0] in RUNS:
            Q[k] = load(*v)
        else:
            print("missing", v, file=sys.stderr)
    QJ = {k: Q[k] for k in Q if k.startswith("joint")}
    res.append(oracle(QJ, 100.0, "joint small_sim (as run)", "Wednesday 300k, small_sim, joint configurations"))
    res.append(oracle(QJ, 50.0, "joint micro_sim (as run)", "Wednesday 300k, micro_sim, joint configurations"))
    res.append(oracle(Q, 50.0, "joint micro_sim (as run)", "Wednesday 300k, micro_sim, all saved methods"))
    (CACHE / "oracle.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
