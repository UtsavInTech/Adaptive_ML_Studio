"""Turn saved experiment bundles into comparison tables (Markdown) and a long-format CSV.

    backend/.venv/bin/python research_testbed/scripts/compare_runs.py results/experiments/<id> [<id> …] \
        [--out research_testbed/results/phase2.md] [--csv research_testbed/results/phase2.csv]

Every figure is read from the bundles' summary.json files; nothing is recomputed or tuned. The
tables name the run IDs they come from, so each number can be traced back.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ORDER = ["no_change", "static", "incremental", "adaptive", "arf", "srp", "lev_bag", "joint"]
LABELS = {
    "no_change": "Repeat last label", "static": "Static", "incremental": "Incremental",
    "adaptive": "Adaptive pipeline", "arf": "ARF", "srp": "SRP", "lev_bag": "Leveraging bagging",
    "joint": "Joint controller",
}


def name(t: dict) -> str:
    """Method label, plus the profile when it is not the standard one and the ablation, if any."""
    label = LABELS.get(t["method"], t["method"])
    profile = t["trial"].split("__")[1] if "__" in t["trial"] else "standard"
    if profile != "standard":
        label += f" · {profile}"
    if "-ablation-" in t["run"]:
        label += " · without " + t["run"].split("-ablation-")[1].replace("no-", "").replace("-", " ")
    return label


def load(dirs: list[Path]) -> list[dict]:
    trials = []
    for d in dirs:
        for f in sorted((d / "trials").glob("*/summary.json")):
            payload = json.loads(f.read_text())
            for method, s in payload["summaries"].items():
                trials.append({"run": d.name, "trial": f.parent.name, "method": method, "timing": payload["timing"], "s": s})
    trials.sort(key=lambda t: (ORDER.index(t["method"]) if t["method"] in ORDER else 99, t["trial"], t["run"]))
    return trials


def pct(v, digits=1):
    return "—" if v is None else f"{100 * v:.{digits}f}"


def num(v, digits=3):
    return "—" if v is None else f"{v:.{digits}f}"


def main_table(trials) -> list[str]:
    rows = ["| Method | Accuracy % | κ | κ-temporal | Macro-F1 | Attack recall % | False alarms % (benign) | Mean µs | p99 µs | Peak MB | Model changes |",
            "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for t in trials:
        s, ss = t["s"], t["s"].get("stream_scores_after_warmup") or {}
        sc = s["scores_after_warmup"]
        benign = (s.get("attack_types_after_warmup") or {}).get("BENIGN", {})
        rows.append(
            f"| {name(t)} | {pct(sc['accuracy'], 2)} | {num(ss.get('kappa'))} | "
            f"{num(ss.get('kappa_temporal'))} | {num(ss.get('macro_f1'))} | {pct(sc['recall'])} | "
            f"{pct(benign.get('flagged_share'), 2)} | {num(s['latency_us']['mean'], 1)} | {num(s['latency_us']['p99'], 1)} | "
            f"{num(t['timing'].get('peak_rss_mb'), 0)} | {s['adaptations']['count']} |"
        )
    nc = next((t["s"]["stream_scores_after_warmup"]["no_change_accuracy"] for t in trials
               if t["s"].get("stream_scores_after_warmup")), None)
    if nc is not None:
        rows.append("")
        rows.append(f"Accuracy of repeating the previous row's label over the same rows: **{pct(nc, 2)} %** "
                    "(the reference for κ-temporal).")
    return rows


def per_type_table(trials) -> list[str]:
    types = {}
    for t in trials:
        for label, v in (t["s"].get("attack_types_after_warmup") or {}).items():
            types.setdefault(label, v)
    if not types:
        return []
    names = sorted(types, key=lambda n: (not types[n]["counted_as_attack"], n))
    head = "| Original label | Counted as | Rows | " + " | ".join(name(t) for t in trials) + " |"
    rows = [head, "|---|---|--:|" + "--:|" * len(trials)]
    for label in names:
        cells = [pct((t["s"]["attack_types_after_warmup"] or {}).get(label, {}).get("flagged_share")) for t in trials]
        rows.append(f"| {label} | {'attack' if types[label]['counted_as_attack'] else 'benign'} | {types[label]['rows']:,} | " + " | ".join(cells) + " |")
    return rows


def period_table(trials) -> list[str]:
    first = next((t for t in trials if t["s"].get("attack_periods")), None)
    if first is None:
        return []
    head = "| # | Attack period | Flows | " + " | ".join(name(t) for t in trials) + " |"
    rows = [head, "|--:|---|--:|" + "---|" * len(trials)]
    for k, p in enumerate(first["s"]["attack_periods"], 1):
        cells = []
        for t in trials:
            q = t["s"]["attack_periods"][k - 1]
            missed = q["flows_until_first_flagged"]
            cells.append(f"{pct(q['recall'], 0)} · {'never' if missed is None else missed}")
        rows.append(f"| {k} | {p['attack_type']} (rows {p['start_row']:,}–{p['end_row']:,}) | {p['flows']:,} | " + " | ".join(cells) + " |")
    return rows


def cost_table(trials) -> list[str]:
    keys = ["C_pre", "C_fs", "C_inf", "C_drift", "C_upd", "C_ret", "C_ctrl", "unattributed", "total"]
    if not any(t["s"].get("cost_terms_us_per_row") for t in trials):
        return []
    rows = ["| Method | " + " | ".join(keys) + " |", "|---|" + "--:|" * len(keys)]
    for t in trials:
        c = t["s"].get("cost_terms_us_per_row")
        if c:
            rows.append(f"| {name(t)} | " + " | ".join(num(c.get(k), 2) for k in keys) + " |")
    rows += ["", "C_comm is not applicable: every stage runs in one local process."]
    return rows


def controller_table(trials) -> list[str]:
    ctrl = [t for t in trials if t["s"].get("controller")]
    if not ctrl:
        return []
    rows = ["| Run | Rules | Resource checks | Rows in lightweight mode | Final features · stride · narrow | Actions |",
            "|---|---|---|--:|---|---|"]
    for t in ctrl:
        c = t["s"]["controller"]
        acts = ", ".join(f"{k} ×{v}" for k, v in c["actions"].items()) or "none"
        rows.append(f"| {name(t)} | {' '.join(c['rules'])} | {'on' if c['resource_gating'] else 'off'} | "
                    f"{c['rows_in_lightweight_mode']:,} | {c['final_features']} · {c['final_update_stride']} · "
                    f"{'yes' if c.get('final_narrow_processing') else 'no'} | {acts} |")
    return rows


def write_csv(trials, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run", "trial", "method", "scope", "name", "metric", "value"])
        for t in trials:
            s = t["s"]
            base = [t["run"], t["trial"], t["method"]]
            for k, v in s["scores_after_warmup"].items():
                w.writerow(base + ["overall", "", k, v])
            for k, v in (s.get("stream_scores_after_warmup") or {}).items():
                w.writerow(base + ["overall", "", k, v])
            for k, v in s["latency_us"].items():
                w.writerow(base + ["overall", "", f"latency_us_{k}", v])
            w.writerow(base + ["overall", "", "peak_rss_mb", t["timing"].get("peak_rss_mb")])
            for label, v in (s.get("attack_types_after_warmup") or {}).items():
                w.writerow(base + ["label", label, "flagged_share", v["flagged_share"]])
                w.writerow(base + ["label", label, "rows", v["rows"]])
            for k, p in enumerate(s.get("attack_periods") or [], 1):
                for metric in ("recall", "flows_until_first_flagged", "false_alarm_rate", "detector_alerts", "adaptations"):
                    w.writerow(base + ["period", f"{k}:{p['attack_type']}", metric, p[metric]])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    trials = load(args.runs)
    lines = ["## Overall (after warm-up)", "", *main_table(trials), "",
             "## Share of each original label flagged as an attack (%)", "",
             "For an attack type this is its recall; for benign traffic it is the false-alarm rate.", "",
             *per_type_table(trials), "",
             "## Cost per row after warm-up, by the review's terms (µs)", "", *(cost_table(trials) or ["Not recorded in these runs."]), "",
             "## Joint controller decisions", "", *(controller_table(trials) or ["No joint-controller trials in these runs."]), "",
             "## Each dated attack period: recall % · flows of that attack before the first was flagged", "",
             *period_table(trials), "",
             "Runs: " + ", ".join(f"`{d.name}`" for d in args.runs)]
    text = "\n".join(lines) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    else:
        print(text)
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        write_csv(trials, args.csv)


if __name__ == "__main__":
    main()
