"""Figures for findings_from_results.md (static PNGs). Reads the JSON caches written by the other scripts."""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common import CACHE, FIG, outcomes, summary, trial_dirs

S = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": SURF, "axes.facecolor": SURF, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.6, "axes.axisbelow": True})


def fig_error_position():
    R = {r["label"]: r for r in json.loads((CACHE / "error_structure_all.json").read_text())}
    keys = ["Repeat last label", "Adaptive (old ctrl)", "Joint std", "Joint gateway", "Joint gateway −R3", "ARF", "SRP"]
    buckets = ["0-0", "1-9", "10-99", "100-999", ">=1000"]
    names = ["switch row", "1–9", "10–99", "100–999", "≥1000"]
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    left = np.zeros(len(keys))
    for j, b in enumerate(buckets):
        v = np.array([R[k]["err_by_runpos"][b] / R[k]["errors"] for k in keys])
        ax.barh(keys, v, left=left, color=S[j], edgecolor=SURF, linewidth=2, label=names[j], height=0.6)
        left += v
    for i, k in enumerate(keys):
        ax.text(1.01, i, f"{R[k]['errors']:,} errors", va="center", color=INK2, fontsize=8)
    ax.set_xlim(0, 1.18)
    ax.invert_yaxis()
    ax.set_xlabel("share of the method's errors, by rows since the true label last changed")
    ax.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.45, 1.16), frameon=False, fontsize=8)
    ax.set_title("Errors sit right after label switches (full stream, after warm-up)", loc="left", color=INK, pad=24)
    fig.tight_layout()
    fig.savefig(FIG / "q1_error_position.png", dpi=150)


def fig_costs():
    rows = [
        ("Repeat last label (Wed)", "q_core", "no_change__standard__max__s11"),
        ("Static (Wed)", "q_core", "static__standard__max__s11"),
        ("Adaptive old ctrl (full)", "p3", "adaptive__standard__max__s42"),
        ("Incremental (Wed)", "q_core", "incremental__standard__max__s11"),
        ("Joint standard (full)", "p3", "joint__standard__max__s42"),
        ("Joint gateway −R3 (full)", "p3_nor3", "joint__gateway_sim__max__s42"),
        ("Joint memory 256K (full)", "mem_full", "joint__memory_sim__max__s11"),
        ("Joint small_sim (Wed)", "q_core", "joint__small_sim__max__s11"),
        ("Joint gateway (full)", "p3", "joint__gateway_sim__max__s42"),
        ("Joint micro_sim (Wed)", "q_core", "joint__micro_sim__max__s11"),
    ]
    terms = ["C_pre", "C_fs", "C_inf", "C_drift", "C_upd", "C_ret", "C_ctrl"]
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    left = np.zeros(len(rows))
    data = []
    for lab, rk, tr in rows:
        s = summary(trial_dirs(rk)[tr])
        m = s["config"]["methods"][0]
        data.append(s["summaries"][m]["cost_terms_us_per_row"])
    for j, t in enumerate(terms):
        v = np.array([(d[t] or 0) / d["total"] for d in data])
        ax.barh([r[0] for r in rows], v, left=left, color=S[j], edgecolor=SURF, linewidth=2, height=0.6, label=t)
        left += v
    for i, d in enumerate(data):
        ax.text(1.01, i, f"{d['total']:.0f} µs", va="center", color=INK2, fontsize=8)
    ax.set_xlim(0, 1.13)
    ax.invert_yaxis()
    ax.set_xlabel("share of service time per row (mean total at right; load differed between runs)")
    ax.legend(ncol=7, loc="upper center", bbox_to_anchor=(0.45, 1.13), frameon=False, fontsize=8)
    ax.set_title("Where the time goes: preprocessing and model update dominate", loc="left", color=INK, pad=22)
    fig.tight_layout()
    fig.savefig(FIG / "q3_cost_terms.png", dpi=150)


def fig_gateway_blocks():
    B = 10_000

    def blk(rk, tr):
        t = trial_dirs(rk)[tr]
        s = summary(t)
        m = s["config"]["methods"][0]
        o = outcomes(t)
        e = (o["y_true"] != o[f"{m}_pred"])[1000:]
        n = len(e) // B * B
        return e[:n].reshape(-1, B).sum(1)

    g = blk("p3", "joint__gateway_sim__max__s42")
    r3 = blk("p3_nor3", "joint__gateway_sim__max__s42")
    mem = blk("mem_full", "joint__memory_sim__max__s11")
    x = (np.arange(len(g)) * B + 1000) / 1e6
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.plot(x, g + 1, color=S[1], lw=1.5, label="joint gateway (R3 cut to 4 features at row 3,635)")
    ax.plot(x, mem + 1, color=S[2], lw=1.5, label="joint memory tier (14 features, live ranking)")
    ax.plot(x, r3 + 1, color=S[0], lw=1.5, label="joint gateway without R3 (56 features, 3× over budget)")
    ax.set_yscale("log")
    ax.set_xlabel("stream row (millions)")
    ax.set_ylabel("errors per 10,000 rows (+1)")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title("4 features lose 5–10× in every attack stretch; quiet benign stretches are error-free for all", loc="left", color=INK)
    fig.tight_layout()
    fig.savefig(FIG / "q2_gateway_blocks.png", dpi=150)


def fig_delay():
    P = json.loads((CACHE / "periods_delay.json").read_text())["delay"]
    sel = [r for r in P if r["coverage"] == "1"]
    labs = [f"{r['method']} d={r['delay']}" for r in sel]
    on = np.array([r["fn_in_onset_window"] + r["fp_in_onset_window"] for r in sel])
    end = np.array([r["fp_in_end_window"] for r in sel])
    tot = np.array([r["errors"] for r in sel])
    other = tot - on - end
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.barh(labs, on, color=S[0], edgecolor=SURF, linewidth=2, height=0.6, label="attack onset window (onset … onset+delay+2,000)")
    ax.barh(labs, end, left=on, color=S[1], edgecolor=SURF, linewidth=2, height=0.6, label="false alarms after an attack ends")
    ax.barh(labs, other, left=on + end, color=S[3], edgecolor=SURF, linewidth=2, height=0.6, label="elsewhere (mostly mid-attack after resets)")
    ax.invert_yaxis()
    ax.set_xlabel("errors after warm-up (Wednesday 300k, small_sim, all labels)")
    ax.legend(frameon=False, fontsize=8, loc="center right")
    ax.set_title("Delayed labels: detection-driven methods lose mid-attack, not at onset", loc="left", color=INK)
    fig.tight_layout()
    fig.savefig(FIG / "q4_label_delay.png", dpi=150)


if __name__ == "__main__":
    FIG.mkdir(parents=True, exist_ok=True)
    fig_error_position()
    fig_costs()
    fig_gateway_blocks()
    fig_delay()
