/** What a running comparison is doing, in words and in one moving bar.
 *
 *  An experiment is a queue of trials: one method, alone, in its own process, so that nothing else
 *  disturbs its timing. Without this view that queue is invisible — a counter going up. Here the
 *  trial that is running says where it is in the data, what the method is doing with each row, and
 *  what its accuracy is so far; the queue shows what has finished and what is waiting.
 *
 *  Everything shown is reported by the running trial. Nothing here is a conclusion.
 */

import { useEffect, useState } from "react";

import { api, type EventRecord, type JobContext, type JobCurrent, type JobProgress, type JobTrial } from "../lib/api";
import { methodLabel, pct } from "../lib/format";
import { href } from "../lib/router";
import { Badge } from "./ui";

const rows = (value: number) => value.toLocaleString();

const KIND_WORD: Record<string, string> = { abrupt: "sudden", gradual: "gradual", incremental: "incremental", recurring: "recurring" };

/** What the method does with every row — the part that is otherwise happening out of sight. */
function working(method: string, state: JobCurrent["methods"][string] | undefined): string {
  switch (method) {
    case "static":
      return "It predicts every row with the model it learned during the warm-up. It no longer learns anything.";
    case "incremental":
      return "It predicts each row, then learns from that row's true label. It never checks whether the data has changed.";
    case "adaptive":
      return state?.adapting
        ? "Its error rate rose and ADWIN confirmed it. A replacement model is now learning from the newest rows, while the current model keeps predicting."
        : "It predicts each row, learns from the true label, and watches its own error rate. If the errors rise and stay up, it trains a replacement model.";
    case "arf":
      return "Ten decision trees vote on every row. Each tree learns from the row and watches its own errors; a tree that falls behind is replaced on its own.";
    default:
      return "It predicts each row, then learns from it.";
  }
}

/** Where the trial is relative to the added change. */
function position(current: JobCurrent, context: JobContext, control: boolean): string {
  const injection = context.injection;
  if (control) return "This is the control: the rows are untouched, with no change added.";
  if (!injection) return "The rows are replayed as recorded. Any drift in them is the data's own.";
  const { start, kind } = injection;
  const end = injection.end ?? start + injection.width;
  if (current.sample < start) return `The added change has not started yet. It begins at row ${rows(start)}.`;
  if (kind === "recurring") {
    const turn = Math.floor((current.sample - start) / (injection.period ?? 1));
    return turn % 2 === 0
      ? `The data is in its changed arrangement (switch number ${turn + 1}). It switches again every ${rows(injection.period ?? 0)} rows.`
      : `The data is back in its original arrangement (switch number ${turn + 1}). It switches again every ${rows(injection.period ?? 0)} rows.`;
  }
  if (current.sample < end) return `The data is changing right now, between rows ${rows(start)} and ${rows(end)}.`;
  return `The change finished at row ${rows(end)}. Every row now follows the new arrangement.`;
}

function headline(current: JobCurrent, context: JobContext): string {
  switch (current.lifecycle) {
    case "starting":
    case "loading":
      return "Starting a fresh process and checking the data file.";
    case "warming_up":
      return `Warming up: learning from the first ${rows(context.warmup)} rows. Nothing is scored yet.`;
    case "summarizing":
      return "All rows processed. Computing the scores and saving the results.";
    case "completed":
      return "This trial is finished.";
    default:
      return `Row ${rows(current.sample)} of ${rows(current.total)}.`;
  }
}

/** One line for an event the method reported, in plain words. Null for events not worth showing. */
function say(event: EventRecord): string | null {
  switch (event.type) {
    case "frozen":
      return "Warm-up over. It stops learning and only predicts from here.";
    case "selection_applied":
      return `Chose the input columns to keep: ${(event.selected as string[]).join(", ")}.`;
    case "drift_true":
      return "The added change begins here.";
    case "drift_detected":
      return event.error_increased ? "ADWIN confirmed a sustained rise in prediction errors." : null;
    case "drift_ignored":
      return `Another alert, but no action was taken (${String(event.reason ?? "cooling down")}).`;
    case "background_started":
      return "Started training a replacement model on the newest rows.";
    case "adaptation_started":
      return "Adapting: the replacement must learn enough rows before it can take over.";
    case "adaptation_completed":
      return `The replacement model took over. This is model version ${event.model_version}.`;
    case "adaptation_failed":
      return "The replacement could not be used. The previous model carries on.";
    case "background_discarded":
      return "The replacement was not needed and was discarded.";
    default:
      return null;
  }
}

function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function Mark({ status }: { status: JobTrial["status"] }) {
  const symbol = { done: "✓", running: "●", waiting: "○", failed: "✕" }[status];
  return <span className={`trial-mark ${status}`} aria-hidden="true">{symbol}</span>;
}

export default function ExperimentBoard({ job }: { job: JobProgress }) {
  const running = job.status === "running";
  const [, tick] = useState(0);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  const { context, plan, current } = job;
  const active = plan?.find((trial) => trial.status === "running");
  const state = active && current ? current.methods[active.method] : undefined;
  const elapsed = job.started_at ? ((job.finished_at ?? Date.now() / 1000) - job.started_at) : null;
  const done = plan?.filter((trial) => trial.status === "done").length ?? job.done;
  const total = plan?.length ?? job.total ?? 0;
  const injection = context?.injection ?? null;
  const share = (value: number) => `${Math.min(100, Math.max(0, (value / Math.max(current?.total ?? context?.length ?? 1, 1)) * 100))}%`;
  const lines = (job.feed ?? [])
    .filter((event) => event.trial_id === active?.trial_id)
    .map((event) => ({ event, text: say(event) }))
    .filter((line): line is { event: typeof line.event; text: string } => line.text !== null)
    .slice(-5)
    .reverse();

  return (
    <section className={`board ${running ? "running" : "finished"}`} role="status" aria-live="polite">
      <header className="board-head">
        <div>
          <span className="eyebrow">{running ? "Comparison running" : job.status === "completed" ? "Comparison finished" : `Comparison ${job.status}`}</span>
          <h2>{job.name}</h2>
          <p className="board-sub">
            {total > 0 && <>{running ? `Trial ${Math.min(done + 1, total)} of ${total}` : `${done} of ${total} trials completed`}</>}
            {elapsed != null && <> · {clock(elapsed)} {running ? "elapsed" : "in total"}</>}
            {injection && <> · {KIND_WORD[injection.kind]} change at row {rows(injection.start)}</>}
            {context && !injection && context.scenario === "csv" && <> · natural replay, nothing added</>}
          </p>
        </div>
        {running
          ? <button type="button" className="btn danger" onClick={() => void api.stopJob()}>Stop after this trial</button>
          : job.experiment_id && <a className="btn primary" href={href({ page: "experiment", id: job.experiment_id })}>View results →</a>}
      </header>

      {job.error && <p className="banner error">{job.error}</p>}

      {plan && plan.length > 0 && (
        <div className="board-steps" aria-hidden="true">
          {plan.map((trial) => <span key={trial.trial_id} className={`step ${trial.status}${trial.control ? " control" : ""}`} />)}
        </div>
      )}

      {running && active && current && context && (
        <div className="board-now">
          <div className="now-title">
            <span className="eyebrow">Right now</span>
            <h3>{methodLabel(active.method)}</h3>
            <span className={`tag${active.control ? "" : " sim"}`}>{active.control ? "control · untouched rows" : injection ? "with the added change" : "rows as recorded"}</span>
          </div>

          <div className="now-bar" aria-label={`Row ${rows(current.sample)} of ${rows(current.total)}`}>
            <span className="fill" style={{ width: share(current.sample) }} />
            <span className="warm" style={{ width: share(context.warmup) }} title="warm-up" />
            {injection && !active.control && (
              <span
                className="change"
                style={{ left: share(injection.start), width: `max(3px, ${share((injection.end ?? injection.start + 1) - injection.start)})` }}
                title="the added change"
              />
            )}
          </div>
          <div className="now-bar-key">
            <span>row 0</span>
            <span>warm-up ends at {rows(context.warmup)}</span>
            {injection && !active.control && <span className="at-change">change at {rows(injection.start)}</span>}
            <span>{rows(current.total)}</span>
          </div>

          <p className="now-said"><strong>{headline(current, context)}</strong></p>
          {current.lifecycle === "running" && (
            <>
              <p className="now-said">{working(active.method, state)}</p>
              <p className="now-said muted">{position(current, context, active.control)}</p>
            </>
          )}

          <dl className="now-stats">
            <div><dt>Accuracy so far</dt><dd>{pct(state?.accuracy)}</dd></div>
            <div><dt>Last 1,000 rows</dt><dd>{pct(state?.recent_accuracy)}</dd></div>
            <div><dt>Precision so far</dt><dd>{pct(state?.precision)}</dd></div>
            <div><dt>Model version</dt><dd>{state ? state.model_version : "—"}</dd></div>
            <div><dt>Rows scored</dt><dd>{state ? rows(state.scored) : "—"}</dd></div>
          </dl>

          {lines.length > 0 && (
            <ol className="now-feed">
              {lines.map(({ event, text }, index) => (
                <li key={`${event.i}-${event.type}-${index}`}>
                  <span className="at">row {rows(event.i)}</span>
                  <span>{text}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}

      {plan && plan.length > 0 && (
        <div className="board-queue">
          <div className="queue-head">
            <span className="eyebrow">{running ? "The queue" : "What was run"}</span>
            <span className="small muted">Each method runs alone, in a fresh process, so its timing is not disturbed by the others.</span>
          </div>
          <ol>
            {plan.map((trial) => (
              <li key={trial.trial_id} className={trial.status}>
                <Mark status={trial.status} />
                <span className="who">
                  {methodLabel(trial.method)}
                  <small>
                    {trial.control ? "control · untouched rows" : injection ? "with the added change" : "rows as recorded"}
                    {trial.profile !== "Standard" ? ` · ${trial.profile}` : ""}
                    {(plan.some((other) => other.seed !== trial.seed)) ? ` · seed ${trial.seed}` : ""}
                  </small>
                </span>
                <span className="what">
                  {trial.status === "done" && <>accuracy <strong>{pct(trial.accuracy)}</strong> · precision <strong>{pct(trial.precision)}</strong></>}
                  {trial.status === "running" && <Badge tone="info" pulse>running</Badge>}
                  {trial.status === "waiting" && <span className="muted">waiting</span>}
                  {trial.status === "failed" && <span className="muted">did not finish</span>}
                </span>
                <span className="took">{trial.seconds != null ? `${trial.seconds.toFixed(1)} s` : ""}</span>
              </li>
            ))}
          </ol>
          {!running && job.status === "completed" && (
            <p className="small muted">
              These are whole-run figures. Open the results for accuracy and precision before, during and after the change.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
