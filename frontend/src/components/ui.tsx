/** Shared building blocks. Every explanation goes through ExplainButton, so the interaction is
 *  identical everywhere and nothing re-implements popover behaviour. */

import type { ReactNode } from "react";

import type { ExplainId } from "../lib/explain";
import { ExplainButton } from "./Explain";

export function SectionHead({ title, hint, explain }: { title: string; hint?: string; explain?: ExplainId }) {
  return (
    <div className="section-head">
      <h2>{title}</h2>
      {explain && <ExplainButton id={explain} />}
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function Panel({
  title, sub, explain, actions, children, bodyClass,
}: {
  title?: ReactNode;
  sub?: string;
  explain?: ExplainId;
  actions?: ReactNode;
  children: ReactNode;
  bodyClass?: string;
}) {
  return (
    <section className="panel">
      {(title || actions) && (
        <header className="panel-head">
          <h2>
            {title}
            {explain && <ExplainButton id={explain} />}
          </h2>
          {sub && <span className="sub">{sub}</span>}
          <div className="spacer" />
          {actions}
        </header>
      )}
      <div className={`panel-body ${bodyClass ?? ""}`}>{children}</div>
    </section>
  );
}

export function Badge({
  tone = "idle", children, pulse,
}: { tone?: "ok" | "info" | "warn" | "error" | "idle"; children: ReactNode; pulse?: boolean }) {
  return (
    <span className={`badge ${tone}${pulse ? " pulse" : ""}`}>
      <span className="dot" aria-hidden="true" />
      {children}
    </span>
  );
}

/** Where a number came from. The simulated case is always spelled out, never implied. */
export function ProvenanceBadge({
  kind, detail,
}: { kind: "measured" | "simulated" | "synthetic" | "real" | "injected" | "placeholder"; detail?: string }) {
  const text = {
    measured: "Measured on this machine",
    simulated: "Simulated edge — not edge hardware",
    synthetic: "Synthetic data",
    real: "Real data",
    // Real rows with one change added at a known position: never to be read as plain real data.
    injected: "Real data + controlled drift",
    placeholder: "Placeholder budgets",
  }[kind];
  const explain: ExplainId | undefined =
    kind === "simulated" || kind === "placeholder" ? "edge" : kind === "measured" ? "provenance" : kind === "injected" ? "injectedDrift" : undefined;
  return (
    <span className="provenance">
      <span className={kind === "simulated" || kind === "placeholder" || kind === "injected" ? "tag sim" : kind === "real" ? "tag real" : "tag"} title={detail}>
        {text}
      </span>
      {explain && <ExplainButton id={explain} />}
    </span>
  );
}

export function MetricCard({
  label, value, unit, sub, explain, tone, compare,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  sub?: ReactNode;
  explain?: ExplainId;
  tone?: "accent" | "alert";
  compare?: boolean;
}) {
  return (
    <div className={`metric${tone ? ` ${tone}` : ""}${compare ? " compare" : ""}`}>
      <div className="metric-label">
        {label}
        {explain && <ExplainButton id={explain} />}
      </div>
      <div className="metric-value">
        {value}
        {unit && <span className="unit">{unit}</span>}
      </div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}

export const MetricGrid = ({ children }: { children: ReactNode }) => <div className="metric-grid">{children}</div>;

export type Phase = "idle" | "stable" | "drift" | "adapting" | "recovery";

const PHASE_TEXT: Record<Phase, { icon: string; title: string }> = {
  idle: { icon: "◌", title: "Not running" },
  stable: { icon: "●", title: "Stable" },
  drift: { icon: "⚠", title: "Drift detected" },
  adapting: { icon: "↻", title: "Adapting" },
  recovery: { icon: "◷", title: "Monitoring after adaptation" },
};

/** The one thing a visitor should read first: what is happening, in a sentence. */
export function StateBanner({
  phase, sentence, meta, explain,
}: { phase: Phase; sentence: string; meta?: ReactNode; explain?: ExplainId }) {
  const { icon, title } = PHASE_TEXT[phase];
  return (
    <section className={`state-banner ${phase}`} aria-live="polite">
      <span className="icon" aria-hidden="true">{icon}</span>
      <div className="headline">
        <span className="title">
          {title}
          {explain && <ExplainButton id={explain} />}
        </span>
        <span className="said">{sentence}</span>
      </div>
      {meta && <div className="meta">{meta}</div>}
    </section>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="title">{title}</div>
      {hint && <div className="hint">{hint}</div>}
      {action}
    </div>
  );
}

/** What happened, why, and what the reader can do — with the raw detail tucked away. */
export function ErrorState({
  title, why, action, technical,
}: { title: string; why: string; action?: ReactNode; technical?: string }) {
  return (
    <div className="error-state">
      <div className="title">{title}</div>
      <div className="hint">{why}</div>
      {action}
      {technical && (
        <details className="tech-details" style={{ width: "100%" }}>
          <summary>View technical error</summary>
          <div className="tech-body">
            <code className="mono small">{technical}</code>
          </div>
        </details>
      )}
    </div>
  );
}

export const Loading = ({ label = "Loading…" }: { label?: string }) => (
  <div className="loading-lines" role="status" aria-label={label}>
    <span />
    <span />
    <span />
  </div>
);

/** Progressive disclosure: the default view stays readable, the detail stays available. */
export function TechnicalDetails({ summary = "View technical details", children }: { summary?: string; children: ReactNode }) {
  return (
    <details className="tech-details">
      <summary>{summary}</summary>
      <div className="tech-body">{children}</div>
    </details>
  );
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean; dot?: boolean }[] }) {
  return (
    <div className="legend">
      {items.map((item) => (
        <span className="key" key={item.label} style={{ color: item.color }}>
          <span
            className={`swatch${item.dashed ? " dashed" : ""}${item.dot ? " dot" : ""}`}
            style={{ background: item.dashed ? undefined : item.color }}
          />
          <span className="muted">{item.label}</span>
        </span>
      ))}
    </div>
  );
}

export function Field({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="field-block">
      <span className="k">{k}</span>
      <span className="v">{children}</span>
    </div>
  );
}
