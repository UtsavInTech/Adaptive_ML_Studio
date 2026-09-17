/** The pipeline as a flow rather than a row of equal cards.
 *
 *  Every sample walks the main path left to right, in the order the engine actually runs it
 *  (`STAGE_NAMES` in the pipeline module): preprocess → select → predict → detect → learn. Adaptation
 *  hangs off the drift check as a branch, because that is what it is — a step that only runs when a
 *  change has been confirmed, while prediction carries on regardless.
 *
 *  Selecting a step opens what it does, how this project implements it, what it measured, and which
 *  paper reference and research gap it belongs to.
 */

import type { BlockRecord, Extras } from "../lib/api";
import type { ExplainId } from "../lib/explain";
import { us } from "../lib/format";
import { ExplainButton } from "./Explain";
import { Field } from "./ui";

export type StageKey = "stream" | "preprocess" | "select" | "predict" | "detect" | "adapt" | "update" | "monitor";

type Stage = {
  key: StageKey;
  label: string;
  /** The block field holding this step's measured time, when the engine times it separately. */
  timing?: string;
  explain?: ExplainId;
  does: string;
  technique: string;
  reference?: string;
  gaps: string;
};

const STAGES: Stage[] = [
  {
    key: "stream",
    label: "Data stream",
    does: "Produces the samples, one at a time, with a concept change scheduled at a known position.",
    technique: "SEA concepts generator with a sigmoid concept transition, placed by sample index",
    gaps: "G1",
  },
  {
    key: "preprocess",
    label: "Preprocessing",
    timing: "preprocess_mean_ns",
    does: "Fills in missing values, puts features on a comparable scale, and limits extreme values.",
    technique: "Running-mean imputation → exponentially weighted standardisation → clipping at 5σ",
    reference: "[3], [17], [19]",
    gaps: "G1",
  },
  {
    key: "select",
    label: "Feature selection",
    timing: "select_mean_ns",
    explain: "featureSelection",
    does: "Keeps the most useful features so the model does less work per sample.",
    technique: "Rank by |weight| of an online linear model, keep the top k (truncation step of OFS)",
    reference: "[4], [16]",
    gaps: "G1, G2",
  },
  {
    key: "predict",
    label: "Prediction",
    timing: "predict_mean_ns",
    explain: "prequential",
    does: "Predicts the label of each incoming sample before its true label is known.",
    technique: "Hoeffding tree (River), prequential test-then-train",
    reference: "[10], [18]",
    gaps: "G1",
  },
  {
    key: "detect",
    label: "Drift check",
    timing: "detect_mean_ns",
    explain: "adwin",
    does: "Compares the prediction with the true label and watches that error stream for a sustained change.",
    technique: "ADWIN on the 0/1 error stream — a sensitive detector warns, a strict one confirms",
    reference: "[5]",
    gaps: "G1, G3",
  },
  {
    key: "adapt",
    label: "Model adaptation",
    timing: "adapt_mean_ns",
    explain: "adaptation",
    does: "Runs only when drift is confirmed: prepares a replacement model and promotes it when ready.",
    technique: "A replacement trains on post-warning samples while the current model keeps serving predictions",
    reference: "§VI options; background learners as in [20]",
    gaps: "G1, G2, G5",
  },
  {
    key: "update",
    label: "Learning",
    timing: "update_mean_ns",
    explain: "incremental",
    does: "Learns from the labelled sample, so the model keeps up with the stream between drifts.",
    technique: "Incremental update of the active model; a resource governor may raise the update stride",
    reference: "[10], [18]",
    gaps: "G1, G5",
  },
  {
    key: "monitor",
    label: "Monitoring",
    explain: "monitor",
    does: "Records accuracy, timing and resource use, and reports its own cost separately.",
    technique: "Per-stage timing per sample; CPU and memory sampled from outside the engine process",
    reference: "§VI metrics",
    gaps: "G2, G3",
  },
];

const MAIN: StageKey[] = ["stream", "preprocess", "select", "predict", "detect", "update", "monitor"];

type Props = {
  block?: BlockRecord;
  extras: Extras["methods"][string] | undefined;
  streamDetail: string;
  monitorUs: number | null;
  phase: string;
  selected: StageKey | null;
  onSelect: (key: StageKey | null) => void;
  config: any;
};

export default function PipelineFlow({ block, extras, streamDetail, monitorUs, phase, selected, onSelect, config }: Props) {
  const stage = (key: StageKey) => STAGES.find((s) => s.key === key)!;

  const detail = (key: StageKey): string => {
    switch (key) {
      case "stream":
        return streamDetail;
      case "preprocess":
        return "impute → scale → clip";
      case "select":
        return extras ? `${extras.features.length} of ${extras.ranking.length} features kept` : "—";
      case "predict":
        return extras ? `model v${extras.model_version}` : "—";
      case "detect":
        return extras?.detector ? `watching ${Math.round(extras.detector.width).toLocaleString()} recent samples` : "not used";
      case "adapt":
        if (extras?.adapting) return `preparing a replacement · ${extras.replacement_trained ?? 0} samples`;
        return phase === "recovery" ? "replacement promoted" : "idle — no drift confirmed";
      case "update":
        if (!extras) return "—";
        return extras.update_stride > 1 ? `every ${extras.update_stride}th labelled sample` : "every labelled sample";
      case "monitor":
        return monitorUs != null ? "recording measurements" : "—";
    }
  };

  const time = (key: StageKey): string => {
    const definition = stage(key);
    if (key === "monitor") return monitorUs != null ? us(monitorUs, 2) : "";
    if (!definition.timing || !block) return "";
    const value = block[definition.timing];
    // A conditional step that did not run in this block has no measured cost; "0.00 µs" would read as
    // a measurement of something that never happened.
    if (typeof value !== "number" || value === 0) return "";
    return us(value / 1000, 2);
  };

  const tone = (key: StageKey): string => {
    if (key === "adapt") return extras?.adapting || phase === "adapting" ? "alert" : extras ? "idle" : "";
    if (key === "detect" && phase === "drift") return "alert";
    if (key === "select" && extras?.governor?.constrained) return "alert";
    return block ? "active" : "";
  };

  const node = (key: StageKey, index: number | null) => {
    const definition = stage(key);
    return (
      <div className={`flow-node-wrap${key === "adapt" ? " branch" : ""}`} key={key}>
        <button
          type="button"
          className={`flow-node ${tone(key)}`}
          aria-pressed={selected === key}
          onClick={() => onSelect(selected === key ? null : key)}
        >
          <span className="flow-node-head">
            {index != null && (
              <span className="flow-node-no" aria-hidden="true">
                {index}
              </span>
            )}
            <span className="flow-node-name">{definition.label}</span>
          </span>
          <span className="flow-node-detail">{detail(key)}</span>
          <span className="flow-node-time mono">{time(key)}</span>
        </button>
        {definition.explain && (
          <span className="flow-node-explain">
            <ExplainButton id={definition.explain} />
          </span>
        )}
      </div>
    );
  };

  const open = STAGES.find((s) => s.key === selected);

  return (
    <div className="stack tight">
      <div className="flowchart" role="group" aria-label="Pipeline stages">
        {MAIN.slice(0, 5).map((key, index) => node(key, index + 1))}
        <div className="flow-branch">
          <span className="flow-branch-label" aria-hidden="true">
            if drift is confirmed
          </span>
          {node("adapt", 6)}
          <span className="flow-branch-note">Prediction continues while the replacement is prepared.</span>
        </div>
        {MAIN.slice(5).map((key, index) => node(key, index + 7))}
      </div>

      {open && (
        <div className="panel">
          <div className="panel-head">
            <h2>{open.label}</h2>
            <span className="sub">{open.key === "adapt" ? "conditional step" : "step on the main path"}</span>
            <div className="spacer" />
            <button type="button" className="btn small" onClick={() => onSelect(null)}>
              Close
            </button>
          </div>
          <div className="panel-body">
            <div className="stage-detail">
              <Field k="What it does">{open.does}</Field>
              <Field k="How this project implements it">{open.technique}</Field>
              <Field k="Measured cost">
                {time(open.key) || "—"}
                {open.key === "monitor" && <span className="muted"> · reported separately from prediction time</span>}
              </Field>
              {open.reference && <Field k="Paper reference">{open.reference}</Field>}
              <Field k="Research gap">{open.gaps}</Field>
              {open.key === "select" && extras && (
                <Field k="Feature relevance">
                  <span className="chips">
                    {extras.ranking.map(([feature, weight]) => (
                      <span key={feature} className={`chip${extras.features.includes(feature) ? "" : " dropped"}`}>
                        {feature} · {weight.toFixed(3)}
                      </span>
                    ))}
                  </span>
                </Field>
              )}
              {open.key === "detect" && config && (
                <Field k="Settings">
                  ADWIN δ = {config.pipeline.detector.delta_drift} (warning δ = {config.pipeline.detector.delta_warning}),
                  checked every {config.pipeline.detector.clock} samples
                </Field>
              )}
              {open.key === "adapt" && config && (
                <Field k="Settings">
                  {config.pipeline.adaptation.allow_background
                    ? `replacement promoted after ${config.pipeline.adaptation.background_min_samples} samples`
                    : "background models disallowed by the profile — the model is reset instead"}
                  , cooldown {config.pipeline.adaptation.cooldown} samples
                </Field>
              )}
              {open.key === "stream" && config && (
                <Field k="Settings">
                  seed {config.seed} · {config.stream.length.toLocaleString()} samples · label noise{" "}
                  {(config.stream.noise * 100).toFixed(0)} %
                </Field>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
