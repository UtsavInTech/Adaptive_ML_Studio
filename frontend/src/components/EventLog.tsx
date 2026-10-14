/** Factual event log: what happened, at which sample, and why. No interpretation. */

import { useState } from "react";

import type { EventRecord } from "../lib/api";
import { samples } from "../lib/format";
import { EmptyState } from "./ui";

const CLASSES: Record<string, string> = {
  drift_true: "drift",
  drift_detected: "drift",
  drift_scheduled: "drift",
  drift_ignored: "info",
  adaptation_started: "adapt",
  adaptation_completed: "adapt",
  adaptation_failed: "error",
  background_started: "adapt",
  background_discarded: "info",
  budget_exceeded: "budget",
  budget_cleared: "budget",
  config_changed: "budget",
  command_rejected: "error",
  selection_applied: "info",
  frozen: "info",
};

export function describe(event: EventRecord): { text: string; why?: string } {
  const method = event.method ? `${event.method}: ` : "";
  switch (event.type) {
    case "drift_true":
      if (event.injected) {
        return {
          text: `The added change begins (${event.drift_kind})`,
          why: "two input columns are exchanged from here · the position was chosen in the setup",
        };
      }
      return {
        text: `Drift in the data (concept ${event.from_variant} → ${event.to_variant})`,
        why: `${(((event.label_flip_fraction as number) ?? 0) * 100).toFixed(1)} % of the input space changes label · scheduled ground truth`,
      };
    case "drift_scheduled":
      return { text: `Drift scheduled for sample ${samples(event.position as number)}`, why: "injected during the run and recorded in the configuration" };
    case "drift_detected":
      return {
        text: `${method}drift detected`,
        why: `error estimate ${(((event.error_estimate as number) ?? 0) * 100).toFixed(1)} % · detector window ${samples(Math.round(event.width as number))}`,
      };
    case "drift_ignored":
      return { text: `${method}change detected, no action taken`, why: String(event.reason ?? "") };
    case "background_started":
      return { text: `${method}training a replacement model`, why: String(event.reason ?? "") };
    case "background_discarded":
      return { text: `${method}replacement discarded`, why: String(event.reason ?? "") };
    case "adaptation_started":
      return {
        text: `${method}adapting — replacement needs ${samples(event.needed as number)} samples`,
        why: String(event.reason ?? ""),
      };
    case "adaptation_completed":
      return {
        text: `${method}adaptation completed (${event.action}) → model v${event.model_version}`,
        why: `${samples(event.samples_after_detection as number)} samples after detection · replacement trained on ${samples(event.trained_on as number)} samples`,
      };
    case "adaptation_failed":
      return { text: `${method}adaptation failed — continuing with previous model`, why: String(event.error ?? "") };
    case "budget_exceeded":
      return { text: `${method}above the simulated budget`, why: `${event.measured_us} µs/sample measured vs ${event.limit_us} µs allowed` };
    case "budget_cleared":
      return { text: `${method}back within the simulated budget`, why: `${event.measured_us} µs/sample vs ${event.limit_us} µs allowed` };
    case "config_changed":
      return { text: `${method}${event.field} changed: ${event.old} → ${event.new}`, why: String(event.reason ?? "") };
    case "selection_applied":
      return {
        text: `${method}features selected: ${(event.selected as string[]).join(", ")}`,
        why: (event.dropped as string[]).length ? `dropped ${(event.dropped as string[]).join(", ")}` : undefined,
      };
    case "frozen":
      return { text: `${method}frozen after warm-up`, why: "the static baseline stops learning here" };
    case "command_rejected":
      return { text: `Command rejected: ${event.command}`, why: String(event.reason ?? "") };
    default:
      return { text: `${method}${event.type}` };
  }
}

const FILTERS = [
  { key: "all", label: "All" },
  { key: "drift", label: "Drift" },
  { key: "adapt", label: "Adaptation" },
  { key: "budget", label: "Resources" },
] as const;

export default function EventLog({ events, height = 320 }: { events: EventRecord[]; height?: number }) {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");
  const visible = events
    .filter((event) => filter === "all" || CLASSES[event.type] === filter)
    .slice(-250)
    .reverse();

  return (
    <div className="event-log">
      <div className="row wrap" style={{ padding: "10px 14px" }}>
        <div className="segmented">
          {FILTERS.map((option) => (
            <button key={option.key} type="button" aria-pressed={filter === option.key} onClick={() => setFilter(option.key)}>
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <div className="event-scroll" style={{ maxHeight: height }}>
        {visible.length === 0 && (
          <EmptyState
            title={filter === "all" ? "Nothing has happened yet" : "No events of this kind yet"}
            hint="Drift, detection, adaptation and resource decisions appear here as they occur, each with the sample it happened at."
          />
        )}
        {visible.map((event, index) => {
          const { text, why } = describe(event);
          return (
            <div className={`event ${CLASSES[event.type] ?? "info"}`} key={`${event.i}-${event.type}-${index}`}>
              <span className="at">{samples(event.i)}</span>
              <span>
                <strong>{text}</strong>
                {why && <div className="why">{why}</div>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
