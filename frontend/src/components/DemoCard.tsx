/** Demo narration. Every caption is driven by a real event or a measured value — never by a timer. */

import type { ExplainId } from "../lib/explain";
import { samples } from "../lib/format";
import { ExplainButton } from "./Explain";

export default function DemoCard({
  index, total, title, text, sample, explain,
}: {
  index: number;
  total: number;
  title: string;
  text: string;
  sample?: number | null;
  explain?: ExplainId;
}) {
  return (
    <section className="demo-card" aria-live="polite">
      <div className="stack tight" style={{ gap: 4 }}>
        <span className="step-badge">Step {index + 1} of {total}</span>
        <div className="demo-progress" aria-hidden="true">
          {Array.from({ length: total }, (_, i) => (
            <i key={i} className={i <= index ? "done" : ""} />
          ))}
        </div>
      </div>
      <div className="stack tight" style={{ gap: 2, minWidth: 0 }}>
        <div className="demo-title">{title}</div>
        <div className="demo-text">{text}</div>
      </div>
      <div className="spacer" />
      {sample != null && (
        <div className="stack tight" style={{ gap: 0, textAlign: "right" }}>
          <span className="tiny muted">at sample</span>
          <span className="demo-sample">{samples(sample)}</span>
        </div>
      )}
      {explain && <ExplainButton id={explain} variant="text" label="Why this matters" />}
    </section>
  );
}
