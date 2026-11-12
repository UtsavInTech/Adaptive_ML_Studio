"""Q3: cost terms per method / tier / run, as shares of the measured service time; plus the
controller state each joint run ended in. Prints a markdown table."""
from __future__ import annotations

from common import EXP, summary

TERMS = ["C_pre", "C_fs", "C_inf", "C_drift", "C_upd", "C_ret", "C_ctrl", "unattributed"]


def main():
    rows = []
    for run in sorted(EXP.iterdir()):
        if not (run / "trials").is_dir():
            continue
        for t in sorted((run / "trials").iterdir()):
            try:
                s = summary(t)
            except Exception:
                continue
            m = s["config"]["methods"][0]
            sm = s["summaries"][m]
            c = sm.get("cost_terms_us_per_row")
            if not c:
                continue
            ctl = sm.get("controller") or {}
            st = s["config"]["stream"]
            rows.append((run.name[16:60], t.name, st.get("label_delay", 0), c, sm["stream_scores_after_warmup"]["kappa_temporal"],
                         ctl.get("final_features"), ctl.get("final_update_stride"), ctl.get("final_narrow_processing"),
                         s["timing"].get("cpu_us_per_sample")))
    print("| run | trial | delay | " + " | ".join(TERMS) + " | total µs | biggest | κt | k·stride·narrow |")
    print("|" + "---|" * (len(TERMS) + 7))
    for run, tr, d, c, kt, k, sd, nw, cpu in rows:
        tot = c["total"]
        big = max(TERMS[:-1], key=lambda x: c[x] or 0)
        cells = " | ".join(f"{(c[x] or 0):.1f} ({100 * (c[x] or 0) / tot:.0f}%)" for x in TERMS)
        print(f"| {run} | {tr} | {d} | {cells} | {tot:.1f} | {big} | {kt:.2f} | {k}·{sd}·{nw} |")


if __name__ == "__main__":
    main()
