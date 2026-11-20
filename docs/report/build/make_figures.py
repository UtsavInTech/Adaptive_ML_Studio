"""Draws the diagrams and charts used in the project report.

Run with the project's own Python:  backend/.venv/bin/python docs/report/build/make_figures.py

Diagrams are drawn here with matplotlib (plain boxes and arrows). Every chart reads the saved
result tables in research_testbed/reports/, so the numbers in the report are the numbers in the
files. The accuracy timeline needs the saved trial outcomes in results/experiments/.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter
from matplotlib.patches import FancyArrow, FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "assets"
REPORTS = ROOT / "research_testbed" / "reports"
plt.rcParams.update({
    "font.family": "STIXGeneral", "mathtext.fontset": "stix", "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.8,
    "axes.edgecolor": "#222222", "axes.labelsize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "savefig.dpi": 300, "figure.dpi": 100,
})
INK = "#1a1a1a"
RULES = "#b8741a"      # the review's rules
OURS = "#1f7a5a"       # the new controller
GREY = "#8c959f"
BLUE = "#3b6ea5"


def settings(name: str) -> list[dict]:
    with (REPORTS / name / "tables" / "settings.csv").open() as f:
        return list(csv.DictReader(f))


def pick(rows, **kw):
    for r in rows:
        if all(r[k] == v for k, v in kw.items()):
            return r
    raise KeyError(kw)


def f(r, key):
    return float(r[key])


COMMA = FuncFormatter(lambda v, _: f"{v:,.0f}")


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight", pad_inches=0.06, facecolor="white")
    plt.close(fig)
    print("wrote", name)


# ------------------------------------------------------------------ diagram helpers
def box(ax, x, y, w, h, text, size=9, bold=False, fc="white", ec=INK, lw=1.0, align="center", italic=False):
    ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, zorder=3,
            fontweight="bold" if bold else "normal", fontstyle="italic" if italic else "normal", linespacing=1.25)


def arrow(ax, x0, y0, x1, y1, width=0.012, head=0.05, hollow=True):
    dx, dy = x1 - x0, y1 - y0
    ax.add_patch(FancyArrow(x0, y0, dx, dy, width=width, head_width=head, head_length=head * 0.9,
                            length_includes_head=True, fc="white" if hollow else INK, ec=INK, lw=0.9, zorder=4))


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w), ax.set_ylim(0, h), ax.axis("off")
    return fig, ax


# ------------------------------------------------------------------ diagrams
def fig_architecture():
    fig, ax = canvas(6.2, 4.0)
    # four layers, stacked, joined by hollow arrows (the plain style of the university's other reports)
    box(ax, 0.1, 3.32, 6.0, 0.58,
        "Browser: React and TypeScript application with six pages\n(Home, Live demo, Experiments, Testbed, Findings, Method)", size=9)
    box(ax, 0.1, 2.5, 6.0, 0.58,
        "API server (FastAPI): checks every setting, runs one job at a time,\nstreams progress to the browser and serves saved reports", size=9)
    ax.add_patch(Rectangle((0.1, 0.78), 6.0, 1.45, fc="#f3f3f3", ec=INK, lw=1.0, zorder=1))
    ax.text(3.1, 2.07, "Trial worker (a separate process for every trial)", ha="center", va="center", fontsize=9, fontweight="bold")
    inner = ["Stream reader\none row at\na time", "Pipeline\nprepare, select,\npredict, detect,\nadapt, learn", "Controller\nrules R1 to R5\nor effort\ncontroller", "Metrics and\nstage timers"]
    xs = [0.25, 1.78, 3.31, 4.84]
    for x, t in zip(xs, inner):
        box(ax, x, 0.9, 1.2, 0.95, t, size=8)
    for x in (1.45, 2.98, 4.51):
        arrow(ax, x, 1.37, x + 0.33, 1.37, width=0.03, head=0.11)
    box(ax, 0.1, 0.0, 6.0, 0.5,
        "Files on disk: data (catalogue, prepared stream), results (settings, outcomes,\nevent logs) and reports (tables, figures). No database is used", size=8.8)
    for y0, y1 in ((3.32, 3.08), (2.5, 2.23), (0.78, 0.5)):
        arrow(ax, 3.1, y0, 3.1, y1, width=0.05, head=0.14)
    save(fig, "fig_architecture")

def fig_pipeline():
    fig, ax = canvas(6.2, 3.0)
    top = ["1  Data stream", "2  Preprocessing", "3  Feature\nselection", "4  Prediction"]
    bot = ["8  Monitoring", "7  Learning", "6  Model\nadaptation", "5  Drift\ndetection"]
    w, h, gap = 1.2, 0.62, 0.38
    x0 = 0.12
    for i, t in enumerate(top):
        box(ax, x0 + i * (w + gap), 2.0, w, h, t, size=9)
        if i < 3:
            arrow(ax, x0 + i * (w + gap) + w, 2.31, x0 + (i + 1) * (w + gap), 2.31, width=0.03, head=0.12)
    for i, t in enumerate(bot):
        box(ax, x0 + i * (w + gap), 0.95, w, h, t, size=9)
        if i < 3:
            arrow(ax, x0 + (i + 1) * (w + gap), 1.26, x0 + i * (w + gap) + w, 1.26, width=0.03, head=0.12)
    xr = x0 + 3 * (w + gap) + w / 2
    arrow(ax, xr, 2.0, xr, 1.57, width=0.03, head=0.12)
    ax.text(xr - 0.12, 1.78, "label arrives", fontsize=7.6, ha="right", va="center", style="italic")
    box(ax, 0.12, -0.08, 5.94, 0.5, "Controller: reads drift, error rate, time and memory;\nit decides how much work each row gets", size=8.6, fc="#f3f3f3")
    ax.annotate("", xy=(3.1, 0.95), xytext=(3.1, 0.42), arrowprops=dict(arrowstyle="<|-|>", lw=1.0, color=INK))
    ax.text(0.12, 2.88, "Each row is predicted first and learned from afterwards", fontsize=9, style="italic", va="center")
    save(fig, "fig_pipeline")

def fig_controller():
    fig, ax = canvas(6.2, 2.95)
    w, h = 1.85, 0.8
    xs = [0.1, 2.17, 4.24]
    box(ax, xs[0], 1.95, w, h, "Activity signal\nlabel changes, recent\nerrors, drift alarm", size=8.2)
    box(ax, xs[1], 1.95, w, h, "Price of compute\nrises when over budget,\nfalls when under", size=8.2)
    box(ax, xs[2], 1.95, w, h, "Effort level for the row\nthe richest level worth\nits price", size=8.2)
    arrow(ax, xs[0] + w, 2.35, xs[1], 2.35, width=0.03, head=0.12)
    arrow(ax, xs[1] + w, 2.35, xs[2], 2.35, width=0.03, head=0.12)
    box(ax, xs[2], 0.95, w, h * 0.8, "The row is processed,\nits cost taken from a\ncost model", size=8.2)
    box(ax, xs[1], 0.95, w, h * 0.8, "Cost compared with\nthe budget per row", size=8.2)
    arrow(ax, xs[2] + w / 2, 1.95, xs[2] + w / 2, 1.59, width=0.03, head=0.12)
    arrow(ax, xs[2], 1.27, xs[1] + w, 1.27, width=0.03, head=0.12)
    arrow(ax, xs[1] + w / 2, 1.59, xs[1] + w / 2, 1.95, width=0.03, head=0.12)
    box(ax, 0.1, 0.1, 5.99, 0.5, "Hard limits always win: memory limit, time limit for one row,\nand no replacement model on the smallest device", size=8.4, fc="#f3f3f3")
    save(fig, "fig_controller")

def fig_phases():
    fig, ax = canvas(6.4, 1.75)
    steps = ["Review of\n20 studies", "Studio:\npipeline, live\ndemo, runner", "Real data:\nCIC-IDS2017\nstream reader",
             "Fair scoring\nand baselines", "Controllers:\nrules R1 to R5,\neffort", "Device tiers,\nlate labels,\nprotocol", "Screens and\nreports"]
    w, gap = 0.78, 0.15
    for i, t in enumerate(steps):
        x = 0.08 + i * (w + gap)
        box(ax, x, 0.55, w, 0.95, t, size=7.6)
        ax.text(x + w / 2, 0.3, f"Phase {i + 1}" if i else "Phase 0", ha="center", fontsize=8, style="italic")
        if i < len(steps) - 1:
            arrow(ax, x + w, 1.02, x + w + gap, 1.02, width=0.025, head=0.1)
    save(fig, "fig_phases")


# ------------------------------------------------------------------ charts
def fig_accuracy_vs_kappa():
    rows = settings("phase2")
    order = [("no_change", "Repeat\nlast label"), ("incremental", "Incre-\nmental"), ("adaptive", "Adaptive\npipeline"),
             ("lev_bag", "Lev.\nbagging"), ("arf", "ARF"), ("srp", "SRP")]
    rs = [pick(rows, method=m, tier="standard") for m, _ in order]
    acc = [f(r, "accuracy") * 100 for r in rs]
    kap = [f(r, "kappa_temporal") for r in rs]
    lo = [f(r, "kappa_temporal") - f(r, "kappa_temporal_low") for r in rs]
    hi = [f(r, "kappa_temporal_high") - f(r, "kappa_temporal") for r in rs]
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 2.9), sharex=True)
    x = np.arange(len(order))
    colors = [GREY] + [BLUE] * 5
    a.bar(x, acc, color=colors, width=0.62)
    for xi, v in zip(x, acc):
        a.text(xi, v + 1.5, f"{v:.1f}", ha="center", fontsize=8)
    a.set_ylim(0, 112), a.set_yticks([0, 25, 50, 75, 100]), a.set_ylabel("Accuracy (%)")
    a.set_title("(a) Accuracy: almost no difference", fontsize=9.5)
    b.bar(x, kap, color=colors, width=0.62, yerr=[lo, hi], error_kw=dict(lw=0.8, capsize=2, ecolor=INK))
    for xi, v, h in zip(x, kap, hi):
        b.text(xi, v + h + 0.03, f"{v:.2f}", ha="center", fontsize=8)
    b.set_ylim(0, 1.12), b.set_ylabel(r"Score above copying ($\kappa$-temporal)")
    b.set_title("(b) Score above copying: clear spread", fontsize=9.5)
    for ax_ in (a, b):
        ax_.set_xticks(x), ax_.set_xticklabels([l for _, l in order], fontsize=8)
        ax_.grid(axis="y", color="#dddddd", lw=0.6), ax_.set_axisbelow(True)
    fig.tight_layout(w_pad=1.6)
    save(fig, "fig_accuracy_vs_kappa")


def fig_cost_terms():
    rows = settings("effort")
    sel = [("incremental", "Incremental\n(no detection)"), ("joint", "Review's rules\n(R1 to R5)"), ("effort", "New controller\n(ours)")]
    groups = [("Getting the data ready", ["C_pre", "C_fs"], "#3b6ea5"), ("Making the prediction", ["C_inf"], "#1f7a5a"),
              ("Learning from the answer", ["C_upd", "C_ret"], "#d9772b"), ("Drift checks and control", ["C_drift", "C_ctrl"], "#9aa3ad")]
    fig, ax = plt.subplots(figsize=(6.4, 2.55))
    for i, (m, label) in enumerate(sel):
        r = pick(rows, setting="core", method=m, tier="small_sim")
        left = 0.0
        for gname, keys, col in groups:
            v = sum(f(r, k) for k in keys)
            ax.barh(i, v, left=left, color=col, edgecolor="white", lw=0.8, height=0.58)
            if v > 12:
                ax.text(left + v / 2, i, f"{v:.0f}", ha="center", va="center", color="white", fontsize=8.5, fontweight="bold")
            left += v
        ax.text(left + 3, i, f"{left:.0f} µs", va="center", fontsize=9)
    ax.set_yticks(range(len(sel))), ax.set_yticklabels([s[1] for s in sel], fontsize=8.6)
    ax.invert_yaxis(), ax.set_xlim(0, 195), ax.set_xlabel("Microseconds per connection, small device (simulated)")
    ax.grid(axis="x", color="#e3e3e3", lw=0.6), ax.set_axisbelow(True)
    handles = [Rectangle((0, 0), 1, 1, fc=c) for _, _, c in groups]
    ax.legend(handles, [g for g, _, _ in groups], ncol=2, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.27))
    fig.tight_layout()
    save(fig, "fig_cost_terms")


def fig_heldout():
    rows = settings("heldout")
    cats = [("thursday", "small_sim", "Thursday\nsmall device"), ("friday", "small_sim", "Friday\nsmall device"),
            ("thursday", "micro_sim", "Thursday\nvery small"), ("friday", "micro_sim", "Friday\nvery small")]
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.6, 3.0))
    x = np.arange(len(cats))
    w = 0.4
    for key, ax_, ylabel in (("mean_us", a, "Microseconds per connection"), ("errors", b, "Wrong decisions per day")):
        for j, (m, col, lab) in enumerate((("joint", RULES, "Review's rules (R1 to R5)"), ("effort", OURS, "New controller (ours)"))):
            vals = [f(pick(rows, setting=s, method=m, tier=t), key) for s, t, _ in cats]
            bars = ax_.bar(x + (j - 0.5) * w, vals, w, color=col, label=lab)
            for xi, v in zip(x + (j - 0.5) * w, vals):
                ax_.text(xi, v + (3 if key == "mean_us" else 50), f"{v:,.0f}", ha="center", va="bottom", fontsize=6.8,
                         bbox=dict(fc="white", ec="none", pad=0.4, alpha=0.85), zorder=6)
        ax_.set_xticks(x), ax_.set_xticklabels([c[2] for c in cats], fontsize=7.6)
        ax_.set_ylabel(ylabel), ax_.grid(axis="y", color="#e3e3e3", lw=0.6), ax_.set_axisbelow(True)
    # budget marks on the time panel
    for xi, (s, t, _) in zip(x, cats):
        bud = f(pick(rows, setting=s, method="effort", tier=t), "budget_us")
        a.plot([xi - 0.42, xi + 0.42], [bud, bud], color=INK, lw=1.4, ls=(0, (3, 2)), zorder=4)
    a.plot([], [], color=INK, lw=1.4, ls=(0, (3, 2)), label="Device time budget")
    a.set_ylim(0, 185), b.set_ylim(0, 4300), b.yaxis.set_major_formatter(COMMA)
    a.set_title("(a) Computing time", fontsize=9.5), b.set_title("(b) Quality", fontsize=9.5)
    h, l = a.get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, fontsize=8, frameon=False, bbox_to_anchor=(0.5, -0.04))
    fig.tight_layout(rect=(0, 0.06, 1, 1), w_pad=1.6)
    save(fig, "fig_heldout")


def fig_late_labels():
    rows = settings("effort")
    sel = [("incremental", "Incremental\n(no detection)"), ("joint", "Review's rules\n(R1 to R5)"), ("effort", "New controller\n(ours)")]
    fig, ax = plt.subplots(figsize=(5.4, 2.7))
    x = np.arange(len(sel)); w = 0.36
    on = [f(pick(rows, setting="core", method=m, tier="small_sim"), "errors") for m, _ in sel]
    late = [f(pick(rows, setting="labels_delay1000", method=m, tier="small_sim"), "errors") for m, _ in sel]
    ax.bar(x - w / 2, on, w, color=GREY, label="Answers arrive at once")
    ax.bar(x + w / 2, late, w, color="#b5483a", label="Answers arrive 1,000 connections late")
    for xi, v in zip(x - w / 2, on):
        ax.text(xi, v + 1000, f"{v:,.0f}", ha="center", fontsize=8)
    for xi, v in zip(x + w / 2, late):
        ax.text(xi, v + 1000, f"{v:,.0f}", ha="center", fontsize=8)
    ax.set_xticks(x), ax.set_xticklabels([s[1] for s in sel], fontsize=8.6)
    ax.set_ylabel("Wrong decisions"), ax.set_ylim(0, 70000), ax.yaxis.set_major_formatter(COMMA)
    ax.grid(axis="y", color="#e3e3e3", lw=0.6), ax.set_axisbelow(True)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    save(fig, "fig_late_labels")


def fig_timeline():
    spec = importlib.util.spec_from_file_location("report_script", ROOT / "research_testbed" / "scripts" / "report.py")
    sys.path.insert(0, str(ROOT / "backend"))
    rep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rep)
    runs = []
    for line in (REPORTS / "phase2" / "report.md").read_text().splitlines():
        if line.startswith("- `core`: `"):
            runs.append(("core", ROOT / "results" / "experiments" / line.split("`")[3]))
    trials = rep.load(runs, 10_000)
    sched = json.loads((ROOT / "data" / "cicids2017" / "prepared" / "schedule.json").read_text())
    want = [("no_change", "Repeat last label", GREY, 0.9), ("static", "Trained once (static)", "#222222", 1.0),
            ("incremental", "Incremental", BLUE, 1.0), ("adaptive", "Adaptive pipeline", OURS, 1.1), ("arf", "Adaptive Random Forest", RULES, 1.0)]
    fig, ax = plt.subplots(figsize=(6.6, 3.1))
    window = 10_000
    for p in sched["attack_periods"]:
        if p["flows"] >= 100:
            ax.axvspan(p["start_row"] / 1e6, p["end_row"] / 1e6, color="#d9534f", alpha=0.10, lw=0)
    for m, label, col, lw in want:
        t = next(t for t in trials if t["method"] == m and t["tier"] == "standard" and t["outcomes"])
        y, p = rep._outcomes(t["outcomes"], m)
        c = np.concatenate(([0], np.cumsum((y == p).astype(float))))
        roll = (c[window:] - c[:-window]) / window
        xs = np.arange(window, len(y) + 1)
        keep = xs >= t["warmup"] + window
        ax.plot(xs[keep] / 1e6, roll[keep], color=col, lw=lw, label=label)
    names = {"monday": "Mon", "tuesday": "Tue", "wednesday": "Wed", "thursday": "Thu", "friday": "Fri"}
    for d, r in sched["day_start_rows"].items():
        ax.axvline(r / 1e6, color="#999999", lw=0.6, ls=":")
        ax.text(r / 1e6 + 0.02, 1.045, names[d], fontsize=8.5, va="bottom")
    ax.set_xlim(0, 2.1), ax.set_ylim(-0.02, 1.08)
    ax.set_xlabel("Position in the stream (millions of connections)"), ax.set_ylabel("Accuracy over the last 10,000 rows")
    ax.grid(axis="y", color="#e8e8e8", lw=0.6)
    ax.legend(fontsize=7.8, ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    fig.tight_layout()
    save(fig, "fig_timeline")


if __name__ == "__main__":
    only = set(sys.argv[1:])
    for name, fn in [("architecture", fig_architecture), ("pipeline", fig_pipeline), ("controller", fig_controller),
                     ("phases", fig_phases), ("accuracy", fig_accuracy_vs_kappa), ("cost", fig_cost_terms),
                     ("heldout", fig_heldout), ("late", fig_late_labels), ("timeline", fig_timeline)]:
        if not only or name in only:
            fn()
