/** Chart option builders. The x-axis is always the sample index, so runs stay comparable across
 *  stream rates. Event markers (true drift, detection, adaptation) are drawn by a small plugin. */

import uPlot from "uplot";

export type Marker = { x: number; kind: "true" | "detected" | "adaptation" | "budget"; label: string; sub?: string };

/** A shaded stretch of rows behind the lines — the windows a table's columns were scored over. */
export type Band = { from: number; to: number; color: string; label?: string };

/** Draws bands under the series. `globalAlpha` keeps them faint enough to read the lines through. */
export function bandsPlugin(bands: () => Band[]): uPlot.Plugin {
  return {
    hooks: {
      drawClear: (u: uPlot) => {
        const { ctx } = u;
        const { left, top, width, height } = u.bbox;
        ctx.save();
        ctx.textAlign = "left"; // uPlot leaves its own alignment on the canvas
        ctx.textBaseline = "bottom";
        ctx.font = `600 ${11 * devicePixelRatio}px ${css("--font", "sans-serif")}`;
        for (const band of bands()) {
          const a = Math.max(left, Math.round(u.valToPos(band.from, "x", true)));
          const b = Math.min(left + width, Math.round(u.valToPos(band.to, "x", true)));
          if (b <= a) continue;
          ctx.globalAlpha = 0.13;
          ctx.fillStyle = band.color;
          ctx.fillRect(a, top, b - a, height);
          if (band.label) {
            ctx.globalAlpha = 0.9;
            ctx.fillText(band.label, a + 4 * devicePixelRatio, top + height - 4 * devicePixelRatio);
          }
        }
        ctx.restore();
      },
    },
  };
}

export const STAGE_ORDER = ["preprocess", "select", "predict", "detect", "adapt", "update"] as const;

export function css(name: string, fallback = "#888"): string {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export const methodColor = (method: string): string =>
  ({ static: css("--static"), adaptive: css("--adaptive"), incremental: css("--incremental"), arf: css("--arf") })[method] ??
  css("--accent");

const markerColor = (kind: Marker["kind"]): string =>
  ({ true: css("--drift"), detected: css("--detect"), adaptation: css("--adapt"), budget: css("--warn") })[kind];

/** Vertical event markers, drawn as labelled flags in a lane above the plot.
 *
 *  These are the story of the run — the data changed here, the detector reacted here, the model was
 *  replaced here — so they get their own band of the canvas (`FLAG_LANE` px of top padding) rather
 *  than being drawn over the curve they annotate. Chips stack into whichever lane is free, because a
 *  drift, its detection and the adaptation that follows land within a few hundred samples of each
 *  other and would otherwise overprint. */
export const FLAG_LANES = 3;
const LANE_HEIGHT = 20;
export const FLAG_LANE = FLAG_LANES * LANE_HEIGHT + 6;

export function markersPlugin(markers: () => Marker[]): uPlot.Plugin {
  return {
    hooks: {
      draw: (u: uPlot) => {
        const { ctx } = u;
        const list = markers();
        const present = document.documentElement.classList.contains("present");
        const fontSize = present ? 12 : 10.5;
        const font = css("--font", "sans-serif");
        const padding = 6;
        const chipHeight = 17;
        // The rightmost pixel each lane has already used, so a chip only shares a lane when it fits.
        const laneEnds = new Array(FLAG_LANES).fill(-Infinity);
        ctx.save();
        // uPlot leaves its own alignment on the context when it finishes drawing the axes; without
        // this the chip labels are laid out from the wrong edge and render outside their chip.
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        for (const marker of list) {
          const left = Math.round(u.valToPos(marker.x, "x", true));
          if (left < u.bbox.left - 2 || left > u.bbox.left + u.bbox.width + 2) continue;
          const colour = markerColor(marker.kind);
          ctx.strokeStyle = colour;
          ctx.lineWidth = present ? 2.5 : 1.5;
          ctx.setLineDash(marker.kind === "true" ? [5, 4] : []);
          ctx.beginPath();
          ctx.moveTo(left, u.bbox.top - 2);
          ctx.lineTo(left, u.bbox.top + u.bbox.height);
          ctx.stroke();
          ctx.setLineDash([]);

          // An unlabelled marker is still an event — it draws its line, but claims no room for a
          // chip. Repeat events on a small chart use this so the labelled ones stay readable.
          if (!marker.label) continue;

          ctx.font = `700 ${fontSize}px ${font}`;
          const label = marker.sub ? `${marker.label.toUpperCase()}  ${marker.sub}` : marker.label.toUpperCase();
          const width = ctx.measureText(label).width + padding * 2;
          const chipLeft = Math.min(Math.max(u.bbox.left, left + 4), u.bbox.left + u.bbox.width - width);
          let lane = laneEnds.findIndex((end) => chipLeft > end + 5);
          if (lane < 0) lane = FLAG_LANES - 1;
          laneEnds[lane] = chipLeft + width;
          const top = u.bbox.top - FLAG_LANE + 3 + lane * LANE_HEIGHT;

          // A hairline from the chip down to the event's own line, so a stacked chip still reads as
          // belonging to the sample it marks.
          ctx.strokeStyle = colour;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(left, top + chipHeight);
          ctx.lineTo(left, u.bbox.top - 2);
          ctx.stroke();

          ctx.fillStyle = colour;
          ctx.beginPath();
          ctx.roundRect(chipLeft, top, width, chipHeight, 3);
          ctx.fill();
          ctx.fillStyle = css("--surface", "#fff");
          ctx.fillText(label, chipLeft + padding, top + 3.5);
        }
        ctx.restore();
      },
    },
  };
}

export type TooltipContent = { title: string; rows: { k: string; v: string }[] } | null;

/** A small hover panel: what this point is, in a few lines. Built with DOM nodes rather than HTML
 *  strings, and deliberately short — a chart tooltip that needs scrolling is not a tooltip. */
export function tooltipPlugin(render: (u: uPlot, idx: number) => TooltipContent): uPlot.Plugin {
  let tip: HTMLDivElement | null = null;
  return {
    hooks: {
      init: (u: uPlot) => {
        tip = document.createElement("div");
        tip.className = "u-tip";
        tip.hidden = true;
        u.over.appendChild(tip);
      },
      setCursor: (u: uPlot) => {
        if (!tip) return;
        const idx = u.cursor.idx;
        const left = u.cursor.left ?? -1;
        const top = u.cursor.top ?? -1;
        const content = idx == null || left < 0 ? null : render(u, idx);
        if (!content) {
          tip.hidden = true;
          return;
        }
        tip.textContent = "";
        const title = document.createElement("strong");
        title.textContent = content.title;
        tip.appendChild(title);
        for (const row of content.rows) {
          const line = document.createElement("span");
          const key = document.createElement("i");
          key.textContent = row.k;
          const value = document.createElement("b");
          value.textContent = row.v;
          line.append(key, value);
          tip.appendChild(line);
        }
        tip.hidden = false;
        // Keep the panel inside the plot, flipping to the other side of the cursor near an edge.
        const width = tip.offsetWidth;
        const height = tip.offsetHeight;
        const maxX = u.over.clientWidth - width - 8;
        const maxY = u.over.clientHeight - height - 8;
        const x = Math.min(Math.max(8, left + 14), Math.max(8, maxX));
        const y = Math.min(Math.max(8, top + 14), Math.max(8, maxY));
        tip.style.transform = `translate(${x}px, ${y}px)`;
      },
    },
  };
}

const baseAxes = (xLabel: string, yLabel: string, yFormat?: (v: number) => string): uPlot.Axis[] => [
  {
    label: xLabel,
    labelSize: 22,
    stroke: css("--muted"),
    grid: { stroke: css("--grid"), width: 1 },
    ticks: { stroke: css("--grid") },
    font: `11px ${css("--font", "sans-serif")}`,
    labelFont: `11px ${css("--font", "sans-serif")}`,
    values: (_u, splits) => splits.map((v) => (v >= 1000 ? `${(v / 1000).toFixed(v % 1000 ? 1 : 0)}k` : `${v}`)),
  },
  {
    label: yLabel,
    labelSize: 26,
    stroke: css("--muted"),
    grid: { stroke: css("--grid"), width: 1 },
    ticks: { stroke: css("--grid") },
    font: `11px ${css("--font", "sans-serif")}`,
    labelFont: `11px ${css("--font", "sans-serif")}`,
    values: yFormat ? (_u, splits) => splits.map(yFormat) : undefined,
  },
];

const cursor: uPlot.Cursor = { drag: { x: true, y: false }, points: { size: 5 } };

export type LineSpec = { label: string; color: string; dash?: number[]; width?: number; fill?: string };

export function lineChart(opts: {
  xLabel: string;
  yLabel: string;
  lines: LineSpec[];
  yRange?: [number | null, number | null];
  yFormat?: (v: number) => string;
  markers?: () => Marker[];
  bands?: () => Band[];
  legend?: boolean;
  tooltip?: (u: uPlot, idx: number) => TooltipContent;
}): uPlot.Options {
  const yScale: uPlot.Scale = opts.yRange ? { range: () => [opts.yRange![0] ?? 0, opts.yRange![1] ?? 1] } : { time: false };
  return {
    width: 600,
    height: 200,
    legend: { show: opts.legend ?? false },
    cursor,
    // Event flags get their own band above the plot rather than stretching the y-axis past the data
    // — an accuracy axis that runs to 110 % to make room for a label is a lie for a layout's sake.
    padding: [opts.markers ? FLAG_LANE : 10, 12, 0, 0],
    scales: { x: { time: false }, y: yScale },
    axes: baseAxes(opts.xLabel, opts.yLabel, opts.yFormat),
    series: [
      { label: "sample" },
      ...opts.lines.map((line) => ({
        label: line.label,
        stroke: line.color,
        width: line.width ?? 1.75,
        dash: line.dash,
        fill: line.fill,
        spanGaps: false,
        points: { show: false },
      })),
    ],
    plugins: [
      ...(opts.bands ? [bandsPlugin(opts.bands)] : []),
      ...(opts.markers ? [markersPlugin(opts.markers)] : []),
      ...(opts.tooltip ? [tooltipPlugin(opts.tooltip)] : []),
    ],
  };
}

/** Stacked bands for the per-stage cost breakdown (values are cumulated by the caller). */
export function stackedChart(opts: { xLabel: string; yLabel: string; keys: readonly string[]; markers?: () => Marker[] }): uPlot.Options {
  const colors = opts.keys.map((_, i) => css(`--stage-${i + 1}`));
  return {
    width: 600,
    height: 170,
    legend: { show: false },
    cursor,
    padding: [10, 12, 0, 0],
    scales: { x: { time: false }, y: { time: false } },
    axes: baseAxes(opts.xLabel, opts.yLabel),
    series: [
      { label: "sample" },
      ...opts.keys.map((key, i) => ({
        label: key,
        stroke: colors[i],
        width: 1,
        fill: colors[i] + "55",
        points: { show: false },
      })),
    ],
    plugins: opts.markers ? [markersPlugin(opts.markers)] : [],
  };
}

/** Cumulative sums so stacked bands can be drawn as overlapping filled lines (top band first). */
export function stack(series: number[][]): number[][] {
  const out: number[][] = [];
  for (let i = series.length - 1; i >= 0; i--) {
    const previous = out[0];
    out.unshift(series[i].map((v, j) => v + (previous ? previous[j] : 0)));
  }
  return out;
}

/** Points only (no connecting line): one series per label so each point keeps its method's colour. */
export function pointsChart(opts: {
  xLabel: string;
  yLabel: string;
  labels: string[];
  colors: string[];
  yFormat?: (v: number) => string;
  tooltip?: (u: uPlot, idx: number) => TooltipContent;
}): uPlot.Options {
  return {
    width: 600,
    height: 200,
    legend: { show: false },
    cursor: { show: true, points: { size: 9 } },
    padding: [12, 14, 0, 0],
    scales: { x: { time: false }, y: { time: false } },
    axes: baseAxes(opts.xLabel, opts.yLabel, opts.yFormat),
    series: [
      { label: "x" },
      ...opts.labels.map((label, i) => ({
        label,
        stroke: opts.colors[i],
        paths: () => null,
        points: { show: true, size: 9, fill: opts.colors[i], stroke: opts.colors[i] },
      })),
    ],
    plugins: opts.tooltip ? [tooltipPlugin(opts.tooltip)] : [],
  };
}

export function scatterChart(axes: [string, string], realData = false): uPlot.Options {
  return {
    width: 300,
    height: 190,
    legend: { show: false },
    cursor: { show: false },
    padding: [8, 10, 0, 0],
    scales: realData ? { x: { time: false }, y: { time: false } } : { x: { time: false, range: [0, 10] }, y: { time: false, range: [0, 10] } },
    axes: baseAxes(axes[0], axes[1]),
    series: [
      { label: axes[0] },
      { label: "class 1", stroke: css("--accent"), fill: css("--accent"), paths: () => null, points: { show: true, size: 4, fill: css("--accent") } },
      { label: "class 0", stroke: css("--muted"), fill: css("--muted"), paths: () => null, points: { show: true, size: 4, fill: css("--muted") } },
      { label: "boundary", stroke: css("--drift"), width: 1.5, dash: [4, 3], points: { show: false } },
    ],
  };
}
