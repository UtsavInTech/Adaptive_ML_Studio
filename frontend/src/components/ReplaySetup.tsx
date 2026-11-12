/** Set up a run on a real dataset: which data, how it changes, how it is scored, which methods.
 *
 *  The second step is the one that makes before / during / after scores possible. Real data drifts
 *  on its own but nobody has marked where, so a run can either replay the rows untouched, or add
 *  one controlled change at a known row. The form says plainly which of the two it is about to do.
 */

import { useEffect, useMemo, useState } from "react";

import { api, type Dataset, type DriftKind, type DriftKinds } from "../lib/api";
import { methodLabel } from "../lib/format";
import { href } from "../lib/router";
import DriftShape from "./DriftShape";
import { ExplainButton } from "./Explain";

const METHODS: Record<string, string> = {
  static: "Learns once from the warm-up rows, then never changes",
  incremental: "Keeps learning from every row, but never checks for drift",
  adaptive: "Keeps learning, watches its own errors, and replaces the model when they rise",
  arf: "Ten trees that each watch for drift and are replaced one at a time",
};

type Change = DriftKind | "none";

const EXPLAIN = { abrupt: "driftAbrupt", gradual: "driftGradual", incremental: "driftIncremental", recurring: "driftRecurring" } as const;

type Props = {
  experiment?: boolean;
  disabled: boolean;
  onStart: (config: Record<string, unknown>, name: string) => Promise<void>;
};

/** "about 21 days", "about 17 hours" — what a number of rows means in the data's own time. */
function duration(rows: number, rowSeconds: number | undefined): string | null {
  if (!rowSeconds || rows <= 0) return null;
  const hours = (rows * rowSeconds) / 3600;
  if (hours < 1) return `about ${Math.round(hours * 60)} minutes`;
  if (hours < 48) return `about ${Math.round(hours)} hours`;
  return `about ${Math.round(hours / 24)} days`;
}

const whole = (value: number) => Number.isInteger(value);

export default function ReplaySetup({ experiment = false, disabled, onStart }: Props) {
  const [step, setStep] = useState(0);
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [kinds, setKinds] = useState<DriftKinds | null>(null);
  const [selected, setSelected] = useState("");
  const [length, setLength] = useState(12000);
  const [warmup, setWarmup] = useState(1000);
  const [change, setChange] = useState<Change>("abrupt");
  const [start, setStart] = useState(6000);
  const [width, setWidth] = useState(2000);
  const [period, setPeriod] = useState(4000);
  const [swap, setSwap] = useState<[string, string]>(["", ""]);
  const [control, setControl] = useState(true);
  const [methods, setMethods] = useState(experiment ? Object.keys(METHODS) : ["static", "adaptive"]);
  const [profile, setProfile] = useState("standard");
  const [repeats, setRepeats] = useState(1);
  const [rate, setRate] = useState(1000);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [large, setLarge] = useState<Dataset[]>([]);

  /** Defaults follow the dataset: the whole file for a comparison, a warm-up that covers a full
   *  cycle of the data, and a change in the middle of what will be replayed. */
  const choose = (d: Dataset) => {
    const rows = experiment ? d.rows : Math.min(12000, d.rows);
    setSelected(d.id);
    setLength(rows);
    setWarmup(Math.min(d.recommended_warmup ?? 1000, rows - 1));
    setStart(Math.max(1000, Math.floor(rows / 2 / 1000) * 1000));
    setSwap(d.drift_injection?.swap ?? [d.features[0], d.features[1]]);
  };

  const load = () => {
    setProblem(null);
    api.driftKinds().then(setKinds).catch(() => {});
    api.datasets().then((all) => {
      // Large streaming datasets have real, dated changes and refuse the column exchange offered here.
      // They are run from the Testbed page instead.
      const data = all.filter((d) => !d.streaming);
      setLarge(all.filter((d) => d.streaming));
      setDatasets(data);
      const first = data.find((d) => d.available);
      if (first) choose(first);
    }).catch((e) => setProblem(e.message));
  };
  useEffect(load, []);

  const dataset = datasets?.find((d) => d.id === selected);
  const injected = change !== "none";
  const takes = change === "gradual" || change === "incremental" ? width : 1;
  const end = start + takes;
  const phases = kinds?.phases ?? { before: 2000, settle: 1000, after: 2000 };

  const issues = useMemo(() => {
    const out: string[] = [];
    if (!dataset) return out;
    if (!whole(length) || length > dataset.rows || length < 2) out.push(`Replay between 2 and ${dataset.rows.toLocaleString()} rows.`);
    if (!whole(warmup) || warmup < 1 || warmup >= length) out.push("The warm-up must be shorter than the replay.");
    if (methods.length === 0) out.push("Choose at least one method.");
    if (injected) {
      if (!whole(start) || start <= warmup) out.push("The change must start after the warm-up.");
      if (!whole(takes) || end >= length) out.push("The change must be complete before the replay ends.");
      if ((change === "gradual" || change === "incremental") && width < 2) out.push("A gradual or incremental change needs at least 2 rows.");
      if (change === "recurring" && (!whole(period) || period < 1)) out.push("Choose how many rows each arrangement lasts.");
      if (swap[0] === swap[1]) out.push("Choose two different columns to exchange.");
    }
    return out;
  }, [dataset, length, warmup, methods.length, injected, start, takes, end, change, width, period, swap]);
  const valid = !!dataset?.available && issues.length === 0;

  const withControl = experiment && injected && control;
  const trialCount = methods.length * repeats * (profile === "both" ? 2 : 1) * (withControl ? 2 : 1);
  const kindCopy = injected ? kinds?.kinds[change] : undefined;

  /** One sentence saying exactly what will be done to the data. */
  const summary = !injected
    ? "The rows are replayed exactly as recorded. Nothing is changed."
    : change === "abrupt"
      ? `From row ${start.toLocaleString()} onward, the columns ${swap[0]} and ${swap[1]} are exchanged, all at once.`
      : change === "gradual"
        ? `Between rows ${start.toLocaleString()} and ${end.toLocaleString()}, more and more rows have ${swap[0]} and ${swap[1]} exchanged. After that, every row does.`
        : change === "incremental"
          ? `Between rows ${start.toLocaleString()} and ${end.toLocaleString()}, ${swap[0]} and ${swap[1]} drift steadily into each other's place, a little more with every row.`
          : `From row ${start.toLocaleString()}, ${swap[0]} and ${swap[1]} are exchanged for ${period.toLocaleString()} rows, restored for ${period.toLocaleString()}, and so on.`;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (experiment && step < 2) { setStep(step + 1); return; }
    if (!valid || !dataset) return;
    setBusy(true); setProblem(null);
    const what = injected ? `${kindCopy?.label.toLowerCase() ?? change} drift` : "natural replay";
    const name = `${dataset.name} · ${what}${experiment ? " · method comparison" : ""}`;
    const injection = injected
      ? { kind: change, start, width: takes, swap, ...(change === "recurring" ? { period } : {}) }
      : undefined;
    const base = {
      seed: 42, methods,
      stream: {
        scenario: "csv", dataset: dataset.id, dataset_sha256: dataset.sha256, length, noise: 0,
        rate: experiment || rate === 0 ? null : rate, ...(injection ? { injection } : {}),
      },
      evaluation: { warmup, block_size: 100 },
    };
    const config = experiment
      ? {
          name, base, control: withControl,
          profiles: profile === "both" ? ["standard", "edge_sim"] : [profile],
          seeds: Array.from({ length: repeats }, (_, i) => 42 + i),
        }
      : { ...base, profile };
    try { await onStart(config, name); } catch (e) { setProblem((e as Error).message); } finally { setBusy(false); }
  };

  const off = disabled || busy;
  const share = (rows: number) => `${Math.max(0, (rows / Math.max(length, 1)) * 100)}%`;
  const beforeFrom = Math.max(warmup, start - phases.before);
  const duringTo = Math.min(length, end + phases.settle);
  const afterTo = Math.min(length, duringTo + phases.after);

  return (
    <form className={`replay-setup${experiment ? " comparison-setup" : ""}`} noValidate={experiment} onSubmit={(event) => void submit(event)}>
      <div className="replay-main">
        {experiment && <>
          <div className="setup-intro"><span className="eyebrow">New comparison</span><h2>Can your model keep up with change?</h2><p>Use the same data to see how each learning strategy responds, and what it costs.</p></div>
          <nav className="setup-steps" aria-label="Comparison setup">
            {[{ title: "Dataset", detail: dataset?.name ?? "Choose your data" }, { title: "Data change", detail: injected ? kindCopy?.label ?? change : "Natural replay" }, { title: "Methods & run", detail: `${methods.length} methods · ${trialCount} trials` }].map((item, index) =>
              <button type="button" key={item.title} aria-current={step === index ? "step" : undefined} onClick={() => setStep(index)}>
                <span className="setup-step-index">{String(index + 1).padStart(2, "0")}</span><span><strong>{item.title}</strong><small>{item.detail}</small></span>
              </button>)}
          </nav>
        </>}
        <section hidden={experiment && step !== 0} aria-label="Dataset selection">
        <div className="setup-heading"><span className="step-number">01</span><h2>Choose your dataset</h2><span className="tag">Kaggle · local snapshots</span></div>
        {datasets === null && !problem && <p role="status">Loading datasets…</p>}
        {datasets?.length === 0 && <p>No dataset snapshots installed yet. Add a verified file to the dataset catalog.</p>}
        {large.length > 0 && (
          <p className="small muted" style={{ marginTop: -8 }}>
            {large.map((d) => d.name).join(", ")} {large.length === 1 ? "is" : "are"} too large for this form and {large.length === 1 ? "has" : "have"} real,
            dated attacks instead of an added change. <a href={href({ page: "testbed" })}>Run it on the Testbed page →</a>
          </p>
        )}
        <div className="dataset-options">
          {datasets?.map((d) => (
            <label key={d.id} className={`dataset-option ${selected === d.id ? "selected" : ""}`}>
              <input type="radio" name="dataset" value={d.id} checked={selected === d.id} disabled={off || !d.available} onChange={() => choose(d)} />
              <span>
                <strong>{d.name}</strong>
                <span>{d.rows.toLocaleString()} rows · {d.features.length} input columns{!d.available ? " · file missing" : ""}</span>
                {d.span && <span>{d.span}</span>}
              </span>
            </label>
          ))}
        </div>

        </section>
        <section hidden={experiment && step !== 1} aria-label="Data change">
        {experiment && <p className="step-context">Introduce a known change to measure recovery, or keep the original data to observe natural drift.</p>}
        <div className="setup-heading">
          <span className="step-number">02</span><h2>Choose how the data changes</h2>
          <ExplainButton id="injectedDrift" variant="text" label="Why add a change?" />
        </div>
        <div className="change-options" role="radiogroup" aria-label="How the data changes">
          <label className={`change-option ${change === "none" ? "selected" : ""}`}>
            <input type="radio" name="change" checked={change === "none"} disabled={off} onChange={() => setChange("none")} />
            <DriftShape kind="none" />
            <strong>No added change</strong>
            <small>Replay the rows as recorded. Real data drifts on its own, but nobody has marked where.</small>
          </label>
          {(Object.keys(EXPLAIN) as DriftKind[]).map((kind) => (
            <label key={kind} className={`change-option ${change === kind ? "selected" : ""}`}>
              <input type="radio" name="change" checked={change === kind} disabled={off} onChange={() => setChange(kind)} />
              <DriftShape kind={kind} />
              <strong>{kinds?.kinds[kind].label ?? kind}</strong>
              <small>{kinds?.kinds[kind].said ?? ""}</small>
            </label>
          ))}
        </div>
        <div className={`change-summary ${injected ? "injected" : ""}`} aria-live="polite">
          <p>
            <strong>{injected ? "What will be done to the data: " : "Nothing is added: "}</strong>{summary}
            {injected && <ExplainButton id={EXPLAIN[change as DriftKind]} />}
          </p>
          {kindCopy && <p className="small muted">In real life: {kindCopy.example}</p>}
          {!injected && (
            <p className="small muted">
              Because the position of the data's own drift is unknown, accuracy before and after it cannot be measured in this
              mode. Detector alerts are still counted. <ExplainButton id="naturalReplay" />
            </p>
          )}
          {injected && dataset && (
            <details className="change-advanced">
              <summary>Adjust the change</summary>
              <fieldset disabled={off} className="setup-fields">
                <label className="field">First changed row
                  <input type="number" min={warmup + 1} max={length - 2} step={1} value={start} onChange={(e) => setStart(Number(e.target.value))} required />
                </label>
                {(change === "gradual" || change === "incremental") && (
                  <label className="field">Rows the change takes
                    <input type="number" min={2} max={length - start - 1} step={1} value={width} onChange={(e) => setWidth(Number(e.target.value))} required />
                  </label>
                )}
                {change === "recurring" && (
                  <label className="field">Rows before it switches back
                    <input type="number" min={1} step={1} value={period} onChange={(e) => setPeriod(Number(e.target.value))} required />
                  </label>
                )}
                <label className="field">Column exchanged
                  <select value={swap[0]} onChange={(e) => setSwap([e.target.value, swap[1]])}>{dataset.features.map((f) => <option key={f}>{f}</option>)}</select>
                </label>
                <label className="field">with column
                  <select value={swap[1]} onChange={(e) => setSwap([swap[0], e.target.value])}>{dataset.features.map((f) => <option key={f}>{f}</option>)}</select>
                </label>
              </fieldset>
              {dataset.drift_injection && (
                <p className="small muted">
                  Default columns: {dataset.drift_injection.swap.join(" and ")} — {dataset.drift_injection.rule}. The rows, their
                  order and their labels are never altered.
                </p>
              )}
            </details>
          )}
        </div>

        </section>
        <section hidden={experiment && step !== 2} aria-label="Methods and evaluation">
        {experiment && <p className="step-context">Choose the learning strategies to compare. Each runs separately so its processing cost can be measured fairly.</p>}
        <div className="setup-heading"><span className="step-number">03</span><h2>Set the evaluation</h2></div>
        <fieldset disabled={off} className="setup-fields">
          <label className="field">Rows to replay
            <input type="number" min={2} max={dataset?.rows} step={1} value={length} onChange={(e) => setLength(Number(e.target.value))} required />
            {dataset && duration(length, dataset.row_seconds) && <small>{duration(length, dataset.row_seconds)} of data</small>}
          </label>
          <label className="field"><span className="field-label">Warm-up rows <ExplainButton id="warmup" /></span>
            <input type="number" min={1} max={length - 1} step={1} value={warmup} onChange={(e) => setWarmup(Number(e.target.value))} required />
            {dataset && duration(warmup, dataset.row_seconds) && <small>{duration(warmup, dataset.row_seconds)} of data, used for learning only</small>}
          </label>
          <label className="field">Resource profile
            <select value={profile} onChange={(e) => setProfile(e.target.value)}>
              <option value="standard">Standard · this computer</option><option value="edge_sim">Simulated edge · software budgets</option>
              {experiment && <option value="both">Compare standard + simulated edge</option>}
            </select>
          </label>
          {experiment ? (
            <label className="field">Model seeds
              <select value={repeats} onChange={(e) => setRepeats(Number(e.target.value))}>
                <option value={1}>One · 42</option><option value={3}>Three · 42, 43, 44</option>
              </select>
            </label>
          ) : (
            <label className="field">Replay speed
              <select value={rate} onChange={(e) => setRate(Number(e.target.value))}>
                <option value={500}>500 rows / second</option><option value={1000}>1,000 rows / second</option><option value={0}>Maximum speed</option>
              </select>
            </label>
          )}
        </fieldset>
        {dataset?.warmup_reason && dataset.recommended_warmup !== 1000 && (
          <p className="small muted" style={{ marginTop: 10 }}>Why {dataset.recommended_warmup?.toLocaleString()} warm-up rows here: {dataset.warmup_reason}</p>
        )}

        {experiment ? (
          <fieldset className="method-options" disabled={off}><legend>Methods to compare</legend>
            {Object.entries(METHODS).map(([key, help]) => (
              <label key={key}>
                <input type="checkbox" checked={methods.includes(key)} onChange={(e) => setMethods(e.target.checked ? [...methods, key] : methods.filter((m) => m !== key))} />
                <span><strong>{methodLabel(key)}</strong><small>{help}</small></span>
              </label>
            ))}
          </fieldset>
        ) : <p className="small muted" style={{ marginTop: 16 }}>The static baseline and the adaptive pipeline run side by side as each row arrives.</p>}

        {experiment && injected && (
          <label className="control-option">
            <input type="checkbox" checked={control} disabled={off} onChange={(e) => setControl(e.target.checked)} />
            <span>
              <strong>Also run every method on the untouched rows</strong> <ExplainButton id="controlRun" />
              <small>A control. It shows how much of a drop comes from the added change rather than from the data's own drift. Doubles the number of trials.</small>
            </span>
          </label>
        )}

        <div className="run-map" aria-label="How the rows are used">
          <div className="run-map-bar">
            <span className="seg warm" style={{ width: share(warmup) }} title="warm-up" />
            {injected ? (
              <>
                <span className="seg scored" style={{ width: share(beforeFrom - warmup) }} />
                <span className="seg before" style={{ width: share(start - beforeFrom) }} title="before" />
                <span className="seg during" style={{ width: share(duringTo - start) }} title="during" />
                <span className="seg after" style={{ width: share(afterTo - duringTo) }} title="after" />
                <span className="seg scored" style={{ width: share(length - afterTo) }} />
              </>
            ) : <span className="seg scored" style={{ width: share(length - warmup) }} />}
          </div>
          <div className="run-map-key">
            <span><i className="seg warm" /> <strong>{warmup.toLocaleString()}</strong> warm-up rows: learn only</span>
            {injected ? (
              <>
                <span><i className="seg before" /> before: rows <strong>{beforeFrom.toLocaleString()}–{start.toLocaleString()}</strong></span>
                <span><i className="seg during" /> during: <strong>{start.toLocaleString()}–{duringTo.toLocaleString()}</strong></span>
                <span><i className="seg after" /> after: <strong>{duringTo.toLocaleString()}–{afterTo.toLocaleString()}</strong></span>
              </>
            ) : <span><i className="seg scored" /> <strong>{Math.max(0, length - warmup).toLocaleString()}</strong> scored rows: predict first, then learn</span>}
            {injected && <ExplainButton id="phases" />}
          </div>
        </div>

        </section>
        {experiment && step < 2 && <div className="setup-navigation">
          <span className="small muted">Step {step + 1} of 3 · {step === 0 ? "Start with a verified dataset" : "Choose the change to investigate"}</span>
          <div className="row" style={{ gap: 10 }}>{step > 0 && <button type="button" className="btn" onClick={() => setStep(step - 1)}>Back</button>}
          <button type="button" className="btn primary" disabled={!dataset?.available} onClick={() => setStep(step + 1)}>{step === 0 ? "Continue to data change" : "Continue to methods"} →</button></div>
        </div>}
        <div className="setup-footer" hidden={experiment && step !== 2}>
          <div>
            <strong>{experiment ? `${trialCount} trials, one at a time` : "One replay · two methods"}</strong>
            <p className="small muted">
              {experiment
                ? withControl
                  ? `${methods.length} method${methods.length === 1 ? "" : "s"}, each run once with the change and once without. Every trial sees the same rows in the same order.`
                  : "Every method sees the same rows in the same order. Results are saved automatically."
                : "Watch what each method does as the rows arrive. Use Experiments for timing comparisons."}
            </p>
          </div>
          {experiment && <button type="button" className="btn" onClick={() => setStep(1)}>Back</button>}
          <button type="submit" className="btn primary" disabled={off || !valid}>{busy ? "Starting…" : experiment ? "Run comparison →" : "Start dataset replay →"}</button>
        </div>
        {issues.length > 0 && dataset && <p className="small" role="status">{issues[0]}</p>}
        {problem && <div className="banner error" role="alert">{problem}{datasets === null && <button type="button" className="btn small" onClick={load}>Retry</button>}</div>}
      </div>

      <aside className="dataset-brief">
        {experiment && <div className="comparison-receipt" aria-live="polite">
          <span className="eyebrow">Your experiment</span>
          <h3>{trialCount} isolated trials</h3>
          <p>Same rows. Same order. A fair comparison.</p>
          <dl><dt>Learning strategies</dt><dd>{methods.length ? methods.map(methodLabel).join(" · ") : "Choose at least one method"}</dd>
          <dt>Data change</dt><dd>{injected ? `${kindCopy?.label ?? change} at row ${start.toLocaleString()}` : "No added change"}</dd>
          <dt>Comparison baseline</dt><dd>{withControl ? "Changed + untouched data" : "No separate control"}</dd>
          <dt>Trial calculation</dt><dd>{methods.length} methods × {repeats} seed{repeats === 1 ? "" : "s"} × {profile === "both" ? 2 : 1} profile{profile === "both" ? "s" : ""}{withControl ? " × 2 data conditions" : ""}</dd></dl>
          <div className="receipt-outcome"><strong>What you’ll learn</strong><p>Compare prediction accuracy, recovery after change, and the computation each strategy needs.</p></div>
        </div>}
        <details className="dataset-context" open={!experiment}><summary>About this dataset</summary>
        <span className="eyebrow">Dataset notes</span><h3>{dataset?.name ?? "Real data, repeatable runs"}</h3>
        <p>{dataset?.description ?? "Choose a local Kaggle snapshot to replay."}</p>
        {dataset && (
          <>
            <dl>
              <dt>What is predicted</dt><dd>{dataset.target} · positive class {Object.entries(dataset.labels).find(([, v]) => v === 1)?.[0]}</dd>
              {dataset.span && <><dt>Period covered</dt><dd>{dataset.span}</dd></>}
              <dt>Order</dt><dd>{dataset.order}</dd>
              <dt>Where the data's own drift is</dt><dd>Not marked by anyone</dd>
              <dt>Added change in this run</dt><dd>{injected ? `${kindCopy?.label ?? change}, at a known row` : "None"}</dd>
            </dl>
            <p className="small">{dataset.notes}</p><a href={dataset.source} target="_blank" rel="noreferrer">View source on Kaggle ↗</a>
            <details><summary>Snapshot & input columns</summary><p>{dataset.features.join(", ")}</p><p>{dataset.license} · downloaded {dataset.downloaded}</p><code className="dataset-hash">SHA-256 {dataset.sha256}</code></details>
          </>
        )}
        </details>
      </aside>
    </form>
  );
}
