/** "The data changed": the most recent samples in two features, coloured by their true label, with the
 *  current concept boundary. For SEA the inputs keep the same distribution and only the labels move —
 *  which is what concept drift means. */

import { useMemo } from "react";
import type uPlot from "uplot";

import UPlotChart from "../charts/UPlot";
import { scatterChart } from "../charts/plots";
import type { Extras } from "../lib/api";

export default function DataSnapshot({ extras, theme }: { extras: Extras | null; theme: string }) {
  const axes = extras?.axes ?? ["x0", "x1"];
  const options = useMemo(() => scatterChart(axes as [string, string], extras?.real_data), [axes[0], axes[1], theme, extras?.real_data]);

  const data = useMemo<uPlot.AlignedData>(() => {
    const points = [...(extras?.points ?? [])].sort((a, b) => a[0] - b[0]);
    const xs = points.map((p) => p[0]);
    const positive = points.map((p) => (p[2] === 1 ? p[1] : null));
    const negative = points.map((p) => (p[2] === 0 ? p[1] : null));
    const threshold = extras?.concept.threshold ?? null;
    const boundary = xs.map((x) => {
      if (threshold == null) return null;
      const y = threshold - x;
      return y >= 0 && y <= 10 ? y : null;
    });
    return [xs, positive, negative, boundary] as uPlot.AlignedData;
  }, [extras]);

  if (!extras?.points.length) {
    return <div className="empty small">Waiting for samples…</div>;
  }
  return (
    <div className="stack">
      <UPlotChart options={options} data={data} height={186} />
      <div className="legend">
        <span className="key" style={{ color: "var(--accent)" }}>
          <span className="swatch" style={{ background: "var(--accent)", height: 8, width: 8, borderRadius: "50%" }} />
          <span className="muted">label 1</span>
        </span>
        <span className="key" style={{ color: "var(--muted)" }}>
          <span className="swatch" style={{ background: "var(--muted)", height: 8, width: 8, borderRadius: "50%" }} />
          <span className="muted">label 0</span>
        </span>
        {!extras.real_data && <span className="key" style={{ color: "var(--drift)" }}>
          <span className="swatch dashed" />
          <span className="muted">concept boundary (θ = {extras.concept.threshold ?? "—"})</span>
        </span>}
      </div>
    </div>
  );
}
