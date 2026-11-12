"""Build the paper's tables and figures from protocol runs (research testbed, phase 5).

    backend/.venv/bin/python research_testbed/scripts/report.py [--quick] [--out research_testbed/reports/<name>]
    backend/.venv/bin/python research_testbed/scripts/report.py --runs results/experiments/<id> … --out …

Reads the runs listed in research_testbed/protocol/generated[-quick]/runs.txt (or the given run
folders), and writes into the output folder:
  report.md                  every table, the figures, the statistical tests and the run IDs
  tables/trials.csv          one row per trial: settings, scores with 95 % block-bootstrap intervals, costs
  tables/settings.csv        the same, averaged over seeds, per setting · method · tier
  figures/*.png, *.svg       timeline, accuracy-vs-cost fronts, cost terms, ablations, label delay,
                             arrival rate, critical-difference diagram (each only when the runs allow it)
Every number is read or recomputed from the saved bundles (summary.json, outcomes.csv.gz); nothing is
tuned. The report states facts about the runs; interpreting them is the research workstream's job.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from adaptiveml.analysis import block_counts, bootstrap_ci, friedman, metrics, nemenyi_cd  # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LABELS = {
    "no_change": "Repeat last label", "static": "Static", "incremental": "Incremental",
    "adaptive": "Adaptive pipeline", "arf": "ARF", "srp": "SRP", "lev_bag": "Leveraging bagging",
    "joint": "Joint controller", "effort": "Budgeted effort controller",
}
ORDER = list(LABELS)
TIERS = ["standard", "small_sim", "micro_sim"]
COLORS = {"no_change": "#9aa0a6", "static": "#5f6368", "incremental": "#1a73e8", "adaptive": "#12b5cb",
          "arf": "#e8710a", "srp": "#d01884", "lev_bag": "#9334e6", "joint": "#188038",
          "effort": "#b31412"}
FLOOR = -3.0  # κ-temporal axis floor in the accuracy-vs-cost figure; lower points are labelled
COST_TERMS = ["C_pre", "C_fs", "C_inf", "C_drift", "C_upd", "C_ret", "C_ctrl"]


# ---------------------------------------------------------------- loading
def runs_from(args) -> list[tuple[str, Path]]:
    if args.runs:  # a run is `folder` (setting from --setting) or `setting=folder`
        out = []
        for p in args.runs:
            setting, _, folder = str(p).rpartition("=")
            out.append((setting or args.setting, Path(folder)))
        return out
    listing = ROOT / "research_testbed" / "protocol" / ("generated-quick" if args.quick else "generated") / "runs.txt"
    if not listing.exists():
        raise SystemExit(f"no runs listed in {listing.relative_to(ROOT)}; run the protocol first")
    out = []
    for line in listing.read_text().splitlines():
        if line.strip():
            stem, run_id = line.split("\t")
            out.append((stem, ROOT / "results" / "experiments" / run_id))
    return out


def load(runs, block_rows: int) -> list[dict]:
    trials = []
    for stem, folder in runs:
        for path in sorted((folder / "trials").glob("*/summary.json")):
            payload = json.loads(path.read_text())
            cfg, timing = payload["config"], payload["timing"]
            outcomes = path.parent / "outcomes.csv.gz"
            for method, s in payload["summaries"].items():
                counts = None
                if outcomes.exists():
                    y_true, y_pred = _outcomes(outcomes, method)
                    warmup = cfg["evaluation"]["warmup"]
                    if len(y_true) - warmup >= 2 * block_rows:
                        counts = block_counts(y_true, y_pred, warmup, block_rows)
                trials.append({
                    "setting": stem, "run": folder.name, "trial": path.parent.name, "method": method,
                    "tier": cfg["profile"]["name"], "seed": cfg["seed"], "config_hash": payload.get("config_hash"),
                    "stream": cfg["stream"], "controller": cfg.get("controller", {}),
                    "parallel": json.loads((folder / "manifest.json").read_text()).get("parallel_workers", 1),
                    "summary": s, "timing": timing, "scenario": payload["scenario"], "counts": counts,
                    "outcomes": outcomes if outcomes.exists() else None, "warmup": cfg["evaluation"]["warmup"],
                })
    trials.sort(key=lambda t: (t["setting"], ORDER.index(t["method"]) if t["method"] in ORDER else 99,
                               TIERS.index(t["tier"]) if t["tier"] in TIERS else 9, t["seed"]))
    return trials


@lru_cache(maxsize=4)
def _outcome_columns(path: Path) -> dict[str, np.ndarray]:
    """All label and prediction columns of a trial's outcomes.csv.gz, as int8 arrays."""
    with gzip.open(path, "rt", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        keep = [j for j, h in enumerate(header) if h == "y_true" or h.endswith(("_pred", "_service_ns"))]
        cols = [[] for _ in keep]
        for row in reader:
            for c, j in zip(cols, keep):
                c.append(row[j])
    return {header[j]: np.asarray(c, dtype=np.int64 if header[j].endswith("_service_ns") else np.int8)
            for j, c in zip(keep, cols)}


def _outcomes(path: Path, method: str):
    cols = _outcome_columns(path)
    return cols["y_true"], cols[f"{method}_pred"]


# ---------------------------------------------------------------- tables
def setting_rows(trials, n_boot: int) -> list[dict]:
    """Average over seeds per (setting, method, tier); the interval comes from bootstrapping blocks
    whose counts are summed over the seeds (the seeds share the same rows)."""
    groups = defaultdict(list)
    for t in trials:
        groups[(t["setting"], t["method"], t["tier"])].append(t)
    rows = []
    for (setting, method, tier), ts in groups.items():
        counts = [t["counts"] for t in ts if t["counts"] is not None]
        ci = bootstrap_ci(np.sum(counts, axis=0), n_boot=n_boot) if counts and len({len(c) for c in counts}) == 1 else None
        lat = [t["summary"]["latency_us"]["mean"] for t in ts]
        cost = {k: np.mean([t["summary"].get("cost_terms_us_per_row", {}).get(k) or 0 for t in ts]) for k in COST_TERMS}
        ctrl = ts[0]["summary"].get("controller")
        rows.append({
            "setting": setting, "method": method, "tier": tier, "seeds": len(ts),
            **{f"{m}": (ci[m]["value"] if ci else _metric(ts[0], m)) for m in ("accuracy", "kappa_temporal", "macro_f1", "recall", "false_alarm_rate")},
            **{f"{m}_low": ci[m]["low"] if ci else None for m in ("kappa_temporal", "macro_f1")},
            **{f"{m}_high": ci[m]["high"] if ci else None for m in ("kappa_temporal", "macro_f1")},
            "mean_us": float(np.mean(lat)), "mean_us_sd": float(np.std(lat, ddof=1)) if len(lat) > 1 else None,
            "p99_us": float(np.mean([t["summary"]["latency_us"]["p99"] for t in ts])),
            "peak_mb": float(np.mean([t["timing"]["peak_rss_mb"] for t in ts])),
            "adaptations": float(np.mean([t["summary"]["adaptations"]["count"] for t in ts])),
            "lightweight_rows": None if not ctrl else ctrl["rows_in_lightweight_mode"],
            "errors": float(np.mean([t["summary"]["scores_after_warmup"]["fp"] + t["summary"]["scores_after_warmup"]["fn"] for t in ts])),
            "onset_flows_before_flag": float(np.mean([_onset_sum(t) for t in ts])),
            "over_deadline_share": _mean_or_none([_over_deadline(t) for t in ts]),
            "modelled_us": _mean_or_none([((t["summary"].get("controller") or {}).get("effort") or {}).get("mean_modelled_us") for t in ts]),
            "budget_us": (ctrl or {}).get("budgets", {}).get("cpu_us_per_row") if ctrl else None,
            **cost,
            "label_delay": ts[0]["stream"].get("label_delay", 0), "label_coverage": ts[0]["stream"].get("label_coverage", 1.0),
            "arrival": ts[0]["stream"].get("arrival", "constant"), "rate_scale": ts[0]["stream"].get("rate_scale", 1.0),
            "parallel_workers": max(t["parallel"] for t in ts),
        })
    return rows


def _mean_or_none(values):
    values = [v for v in values if v is not None]
    return float(np.mean(values)) if values else None


def _onset_sum(t) -> int:
    """Σ flows before the first flag over the dated attack periods (those with ≥ 100 flows)."""
    return sum(p["flows_until_first_flagged"] if p["flows_until_first_flagged"] is not None else p["flows"]
               for p in (t["summary"].get("attack_periods") or []) if p["flows"] >= 100)


def _over_deadline(t) -> float | None:
    """Share of rows whose measured service time exceeded the tier's per-row deadline."""
    deadline = {"small_sim": 0.5, "micro_sim": 0.2}.get(t["tier"])
    if deadline is None or not t["outcomes"]:
        return None
    service = _service(t["outcomes"], t["method"])
    if service is None:
        return None
    return float(np.mean(service[t["warmup"]:] > deadline * 1e6))


def _service(outcomes: Path, method: str):
    cols = _outcome_columns(outcomes)
    v = cols.get(f"{method}_service_ns")
    return None if v is None else v.astype(float)


def _metric(t, name):
    s = t["summary"]
    if name == "false_alarm_rate":
        return (s.get("attack_types_after_warmup") or {}).get("BENIGN", {}).get("flagged_share")
    if name in ("accuracy", "recall"):
        return s["scores_after_warmup"][name]
    return (s.get("stream_scores_after_warmup") or {}).get(name)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def trial_rows(trials) -> list[dict]:
    out = []
    for t in trials:
        s = t["summary"]
        ci = bootstrap_ci(t["counts"], n_boot=200) if t["counts"] is not None else None
        out.append({
            "setting": t["setting"], "run": t["run"], "trial": t["trial"], "method": t["method"], "tier": t["tier"],
            "seed": t["seed"], "config_hash": t["config_hash"], "predictions_sha256": s["predictions_sha256"],
            "accuracy": s["scores_after_warmup"]["accuracy"], "kappa_temporal": _metric(t, "kappa_temporal"),
            "kappa_temporal_low": ci["kappa_temporal"]["low"] if ci else None,
            "kappa_temporal_high": ci["kappa_temporal"]["high"] if ci else None,
            "macro_f1": _metric(t, "macro_f1"), "recall": s["scores_after_warmup"]["recall"],
            "false_alarm_rate": _metric(t, "false_alarm_rate"), "mean_us": s["latency_us"]["mean"],
            "p99_us": s["latency_us"]["p99"], "peak_mb": t["timing"]["peak_rss_mb"],
            **{k: (s.get("cost_terms_us_per_row") or {}).get(k) for k in COST_TERMS},
        })
    return out


def fmt(v, digits=3, pct=False):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{100 * v:.1f}" if pct else f"{v:.{digits}f}"


def md_table(rows, setting_prefix: str) -> list[str]:
    sel = [r for r in rows if r["setting"].startswith(setting_prefix)]
    if not sel:
        return []
    lines = ["| Setting | Method | Tier | κ-temporal [95 % CI] | Macro-F1 | Attack recall % | False alarms % | Mean µs/row | p99 µs | Model changes |",
             "|---|---|---|---|--:|--:|--:|--:|--:|--:|"]
    for r in sel:
        ci = "" if r["kappa_temporal_low"] is None else f" [{fmt(r['kappa_temporal_low'])}, {fmt(r['kappa_temporal_high'])}]"
        lines.append(f"| {r['setting']} | {LABELS.get(r['method'], r['method'])} | {r['tier']} | {fmt(r['kappa_temporal'])}{ci} | "
                     f"{fmt(r['macro_f1'])} | {fmt(r['recall'], pct=True)} | {fmt(r['false_alarm_rate'], pct=True)} | "
                     f"{fmt(r['mean_us'], 1)} | {fmt(r['p99_us'], 1)} | {fmt(r['adaptations'], 0)} |")
    return lines


# ---------------------------------------------------------------- figures
def save(fig, folder: Path, name: str) -> str:
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(folder / f"{name}.{ext}", dpi=160)
    plt.close(fig)
    return name


def fig_timeline(trials, folder: Path) -> str | None:
    core = [t for t in trials if t["setting"] == "core" and t["tier"] == "standard" and t["outcomes"]]
    if not core:
        return None
    seed = min(t["seed"] for t in core)
    core = [t for t in core if t["seed"] == seed]
    ens = [t for t in trials if t["setting"] == "ensembles" and t["tier"] == "standard" and t["seed"] == seed and t["outcomes"]]
    fig, ax = plt.subplots(figsize=(11, 4))
    rows = len(_outcomes(core[0]["outcomes"], core[0]["method"])[0])
    window = int(max(1000, round(rows / 200, -3)))
    for t in core + ens:
        y, p = _outcomes(t["outcomes"], t["method"])
        correct = (y == p).astype(float)
        c = np.concatenate(([0], np.cumsum(correct)))
        roll = (c[window:] - c[:-window]) / window
        x = np.arange(window, len(correct) + 1)
        keep = x >= t["warmup"] + window
        ax.plot(x[keep], roll[keep], lw=1, color=COLORS.get(t["method"]), label=LABELS.get(t["method"], t["method"]))
    for period in (core[0]["scenario"].get("schedule") or {}).get("attack_periods", []):
        if period["flows"] >= 100:
            ax.axvspan(period["start_row"], period["end_row"], color="#d93025", alpha=0.08, lw=0)
    ax.set_xlabel("row of the replay"), ax.set_ylabel(f"accuracy over {window:,} rows")
    ax.set_title("Accuracy over time · shaded: dated attack periods (≥ 100 flows)", fontsize=10)
    ax.legend(fontsize=7, ncol=8, loc="upper center", bbox_to_anchor=(0.5, -0.18)), ax.set_ylim(None, 1.01)
    return save(fig, folder, "fig1_timeline")


def fig_pareto(rows, folder: Path) -> str | None:
    sel = [r for r in rows if r["setting"] in ("core", "ensembles") and r["kappa_temporal"] is not None]
    tiers = [t for t in TIERS if any(r["tier"] == t for r in sel)]
    if not sel:
        return None
    fig, axes = plt.subplots(1, len(tiers), figsize=(4.2 * len(tiers), 3.8), sharey=True, squeeze=False)
    for ax, tier in zip(axes[0], tiers):
        pts = [r for r in sel if r["tier"] == tier]
        for r in pts:
            err = None
            if r["kappa_temporal_low"] is not None:
                err = [[r["kappa_temporal"] - r["kappa_temporal_low"]], [r["kappa_temporal_high"] - r["kappa_temporal"]]]
            ax.errorbar(r["mean_us"], r["kappa_temporal"], yerr=err, fmt="o", color=COLORS.get(r["method"]),
                        label=LABELS.get(r["method"], r["method"]), capsize=2)
        front = sorted(pts, key=lambda r: r["mean_us"])
        best, line = -np.inf, []
        for r in front:
            if r["kappa_temporal"] > best:
                best = r["kappa_temporal"]
                line.append((r["mean_us"], best))
        if line:
            ax.step(*zip(*line), where="post", color="#202124", lw=0.8, ls="--")
        ax.set_xscale("log"), ax.set_title(tier, fontsize=10), ax.set_xlabel("mean µs per row (log)")
        ax.axhline(0, color="#9aa0a6", lw=0.6)
        low = [r for r in pts if r["kappa_temporal"] < FLOOR]
        if low:  # keep the informative range readable; say what is below it
            ax.set_ylim(FLOOR, 1.05)
            for r in low:
                ax.annotate(f"{LABELS.get(r['method'], r['method'])}: {r['kappa_temporal']:.1f} ↓",
                            (r["mean_us"], FLOOR), xytext=(0, 6), textcoords="offset points", fontsize=7,
                            ha="center", color=COLORS.get(r["method"]))
    axes[0][0].set_ylabel("κ-temporal (0 = repeat last label)")
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, fontsize=7, loc="lower center", ncol=8, bbox_to_anchor=(0.5, -0.02))
    fig.subplots_adjust(bottom=0.25)
    return save(fig, folder, "fig2_accuracy_vs_cost")


def fig_costs(rows, folder: Path) -> str | None:
    sel = [r for r in rows if r["setting"] in ("core", "ensembles") and sum(r[k] for k in COST_TERMS) > 0]
    if not sel:  # runs made before the cost terms existed
        return None
    fig, ax = plt.subplots(figsize=(max(6, 0.45 * len(sel)), 4))
    names = [f"{LABELS.get(r['method'], r['method'])}\n{r['tier']}" for r in sel]
    bottom = np.zeros(len(sel))
    palette = plt.get_cmap("tab10")
    for k, term in enumerate(COST_TERMS):
        vals = np.array([r[term] for r in sel])
        ax.bar(range(len(sel)), vals, bottom=bottom, label=term, color=palette(k))
        bottom += vals
    ax.set_xticks(range(len(sel)), names, rotation=90, fontsize=6)
    ax.set_ylabel("µs per row"), ax.set_yscale("log"), ax.legend(fontsize=7, ncol=7)
    ax.set_title("Cost per row by the review's terms (C_comm not applicable)", fontsize=10)
    return save(fig, folder, "fig3_cost_terms")


def fig_ablations(rows, folder: Path) -> str | None:
    sel = [r for r in rows if r["setting"].startswith("ablations") or (r["setting"] == "core" and r["method"] == "joint")]
    sel = [r for r in sel if r["tier"] != "standard"]
    if not any(r["setting"].startswith("ablations") for r in sel):
        return None
    tiers = sorted({r["tier"] for r in sel}, key=lambda t: TIERS.index(t) if t in TIERS else 9)
    fig, axes = plt.subplots(2, len(tiers), figsize=(5 * len(tiers), 6), squeeze=False)
    for col, tier in enumerate(tiers):
        pts = sorted([r for r in sel if r["tier"] == tier], key=lambda r: r["setting"])
        names = ["full (core)" if r["setting"] == "core" else r["setting"].replace("ablations_", "") for r in pts]
        k = [r["kappa_temporal"] or 0 for r in pts]
        err = [[(r["kappa_temporal"] or 0) - (r["kappa_temporal_low"] or r["kappa_temporal"] or 0) for r in pts],
               [(r["kappa_temporal_high"] or r["kappa_temporal"] or 0) - (r["kappa_temporal"] or 0) for r in pts]]
        axes[0][col].bar(names, k, yerr=err, color=COLORS["joint"], capsize=2)
        axes[0][col].set_title(f"{tier}: κ-temporal", fontsize=10)
        axes[1][col].bar(names, [r["mean_us"] for r in pts], color="#5f6368")
        axes[1][col].set_title(f"{tier}: mean µs per row", fontsize=10)
        for ax in (axes[0][col], axes[1][col]):
            ax.tick_params(axis="x", rotation=60, labelsize=7)
    return save(fig, folder, "fig4_ablations")


def fig_labels(rows, folder: Path) -> str | None:
    sel = [r for r in rows if r["setting"].startswith("labels")]
    if not sel:
        return None
    methods = [m for m in ORDER if any(r["method"] == m for r in sel)]
    fig, axes = plt.subplots(1, len(methods), figsize=(4 * len(methods), 3.5), sharey=True, squeeze=False)
    for ax, m in zip(axes[0], methods):
        for cov in sorted({r["label_coverage"] for r in sel}, reverse=True):
            pts = sorted([r for r in sel if r["method"] == m and r["label_coverage"] == cov], key=lambda r: r["label_delay"])
            ax.plot([max(r["label_delay"], 1) for r in pts], [r["kappa_temporal"] for r in pts], marker="o", label=f"coverage {cov:g}")
        ax.set_xscale("log"), ax.set_title(LABELS.get(m, m), fontsize=10), ax.set_xlabel("label delay, rows (0 shown at 1)")
    axes[0][0].set_ylabel("κ-temporal"), axes[0][0].legend(fontsize=7)
    return save(fig, folder, "fig5_label_delay")


def fig_rates(rows, folder: Path) -> str | None:
    sel = [r for r in rows if r["setting"].startswith("rates")]
    if not sel:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), squeeze=False)
    for key in sorted({(r["method"], r["tier"]) for r in sel}):
        pts = sorted([r for r in sel if (r["method"], r["tier"]) == key], key=lambda r: r["rate_scale"])
        label = f"{LABELS.get(key[0], key[0])} · {key[1]}"
        axes[0][0].plot([r["rate_scale"] for r in pts], [r["kappa_temporal"] for r in pts], marker="o", label=label)
        axes[0][1].plot([r["rate_scale"] for r in pts], [r["mean_us"] for r in pts], marker="o", label=label)
    for ax, title in zip(axes[0], ("κ-temporal", "mean µs per row")):
        ax.set_xscale("log"), ax.set_xlabel("speed-up of the recorded arrival rate"), ax.set_title(title, fontsize=10)
    axes[0][0].legend(fontsize=7)
    return save(fig, folder, "fig6_arrival_rate")


def friedman_test(trials, block_rows: int, segment_blocks: int):
    """Blocks: consecutive segments of the stream (segment_blocks × block_rows rows) per tier and seed.
    Metric: κ-temporal in the segment. Methods: those present in every block."""
    sel = [t for t in trials if t["setting"] in ("core", "ensembles") and t["counts"] is not None]
    by = defaultdict(dict)
    for t in sel:
        by[(t["tier"], t["seed"])][t["method"]] = t["counts"]
    methods = [m for m in ORDER if all(m in d for d in by.values())] if by else []
    if len(methods) < 3:
        return None
    blocks = []
    for d in by.values():
        n = min(len(d[m]) for m in methods)
        for a in range(0, n - segment_blocks + 1, segment_blocks):
            vals = [metrics(d[m][a:a + segment_blocks].sum(axis=0))["kappa_temporal"] for m in methods]
            if all(v is not None for v in vals):
                blocks.append(vals)
    if len(blocks) < 2:
        return None
    scores = np.asarray(blocks)
    result = friedman(scores)
    result["methods_order"] = methods
    result["segment_rows"] = segment_blocks * block_rows
    result["cd"] = nemenyi_cd(len(methods), len(blocks)) if len(methods) <= 10 else None
    return result


def fig_cd(result, folder: Path) -> str | None:
    if not result or result["cd"] is None:
        return None
    ranks, names, cd = result["average_ranks"], result["methods_order"], result["cd"]
    k = len(names)
    fig, ax = plt.subplots(figsize=(8, 0.5 * k + 1.2))
    ax.set_xlim(0.5, k + 0.5), ax.set_ylim(0, k + 1), ax.invert_xaxis()
    ax.axhline(k + 0.5, color="black", lw=1)
    for r in range(1, k + 1):
        ax.plot([r, r], [k + 0.4, k + 0.6], color="black", lw=1)
        ax.text(r, k + 0.75, str(r), ha="center", fontsize=8)
    for j, idx in enumerate(np.argsort(ranks)):
        y = k - j
        ax.plot([ranks[idx], ranks[idx]], [k + 0.5, y], color=COLORS.get(names[idx], "black"), lw=1)
        ax.text(ranks[idx] - 0.05, y, f"{LABELS.get(names[idx], names[idx])} ({ranks[idx]:.2f})", va="center", fontsize=8)
    ax.plot([1, 1 + cd], [0.4, 0.4], color="#d93025", lw=2)
    ax.text(1 + cd / 2, 0.6, f"CD = {cd:.2f}", ha="center", fontsize=8, color="#d93025")
    ax.axis("off")
    ax.set_title(f"Average rank by κ-temporal over {result['blocks']} stream segments (1 = best); "
                 f"Friedman p = {result['p_value']:.2g}", fontsize=9)
    return save(fig, folder, "fig7_critical_difference")


# ---------------------------------------------------------------- reproducibility and rules
def reproducibility(trials) -> list[str]:
    groups = defaultdict(list)
    for t in trials:
        if t["config_hash"]:
            groups[(t["config_hash"], t["method"])].append(t["summary"]["predictions_sha256"])
    repeated = {k: set(v) for k, v in groups.items() if len(v) > 1}
    if not repeated:
        return ["No configuration was run more than once in these runs. Re-run one with "
                "`adaptiveml.experiments.rerun` (or run the protocol twice) to check reproducibility."]
    same = sum(1 for v in repeated.values() if len(v) == 1)
    lines = [f"{len(repeated)} configurations were run more than once; "
             f"{same} produced identical predictions in every repeat."]
    differ = [k for k, v in repeated.items() if len(v) > 1]
    if differ:
        lines.append(f"{len(differ)} groups differ between repeats: " + ", ".join(sorted({m for _, m in differ})) +
                     ". The joint and adaptive controllers react to measured time, so repeats under different load can differ.")
    return lines


def quality_cost_table(rows) -> list[str]:
    lines = ["| Setting | Method | Tier | Errors | κ-temporal [95 % CI] | Attack recall % | False alarms % | "
             "Σ flows before first flag (onsets) | Modelled µs/row | Measured µs/row | Budget µs/row | Rows over deadline % |",
             "|---|---|---|--:|---|--:|--:|--:|--:|--:|--:|--:|"]
    for r in rows:
        ci = "" if r["kappa_temporal_low"] is None else f" [{fmt(r['kappa_temporal_low'])}, {fmt(r['kappa_temporal_high'])}]"
        lines.append(f"| {r['setting']} | {LABELS.get(r['method'], r['method'])} | {r['tier']} | {r['errors']:,.0f} | "
                     f"{fmt(r['kappa_temporal'])}{ci} | {fmt(r['recall'], pct=True)} | {fmt(r['false_alarm_rate'], pct=True)} | "
                     f"{r['onset_flows_before_flag']:,.0f} | {fmt(r['modelled_us'], 1)} | {fmt(r['mean_us'], 1)} | "
                     f"{fmt(r['budget_us'], 0)} | {fmt(r['over_deadline_share'], pct=True)} |")
    return lines if len(lines) > 2 else []


def effort_table(trials) -> list[str]:
    sel = [t for t in trials if (t["summary"].get("controller") or {}).get("effort")]
    if not sel:
        return []
    lines = ["| Setting | Tier | Seed | Rows per level | Mean modelled / measured µs vs budget | Final · peak price | "
             "Updates skipped % | Statistics rows % | Ranking rows % | Final features | Fast switches · damped · muted · warm starts | Actions |",
             "|---|---|--:|---|---|---|--:|--:|--:|--:|---|---|"]
    for t in sel:
        c = t["summary"]["controller"]
        e = c["effort"]
        levels = " · ".join(f"{k} {v:,}" for k, v in e["rows_per_level"].items())
        budget = "—" if e["budget_us_per_row"] is None else f"{e['budget_us_per_row']:.0f}"
        r = e["repairs"]
        acts = ", ".join(f"{k} ×{v}" for k, v in c["actions"].items()) or "none"
        lines.append(f"| {t['setting']} | {t['tier']} | {t['seed']} | {levels} | {e['mean_modelled_us']:.1f} / "
                     f"{e['mean_measured_us']:.1f} vs {budget} | {e['final_price']:.2f} · {e['peak_price']:.2f} | "
                     f"{100 * e['share_rows_update_skipped']:.1f} | {100 * e['share_rows_statistics_updated']:.1f} | "
                     f"{100 * e['share_rows_ranking_updated']:.1f} | {c['final_features']} | "
                     f"{r['fast_switch_promotions']} · {r['damped_alarms']} · {r['muted_labels']:,} · {r['warm_starts']} | {acts} |")
    return lines


def rule_table(trials) -> list[str]:
    sel = [t for t in trials if t["summary"].get("controller")]
    if not sel:
        return []
    lines = ["| Setting | Method | Tier | Seed | Rows in lightweight mode | Final features · stride · narrow | Peak model KB | "
             "Memory checks over budget | Actions |", "|---|---|---|--:|--:|---|--:|--:|---|"]
    for t in sel:
        c = t["summary"]["controller"]
        acts = ", ".join(f"{k} ×{v}" for k, v in c["actions"].items()) or "none"
        peak = c.get("peak_model_bytes")
        checks = f"{c.get('memory_probes_over_budget', 0)} of {c['memory_probes']}" if c.get("memory_probes") else "—"
        narrow = "yes" if c.get("final_narrow_processing") else "no"
        lines.append(f"| {t['setting']} | {LABELS.get(t['method'], t['method'])} | {t['tier']} | {t['seed']} | {c['rows_in_lightweight_mode']:,} | "
                     f"{c['final_features']} · {c['final_update_stride']} · {narrow} | "
                     f"{'—' if not peak else round(peak / 1024)} | {checks} | {acts} |")
    return lines


# ---------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="report on the quick protocol's runs")
    parser.add_argument("--runs", nargs="*", help="run folders instead of the protocol's runs.txt; `setting=folder` names each")
    parser.add_argument("--setting", default="core", help="with --runs: the setting these runs stand for")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--block-rows", type=int, default=10_000)
    parser.add_argument("--segment-blocks", type=int, default=5, help="blocks per Friedman segment")
    parser.add_argument("--n-boot", type=int, default=1000)
    args = parser.parse_args()
    out = args.out or ROOT / "research_testbed" / "reports" / ("protocol-quick" if args.quick else "protocol")
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "tables").mkdir(parents=True, exist_ok=True)

    runs = runs_from(args)
    trials = load(runs, args.block_rows)
    if not trials:
        raise SystemExit("no trials found")
    rows = setting_rows(trials, args.n_boot)
    write_csv(out / "tables" / "settings.csv", rows)
    write_csv(out / "tables" / "trials.csv", trial_rows(trials))
    fr = friedman_test(trials, args.block_rows, args.segment_blocks)
    figs = [f for f in (
        fig_timeline(trials, out / "figures"), fig_pareto(rows, out / "figures"), fig_costs(rows, out / "figures"),
        fig_ablations(rows, out / "figures"), fig_labels(rows, out / "figures"), fig_rates(rows, out / "figures"),
        fig_cd(fr, out / "figures"),
    ) if f]
    parallel = max(t["parallel"] for t in trials)

    lines = [f"# Research testbed report — {out.name}", "",
             f"{len(trials)} trials from {len(runs)} experiment runs. Scores are after warm-up. κ-temporal is "
             "accuracy beyond repeating the previous row's label (0 = no better). Intervals are 95 % "
             f"block-bootstrap intervals ({args.block_rows:,}-row blocks, {args.n_boot} resamples, counts summed over seeds).",
             "", "Device tiers other than `standard` are **simulated with placeholder budgets**. Energy is not measured.",
             *([f"", f"**Trials ran {parallel} at a time on one machine; timings include contention.**"] if parallel > 1 else []),
             ""]
    notes = {"labels": "κ-temporal here still uses the *immediately* previous label as its reference. With "
                       "delayed labels a deployed system cannot see that label, so the reference is stricter than any "
                       "method could reach: compare methods with each other, not with 0."}
    for title, prefix in (("Core methods", "core"), ("Literature ensembles", "ensembles"), ("Ablations of the joint controller", "ablations"),
                          ("Ablations of the budgeted effort controller", "effort_ablations"),
                          ("R5 on a memory-limited tier", "memory"),
                          ("Delayed and partial labels", "labels"), ("Recorded arrival rate", "rates")):
        table = md_table(rows, prefix)
        if table:
            lines += [f"## {title}", "", *([notes[prefix], ""] if prefix in notes else []), *table, ""]
    lines += ["## Figures", ""] + [f"![{f}](figures/{f}.png)" for f in figs] + [""]
    lines += ["## Methods compared over stream segments (Friedman, Nemenyi)", ""]
    if fr:
        names = ", ".join(f"{LABELS.get(m, m)} {r:.2f}" for m, r in zip(fr["methods_order"], fr["average_ranks"]))
        lines += [f"{fr['blocks']} segments of {fr['segment_rows']:,} rows (per tier and seed), metric κ-temporal. "
                  f"Friedman χ² = {fr['chi2']:.1f}, p = {fr['p_value']:.2g}; Iman–Davenport F = {fr['iman_davenport_f']:.1f}, "
                  f"p = {fr['p_value_f']:.2g}. Average ranks (1 = best): {names}. "
                  f"Nemenyi critical difference at α = 0.05: {fr['cd']:.2f}." if fr["cd"] else "", "",
                  "Segments of one stream are not independent datasets, so treat the test as descriptive.", ""]
    else:
        lines += ["Not enough methods or segments in these runs.", ""]
    quality = quality_cost_table(rows)
    if quality:
        lines += ["## Errors, onsets and cost against the budget", "", *quality, ""]
    effort = effort_table(trials)
    if effort:
        lines += ["## Budgeted effort controller", "", *effort, ""]
    rules = rule_table(trials)
    if rules:
        lines += ["## Controller decisions", "", *rules, ""]
    lines += ["## Reproducibility", "", *reproducibility(trials), "",
              "## Runs", "", *[f"- `{stem}`: `{folder.name}`" for stem, folder in runs], ""]
    (out / "report.md").write_text("\n".join(lines))
    print(f"report: {out / 'report.md'} · {len(figs)} figures · {len(trials)} trials")


if __name__ == "__main__":
    main()
