/** Live — the laboratory.
 *
 *  The screen is ordered by the question a viewer asks next, not by the structure of the engine:
 *  what is happening now → what did the model do about it → how well is it predicting → what does
 *  that cost → how does the pipeline work → the raw record. Diagnostics that only matter when
 *  something looks wrong stay folded away, so the default view can be read in one pass.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type uPlot from "uplot";

import UPlotChart from "../charts/UPlot";
import { STAGE_ORDER, lineChart, methodColor, stack, stackedChart, type Marker } from "../charts/plots";
import { DecisionCard, WhatHappenedCard } from "../components/Cards";
import ReplaySetup from "../components/ReplaySetup";
import DataSnapshot from "../components/DataSnapshot";
import DemoCard from "../components/DemoCard";
import EventLog from "../components/EventLog";
import { ExplainButton } from "../components/Explain";
import HeroStory, { type PhaseStep } from "../components/Hero";
import PipelineFlow, { type StageKey } from "../components/PipelineFlow";
import RunControlBar from "../components/RunControlBar";
import {
  Badge, EmptyState, Legend, MetricCard, MetricGrid, Panel, ProvenanceBadge, SectionHead, TechnicalDetails, type Phase,
} from "../components/ui";
import { api, type Preset, type Profile } from "../lib/api";
import { demoProgress } from "../lib/demo";
import { episodes, lastBlock, minScoreBetween, overallScores, phase as phaseOf, recentMean, scoreAt, windowedScores } from "../lib/derive";
import { DASH, kb, methodLabel, num, pct, samples, us } from "../lib/format";
import { liveActions, store, useLive } from "../lib/live";
import { usePresentation } from "../lib/present";
import { scenarioCopy } from "../lib/scenarios";
import { useTheme } from "../lib/theme";

const WINDOWS = [200, 500, 1000];

/** One line of run context: what is being run, at a glance, without opening anything. */
function RunContext({ items }: { items: { k: string; v: React.ReactNode; mono?: boolean; explain?: "seed" }[] }) {
  return (
    <div className="run-context">
      {items.map((item) => (
        <span className="item" key={item.k}>
          <span className="k">
            {item.k}
            {item.explain && <ExplainButton id={item.explain} />}
          </span>
          <span className={`v${item.mono ? " mono" : ""}`}>{item.v}</span>
        </span>
      ))}
    </div>
  );
}

export default function Live() {
  useLive();
  const { resolved: theme } = useTheme();
  const present = usePresentation();
  const [presets, setPresets] = useState<Record<string, Preset>>({});
  const [profiles, setProfiles] = useState<Record<string, Profile>>({});
  const [flips, setFlips] = useState<Record<string, number>>({});
  const [preset, setPreset] = useState("demo_abrupt");
  const [profile, setProfile] = useState("standard");
  const [metric, setMetric] = useState<"accuracy" | "f1">("accuracy");
  const [windowSize, setWindowSize] = useState(500);
  const [stage, setStage] = useState<StageKey | null>(null);
  const [demo, setDemo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [injectVariant, setInjectVariant] = useState(3);

  useEffect(() => {
    api.presets().then((p) => setPresets(p.live)).catch(() => {});
    api.profiles().then(setProfiles).catch(() => {});
    api.scenarios().then((s) => setFlips(s.sea.label_flip_fraction)).catch(() => {});
  }, []);

  const config = store.config;
  const realData = config?.stream?.scenario === "csv";
  // A real-data replay can carry one controlled change at a known row. Then the drift story
  // (where it was, when it was noticed, what was done) is measurable, as it is for synthetic data.
  const injection = (config?.stream?.injection ?? null) as { kind: string; start: number; swap: [string, string] } | null;
  const knownDrift = !realData || injection !== null;
  const methods: string[] = config?.methods ?? Object.keys(store.blocks);
  const warmup: number = config?.evaluation?.warmup ?? 1000;
  const simulated = Boolean(config?.profile?.simulated);
  const placeholder = Boolean(config?.profile?.placeholder);
  const extras = store.extras?.methods?.adaptive;
  const started = Boolean(config) && (store.active || store.status.sample > 0);
  const livePhase = phaseOf(store.events, "adaptive", store.status.sample).phase;
  const phase: Phase = started ? livePhase : "idle";
  const constrained = Boolean(extras?.governor?.constrained);

  const series = useMemo(
    () => Object.fromEntries(methods.map((m) => [m, windowedScores(store.blocks[m] ?? [], windowSize)])),
    [methods.join(","), windowSize, store.status.sample, store.blocks],
  );
  const adaptiveSeries = series["adaptive"] ?? { x: [], accuracy: [], f1: [] };

  const markers = useMemo<Marker[]>(() => {
    const out: Marker[] = [];
    for (const event of store.events) {
      if (event.type === "drift_true") out.push({ x: event.i, kind: "true", label: "drift", sub: samples(event.i) });
      else if (event.type === "drift_detected" && event.error_increased && event.method === "adaptive")
        out.push({ x: event.i, kind: "detected", label: "detected", sub: samples(event.i) });
      else if (event.type === "adaptation_completed" && event.method === "adaptive")
        out.push({ x: event.i, kind: "adaptation", label: "adapted", sub: samples(event.i) });
    }
    return out;
  }, [store.events.length]);
  const markerRef = useRef<Marker[]>(markers);
  markerRef.current = markers;

  const heroOptions = useMemo(
    () =>
      lineChart({
        xLabel: "sample index",
        yLabel: metric === "accuracy" ? "accuracy" : "F1",
        yFormat: (v) => `${(v * 100).toFixed(0)}%`,
        lines: methods.map((method) => ({
          label: methodLabel(method),
          color: methodColor(method),
          dash: method === "static" ? [6, 4] : undefined,
          width: method === "adaptive" ? (present ? 3 : 2.4) : present ? 2 : 1.5,
        })),
        markers: () => markerRef.current,
        tooltip: (u, idx) => {
          const x = u.data[0]?.[idx] as number | undefined;
          if (x == null) return null;
          const rows = methods.map((method, i) => {
            const value = u.data[i + 1]?.[idx];
            return { k: methodLabel(method), v: typeof value === "number" ? pct(value) : DASH };
          });
          // Name the nearest event, so hovering near a marker explains what happened there.
          const near = markerRef.current
            .map((marker) => ({ marker, distance: Math.abs(marker.x - x) }))
            .sort((a, b) => a.distance - b.distance)[0];
          if (near && near.distance <= 400) rows.push({ k: "Event", v: near.marker.label });
          return { title: `Sample ${samples(x)}`, rows };
        },
      }),
    [methods.join(","), metric, theme, present],
  );

  const heroData = useMemo<uPlot.AlignedData>(() => {
    const base = series[methods[0]] ?? { x: [], accuracy: [], f1: [] };
    return [base.x, ...methods.map((m) => (series[m]?.[metric] ?? []) as (number | null)[])] as uPlot.AlignedData;
  }, [series, metric, methods.join(",")]);

  const detectorOptions = useMemo(
    () =>
      lineChart({
        xLabel: "sample index",
        yLabel: "error rate",
        yFormat: (v) => `${(v * 100).toFixed(0)}%`,
        lines: [{ label: "adaptive error", color: methodColor("adaptive") }],
        markers: () => markerRef.current,
      }),
    [theme, present],
  );
  const detectorData = useMemo<uPlot.AlignedData>(
    () => [adaptiveSeries.x, adaptiveSeries.accuracy.map((a) => (a == null ? null : 1 - a))] as uPlot.AlignedData,
    [adaptiveSeries],
  );

  const costOptions = useMemo(
    () => stackedChart({ xLabel: "sample index", yLabel: "µs per sample", keys: STAGE_ORDER, markers: () => markerRef.current }),
    [theme, present],
  );
  const costData = useMemo<uPlot.AlignedData>(() => {
    const blocks = store.blocks["adaptive"] ?? [];
    const x = blocks.map((b) => b.start + b.n);
    const stages = STAGE_ORDER.map((key) => blocks.map((b) => ((b[`${key}_mean_ns`] as number) ?? 0) / 1000));
    return [x, ...stack(stages)] as uPlot.AlignedData;
  }, [store.status.sample, store.blocks]);

  const adaptiveBlocks = store.blocks["adaptive"] ?? [];
  const block = lastBlock(adaptiveBlocks);
  const engineBlock = store.engine[store.engine.length - 1];
  const resource = store.resources[store.resources.length - 1];
  const allEpisodes = episodes(store.events);
  const episode = [...allEpisodes].reverse().find((e) => e.driftIndex != null) ?? allEpisodes[allEpisodes.length - 1];
  const anchor = episode?.driftIndex ?? episode?.detectedAt ?? null;
  const preAccuracy = scoreAt(adaptiveSeries, anchor == null ? null : anchor - 1);
  const minAccuracy = minScoreBetween(adaptiveSeries, anchor, episode?.adaptedAt != null ? episode.adaptedAt + 3000 : store.status.sample);
  const postAccuracy = episode?.adaptedAt != null ? scoreAt(adaptiveSeries, Math.min(episode.adaptedAt + 1500, store.status.sample)) : null;
  const scores = Object.fromEntries(methods.map((m) => [m, overallScores(store.blocks[m] ?? [], warmup)]));
  const latest = (method: string, key: "accuracy" | "f1") => {
    const s = series[method];
    return s ? (s[key][s[key].length - 1] ?? null) : null;
  };
  const meanService = recentMean(adaptiveBlocks, "service_mean_ns");
  const p95Service = recentMean(adaptiveBlocks, "service_p95_ns");
  const throughput = useMemo(() => {
    const total = store.engine.reduce((sum, b) => sum + b.n, 0);
    const wall = store.engine.reduce((sum, b) => sum + b.wall_ms, 0);
    return wall > 0 ? (total / wall) * 1000 : null;
  }, [store.engine.length]);
  const elapsedMs = useMemo(() => store.engine.reduce((sum, b) => sum + b.wall_ms, 0), [store.engine.length]);

  /** Which preset is actually running: matched on the backend's own name, so a page reload mid-run
   *  still labels the scenario correctly rather than trusting this screen's local selection. */
  const runningScenario = useMemo(() => {
    const match = Object.entries(presets).find(([, entry]) => entry.name === store.name);
    if (match) return scenarioCopy(match[0], match[1].name).title;
    return store.name || scenarioCopy(preset, presets[preset]?.name).title;
  }, [presets, store.name, preset]);

  /** The headline and its supporting sentence: what a visitor reads first, in plain English. */
  const story = (): { headline: string; sentence: string } => {
    if (!started) {
      return {
        headline: "Nothing is running yet.",
        sentence: "Choose a dataset and start a replay. Each row is predicted before its label is used for learning.",
      };
    }
    if (store.status.lifecycle === "warming_up") {
      return {
        headline: "Warming up on the first samples.",
        sentence: `Every method learns from the first ${samples(warmup)} samples before measurement begins, so the comparison starts from the same footing.`,
      };
    }
    if (store.status.lifecycle === "paused") {
      return {
        headline: "The run is paused.",
        sentence: "No samples are being processed. Resume to continue from exactly where it stopped.",
      };
    }
    if (realData && injection && phase === "stable" && store.status.sample < injection.start) return {
      headline: "Replaying real observations.",
      sentence: `The rows are untouched so far. At row ${samples(injection.start)} the columns ${injection.swap[0]} and ${injection.swap[1]} will be exchanged (${injection.kind} change), so that its position is known.`,
    };
    if (realData && !injection) return {
      headline: store.status.lifecycle === "completed" ? "Dataset replay complete." : "Replaying real observations.",
      sentence: "Track prediction quality and detector alerts on the recorded data. Drift locations are not annotated, so detection delay and recovery from a known drift are unavailable.",
    };
    switch (phase) {
      case "drift":
        return {
          headline: episode?.detectedAt != null ? `Drift detected at sample ${samples(episode.detectedAt)}.` : "Drift detected in the data.",
          sentence:
            episode?.delay != null
              ? `ADWIN found a sustained increase in prediction errors, ${samples(episode.delay)} samples after the data actually changed.`
              : "ADWIN found a sustained increase in the adaptive pipeline's own prediction errors.",
        };
      case "adapting":
        return {
          headline: "The model is being replaced.",
          sentence: "A new model is learning from samples taken after the change, while the current model keeps making predictions.",
        };
      case "recovery":
        return {
          headline: `The model adapted at sample ${samples(episode?.adaptedAt ?? 0)}.`,
          sentence: "We are now watching whether its accuracy returns toward the level it held before the drift.",
        };
      default:
        return {
          headline: "Monitoring the model’s predictions.",
          sentence: "Both methods are processing the same stream. The charts show their measured prediction quality.",
        };
    }
  };

  /** The journey so far: each stage, and the sample index it happened at. */
  const steps = useMemo<PhaseStep[]>(() => {
    const at = (value: number | null | undefined) => (value == null ? null : value);
    const done = (value: number | null | undefined) => value != null;
    return [
      {
        key: "drift",
        label: "Drift",
        at: at(episode?.driftIndex),
        tone: "drift",
        state: done(episode?.driftIndex) ? (phase === "drift" ? "current" : "done") : "todo",
      },
      {
        key: "detected",
        label: "Detected",
        at: at(episode?.detectedAt),
        tone: "detect",
        state: done(episode?.detectedAt) ? (phase === "drift" ? "current" : "done") : "todo",
      },
      {
        key: "adapted",
        label: "Adapted",
        at: at(episode?.adaptedAt),
        tone: "adapt",
        state: done(episode?.adaptedAt) ? "done" : phase === "adapting" ? "current" : "todo",
      },
      {
        key: "monitoring",
        label: "Monitoring",
        at: null,
        state: phase === "recovery" ? "current" : "todo",
      },
    ];
  }, [episode?.driftIndex, episode?.detectedAt, episode?.adaptedAt, phase]);

  const start = async () => {
    setBusy(true);
    setProblem(null);
    try {
      await liveActions.start({ preset, profile });
    } catch (error) {
      setProblem(String((error as Error).message));
    } finally {
      setBusy(false);
    }
  };

  const command = async (kind: "pause" | "resume" | "stop" | "inject-drift", body?: unknown) => {
    setBusy(true);
    try {
      await liveActions.command(kind, body);
    } catch (error) {
      setProblem(String((error as Error).message));
    } finally {
      setBusy(false);
    }
  };

  const narration = demo
    ? demoProgress({
        lifecycle: store.status.lifecycle,
        sample: store.status.sample,
        warmup,
        events: store.events,
        episode,
        preAccuracy,
        minAccuracy,
      })
    : null;
  const narrationSample =
    narration == null
      ? null
      : narration.index <= 2
        ? episode?.driftIndex ?? null
        : narration.index <= 4
          ? episode?.detectedAt ?? null
          : episode?.adaptedAt ?? store.status.sample;

  const { headline, sentence } = story();

  return (
    <div className="page">
      <header className="lab-heading">
        <span className="eyebrow">Research workspace / Dataset test</span>
        <h1>Watch learning happen.</h1>
        <p>Replay a static Kaggle dataset row by row. Inspect accuracy, detector alerts, and the work behind every prediction.</p>
      </header>
      <ReplaySetup disabled={busy || store.active || store.job?.status === "running"} onStart={async (config, name) => {
        setDemo(false); await liveActions.start({config, name});
      }} />
      {store.job?.status === "running" && <p className="banner">An experiment is running. Wait for it to finish before starting a replay.</p>}
      {store.active && realData && <div className="replay-toolbar">
        <span role="status">{store.status.sample.toLocaleString()} / {store.status.total.toLocaleString()} rows · {store.status.lifecycle}</span>
        <progress aria-label="Dataset replay progress" value={store.status.sample} max={store.status.total} />
        <button className="btn" disabled={busy} onClick={() => void command(store.status.lifecycle === "paused" ? "resume" : "pause")}>{store.status.lifecycle === "paused" ? "Resume" : "Pause"}</button>
        <button className="btn danger" disabled={busy} onClick={() => void command("stop")}>Stop replay</button>
      </div>}
      {started && <HeroStory
        statusLabel={realData ? `Dataset replay · ${store.status.lifecycle.replaceAll("_", " ")}` : undefined}
        phase={phase}
        headline={headline}
        sentence={sentence}
        steps={started && knownDrift ? steps : undefined}
        live={store.active}
        explain={phase === "drift" || phase === "adapting" ? "drift" : undefined}
        meta={
          <>
            <Badge tone={store.active ? "ok" : "idle"} pulse={store.active}>
              {store.status.lifecycle.replace("_", " ")}
            </Badge>
            <ProvenanceBadge kind="measured" />
            <ProvenanceBadge kind={injection ? "injected" : realData ? "real" : "synthetic"} />
            {simulated && <ProvenanceBadge kind={placeholder ? "placeholder" : "simulated"} />}
          </>
        }
      />}

      {started && config && (
        <RunContext
          items={[
            { k: "Scenario", v: runningScenario },
            { k: "Methods", v: methods.map(methodLabel).join(" vs ") },
            { k: "Profile", v: `${config.profile.label}${simulated ? " (simulated)" : ""}` },
            { k: realData ? "Source" : "Concept", v: realData ? "Fixed Kaggle snapshot" : store.extras ? `variant ${store.extras.concept.variant}` : DASH, mono: !realData },
            {
              k: "Samples",
              v: `${samples(store.status.sample)} / ${samples(store.status.total)}${
                store.status.total ? ` · ${Math.round((store.status.sample / store.status.total) * 100)}%` : ""
              }`,
              mono: true,
            },
            { k: "Elapsed", v: elapsedMs ? `${(elapsedMs / 1000).toFixed(0)} s` : DASH, mono: true },
            { k: "Seed", v: config.seed ?? DASH, mono: true, explain: "seed" },
          ]}
        />
      )}

      {narration && (
        <DemoCard
          index={narration.index}
          total={narration.total}
          title={narration.step.title}
          text={narration.step.text}
          sample={narrationSample}
          explain={narration.index <= 2 ? "drift" : narration.index <= 4 ? "adwin" : "adaptation"}
        />
      )}

      <details className="synthetic-tools" open={store.active && !realData ? true : undefined}>
      <summary>Synthetic demo · controlled concept changes</summary>
      <RunControlBar
        presets={presets}
        preset={preset}
        onPreset={(value) => { setPreset(value); setDemo(false); }}
        profiles={profiles}
        profile={profile}
        onProfile={setProfile}
        variants={[0, 1, 2, 3].filter((v) => v !== (store.extras?.concept.variant ?? -1))}
        injectVariant={injectVariant}
        onInjectVariant={setInjectVariant}
        flip={flips[`${store.extras?.concept.variant ?? 0}->${injectVariant}`] ?? null}
        active={store.active && !realData}
        lifecycle={store.status.lifecycle}
        sample={store.status.sample}
        total={store.status.total}
        seed={config?.seed ?? null}
        busy={busy || store.active && realData || store.job?.status === "running"}
        demo={demo}
        onStart={() => { setDemo(false); void start(); }}
        onPause={() => void command("pause")}
        onResume={() => void command("resume")}
        onStop={() => void command("stop")}
        onInject={() => void command("inject-drift", { to_variant: injectVariant })}
        onDemo={async () => {
          setDemo(true);
          setPreset("demo_abrupt");
          if (!store.active) {
            setProfile("standard");
            await liveActions.start({ preset: "demo_abrupt", profile: "standard" });
          }
        }}
      />

      </details>
      {problem && (
        <div className="banner error">
          <div>
            <strong>That action could not be completed.</strong> {problem}
          </div>
        </div>
      )}
      {store.error && (
        <div className="banner error">
          <div>
            <strong>The run stopped with an error.</strong> Everything measured up to that point is still saved.
            <div className="small mono">{store.error.message}</div>
          </div>
        </div>
      )}
      {simulated && (
        <div className="banner">
          <div>
            <strong>Simulated edge profile.</strong> Edge constraints are simulated in software on this computer
            {placeholder ? " using placeholder values" : ""}; no physical edge device is being measured.
          </div>
          <ExplainButton id="edge" variant="text" label="What does this mean?" />
        </div>
      )}

      {started ? <>
      <section className="stack tight">
        <SectionHead title="What happened to the model" hint="One timeline: the stream position, not clock time" />
        <div className={knownDrift ? "two-col" : "stack"}>
          <Panel
            title={metric === "accuracy" ? "Accuracy over time" : "F1 over time"}
            explain={metric === "accuracy" ? "windowedAccuracy" : "f1"}
            actions={
              <div className="row" style={{ gap: 10 }}>
                <div className="segmented">
                  <button type="button" aria-pressed={metric === "accuracy"} onClick={() => setMetric("accuracy")}>Accuracy</button>
                  <button type="button" aria-pressed={metric === "f1"} onClick={() => setMetric("f1")}>F1</button>
                </div>
                <label className="field secondary">
                  Window
                  <select value={windowSize} onChange={(e) => setWindowSize(Number(e.target.value))}>
                    {WINDOWS.map((w) => <option key={w} value={w}>{w} samples</option>)}
                  </select>
                </label>
              </div>
            }
          >
            {heroData[0]?.length ? (
              <>
                <UPlotChart options={heroOptions} data={heroData} height={present ? 400 : 330} />
                <Legend
                  items={[
                    ...methods.map((m) => ({ label: methodLabel(m), color: methodColor(m), dashed: m === "static" })),
                    ...(knownDrift ? [{ label: injection ? "the added change" : "drift in the data", color: "var(--drift)", dashed: true }] : []),
                    { label: "detected", color: "var(--detect)" },
                    { label: "adapted", color: "var(--adapt)" },
                  ]}
                />
                <p className="chart-note row secondary" style={{ gap: 5 }}>
                  Flags mark the events this run recorded. The horizontal axis is the position in the stream, not clock
                  time. <ExplainButton id="sampleIndex" />
                </p>
              </>
            ) : (
              <EmptyState
                title="No run yet"
                hint="Prediction scores will appear as rows are processed. Detector events are marked when recorded."
              />
            )}
          </Panel>

          {knownDrift && <Panel title="The story of this run" sub={injection ? "added change → detection → adaptation" : "drift → detection → adaptation"}>
            <WhatHappenedCard
              added={injection}
              episode={episode}
              preAccuracy={preAccuracy}
              minAccuracy={minAccuracy}
              postAccuracy={postAccuracy}
              staticAccuracy={latest("static", "accuracy")}
              modelVersion={extras?.model_version ?? null}
            />
          </Panel>}
        </div>
      </section>

      <section className="stack tight">
        <SectionHead title="How well it is predicting" hint={`Over the last ${windowSize} samples, and across the whole run`} />
        <MetricGrid>
          <MetricCard
            label="Accuracy — adaptive pipeline"
            explain="accuracy"
            tone="accent"
            value={pct(latest("adaptive", "accuracy"))}
            sub={`${pct(scores["adaptive"]?.accuracy)} across the whole run`}
          />
          <MetricCard
            label="Accuracy — static baseline"
            explain="staticMethod"
            value={pct(latest("static", "accuracy"))}
            sub={`${pct(scores["static"]?.accuracy)} across the whole run`}
          />
          <MetricCard
            label="F1 — adaptive pipeline"
            explain="f1"
            value={pct(latest("adaptive", "f1"))}
            sub={`${pct(scores["adaptive"]?.f1)} across the whole run`}
          />
        </MetricGrid>

        <div className="stat-strip" style={{ marginTop: 4 }}>
          <div>
            <span className="k">
              Processing time <ExplainButton id="latency" />
            </span>
            <span className="v">
              {meanService != null ? (meanService / 1000).toFixed(1) : DASH}
              <span className="unit">µs</span>
            </span>
          </div>
          <div>
            <span className="k">
              p95 <ExplainButton id="p95" />
            </span>
            <span className="v">
              {p95Service != null ? (p95Service / 1000).toFixed(1) : DASH}
              <span className="unit">µs</span>
            </span>
          </div>
          <div>
            <span className="k">
              Throughput <ExplainButton id="throughput" />
            </span>
            <span className="v">
              {throughput ? num(throughput) : DASH}
              <span className="unit">/s</span>
            </span>
          </div>
          <div>
            <span className="k">
              Processor <ExplainButton id="cpuPerSample" />
            </span>
            <span className="v">
              {resource ? resource.cpu_percent.toFixed(0) : DASH}
              <span className="unit">%</span>
            </span>
          </div>
          <div>
            <span className="k">
              Memory <ExplainButton id="rss" />
            </span>
            <span className="v">
              {resource ? resource.rss_mb.toFixed(0) : DASH}
              <span className="unit">MB</span>
            </span>
          </div>
          <div>
            <span className="k">
              Model size <ExplainButton id="modelSize" />
            </span>
            <span className="v">{block?.model_size_bytes != null ? kb(block.model_size_bytes / 1024) : DASH}</span>
          </div>
        </div>
      </section>

      <section className="stack tight">
        <SectionHead
          title="How the pipeline works"
          hint="The path every sample takes — select a step to see what it does and what it measured"
        />
        <PipelineFlow
          block={block}
          extras={extras}
          streamDetail={
            config
              ? `${String(config.stream.scenario).toUpperCase()} · ${config.stream.rate ? `${config.stream.rate}/s` : "max speed"} ${realData ? "· original rows" : `· noise ${config.stream.noise}`}`
              : "not started"
          }
          monitorUs={store.final?.timing.monitor_us_per_sample ?? null}
          phase={phase}
          selected={stage}
          onSelect={setStage}
          config={config}
        />
      </section>

      <div className="two-col">
        <Panel title="Event log" sub="every drift, adaptation and resource decision" bodyClass="flush">
          <EventLog events={store.events} height={present ? 420 : 320} />
        </Panel>
        <div className="stack">
          <Panel title="What the pipeline is doing now">
            <DecisionCard extras={extras} resource={resource} phase={phase} constrained={constrained} />
          </Panel>
          {store.final && (
            <Panel title="Run saved">
              <div className="card-rows">
                <div className="card-row"><span className="k">Status</span><span className="v">{store.final.status}</span></div>
                <div className="card-row">
                  <span className="k">Results</span>
                  <span className="v"><a href={`#/experiments/${store.final.experiment_id}`}>open this run</a></span>
                </div>
                <div className="card-row">
                  <span className="k row" style={{ gap: 4 }}>Monitoring overhead <ExplainButton id="monitor" /></span>
                  <span className="v">{us(store.final.timing.monitor_us_per_sample)}</span>
                </div>
              </div>
            </Panel>
          )}
        </div>
      </div>

      <TechnicalDetails summary="Diagnostics — what the data looks like, what the detector sees, where the time goes">
        <div className="small-charts">
          <Panel title="What the data looks like" explain="drift" bodyClass="tight">
            <DataSnapshot extras={store.extras} theme={theme} />
          </Panel>
          <Panel title="The error rate the detector watches" explain="adwin" bodyClass="tight">
            {detectorData[0]?.length ? (
              <UPlotChart options={detectorOptions} data={detectorData} height={present ? 230 : 190} />
            ) : (
              <EmptyState title="No data yet" hint="The detector's view of the error rate appears once the run starts." />
            )}
          </Panel>
        </div>
        <Panel title="Where the processing time goes" explain="latency" bodyClass="tight">
          {costData[0]?.length ? (
            <>
              <UPlotChart options={costOptions} data={costData} height={present ? 230 : 190} />
              <Legend items={STAGE_ORDER.map((key, i) => ({ label: key, color: `var(--stage-${i + 1})` }))} />
            </>
          ) : (
            <EmptyState title="No data yet" hint="Once the run starts, each pipeline step's time per sample is stacked here." />
          )}
        </Panel>
        <div className="row wrap" style={{ gap: 18 }}>
          <span className="small muted">
            Response time{" "}
            <span className="mono">{engineBlock?.response_mean_ms != null ? `${engineBlock.response_mean_ms.toFixed(1)} ms` : DASH}</span>
          </span>
          <span className="small muted">
            Backlog <span className="mono">{engineBlock?.backlog != null ? num(engineBlock.backlog) : DASH}</span>
          </span>
          <span className="small muted">
            Detections{" "}
            <span className="mono">
              {num(store.events.filter((e) => e.type === "drift_detected" && e.error_increased && e.method === "adaptive").length)}
            </span>
          </span>
          <span className="small muted">
            Adaptations{" "}
            <span className="mono">{num(store.events.filter((e) => e.type === "adaptation_completed" && e.method === "adaptive").length)}</span>
          </span>
        </div>
      </TechnicalDetails>

      {config && (
        <TechnicalDetails summary="View technical details of this run">
          <dl className="kv">
            <dt>Scenario</dt>
            <dd>{String(config.stream.scenario)} · seed {config.seed} · {realData ? `dataset ${config.stream.dataset}` : `noise ${config.stream.noise}`} · {samples(config.stream.length)} samples</dd>
            <dt>Learner</dt>
            <dd>{String(config.pipeline.learner.type)} (grace period {config.pipeline.learner.grace_period})</dd>
            <dt>Detector</dt>
            <dd>ADWIN δ={config.pipeline.detector.delta_drift} · warning δ={config.pipeline.detector.delta_warning} · clock {config.pipeline.detector.clock}</dd>
            <dt>Preprocessing</dt>
            <dd>{String(config.pipeline.preprocessing.scaler)} (fading {config.pipeline.preprocessing.fading_factor}) · clip {config.pipeline.preprocessing.clip}σ</dd>
            <dt>Adaptation</dt>
            <dd>
              promote after {config.pipeline.adaptation.background_min_samples} samples · cooldown {config.pipeline.adaptation.cooldown} ·
              background models {config.pipeline.adaptation.allow_background ? "allowed" : "disallowed"}
            </dd>
            <dt>Profile</dt>
            <dd>{String(config.profile.label)}{simulated ? " (simulated in software)" : ""}</dd>
          </dl>
        </TechnicalDetails>
      )}
      </> : <div className="replay-idle"><strong>Your results will appear here.</strong><p>Start a replay to see measured accuracy, F1, stage latency, resource use, and detector events. Every run is saved for review in Experiments.</p></div>}
    </div>
  );
}
