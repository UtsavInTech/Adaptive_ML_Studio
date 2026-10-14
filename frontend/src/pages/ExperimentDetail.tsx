/** One run's results: the facts of the run, then the methods side by side, then accuracy against cost.
 *  Every number comes from the stored bundle; no conclusion is drawn here. */

import { useEffect, useMemo, useState } from "react";
import type uPlot from "uplot";

import UPlotChart from "../charts/UPlot";
import { css, lineChart, methodColor, pointsChart, type Band, type Marker } from "../charts/plots";
import DriftShape from "../components/DriftShape";
import EventLog from "../components/EventLog";
import { ExplainButton } from "../components/Explain";
import {
  Badge, EmptyState, ErrorState, Legend, Loading, MetricCard, MetricGrid, Panel, ProvenanceBadge, SectionHead, TechnicalDetails,
} from "../components/ui";
import { api, type DriftPhases, type EventRecord, type Manifest, type MethodSummary, type PhaseScores, type Timing, type TrialSeries } from "../lib/api";
import type { ExplainId } from "../lib/explain";
import { DASH, kb, methodLabel, num, pct, samples, us } from "../lib/format";
import { store, useLive } from "../lib/live";
import { usePresentation } from "../lib/present";
import { useTheme } from "../lib/theme";

type TrialData = { summaries: Record<string, MethodSummary>; timing: Timing; scenario: any; config: any };

const COLUMNS: { key: string; label: string; explain?: ExplainId; group: string }[] = [
  { key: "accuracy", label: "Accuracy", explain: "accuracy", group: "Predictive performance" },
  { key: "f1", label: "F1", explain: "f1", group: "Predictive performance" },
  { key: "mean", label: "Mean time", explain: "latency", group: "Processing cost" },
  { key: "p95", label: "p95", explain: "p95", group: "Processing cost" },
  { key: "p99", label: "p99", explain: "p99", group: "Processing cost" },
  { key: "cpu", label: "CPU / sample", explain: "cpuPerSample", group: "Processing cost" },
  { key: "rss", label: "Peak memory", explain: "rss", group: "Resources" },
  { key: "model", label: "Model size", explain: "modelSize", group: "Resources" },
  { key: "adaptations", label: "Adaptations", explain: "adaptation", group: "Drift and adaptation" },
  { key: "delay", label: "Detection delay", explain: "detectionDelay", group: "Drift and adaptation" },
  { key: "pre", label: "Before drift", group: "Drift and adaptation" },
  { key: "late", label: "Late after drift", group: "Drift and adaptation" },
];

export default function ExperimentDetail({ id, trial }: { id: string; trial?: string }) {
  useLive();
  const { resolved: theme } = useTheme();
  const present = usePresentation();
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [trials, setTrials] = useState<Record<string, TrialData>>({});
  const [series, setSeries] = useState<TrialSeries | null>(null);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [allSeries, setAllSeries] = useState<Record<string, TrialSeries>>({});
  const [showControl, setShowControl] = useState(false);
  const [problem, setProblem] = useState<{ why: string; technical?: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const selected = trial ?? manifest?.trials[0]?.trial_id;

  const load = () => {
    setProblem(null);
    setManifest(null);
    setTrials({});
    api.experiment(id)
      .then(async (loaded) => {
        setManifest(loaded);
        const entries = await Promise.all(loaded.trials.map(async (t) => [t.trial_id, await api.trialSummary(id, t.trial_id)] as const));
        setTrials(Object.fromEntries(entries.map(([key, value]) => [key, value as TrialData])));
      })
      .catch((error: Error) =>
        setProblem({ why: "The stored result bundle for this run could not be read from the server.", technical: error.message }),
      );
  };

  useEffect(load, [id]);

  useEffect(() => {
    if (!selected) return;
    setSeries(null);
    api.trialSeries(id, selected).then(setSeries).catch(() => {});
    api.trialEvents(id, selected).then(setEvents).catch(() => setEvents([]));
  }, [id, selected]);

  const markers = useMemo<Marker[]>(() => {
    const out: Marker[] = [];
    for (const event of events) {
      if (event.type === "drift_true") out.push({ x: event.i, kind: "true", label: event.injected ? "change begins" : "drift in data" });
      else if (event.type === "drift_detected" && event.error_increased) out.push({ x: event.i, kind: "detected", label: "detected" });
      else if (event.type === "adaptation_completed") out.push({ x: event.i, kind: "adaptation", label: "adapted" });
    }
    return out;
  }, [events]);

  const methodsInSeries = series ? Object.keys(series.methods) : [];
  const accuracyOptions = useMemo(
    () =>
      lineChart({
        xLabel: "sample index",
        yLabel: "accuracy",
        yFormat: (v) => `${(v * 100).toFixed(0)}%`,
        lines: methodsInSeries.map((m) => ({
          label: methodLabel(m),
          color: methodColor(m),
          dash: m === "static" ? [6, 4] : undefined,
          width: present ? 2.6 : 2,
        })),
        markers: () => markers,
      }),
    [methodsInSeries.join(","), markers, theme, present],
  );
  const accuracyData = useMemo<uPlot.AlignedData>(() => {
    if (!series || !methodsInSeries.length) return [[]] as unknown as uPlot.AlignedData;
    const base = series.methods[methodsInSeries[0]];
    return [base.x, ...methodsInSeries.map((m) => series.methods[m].accuracy)] as uPlot.AlignedData;
  }, [series, methodsInSeries.join(",")]);

  const rows = useMemo(() => {
    if (!manifest) return [];
    return manifest.trials.flatMap((entry) => {
      const data = trials[entry.trial_id];
      return Object.entries(entry.methods).map(([method, headline]) => {
        const summary = data?.summaries?.[method];
        const stability = summary?.stability_reference ?? null;
        return {
          trialId: entry.trial_id,
          method,
          profile: entry.profile,
          seed: entry.seed,
          // A control trial re-ran the method on the untouched rows; it is a comparison, not a result.
          control: entry.control ?? entry.trial_id.endsWith("__control"),
          phases: (summary?.drift_phases ?? null) as DriftPhases | null,
          accuracy: headline.accuracy,
          precision: headline.precision ?? summary?.scores_after_warmup.precision ?? null,
          f1: headline.f1,
          latency: headline.latency_us,
          adaptations: headline.adaptations,
          cpu: data?.timing?.cpu_us_per_sample ?? null,
          rss: data?.timing?.peak_rss_mb ?? null,
          modelKb: summary?.final_model.size_bytes != null ? summary.final_model.size_bytes / 1024 : null,
          timingDependent: Boolean(entry.timing?.timing_dependent_behaviour),
          pre: stability?.pre_drift?.accuracy ?? null,
          late: stability?.post_drift_late?.accuracy ?? null,
          delay: stability?.detection_delay_samples ?? null,
        };
      });
    });
  }, [manifest, trials]);

  /** The results proper. Control trials are kept out of every table, chart and headline except the
   *  before / during / after comparison, where they are shown beside the trial they belong to. */
  const all = rows;
  const mainRows = useMemo(() => all.filter((row) => !row.control), [all]);
  const controlFor = (row: (typeof all)[number]) => all.find((other) => other.control && other.trialId === `${row.trialId}__control`) ?? null;
  const phased = mainRows.filter((row) => row.phases);
  const hasPhases = phased.length > 0;
  const firstScenario = manifest?.trials.find((t) => !t.control)?.scenario;
  const injection = firstScenario?.injection ?? null;
  const hasControls = all.some((row) => row.control);

  // Every method on one chart: needs each trial's series, so only fetched when there is a known change.
  useEffect(() => {
    if (!manifest || !hasPhases || manifest.trials.length > 24) return;
    let cancelled = false;
    Promise.all(manifest.trials.map(async (t) => [t.trial_id, await api.trialSeries(id, t.trial_id)] as const))
      .then((entries) => { if (!cancelled) setAllSeries(Object.fromEntries(entries)); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [id, manifest?.trials.length, hasPhases]);

  const together = useMemo(() => {
    const first = mainRows[0];
    if (!first) return { lines: [] as { method: string; trialId: string }[], data: [[]] as unknown as uPlot.AlignedData };
    const group = all.filter((row) => row.control === showControl && row.profile.name === first.profile.name && row.seed === first.seed);
    const usable = group.filter((row) => allSeries[row.trialId]?.methods[row.method]);
    if (!usable.length) return { lines: [], data: [[]] as unknown as uPlot.AlignedData };
    const x = allSeries[usable[0].trialId].methods[usable[0].method].x;
    const same = usable.filter((row) => allSeries[row.trialId].methods[row.method].x.length === x.length);
    return {
      lines: same.map((row) => ({ method: row.method, trialId: row.trialId })),
      data: [x, ...same.map((row) => allSeries[row.trialId].methods[row.method].accuracy)] as uPlot.AlignedData,
    };
  }, [all, mainRows, allSeries, showControl]);

  const reference = phased[0]?.phases ?? null;
  const bands = useMemo<Band[]>(() => {
    if (!reference) return [];
    const out: Band[] = [];
    if (reference.before) out.push({ from: reference.before.range[0], to: reference.before.range[1], color: css("--static"), label: "before" });
    if (reference.during) out.push({ from: reference.during.range[0], to: reference.during.range[1], color: css("--drift"), label: "during" });
    if (reference.after) out.push({ from: reference.after.range[0], to: reference.after.range[1], color: css("--ok"), label: "after" });
    return out;
  }, [reference, theme]);
  const changeMarkers = useMemo<Marker[]>(() => {
    if (showControl) return [];
    const drifts = firstScenario?.drifts ?? [];
    if (injection?.kind === "recurring") return drifts.map((d, k) => ({ x: d.index, kind: "true" as const, label: k === 0 ? "first switch" : k % 2 ? "back" : "switch" }));
    if (!reference) return [];
    const out: Marker[] = [{ x: reference.start, kind: "true", label: "change begins" }];
    if (reference.end - reference.start > 1) out.push({ x: reference.end, kind: "true", label: "change complete" });
    return out;
  }, [reference, firstScenario, injection, showControl]);

  const togetherOptions = useMemo(
    () =>
      lineChart({
        xLabel: "row (position in the data)",
        yLabel: "accuracy over the last 500 rows",
        yFormat: (v) => `${(v * 100).toFixed(0)}%`,
        lines: together.lines.map((line) => ({
          label: methodLabel(line.method),
          color: methodColor(line.method),
          dash: line.method === "static" ? [6, 4] : undefined,
          width: present ? 2.6 : 1.9,
        })),
        bands: () => bands,
        markers: () => changeMarkers,
        tooltip: (u, idx) => {
          const x = u.data[0]?.[idx] as number | undefined;
          if (x == null) return null;
          return {
            title: `Row ${samples(x)}`,
            rows: together.lines.map((line, i) => {
              const value = u.data[i + 1]?.[idx];
              return { k: methodLabel(line.method), v: typeof value === "number" ? pct(value) : DASH };
            }),
          };
        },
      }),
    [together.lines.map((l) => l.trialId).join(","), bands, changeMarkers, theme, present],
  );

  const tradeoff = useMemo(() => {
    const points = mainRows.filter((row) => row.cpu != null && row.accuracy != null).sort((a, b) => (a.cpu ?? 0) - (b.cpu ?? 0));
    const labels = [...new Set(points.map((point) => point.method))];
    return {
      labels,
      points,
      data: [
        points.map((p) => p.cpu as number),
        ...labels.map((m) => points.map((p) => (p.method === m ? p.accuracy : null))),
      ] as uPlot.AlignedData,
    };
  }, [mainRows]);

  /** The two extremes actually measured in this run, and the adaptive pipeline's own figures.
   *  Deliberately not a ranking: "highest measured accuracy" is a fact, "best method" is a judgement
   *  that belongs to the research workstream. */
  const headlines = useMemo(() => {
    const withAccuracy = mainRows.filter((row) => row.accuracy != null);
    const withCost = mainRows.filter((row) => row.cpu != null);
    return {
      mostAccurate: withAccuracy.length ? withAccuracy.reduce((a, b) => ((b.accuracy ?? 0) > (a.accuracy ?? 0) ? b : a)) : null,
      cheapest: withCost.length ? withCost.reduce((a, b) => ((b.cpu ?? 0) < (a.cpu ?? 0) ? b : a)) : null,
      adaptive: mainRows.find((row) => row.method === "adaptive") ?? null,
    };
  }, [mainRows]);

  const tradeoffOptions = useMemo(
    () =>
      pointsChart({
        xLabel: "processor time per sample (µs)  →  more computation",
        yLabel: "accuracy  ↑ higher is more accurate",
        yFormat: (v) => `${(v * 100).toFixed(0)}%`,
        labels: tradeoff.labels.map(methodLabel),
        colors: tradeoff.labels.map(methodColor),
        tooltip: (_u, idx) => {
          const point = tradeoff.points[idx];
          if (!point) return null;
          return {
            title: methodLabel(point.method),
            rows: [
              { k: "Accuracy", v: pct(point.accuracy, 2) },
              { k: "Processing cost", v: `${num(point.cpu, 1)} µs / sample` },
              { k: "Model size", v: kb(point.modelKb) },
            ],
          };
        },
      }),
    [tradeoff.labels.join(","), tradeoff.points, theme, present],
  );

  if (problem) {
    return (
      <div className="page">
        <ErrorState
          title="This run could not be loaded."
          why={problem.why}
          technical={problem.technical}
          action={
            <div className="row" style={{ gap: 8 }}>
              <button type="button" className="btn small" onClick={load}>Retry</button>
              <a className="btn small" href="#/experiments">Back to all runs</a>
            </div>
          }
        />
      </div>
    );
  }
  if (!manifest) return <div className="page"><Panel title="Loading run"><Loading /></Panel></div>;

  const rerun = async () => {
    setBusy(true);
    try {
      await api.rerun(id);
    } catch (error) {
      setProblem({ why: "The re-run could not be started.", technical: (error as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const facts = (() => {
    const methodCount = new Set(mainRows.map((r) => r.method)).size;
    const firstTrial = manifest.trials[0];
    const scenario = firstTrial?.scenario;
    const totalAdaptations = mainRows.reduce((sum, r) => sum + (r.adaptations ?? 0), 0);
    const cpus = mainRows.map((r) => r.cpu).filter((v): v is number => v != null);
    return {
      methodCount,
      samples: scenario?.length ?? null,
      drifts: scenario?.drifts?.length ?? 0,
      adaptations: totalAdaptations,
      cpuRange: cpus.length ? [Math.min(...cpus), Math.max(...cpus)] : null,
      trials: manifest.trials.length,
    };
  })();

  const job = store.job;
  return (
    <div className="page">
      <Panel
        title={manifest.name}
        sub={manifest.kind}
        actions={
          <div className="row" style={{ gap: 8 }}>
            <a className="btn small" href={api.exportUrl(id)}>Export data</a>
            <button type="button" className="btn small" onClick={() => void rerun()} disabled={busy || job?.status === "running" || store.active}>
              Re-run and check reproducibility
            </button>
          </div>
        }
      >
        <div className="row wrap" style={{ gap: 10 }}>
          <Badge tone={manifest.status === "completed" ? "ok" : manifest.status === "error" ? "error" : "warn"}>{manifest.status}</Badge>
          <ProvenanceBadge kind="measured" detail={manifest.provenance.measured_on} />
          {manifest.provenance.simulated_profiles.length > 0 && <ProvenanceBadge kind="simulated" detail={manifest.provenance.simulated_profiles.join(", ")} />}
          {manifest.provenance.placeholder_budgets && <ProvenanceBadge kind="placeholder" />}
          <ProvenanceBadge kind={manifest.provenance.injected_drift ? "injected" : manifest.provenance.real_data ? "real" : "synthetic"} />
        </div>
        {manifest.error && <div className="banner error" style={{ marginTop: 12 }}><div>{manifest.error}</div></div>}
        {manifest.reproducibility && (
          <div className="banner info" style={{ marginTop: 12 }}>
            <div>
              <strong>Reproducibility:</strong> {manifest.reproducibility.identical} of {manifest.reproducibility.trials_compared} trials produced
              identical predictions when run again. Timings are expected to differ.
            </div>
            <ExplainButton id="reproducibility" />
          </div>
        )}
      </Panel>

      <section className="stack tight">
        <SectionHead title="What this run contains" hint="counts from the stored bundle — not conclusions" />
        <MetricGrid>
          <MetricCard label="Methods evaluated" value={num(facts.methodCount)} sub={`${facts.trials} trial${facts.trials === 1 ? "" : "s"}, each in a fresh process`} />
          <MetricCard label="Samples per trial" value={facts.samples != null ? samples(facts.samples) : DASH} explain="warmup" sub={selected && trials[selected] ? `first ${samples(trials[selected].config.evaluation.warmup)} used for warm-up` : "loading evaluation protocol"} />
          {injection ? (
            <MetricCard label="Change added to the data" explain="injectedDrift" value={injection.label ?? injection.kind} sub={`first changed row ${samples(injection.start)} · chosen in the setup, so its position is known`} />
          ) : (
            <MetricCard label={manifest.provenance.real_data ? "Ground-truth drift" : "Scheduled drifts"} value={manifest.provenance.real_data ? "Unknown" : num(facts.drifts)} sub={manifest.provenance.real_data ? "detector alerts are not drift annotations" : facts.drifts ? "position known in advance" : "none"} />
          )}
          <MetricCard label="Adaptations recorded" value={num(facts.adaptations)} explain="adaptation" sub="across all methods in this run" />
          <MetricCard
            label="Processor time"
            explain="cpuPerSample"
            value={facts.cpuRange ? `${facts.cpuRange[0].toFixed(1)}–${facts.cpuRange[1].toFixed(1)}` : DASH}
            unit="µs / sample"
            sub="range across methods"
          />
        </MetricGrid>
      </section>

      {manifest.provenance.real_data && selected && trials[selected] && <div className="banner">
        <div><strong>{trials[selected].scenario.name}</strong> · {trials[selected].scenario.order}
          {injection ? (
            <p className="small">
              <strong>Real rows with one controlled change added.</strong> {injection.what} The data's own drift is still present
              and still unmarked: only the added change has a known position. Precision and F1 use the positive
              label {Object.entries(trials[selected].scenario.labels ?? {}).find(([, value]) => value === 1)?.[0]}.
            </p>
          ) : (
            <p className="small">No annotated drift locations: detection delay and before/after-drift scores are unavailable.
            F1 uses the positive label {Object.entries(trials[selected].scenario.labels ?? {}).find(([, value]) => value === 1)?.[0]}.</p>
          )}
          <a href={trials[selected].scenario.source} target="_blank" rel="noreferrer">Dataset source ↗</a>
          <details><summary>Snapshot checksum</summary><code className="dataset-hash">{trials[selected].scenario.sha256}</code></details>
        </div>
      </div>}

      {hasPhases && reference && (
        <section className="stack tight">
          <SectionHead title="Before, during and after the change" explain="phases" hint="every method scored over exactly the same rows" />
          <Panel bodyClass="flush">
            <div className="phase-head">
              {injection && <DriftShape kind={injection.kind} />}
              <p>
                {injection
                  ? <><strong>{injection.label ?? injection.kind} change.</strong> {injection.what}</>
                  : <><strong>Scheduled change in a synthetic stream.</strong> Its position is set by the generator.</>}
                {" "}Before = rows {samples(reference.before?.range[0] ?? null)}–{samples(reference.before?.range[1] ?? null)},
                during = {samples(reference.during?.range[0] ?? null)}–{samples(reference.during?.range[1] ?? null)},
                after = {samples(reference.after?.range[0] ?? null)}–{samples(reference.after?.range[1] ?? null)}.
              </p>
            </div>
            <div className="table-scroll">
              <table className="table phase-table">
                <thead>
                  <tr className="group-header">
                    <th />
                    <th colSpan={3}>Accuracy <ExplainButton id="accuracy" /></th>
                    <th colSpan={3}>Precision <ExplainButton id="precision" /></th>
                    <th colSpan={2}>Detector</th>
                  </tr>
                  <tr>
                    <th><span className="th-inner">Method</span></th>
                    {["Before", "During", "After", "Before", "During", "After"].map((label, i) => <th key={i}><span className="th-inner">{label}</span></th>)}
                    <th><span className="th-inner">First alert after the change <ExplainButton id="detectionDelay" /></span></th>
                    <th><span className="th-inner">Alerts during</span></th>
                  </tr>
                </thead>
                <tbody>
                  {phased.map((row) => {
                    const mine = row.phases as DriftPhases;
                    const control = controlFor(row)?.phases ?? null;
                    const cell = (key: "before" | "during" | "after", metric: "accuracy" | "precision") => {
                      const value = (mine[key] as PhaseScores)?.[metric] ?? null;
                      const base = (control?.[key] as PhaseScores)?.[metric] ?? null;
                      return (
                        <td className="num" key={`${key}-${metric}`}>
                          {pct(value)}
                          {control && key !== "before" && <div className="cell-sub">untouched: {pct(base)}</div>}
                        </td>
                      );
                    };
                    const detects = row.method === "adaptive";
                    return (
                      <tr key={`phase-${row.trialId}`}>
                        <td>
                          {methodLabel(row.method)}
                          <div className="cell-sub">{row.profile.label}{mainRows.some((r) => r.seed !== row.seed) ? ` · seed ${row.seed}` : ""}</div>
                        </td>
                        {(["before", "during", "after"] as const).map((key) => cell(key, "accuracy"))}
                        {(["before", "during", "after"] as const).map((key) => cell(key, "precision"))}
                        <td className="num">
                          {detects ? (mine.first_alert_after_start != null ? `${samples(mine.first_alert_after_start)} rows` : "none") : DASH}
                          {detects && control && <div className="cell-sub">untouched: {control.first_alert_after_start != null ? `${samples(control.first_alert_after_start)} rows` : "none"}</div>}
                        </td>
                        <td className="num">
                          {detects ? num(mine.during?.detector_alerts ?? null) : DASH}
                          {detects && control && <div className="cell-sub">untouched: {num(control.during?.detector_alerts ?? null)}</div>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="tiny muted" style={{ padding: "10px 16px", margin: 0 }}>
              {hasControls
                ? "“Untouched” is the control: the same method on the same rows with no change added. Real data moves on its own, so the gap between a figure and its control, not the figure alone, is what the added change accounts for. "
                : "No control was run, so a difference between the windows may come from the data itself as well as from the change. "}
              Only the adaptive pipeline reports detector alerts; on real data it also raises them for the data's own drift.
              The window sizes are configurable reference values. Measurements only; interpretation belongs to the research workstream.
            </p>
          </Panel>

          <Panel
            title="Every method on the same rows"
            sub={showControl ? "control: untouched rows" : injection ? "with the added change" : undefined}
            actions={hasControls ? (
              <div className="segmented">
                <button type="button" aria-pressed={!showControl} onClick={() => setShowControl(false)}>With the change</button>
                <button type="button" aria-pressed={showControl} onClick={() => setShowControl(true)}>Untouched (control)</button>
              </div>
            ) : undefined}
          >
            {together.lines.length ? (
              <>
                <UPlotChart options={togetherOptions} data={together.data} height={present ? 380 : 320} />
                <Legend
                  items={[
                    ...together.lines.map((line) => ({ label: methodLabel(line.method), color: methodColor(line.method), dashed: line.method === "static" })),
                    ...(showControl ? [] : [{ label: "the change", color: "var(--drift)", dashed: true }]),
                  ]}
                />
                <p className="chart-note">
                  Each line is one method's accuracy over its most recent 500 rows. The shaded stretches are the before, during
                  and after windows used in the table above, so the same rows are shaded in both views.
                </p>
              </>
            ) : <Loading label="Loading every method's accuracy" />}
          </Panel>
        </section>
      )}

      {(headlines.mostAccurate || headlines.cheapest) && (
        <section className="stack tight">
          <SectionHead title="Headline measurements" hint="What this run measured — observations, not a ranking" />
          <div className="summary-grid">
            {headlines.mostAccurate && (
              <div className="summary-card ok">
                <span className="cap">
                  Highest measured accuracy <ExplainButton id="accuracy" />
                </span>
                <span className="who">{methodLabel(headlines.mostAccurate.method)}</span>
                <span className="num">{pct(headlines.mostAccurate.accuracy, 2)}</span>
                <span className="note">
                  {headlines.mostAccurate.cpu != null
                    ? `Using ${num(headlines.mostAccurate.cpu, 1)} µs of processor time per sample`
                    : "Processing cost was not recorded for this method"}
                </span>
              </div>
            )}
            {headlines.cheapest && (
              <div className="summary-card static">
                <span className="cap">
                  Lowest measured processing cost <ExplainButton id="cpuPerSample" />
                </span>
                <span className="who">{methodLabel(headlines.cheapest.method)}</span>
                <span className="num">{num(headlines.cheapest.cpu, 1)} µs</span>
                <span className="note">Per sample, with {pct(headlines.cheapest.accuracy, 2)} accuracy</span>
              </div>
            )}
            {headlines.adaptive && (
              <div className="summary-card accent">
                <span className="cap">
                  The adaptive pipeline <ExplainButton id="adaptiveMethod" />
                </span>
                <span className="who">{pct(headlines.adaptive.accuracy, 2)} accuracy</span>
                <span className="num">{headlines.adaptive.cpu != null ? `${num(headlines.adaptive.cpu, 1)} µs` : DASH}</span>
                <span className="note">
                  Processor time per sample, with {num(headlines.adaptive.adaptations)} adaptation
                  {headlines.adaptive.adaptations === 1 ? "" : "s"} during the run
                </span>
              </div>
            )}
          </div>
          <p className="chart-note">
            Every figure above was measured in this run, on this machine. Which method is preferable depends on how much
            accuracy is worth how much computation — that judgement belongs to the research workstream, so the platform
            reports the numbers rather than choosing between them.
          </p>
        </section>
      )}

      <section className="stack tight">
        <SectionHead title="Methods side by side" hint="the same stream, the same machine, one trial at a time" />
        <Panel bodyClass="flush">
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr className="group-header">
                  <th />
                  {["Predictive performance", "Processing cost", "Resources", "Drift and adaptation"].map((group) => (
                    <th key={group} colSpan={COLUMNS.filter((c) => c.group === group).length}>{group}</th>
                  ))}
                </tr>
                <tr>
                  <th><span className="th-inner">Method</span></th>
                  {COLUMNS.map((column) => (
                    <th key={column.key}>
                      <span className="th-inner">
                        {column.label}
                        {column.explain && <ExplainButton id={column.explain} />}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {mainRows.map((row) => (
                  <tr
                    key={`${row.trialId}-${row.method}`}
                    onClick={() => (window.location.hash = `#/experiments/${encodeURIComponent(id)}?trial=${encodeURIComponent(row.trialId)}`)}
                    style={{ cursor: "pointer" }}
                  >
                    <td>
                      {/* A real link, so the row can be reached and opened from the keyboard too. */}
                      <a
                        className="row-link"
                        href={`#/experiments/${encodeURIComponent(id)}?trial=${encodeURIComponent(row.trialId)}`}
                        onClick={(event) => event.stopPropagation()}
                      >
                        {methodLabel(row.method)}
                      </a>
                      <div className="cell-sub">
                        {row.profile.label}
                        {row.timingDependent ? " · timing-dependent" : ""}
                      </div>
                    </td>
                    <td className="num">{pct(row.accuracy, 2)}</td>
                    <td className="num">{pct(row.f1, 2)}</td>
                    <td className="num">{us(row.latency.mean)}</td>
                    <td className="num">{us(row.latency.p95)}</td>
                    <td className="num">{us(row.latency.p99)}</td>
                    <td className="num">{num(row.cpu, 1)} µs</td>
                    <td className="num">{row.rss != null ? `${num(row.rss, 0)} MB` : DASH}</td>
                    <td className="num">{kb(row.modelKb)}</td>
                    <td className="num">{num(row.adaptations)}</td>
                    <td className="num">{row.delay != null ? samples(row.delay) : DASH}</td>
                    <td className="num">{pct(row.pre, 1)}</td>
                    <td className="num">{pct(row.late, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tiny muted" style={{ padding: "10px 16px", margin: 0 }}>
            “Before drift” and “late after drift” are measured over fixed windows anchored at the scheduled change, so every
            method is compared over the same samples. {manifest.note}
          </p>
        </Panel>
      </section>

      <div className="two-col">
        <Panel title="Accuracy against processing cost" explain="tradeoff">
          {tradeoff.labels.length ? (
            <>
              <UPlotChart options={tradeoffOptions} data={tradeoff.data} height={present ? 300 : 240} />
              <Legend items={tradeoff.labels.map((method) => ({ label: methodLabel(method), color: methodColor(method), dot: true }))} />
              <p className="chart-note">
                Moving right means a method needs more computation per sample. Moving up means it predicted more
                accurately in this run. A method that sits high and to the left achieved more with less.
              </p>
              <div className="table-scroll" style={{ marginTop: 12 }}>
                <table className="table">
                  <tbody>
                    {tradeoff.points.map((row) => (
                      <tr key={`cost-${row.trialId}-${row.method}`}>
                        <td>{methodLabel(row.method)}</td>
                        <td className="num">{pct(row.accuracy, 2)}</td>
                        <td className="num">{num(row.cpu, 1)} µs / sample</td>
                        <td className="num">{kb(row.modelKb)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <EmptyState title="No cost measurements in this run" hint="Cost is recorded for every trial that completed; this run has none yet." />
          )}
        </Panel>

        <Panel
          title="Accuracy over time"
          explain="sampleIndex"
          actions={
            <select
              value={selected}
              onChange={(e) => (window.location.hash = `#/experiments/${encodeURIComponent(id)}?trial=${encodeURIComponent(e.target.value)}`)}
              aria-label="Trial to display"
            >
              {manifest.trials.map((t) => {
                const method = Object.keys(t.methods)[0];
                return <option key={t.trial_id} value={t.trial_id}>{method ? methodLabel(method) : t.trial_id}{t.control ? " · control (untouched rows)" : ""}</option>;
              })}
            </select>
          }
        >
          {accuracyData[0]?.length ? (
            <>
              <UPlotChart options={accuracyOptions} data={accuracyData} height={present ? 300 : 240} />
              <Legend
                items={[
                  ...methodsInSeries.map((m) => ({ label: methodLabel(m), color: methodColor(m), dashed: m === "static" })),
                  { label: "drift in the data", color: "var(--drift)", dashed: true },
                  { label: "adaptation", color: "var(--adapt)" },
                ]}
              />
            </>
          ) : (
            <Loading label="Loading series" />
          )}
        </Panel>
      </div>

      <Panel title="Events in this trial" sub={selected} bodyClass="flush">
        <EventLog events={events} height={300} />
      </Panel>

      <TechnicalDetails summary="View run metadata (configuration, environment, reproducibility)">
        <dl className="kv">
          <dt>Run id</dt><dd>{manifest.id}</dd>
          <dt>Created</dt><dd>{manifest.created_utc}</dd>
          <dt>Configuration hash</dt><dd>{manifest.config_hash?.slice(0, 24)}…</dd>
          <dt>Code version</dt>
          <dd>{manifest.app_version?.commit ?? "uncommitted"}{manifest.app_version?.uncommitted_changes ? " (working tree modified)" : ""}</dd>
          <dt>Measured on</dt><dd style={{ fontFamily: "var(--font)" }}>{manifest.provenance.measured_on}</dd>
        </dl>
        <p className="tiny muted" style={{ margin: 0 }}>
          The exported bundle additionally contains every block, every event and the per-sample outcomes, so any metric can be
          recomputed without re-running the experiment.
        </p>
      </TechnicalDetails>
    </div>
  );
}
