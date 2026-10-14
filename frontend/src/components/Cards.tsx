/** "What happened?" — the drift episode told as a short timeline, and the pipeline's current
 *  decision. Both report measurements only; no card claims that anything improved or recovered. */

import type { CSSProperties } from "react";

import type { Extras, ResourceSample } from "../lib/api";
import type { Episode } from "../lib/derive";
import { DASH, pct, samples, us } from "../lib/format";
import { ExplainButton } from "./Explain";
import { EmptyState } from "./ui";

export function WhatHappenedCard({
  episode, preAccuracy, minAccuracy, postAccuracy, staticAccuracy, modelVersion, added,
}: {
  /** Set when the change was added to real data: which two columns were exchanged. */
  added?: { swap: [string, string] } | null;
  episode: Episode | undefined;
  preAccuracy: number | null;
  minAccuracy: number | null;
  postAccuracy: number | null;
  staticAccuracy: number | null;
  modelVersion: number | null;
}) {
  if (!episode) {
    return (
      <EmptyState
        title="No drift has happened yet"
        hint="When the data changes, this is where the story appears: when the change happened, when the detector noticed it, and what the pipeline did about it."
      />
    );
  }

  const items = [
    {
      kind: "drift",
      mark: "1",
      what: "The data changed",
      at: episode.driftIndex,
      says:
        episode.driftIndex == null
          ? "The stream is real data, so the exact moment of change is not known in advance."
          : added
            ? `From this row the columns ${added.swap[0]} and ${added.swap[1]} are exchanged. The rows and their labels are otherwise exactly as recorded.`
            : "The relationship between the inputs and the correct answer was switched at this point in the stream.",
      detail:
        episode.driftIndex == null
          ? undefined
          : added
            ? "This change was added on purpose, at a chosen row, which is what makes the detection delay measurable."
            : "Scheduled in advance, which is what makes the detection delay measurable.",
      explain: (added ? "injectedDrift" : "driftTrue") as "injectedDrift" | "driftTrue",
    },
    {
      kind: "detect",
      mark: "2",
      what: "The detector responded",
      at: episode.detectedAt,
      says:
        episode.detectedAt != null
          ? "ADWIN detected a sustained increase in the model's prediction errors."
          : "ADWIN has not yet confirmed a sustained increase in prediction errors.",
      detail:
        episode.delay != null
          ? `That is ${samples(episode.delay)} samples after the data actually changed.`
          : undefined,
      explain: "detectionDelay" as const,
    },
    {
      kind: episode.failed ? "pending" : "adapt",
      mark: "3",
      what: episode.failed ? "The model was kept" : "The model adapted",
      at: episode.adaptedAt,
      says: episode.failed
        ? "A replacement could not be promoted, so the existing model continued to make predictions."
        : episode.adaptedAt != null
          ? "A replacement model took over from the one that had learned the old relationship."
          : "A replacement model is training now, while the current model keeps making predictions.",
      detail:
        episode.trainedOn != null && episode.adaptedAt != null
          ? `The new model was trained on the ${samples(episode.trainedOn)} most recent samples from after the change${
              episode.samplesToPromotion != null ? `, ${samples(episode.samplesToPromotion)} samples after it was detected` : ""
            }.`
          : undefined,
      explain: "adaptation" as const,
    },
    {
      kind: "pending",
      mark: "4",
      what: "Watching what happens next",
      at: null,
      says: "We are now observing whether accuracy returns toward the level it held before the drift.",
      detail:
        modelVersion != null
          ? `Adaptive model · version ${modelVersion}. The recovery definition will be finalised by the research team.`
          : "The recovery definition will be finalised by the research team.",
      explain: "recovery" as const,
    },
  ];

  return (
    <div className="stack">
      <div className="timeline">
        {items.map((item, index) => (
          <div className={`timeline-item ${item.kind}`} key={item.mark} style={{ "--i": index } as CSSProperties}>
            <span className="marker" aria-hidden="true">{item.mark}</span>
            <div>
              <div className="what">
                {item.what}
                {item.at != null && <span className="at">sample {samples(item.at)}</span>}
                <ExplainButton id={item.explain} />
              </div>
              <div className="says">{item.says}</div>
              {item.detail && <div className="detail">{item.detail}</div>}
            </div>
          </div>
        ))}
      </div>

      <div className="compare-row">
        <div className="compare-cell">
          <div className="k">Accuracy before the drift</div>
          <div className="v">{pct(preAccuracy)}</div>
        </div>
        <div className="compare-cell">
          <div className="k">Lowest point after it</div>
          <div className="v">{pct(minAccuracy)}</div>
        </div>
        <div className="compare-cell">
          <div className="k">After adaptation</div>
          <div className="v">{pct(postAccuracy)}</div>
        </div>
      </div>
      {staticAccuracy != null && (
        <p className="tiny muted" style={{ margin: 0 }}>
          Over the same recent window, the static baseline measured <span className="mono">{pct(staticAccuracy)}</span>. These are
          windowed accuracy values for each pipeline; interpreting them belongs to the research workstream.
        </p>
      )}
    </div>
  );
}

export function DecisionCard({
  extras, resource, phase, constrained,
}: {
  extras: Extras["methods"][string] | undefined;
  resource: ResourceSample | undefined;
  phase: string;
  constrained: boolean;
}) {
  const governor = extras?.governor;
  const items: { tone: "ok" | "warn"; text: string; why?: string }[] = [];
  if (extras) {
    items.push(
      phase === "adapting"
        ? {
            tone: "warn",
            text: "Training a replacement model",
            why: `It has learned from ${samples(extras.replacement_trained ?? 0)} samples so far.`,
          }
        : { tone: "ok", text: `Continuing with the adaptive model · version ${extras.model_version}` },
    );
    items.push(
      extras.update_stride > 1
        ? {
            tone: "warn",
            text: `Learning from every ${extras.update_stride}${extras.update_stride === 2 ? "nd" : "th"} labelled sample`,
            why: "Some learning is being skipped to stay inside the simulated compute budget.",
          }
        : { tone: "ok", text: "Learning from every labelled sample" },
    );
    items.push(
      governor?.constrained
        ? {
            tone: "warn",
            text: `Using fewer features — ${extras.features.length} in use`,
            why: "Measured processing time went above the simulated budget.",
          }
        : { tone: "ok", text: `Keeping ${extras.features.length} selected features` },
    );
  }

  return (
    <div className="stack">
      <div className="card-rows">
        <div className="card-row">
          <span className="k">
            Processor use <ExplainButton id="cpuPerSample" />
          </span>
          <span className="v">{resource ? `${resource.cpu_percent.toFixed(0)} %` : DASH}</span>
        </div>
        <div className="card-row">
          <span className="k">
            Memory <ExplainButton id="rss" />
          </span>
          <span className="v">{resource ? `${resource.rss_mb.toFixed(0)} MB` : DASH}</span>
        </div>
        {governor && (
          <div className="card-row">
            <span className="k">
              Compute budget <ExplainButton id="budget" />
            </span>
            <span className="v">{us(governor.budget_us, 1)} / sample</span>
          </div>
        )}
      </div>
      {governor && (
        <div className={`meter${constrained ? " over" : ""}`} aria-hidden="true">
          <span style={{ width: constrained ? "100%" : "55%" }} />
        </div>
      )}
      <div className="decision">
        {items.map((item) => (
          <div className={`decision-item ${item.tone}`} key={item.text}>
            <span className="mark" aria-hidden="true">{item.tone === "ok" ? "✓" : "⚠"}</span>
            <span>
              {item.text}
              {item.why && <div className="why">{item.why}</div>}
            </span>
          </div>
        ))}
        {!extras && <div className="muted small">Waiting for the first update from the run…</div>}
      </div>
    </div>
  );
}
