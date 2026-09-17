/** The hero: the first thing anyone reads on the Live screen.
 *
 * It answers "what is happening right now?" in three layers — a state label, one large sentence in
 * plain English, and a supporting sentence — then shows the journey the run has taken so far, with
 * the sample index each stage happened at. Nothing here interprets the result; it reports it.
 */

import type { ReactNode } from "react";

import type { ExplainId } from "../lib/explain";
import { samples } from "../lib/format";
import { ExplainButton } from "./Explain";
import type { Phase } from "./ui";

export type PhaseStep = {
  key: string;
  label: string;
  /** The sample index this stage happened at, when it has happened. */
  at: number | null;
  state: "done" | "current" | "todo";
  tone?: "drift" | "detect" | "adapt";
};

const PHASE_LABEL: Record<Phase, string> = {
  idle: "Not running",
  stable: "Running — stable",
  drift: "Drift detected",
  adapting: "Adapting",
  recovery: "Monitoring recovery",
};

export default function HeroStory({
  phase, headline, sentence, steps, meta, explain, live,
}: {
  phase: Phase;
  headline: string;
  sentence: string;
  steps?: PhaseStep[];
  meta?: ReactNode;
  explain?: ExplainId;
  live?: boolean;
}) {
  return (
    <section className={`hero ${phase}`} aria-live="polite">
      <div className="hero-top">
        <div style={{ minWidth: 0 }}>
          <span className={`hero-label${live ? " live" : ""}`}>
            <span className="dot" aria-hidden="true" />
            {PHASE_LABEL[phase]}
          </span>
          <h1>
            {headline}
            {explain && <ExplainButton id={explain} />}
          </h1>
          <p className="hero-said">{sentence}</p>
        </div>
        {meta && <div className="hero-meta">{meta}</div>}
      </div>

      {steps && steps.length > 0 && (
        <div className="phase-track" role="list" aria-label="Progress of this run">
          {steps.map((step, index) => (
            <div key={step.key} style={{ display: "contents" }}>
              {index > 0 && <span className="phase-arrow" aria-hidden="true">→</span>}
              <div className={`phase-node ${step.state} ${step.tone ?? ""}`} role="listitem">
                <span className="chip">{step.label}</span>
                <span className="at">{step.at != null ? `sample ${samples(step.at)}` : "—"}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
