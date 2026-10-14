/** Experiments — set up a controlled comparison, and browse every run that has been recorded.
 *
 *  The basic choice is one line: which scenario to run. What that scenario actually contains is
 *  disclosed underneath, read-only, because the preset is what the backend runs — the platform does
 *  not pretend to offer knobs it would not honour. */

import { useCallback, useEffect, useRef, useState } from "react";

import ExperimentBoard from "../components/ExperimentBoard";
import ReplaySetup from "../components/ReplaySetup";
import { ExplainButton } from "../components/Explain";
import { Badge, EmptyState, ErrorState, Loading, Panel, ProvenanceBadge, SectionHead, TechnicalDetails } from "../components/ui";
import { api, type Manifest, type Preset } from "../lib/api";
import { pct, timeAgo } from "../lib/format";
import { store, useLive } from "../lib/live";
import { href } from "../lib/router";

/** Turn a preset into readable lines. The shape is the backend's: settings shared by every trial live
 *  under `base`, and the lists that multiply into trials (seeds, profiles, rates) sit beside it. */
function describe(config: Record<string, unknown> | undefined): { k: string; v: string }[] {
  if (!config) return [];
  const out: { k: string; v: string }[] = [];
  const base = (config.base ?? {}) as Record<string, unknown>;
  const stream = (base.stream ?? {}) as Record<string, unknown>;
  const methods = base.methods as string[] | undefined;
  const seeds = config.seeds as number[] | undefined;
  const profiles = (config.profiles ?? base.profiles) as string[] | undefined;
  const rates = config.rates as (number | null)[] | undefined;
  const drifts = stream.drifts as { position?: number; to_variant?: number }[] | undefined;

  if (methods?.length) out.push({ k: "Methods compared", v: methods.join(", ") });
  if (profiles?.length) out.push({ k: "Resource profiles", v: profiles.join(", ") });
  if (stream.length != null) out.push({ k: "Samples per trial", v: Number(stream.length).toLocaleString() });
  if (stream.noise != null) out.push({ k: "Label noise", v: `${(Number(stream.noise) * 100).toFixed(0)} % of labels flipped` });
  if (drifts?.length) {
    out.push({
      k: drifts.length === 1 ? "Concept change" : "Concept changes",
      v: drifts
        .map((drift) =>
          `sample ${Number(drift.position ?? 0).toLocaleString()}${drift.to_variant != null ? ` → concept ${drift.to_variant}` : ""}`,
        )
        .join(" · "),
    });
  }
  if (rates?.length) {
    out.push({ k: "Arrival rate", v: rates.map((rate) => (rate == null ? "as fast as the engine allows" : `${rate} samples / second`)).join(" · ") });
  }
  if (seeds?.length) out.push({ k: seeds.length === 1 ? "Seed" : "Seeds", v: seeds.join(", ") });
  else if (base.seed != null) out.push({ k: "Seed", v: String(base.seed) });
  return out;
}

export default function Experiments() {
  useLive();
  const [presets, setPresets] = useState<Record<string, Preset>>({});
  const [preset, setPreset] = useState("compare_methods");
  const [manifests, setManifests] = useState<Manifest[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const boardRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(() => {
    api.experiments()
      .then((list) => { setManifests(list); setProblem(null); })
      .catch(() => setProblem("The list of runs could not be loaded from the server."));
  }, []);

  useEffect(() => {
    api.presets().then((p) => setPresets(p.experiments)).catch(() => {});
    refresh();
  }, [refresh]);

  const job = store.job;
  useEffect(() => {
    if (job && job.status !== "running") refresh();
  }, [job?.status, job?.experiment_id, refresh]);

  const run = async () => {
    setBusy(true);
    setProblem(null);
    try {
      await api.startExperiment({ preset });
      refresh();
    } catch (error) {
      setProblem(String((error as Error).message));
    } finally {
      setBusy(false);
    }
  };

  const running = job?.status === "running";
  const chosen = presets[preset];
  const settings = describe(chosen?.config);

  return (
    <div className="page">
      <header className="lab-heading">
        <span className="eyebrow">Research workspace / Experiments</span>
        <h1>Compare learning strategies.</h1>
        <p>Choose a real dataset, choose how it changes, and measure every method before, during and after that change, alongside what the adaptation costs.</p>
      </header>
      {/* What is running comes first: nobody should have to scroll past a form to find out. */}
      <div ref={boardRef} className="board-slot">{job && <ExperimentBoard job={job} />}</div>
      <ReplaySetup experiment disabled={busy || !!running || store.active} onStart={async (config) => {
        await api.startExperiment({ config }); refresh();
        boardRef.current?.scrollIntoView({ block: "start" });
      }} />
      {store.active && <p className="banner">A dataset replay is active. Stop it before running an isolated comparison.</p>}
      <details className="synthetic-tools"><summary>Synthetic benchmarks · controlled drift experiments</summary>
      <section className="stack tight">
        <SectionHead title="Run an experiment" hint="Each method runs on its own, in a fresh process, one after another" />
        <Panel
          actions={running ? <button type="button" className="btn small danger" onClick={() => void api.stopJob()}>Stop after this trial</button> : undefined}
          title="New experiment"
          sub="choose what to compare"
        >
          <div className="row wrap" style={{ gap: 14 }}>
            <label className="field" style={{ flex: "1 1 340px", maxWidth: 520 }}>
              Scenario
              <select value={preset} onChange={(e) => setPreset(e.target.value)} style={{ maxWidth: "100%" }}>
                {Object.entries(presets).map(([key, value]) => (
                  <option key={key} value={key}>{value.name}</option>
                ))}
              </select>
            </label>
            <button type="button" className="btn primary" onClick={() => void run()} disabled={busy || running || store.active}>
              Run experiment
            </button>
          </div>

          {chosen?.description && <p className="chart-note" style={{ marginTop: 10 }}>{chosen.description}</p>}

          {settings.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <TechnicalDetails summary="Advanced — exactly what this scenario will run">
                <dl className="kv">
                  {settings.map((setting) => (
                    <div key={setting.k} style={{ display: "contents" }}>
                      <dt>{setting.k}</dt>
                      <dd style={{ fontFamily: "var(--font)" }}>{setting.v}</dd>
                    </div>
                  ))}
                </dl>
                <p className="tiny muted" style={{ margin: 0 }}>
                  These values are fixed by the scenario so that every run of it stays comparable. To vary them — a different
                  drift position, a tighter resource budget, another detector setting — edit the scenario file and run it from
                  the command line; the platform will record it exactly the same way.
                </p>
              </TechnicalDetails>
            </div>
          )}

          {store.active && (
            <p className="small muted" style={{ marginTop: 10 }}>
              A live run is in progress. Runs never share the processor, so stop it first to keep the timings comparable.
            </p>
          )}
          {problem && (
            <div style={{ marginTop: 12 }}>
              <ErrorState
                title="The experiment could not be started."
                why={problem}
                action={<button type="button" className="btn small" onClick={() => void run()}>Try again</button>}
              />
            </div>
          )}
          {job && (
            <div className="row wrap" style={{ marginTop: 14, gap: 12 }}>
              <Badge tone={running ? "info" : job.status === "completed" ? "ok" : "warn"} pulse={running}>{job.status}</Badge>
              <span className="small">
                {job.name}
                {job.total != null && ` — trial ${Math.min(job.done + 1, job.total)} of ${job.total}`}
                {job.trial && <span className="mono muted"> · {job.trial}</span>}
              </span>
              {job.experiment_id && !running && <a href={`#/experiments/${job.experiment_id}`}>open results</a>}
            </div>
          )}
        </Panel>
      </section>

      </details>
      <section className="stack tight">
        <SectionHead
          title="Recorded runs"
          hint={manifests ? `${manifests.length} saved — every run is kept with its configuration and environment` : undefined}
        />
        <Panel
          title="All runs"
          sub="live runs and experiments"
          actions={<button type="button" className="btn small" onClick={refresh}>Refresh</button>}
          bodyClass="flush"
        >
          {manifests === null ? (
            <Loading label="Loading runs" />
          ) : manifests.length === 0 ? (
            <EmptyState
              title="No runs recorded yet"
              hint="Run an experiment above to compare methods, or start the guided demo on the Live screen — every run is saved automatically, with the settings needed to reproduce it."
            />
          ) : (
            <div className="list">
              {manifests.map((manifest) => (
                <a key={manifest.id} className="list-item" href={href({ page: "experiment", id: manifest.id })}>
                  <div className="title">
                    {manifest.name}
                    <span className="tag">{manifest.kind}</span>
                    <ProvenanceBadge kind={manifest.provenance?.injected_drift ? "injected" : manifest.provenance?.real_data ? "real" : "synthetic"} />
                    {manifest.provenance?.simulated_profiles?.length > 0 && <ProvenanceBadge kind="simulated" />}
                    {manifest.reproducibility && (
                      <span className="tag">reproduced {manifest.reproducibility.identical}/{manifest.reproducibility.trials_compared}</span>
                    )}
                  </div>
                  <Badge tone={manifest.status === "completed" ? "ok" : manifest.status === "error" ? "error" : "warn"}>{manifest.status}</Badge>
                  <div className="facts">
                    {manifest.trials.length} trial{manifest.trials.length === 1 ? "" : "s"}
                    {manifest.trials.some((t) => !t.control) &&
                      ` · ${manifest.trials
                        .filter((t) => !t.control)
                        .flatMap((t) => Object.entries(t.methods))
                        .slice(0, 4)
                        .map(([m, s]) => `${m} ${pct(s.accuracy, 1)}`)
                        .join(" · ")}`}
                  </div>
                  <div className="facts">{timeAgo(manifest.created_utc)}</div>
                </a>
              ))}
            </div>
          )}
        </Panel>
        <p className="chart-note row" style={{ gap: 6 }}>
          Every run stores the settings, the machine it ran on and a hash of its predictions, so it can be repeated and checked.
          <ExplainButton id="reproducibility" />
        </p>
      </section>
    </div>
  );
}
