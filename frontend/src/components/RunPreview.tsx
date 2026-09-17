/** The home page's one chart: a real recorded run, not an illustration.
 *
 *  It reads the most recent completed run that compared a model which keeps learning against one
 *  trained once, and draws its accuracy with the run's own drift, detection and adaptation events
 *  flagged. The provenance line names the scenario and seed and links to the full run, because a
 *  chart on a landing page is still a measurement and has to say where it came from.
 *
 *  If the backend is not running, or no such run has been recorded yet, the caller's fallback is
 *  drawn instead — the page must still explain the project with nothing behind it.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type uPlot from "uplot";

import UPlotChart from "../charts/UPlot";
import { lineChart, methodColor, type Marker } from "../charts/plots";
import { api, type Manifest } from "../lib/api";
import { pct, samples } from "../lib/format";
import { href } from "../lib/router";
import { useTheme } from "../lib/theme";

type Loaded = {
  manifest: Manifest;
  trialId: string;
  seed: number;
  data: uPlot.AlignedData;
  markers: Marker[];
  /** Events beyond the first of their kind: drawn as lines, not labelled. */
  repeats: number;
};

const WANTED = ["adaptive", "static"] as const;

export default function RunPreview({ fallback }: { fallback: ReactNode }) {
  // uPlot samples the CSS variables when it is built, so the chart has to be rebuilt when the
  // resolved theme changes — otherwise a light page keeps a chart drawn in dark-theme colours.
  const { resolved: theme } = useTheme();
  const [run, setRun] = useState<Loaded | null>(null);
  const [failed, setFailed] = useState(false);
  const markerRef = useRef<Marker[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const manifests = await api.experiments();
        const candidates = [...manifests]
          .filter((manifest) => manifest.status === "completed")
          .sort((a, b) => b.created_utc.localeCompare(a.created_utc));
        for (const manifest of candidates) {
          // The manifest carries the run's status; a live run's single trial entry has none, so the
          // only requirement here is that the trial compared both kinds of model.
          const trial = manifest.trials.find((entry) => WANTED.every((method) => method in entry.methods));
          if (!trial) continue;
          const [series, events] = await Promise.all([
            api.trialSeries(manifest.id, trial.trial_id, 500),
            api.trialEvents(manifest.id, trial.trial_id).catch(() => []),
          ]);
          const adaptive = series.methods["adaptive"];
          const statik = series.methods["static"];
          if (!adaptive?.x?.length || !statik?.accuracy?.length) continue;
          // A run can contain several episodes. On a chart this small only the first of each kind is
          // labelled; the rest still draw their line, so nothing is hidden, and a note says so.
          const markers: Marker[] = [];
          const labelled = new Set<string>();
          const add = (x: number, kind: Marker["kind"], label: string) => {
            const first = !labelled.has(kind);
            labelled.add(kind);
            markers.push({ x, kind, label: first ? label : "", sub: first ? samples(x) : undefined });
          };
          for (const event of events) {
            if (event.type === "drift_true") add(event.i, "true", "data changed");
            else if (event.type === "drift_detected" && event.error_increased && event.method === "adaptive")
              add(event.i, "detected", "detected");
            else if (event.type === "adaptation_completed" && event.method === "adaptive")
              add(event.i, "adaptation", "model replaced");
          }
          const repeats = markers.length - labelled.size;
          if (cancelled) return;
          setRun({
            manifest,
            trialId: trial.trial_id,
            seed: trial.seed,
            data: [adaptive.x, adaptive.accuracy, statik.accuracy] as uPlot.AlignedData,
            markers,
            repeats,
          });
          return;
        }
        if (!cancelled) setFailed(true);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  markerRef.current = run?.markers ?? [];

  const options = useMemo(
    () =>
      lineChart({
        xLabel: "position in the stream (samples)",
        yLabel: "accuracy",
        yFormat: (value) => `${(value * 100).toFixed(0)}%`,
        lines: [
          { label: "Keeps learning", color: methodColor("adaptive"), width: 2.4 },
          { label: "Trained once", color: methodColor("static"), dash: [6, 4], width: 1.6 },
        ],
        markers: () => markerRef.current,
        tooltip: (u, idx) => {
          const x = u.data[0]?.[idx] as number | undefined;
          if (x == null) return null;
          const value = (i: number) => {
            const v = u.data[i]?.[idx];
            return typeof v === "number" ? pct(v) : "—";
          };
          return {
            title: `Sample ${samples(x)}`,
            rows: [
              { k: "Keeps learning", v: value(1) },
              { k: "Trained once", v: value(2) },
            ],
          };
        },
      }),
    [run?.trialId, theme],
  );

  if (failed || !run) return <>{fallback}</>;

  const drift = run.manifest.trials.find((t) => t.trial_id === run.trialId)?.scenario;

  return (
    <figure className="story-curve">
      <div className="story-card">
        <div className="story-card-head">
          <span className="story-axis">Accuracy through one run</span>
          <span className="tag real">Recorded run</span>
        </div>
        <UPlotChart options={options} data={run.data} height={252} />
        <div className="run-preview-legend">
          <span className="key">
            <i className="swatch adaptive" />
            <span>
              <strong>Keeps learning.</strong> Detects the change and replaces its model.
            </span>
          </span>
          <span className="key">
            <i className="swatch static" />
            <span>
              <strong>Trained once, then frozen.</strong> Never updates, so it stays wrong.
            </span>
          </span>
        </div>
      </div>
      <figcaption>
        Measured on this machine: {drift?.name ?? "SEA"} · seed {run.seed} · {samples(drift?.length ?? 0)} samples.
        {run.repeats > 0 && ` ${run.repeats} later event${run.repeats === 1 ? " is" : "s are"} drawn unlabelled.`}{" "}
        <a href={href({ page: "experiment", id: run.manifest.id, trial: run.trialId })}>Open the full run →</a>
      </figcaption>
    </figure>
  );
}
