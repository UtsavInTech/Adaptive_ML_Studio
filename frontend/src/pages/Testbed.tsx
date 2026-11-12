/** Research testbed — run the large-dataset experiments the paper needs, watch them, read the results
 *  and open the generated reports.
 *
 *  The form posts the same experiment configuration as the Experiments page, on a slice of a large
 *  streaming dataset (CIC-IDS2017). Every simulated tier is labelled as simulated with placeholder
 *  budgets, wherever it appears. Nothing on this page judges a result. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import ExperimentBoard from "../components/ExperimentBoard";
import { ExplainButton } from "../components/Explain";
import ReportView from "../components/ReportView";
import { Badge, EmptyState, ErrorState, Loading, Panel, ProvenanceBadge, SectionHead } from "../components/ui";
import { api, type Manifest, type ReportSummary, type TestbedOptions } from "../lib/api";
import { DASH, methodLabel, pct, timeAgo } from "../lib/format";
import { store, useLive } from "../lib/live";
import { href } from "../lib/router";
import { ALL_RULES, aboutDuration, buildConfig, estimateSeconds, formIssues, parseSeeds, trialCount, type TestbedForm } from "../lib/testbed";

type Tab = "setup" | "runs" | "device" | "reports";

const mib = (value: number | null) => (value == null ? "none" : value >= 1 ? `${value} MiB` : `${Math.round(value * 1024)} KiB`);

export default function Testbed({ report }: { report?: string }) {
  useLive();
  const [tab, setTab] = useState<Tab>(report ? "reports" : "setup");
  const [options, setOptions] = useState<TestbedOptions | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [manifests, setManifests] = useState<Manifest[] | null>(null);
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const boardRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(() => {
    api.experiments().then(setManifests).catch(() => setManifests([]));
    api.reports().then(setReports).catch(() => setReports([]));
  }, []);
  const loadOptions = () => {
    setProblem(null);
    api.testbedOptions().then(setOptions).catch((e: Error) => setProblem(e.message));
  };
  useEffect(() => { loadOptions(); refresh(); }, [refresh]);
  useEffect(() => { if (report) setTab("reports"); }, [report]);

  const job = store.job;
  useEffect(() => { if (job && job.status !== "running") refresh(); }, [job?.status, job?.experiment_id, refresh]);

  const streamingIds = new Set(options?.datasets.map((d) => d.id) ?? []);
  // A run counts as a device run only when the machine named itself as a single-board computer.
  const deviceRuns = (manifests ?? []).filter((m) => m.provenance?.device_model);
  const rehearsals = (manifests ?? []).filter((m) => !m.provenance?.device_model && m.name.startsWith("Device run rehearsal"));
  const runs = (manifests ?? []).filter((m) => m.trials.some((t) => t.scenario?.dataset && streamingIds.has(t.scenario.dataset)));

  return (
    <div className="page testbed-page">
      <header className="lab-heading">
        <span className="eyebrow">Research workspace / Testbed</span>
        <h1>Research testbed</h1>
        <p>
          Replay a large, real network-traffic stream through each method on simulated device tiers, with late or partial
          labels, and read the measurements the paper's tables are built from.
        </p>
      </header>
      <div ref={boardRef} className="board-slot" hidden={!job}>{job && <ExperimentBoard job={job} />}</div>
      <nav className="workspace-nav" aria-label="Testbed workspace">
        <button type="button" aria-current={tab === "setup" ? "page" : undefined} onClick={() => setTab("setup")}>Set up and run</button>
        <button type="button" aria-current={tab === "runs" ? "page" : undefined} onClick={() => setTab("runs")}>Testbed runs <span>{manifests ? runs.length : "…"}</span></button>
        <button type="button" aria-current={tab === "device" ? "page" : undefined} onClick={() => setTab("device")}>Real device <span>{manifests ? deviceRuns.length : "…"}</span></button>
        <button type="button" aria-current={tab === "reports" ? "page" : undefined} onClick={() => setTab("reports")}>Reports <span>{reports?.length ?? "…"}</span></button>
      </nav>

      <div hidden={tab !== "setup"}>
        {problem && <ErrorState title="The testbed settings could not be loaded." why="The server did not answer." technical={problem} action={<button type="button" className="btn small" onClick={loadOptions}>Retry</button>} />}
        {!options && !problem && <Panel title="Loading the testbed"><Loading /></Panel>}
        {options && options.datasets.length === 0 && (
          <EmptyState title="No large streaming dataset is registered" hint="Prepare CIC-IDS2017 with scripts/prepare_cicids2017.py; it is then listed here." />
        )}
        {options && options.datasets.length > 0 && (
          <TestbedSetup
            options={options}
            disabled={job?.status === "running" || store.active}
            onStarted={() => { refresh(); boardRef.current?.scrollIntoView({ block: "start" }); }}
          />
        )}
        {store.active && <p className="banner">A dataset replay is active on the Dataset test page. Stop it first: runs never share the processor.</p>}
      </div>

      <section hidden={tab !== "runs"} className="stack tight">
        <SectionHead title="Runs on the large dataset" hint="open one for its testbed measures: κ-temporal, cost terms, attacks, controller decisions" />
        <Panel bodyClass="flush" actions={<button type="button" className="btn small" onClick={refresh}>Refresh</button>}>
          {manifests === null ? <Loading label="Loading runs" /> : runs.length === 0 ? (
            <EmptyState title="No testbed runs yet" hint="Start one under “Set up and run”. Runs made from the command line with the protocol scripts appear here too." />
          ) : (
            <div className="list">
              {runs.map((m) => <RunRow key={m.id} m={m} />)}
            </div>
          )}
        </Panel>
      </section>

      <section hidden={tab !== "device"} className="stack tight">
        <SectionHead title="Runs measured on a real device" hint="optional: the same trials on a Raspberry Pi, brought back as a file" />
        <Panel bodyClass="flush" actions={<button type="button" className="btn small" onClick={refresh}>Refresh</button>}>
          {manifests === null ? <Loading label="Loading runs" /> : deviceRuns.length === 0 ? (
            <EmptyState
              title="No run from a real device yet"
              hint="Every budgeted result in this app so far is simulated on a laptop. This step replaces the simulation with a measurement; the project is complete without it."
            />
          ) : (
            <div className="list">{deviceRuns.map((m) => <RunRow key={m.id} m={m} />)}</div>
          )}
        </Panel>
        {rehearsals.length > 0 && (
          <Panel title="Rehearsals of the device kit" bodyClass="flush">
            <p className="small muted device-note">Made with the same kit on a machine that is not a single-board computer. They show that the kit works, not how a device performs.</p>
            <div className="list">{rehearsals.map((m) => <RunRow key={m.id} m={m} />)}</div>
          </Panel>
        )}
        <Panel title="How to make a device run">
          <ol className="device-steps">
            <li><strong>On the laptop, pack the kit.</strong> One file with the code and the prepared dataset.<code>research_testbed/device/pack.sh</code></li>
            <li><strong>Copy it to the device and unpack it.</strong> A Raspberry Pi 4 or 5 with 64-bit Raspberry Pi OS and about 3 GB free.<code>scp research_testbed/device/out/adaptiveml-device-kit.tar.gz pi@raspberrypi.local:~</code></li>
            <li><strong>On the device, set up once.</strong><code>bash research_testbed/device/setup.sh</code></li>
            <li><strong>On the device, run.</strong> It measures the device's own cost per connection, sets two budgets from it, runs the methods and writes one results file. Use <span className="mono">--quick</span> first.<code>backend/.venv/bin/python research_testbed/device/run_on_device.py --quick</code></li>
            <li><strong>Back on the laptop, import the results file.</strong> The runs then appear in the list above.<code>backend/.venv/bin/python research_testbed/device/import_bundle.py device-….tar.gz</code></li>
          </ol>
          <p className="small muted">
            Full instructions: research_testbed/device/README.md. On the device the budgets are still set by a rule (placeholder
            budgets), and energy is not measured.
          </p>
        </Panel>
      </section>

      <section hidden={tab !== "reports"} className="stack tight">
        <SectionHead title="Generated reports" hint="written by research_testbed/scripts/report.py from saved runs" />
        <Panel bodyClass="flush">
          {reports === null ? <Loading label="Loading reports" /> : reports.length === 0 ? (
            <EmptyState title="No reports generated yet" hint="Run research_testbed/scripts/report.py after a protocol run; its report appears here." />
          ) : (
            <div className="list">
              {reports.map((r) => (
                <a key={r.name} className="list-item" href={href({ page: "testbed", report: r.name })} aria-current={report === r.name ? "page" : undefined}>
                  <div className="title">{r.title}<span className="tag mono">{r.name}</span></div>
                  <div className="facts">{r.figures} figure{r.figures === 1 ? "" : "s"} · {r.tables} table{r.tables === 1 ? "" : "s"}</div>
                  <div className="facts">{timeAgo(new Date(r.modified * 1000).toISOString())}</div>
                </a>
              ))}
            </div>
          )}
        </Panel>
        {report && <ReportView name={report} />}
      </section>
    </div>
  );
}

function RunRow({ m }: { m: Manifest }) {
  const kt = m.trials.flatMap((t) => Object.entries(t.methods).map(([method, s]) => ({ method, tier: t.profile?.name, kt: (s as { kappa_temporal?: number | null }).kappa_temporal })));
  return (
    <a className="list-item" href={href({ page: "experiment", id: m.id })}>
      <div className="title">
        {m.name}
        <ProvenanceBadge kind="real" />
        {m.provenance?.device_model && <span className="tag real">measured on {m.provenance.device_model}</span>}
        {m.provenance?.simulated_profiles?.length > 0 && <span className="tag sim">simulated · placeholder budgets</span>}
        {m.provenance?.device_model && m.provenance.placeholder_budgets && <span className="tag sim">placeholder budgets</span>}
      </div>
      <Badge tone={m.status === "completed" ? "ok" : m.status === "error" ? "error" : "warn"}>{m.status}</Badge>
      <div className="facts">
        {m.trials.length} trial{m.trials.length === 1 ? "" : "s"}
        {kt.slice(0, 4).map((k) => ` · ${k.method}${k.tier && k.tier !== "standard" ? ` (${k.tier})` : ""} κ-t ${k.kt == null ? DASH : k.kt.toFixed(2)}`).join("")}
      </div>
      <div className="facts">{timeAgo(m.created_utc)}</div>
    </a>
  );
}

function TestbedSetup({ options, disabled, onStarted }: { options: TestbedOptions; disabled: boolean; onStarted: () => void }) {
  const [datasetId, setDatasetId] = useState(options.datasets.find((d) => d.available)?.id ?? options.datasets[0].id);
  const dataset = options.datasets.find((d) => d.id === datasetId) ?? options.datasets[0];
  const [sliceId, setSliceId] = useState<string>(dataset.slices.some((s) => s.id === options.defaults.slice) ? options.defaults.slice : dataset.slices[0].id);
  const preset = dataset.slices.find((s) => s.id === sliceId);
  const [custom, setCustom] = useState({ start: preset?.start ?? 0, length: Math.min(preset?.length ?? 100_000, 100_000) });
  const start = preset ? preset.start : custom.start;
  const length = preset ? preset.length : custom.length;
  const [methods, setMethods] = useState(["no_change", "adaptive", "joint"]);
  const [tiers, setTiers] = useState(["small_sim"]);
  const [labelDelay, setLabelDelay] = useState(0);
  const [coverage, setCoverage] = useState(100);
  const [arrival, setArrival] = useState<"constant" | "recorded">("constant");
  const [rateScale, setRateScale] = useState(10);
  const [rules, setRules] = useState(ALL_RULES);
  const [gating, setGating] = useState(true);
  const [seedText, setSeedText] = useState(options.defaults.seeds.join(", "));
  const [warmup, setWarmup] = useState(options.defaults.warmup);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const sliceLabel = preset?.label ?? `rows ${custom.start.toLocaleString()}–${(custom.start + custom.length).toLocaleString()}`;
  const autoName = `Testbed · ${sliceLabel} · ${methods.length} method${methods.length === 1 ? "" : "s"} · ${tiers.join(", ") || "no tier"}`;
  const seeds = parseSeeds(seedText) ?? [];
  const form: TestbedForm = {
    dataset: dataset.id, sha256: dataset.sha256, start, length, sliceLabel, methods, tiers,
    labelDelay, labelCoverage: coverage / 100, arrival, rateScale, rules, resourceGating: gating, seeds, warmup,
    name: name.trim() || autoName,
  };
  const issues = formIssues(form, dataset.rows);
  const trials = trialCount(form);
  const seconds = estimateSeconds(form, options);
  const large = length > options.defaults.large_rows;
  const slow = methods.filter((m) => options.methods.find((o) => o.id === m)?.slow);
  const periods = useMemo(
    () => (dataset.schedule?.attack_periods ?? []).filter((p) => p.start_row >= start && p.start_row < start + length),
    [dataset, start, length],
  );
  const joint = methods.includes("joint");
  const off = disabled || busy;

  const toggle = (list: string[], set: (v: string[]) => void, id: string, on: boolean) => set(on ? [...list, id] : list.filter((x) => x !== id));

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (issues.length || off) return;
    setBusy(true);
    setProblem(null);
    try {
      await api.startExperiment({ config: buildConfig(form) });
      onStarted();
    } catch (e) {
      setProblem((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="replay-setup comparison-setup testbed-setup" onSubmit={(e) => void submit(e)} noValidate>
      <div className="replay-main">
        {!dataset.available && <p className="banner error">The dataset file is missing. Run scripts/prepare_cicids2017.py to prepare it.</p>}

        <section aria-label="Presentation demo" className="demo-preset">
          <div>
            <strong>Short demo for a presentation</strong>
            <span>
              Fills the form with a one-minute run: 40,000 connections that include two real attacks (Slowloris and
              Slowhttptest), on the simulated small device, comparing copying the last answer, the review's rules
              (R1–R5) and the new budgeted effort controller.
            </span>
          </div>
          <button
            type="button"
            className="btn small"
            disabled={off}
            onClick={() => {
              setSliceId("custom");
              setCustom({ start: 730_000, length: 40_000 });
              setMethods(["no_change", "joint", "effort"]);
              setTiers(["small_sim"]);
              setLabelDelay(0);
              setCoverage(100);
              setArrival("constant");
              setRules(ALL_RULES);
              setGating(true);
              setName("Demo · rules (R1–R5) vs budgeted effort controller");
            }}
          >
            Use demo settings
          </button>
        </section>

        <section aria-label="Slice of the stream">
          <div className="setup-heading"><span className="step-number">01</span><h2>Choose the slice of the stream</h2>
            {options.datasets.length > 1 ? (
              <select value={datasetId} onChange={(e) => { setDatasetId(e.target.value); setSliceId("week"); }} disabled={off}>
                {options.datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            ) : <span className="tag real">{dataset.name}</span>}
          </div>
          <div className="dataset-options slice-options">
            {dataset.slices.map((s) => (
              <label key={s.id} className={`dataset-option ${sliceId === s.id ? "selected" : ""}`}>
                <input type="radio" name="slice" checked={sliceId === s.id} disabled={off} onChange={() => setSliceId(s.id)} />
                <span>
                  <strong>{s.label}</strong>
                  <span>{s.length.toLocaleString()} rows from row {s.start.toLocaleString()}</span>
                  <span>{s.said}</span>
                </span>
              </label>
            ))}
            <label className={`dataset-option ${sliceId === "custom" ? "selected" : ""}`}>
              <input type="radio" name="slice" checked={sliceId === "custom"} disabled={off} onChange={() => { setCustom({ start, length: Math.min(length, 100_000) }); setSliceId("custom"); }} />
              <span><strong>Custom rows</strong><span>Any first row and length, e.g. a short check.</span></span>
            </label>
          </div>
          {sliceId === "custom" && (
            <fieldset className="setup-fields" disabled={off} style={{ marginBottom: 16 }}>
              <label className="field">First row
                <input type="number" min={0} max={dataset.rows - 2} step={1} value={custom.start} onChange={(e) => setCustom({ ...custom, start: Number(e.target.value) })} />
              </label>
              <label className="field">Rows to replay
                <input type="number" min={2} max={dataset.rows} step={1} value={custom.length} onChange={(e) => setCustom({ ...custom, length: Number(e.target.value) })} />
              </label>
            </fieldset>
          )}
          <p className="small">
            <strong>{length.toLocaleString()} rows</strong>, rows {start.toLocaleString()}–{(start + length).toLocaleString()} of {dataset.rows.toLocaleString()}.
            {" "}{periods.length ? `${periods.length} dated attack period${periods.length === 1 ? " starts" : "s start"} inside: ${[...new Set(periods.map((p) => p.attack_type))].join(", ")}.` : "No dated attack period starts inside these rows."}
            <ExplainButton id="attackPeriods" />
          </p>
        </section>

        <section aria-label="Methods">
          <div className="setup-heading"><span className="step-number">02</span><h2>Choose the methods</h2></div>
          <fieldset className="method-options" disabled={off}>
            <legend>Each method runs alone, in a fresh process, once per tier and seed</legend>
            {options.methods.map((m) => (
              <label key={m.id}>
                <input type="checkbox" checked={methods.includes(m.id)} onChange={(e) => toggle(methods, setMethods, m.id, e.target.checked)} />
                <span>
                  <strong>{methodLabel(m.id)} {m.slow && <span className="tag sim">very slow: roughly 5 ms per row</span>}</strong>
                  <small>{m.said} Typically about {m.us_per_row.toLocaleString()} µs per row.</small>
                </span>
              </label>
            ))}
          </fieldset>
        </section>

        <section aria-label="Device tiers">
          <div className="setup-heading"><span className="step-number">03</span><h2>Choose the device tiers</h2><ExplainButton id="deviceTier" /></div>
          <div className="tier-options">
            {options.tiers.map((t) => (
              <label key={t.name} className={`tier-option ${tiers.includes(t.name) ? "selected" : ""}`}>
                <input type="checkbox" checked={tiers.includes(t.name)} disabled={off} onChange={(e) => toggle(tiers, setTiers, t.name, e.target.checked)} />
                <span>
                  <strong>{t.name}</strong>
                  {t.simulated ? <span className="tag sim">simulated · placeholder budgets</span> : <span className="tag">this computer · no budget</span>}
                  <small>{t.label}. {t.note}</small>
                  <dl className="tier-budgets">
                    <dt>CPU per row</dt><dd>{t.budgets.cpu_us_per_row == null ? "none" : `${Math.round(t.budgets.cpu_us_per_row)} µs`}</dd>
                    <dt>Deadline per row</dt><dd>{t.budgets.deadline_ms == null ? "none" : `${t.budgets.deadline_ms} ms`}</dd>
                    <dt>Model memory</dt><dd>{mib(t.budgets.model_memory_mib)}</dd>
                    <dt>Replacement model</dt><dd>{t.budgets.background_replacement ? "allowed" : "not allowed"}</dd>
                  </dl>
                </span>
              </label>
            ))}
          </div>
        </section>

        <section aria-label="Labels and arrival">
          <div className="setup-heading"><span className="step-number">04</span><h2>Labels and arrival</h2><ExplainButton id="labelDelay" /></div>
          <fieldset className="setup-fields" disabled={off}>
            <label className="field">Label delay (rows)
              <input type="number" min={0} step={1} value={labelDelay} onChange={(e) => setLabelDelay(Number(e.target.value))} />
              <small>{labelDelay === 0 ? "Each label arrives right after its prediction." : `Each label arrives ${labelDelay.toLocaleString()} rows after its prediction.`}</small>
            </label>
            <label className="field">Label coverage (%)
              <input type="number" min={1} max={100} step={1} value={coverage} onChange={(e) => setCoverage(Number(e.target.value))} />
              <small>{coverage >= 100 ? "Every row's label arrives." : `Only ${coverage} % of rows ever get their label (the same rows for every method).`}</small>
            </label>
            <label className="field"><span className="field-label">Arrival <ExplainButton id="arrivalRate" /></span>
              <select value={arrival} onChange={(e) => setArrival(e.target.value as "constant" | "recorded")}>
                <option value="constant">As fast as possible (tier's nominal rate)</option>
                <option value="recorded">Recorded rate × speed-up</option>
              </select>
            </label>
            {arrival === "recorded" && (
              <label className="field">Speed-up
                <select value={rateScale} onChange={(e) => setRateScale(Number(e.target.value))}>
                  {[1, 10, 100, 1000].map((x) => <option key={x} value={x}>× {x.toLocaleString()}</option>)}
                </select>
                <small>The CPU budget per row follows the recorded rate, so it shrinks during bursts.</small>
              </label>
            )}
          </fieldset>
        </section>

        <section aria-label="Joint controller">
          <div className="setup-heading"><span className="step-number">05</span><h2>Joint controller rules</h2>
            {!joint && <span className="tag">only used by the joint controller, which is not selected</span>}
          </div>
          <fieldset className="rule-options" disabled={off || !joint}>
            {options.rules.map((r) => (
              <label key={r.id}>
                <input type="checkbox" checked={rules.includes(r.id)} onChange={(e) => toggle(rules, setRules, r.id, e.target.checked)} />
                <span><strong>{r.id} · {r.title}</strong><small>{r.said}</small></span>
              </label>
            ))}
            <label>
              <input type="checkbox" checked={gating} onChange={(e) => setGating(e.target.checked)} />
              <span><strong>{options.resource_check.title}</strong><small>{options.resource_check.said}</small></span>
            </label>
          </fieldset>
          {joint && rules.length < ALL_RULES.length && <p className="small muted">Rules switched off: {ALL_RULES.filter((r) => !rules.includes(r)).join(", ")}. This is an ablation.</p>}
        </section>

        <section aria-label="Seeds and warm-up">
          <div className="setup-heading"><span className="step-number">06</span><h2>Seeds, warm-up and name</h2></div>
          <fieldset className="setup-fields" disabled={off}>
            <label className="field"><span className="field-label">Seeds <ExplainButton id="seed" /></span>
              <input type="text" value={seedText} onChange={(e) => setSeedText(e.target.value)} placeholder="11, 23, 37" />
              <small>Seeds change the randomised ensembles and which rows get labels under partial coverage. The row order never changes.</small>
            </label>
            <label className="field"><span className="field-label">Warm-up rows <ExplainButton id="warmup" /></span>
              <input type="number" min={1} step={1} value={warmup} onChange={(e) => setWarmup(Number(e.target.value))} />
              <small>Learned from, never scored.</small>
            </label>
            <label className="field" style={{ gridColumn: "1 / -1" }}>Run name
              <input type="text" value={name} placeholder={autoName} maxLength={120} onChange={(e) => setName(e.target.value)} />
            </label>
          </fieldset>
        </section>

        {large && (
          <div className="banner" role="note" style={{ marginTop: 18 }}>
            <div>
              <strong>This slice is {length.toLocaleString()} rows, more than {options.defaults.large_rows.toLocaleString()}.</strong>{" "}
              Estimated duration: {aboutDuration(seconds)} for {trials} trial{trials === 1 ? "" : "s"}. No other run can start until it
              finishes; it can be stopped after the current trial.
            </div>
          </div>
        )}
        {slow.length > 0 && (
          <p className="banner" role="note">
            {slow.map(methodLabel).join(" and ")} {slow.length === 1 ? "is" : "are"} very slow: roughly 5 ms per row, about 25 minutes per 300,000 rows for each tier and seed.
          </p>
        )}

        <div className="setup-footer">
          <div>
            <strong>{trials} trial{trials === 1 ? "" : "s"}, one at a time · {aboutDuration(seconds)}</strong>
            <p className="small muted">
              {methods.length} method{methods.length === 1 ? "" : "s"} × {tiers.length} tier{tiers.length === 1 ? "" : "s"} × {seeds.length} seed{seeds.length === 1 ? "" : "s"}.
              The estimate comes from earlier runs on an 8 GB Apple Silicon Mac and is only a guide.
            </p>
          </div>
          <button type="submit" className="btn primary" disabled={off || issues.length > 0 || !dataset.available}>{busy ? "Starting…" : "Run testbed experiment →"}</button>
        </div>
        {issues.length > 0 && <p className="small" role="status">{issues[0]}</p>}
        {disabled && !busy && <p className="small muted">Another run is in progress. Wait for it, or stop it, before starting this one.</p>}
        {problem && <div className="banner error" role="alert">{problem}</div>}
      </div>

      <aside className="dataset-brief">
        <div className="comparison-receipt" aria-live="polite">
          <span className="eyebrow">Your testbed run</span>
          <h3>{trials} isolated trial{trials === 1 ? "" : "s"}</h3>
          <dl>
            <dt>Rows</dt><dd>{sliceLabel} · {length.toLocaleString()} rows</dd>
            <dt>Methods</dt><dd>{methods.length ? methods.map(methodLabel).join(" · ") : "Choose at least one"}</dd>
            <dt>Tiers</dt><dd>{tiers.length ? tiers.map((t) => `${t}${options.tiers.find((o) => o.name === t)?.simulated ? " (simulated, placeholder budgets)" : ""}`).join(" · ") : "Choose at least one"}</dd>
            <dt>Labels</dt><dd>{labelDelay ? `${labelDelay.toLocaleString()} rows late` : "immediate"} · {pct(coverage / 100, 0)} of rows</dd>
            <dt>Arrival</dt><dd>{arrival === "recorded" ? `recorded rate × ${rateScale}` : "as fast as possible"}</dd>
            {joint && <><dt>Joint controller</dt><dd>{rules.length ? rules.join(", ") : "no rules"} · resource checks {gating ? "on" : "off"}</dd></>}
            <dt>Seeds · warm-up</dt><dd>{seeds.join(", ") || DASH} · {warmup.toLocaleString()} rows</dd>
          </dl>
          <div className="receipt-outcome">
            <strong>What is measured</strong>
            <p>Accuracy, κ-temporal, macro-F1, attack recall and false alarms, time per row split into cost terms, each attack period, and the controller's decisions.</p>
          </div>
        </div>
      </aside>
    </form>
  );
}
