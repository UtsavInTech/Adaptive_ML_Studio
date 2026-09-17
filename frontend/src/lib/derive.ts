/** Pure derivations from blocks and events: windowed scores, pipeline state, adaptation episodes.
 *  These mirror the backend's definitions so the live view and the stored bundle agree. */

import type { BlockRecord, EventRecord } from "./api";

export type PipelinePhase = "stable" | "drift" | "adapting" | "recovery";

export type WindowedSeries = { x: number[]; accuracy: (number | null)[]; f1: (number | null)[] };

/** Accuracy/F1 over a sliding window of whole blocks (same algorithm as results.windowed_scores). */
export function windowedScores(blocks: BlockRecord[], window: number): WindowedSeries {
  const x: number[] = [];
  const accuracy: (number | null)[] = [];
  const f1: (number | null)[] = [];
  let tp = 0, fp = 0, tn = 0, fn = 0, n = 0;
  const queue: BlockRecord[] = [];
  for (const block of blocks) {
    queue.push(block);
    tp += block.tp; fp += block.fp; tn += block.tn; fn += block.fn; n += block.n;
    while (queue.length && n - queue[0].n >= window) {
      const old = queue.shift()!;
      tp -= old.tp; fp -= old.fp; tn -= old.tn; fn -= old.fn; n -= old.n;
    }
    x.push(block.start + block.n);
    accuracy.push(n ? (tp + tn) / n : null);
    const denominator = 2 * tp + fp + fn;
    f1.push(denominator ? (2 * tp) / denominator : null);
  }
  return { x, accuracy, f1 };
}

export function overallScores(blocks: BlockRecord[], fromSample: number) {
  let tp = 0, fp = 0, tn = 0, fn = 0;
  for (const block of blocks) {
    if (block.start < fromSample) continue;
    tp += block.tp; fp += block.fp; tn += block.tn; fn += block.fn;
  }
  const n = tp + fp + tn + fn;
  const denominator = 2 * tp + fp + fn;
  return {
    n,
    accuracy: n ? (tp + tn) / n : null,
    f1: denominator ? (2 * tp) / denominator : null,
    precision: tp + fp ? tp / (tp + fp) : null,
    recall: tp + fn ? tp / (tp + fn) : null,
  };
}

export const lastBlock = (blocks: BlockRecord[] | undefined): BlockRecord | undefined => blocks?.[blocks.length - 1];

/** Mean over the last `count` blocks of a numeric block field. */
export function recentMean(blocks: BlockRecord[] | undefined, field: string, count = 4): number | null {
  if (!blocks?.length) return null;
  const slice = blocks.slice(-count);
  let total = 0;
  let weight = 0;
  for (const block of slice) {
    const value = block[field];
    if (typeof value === "number") {
      total += value * block.n;
      weight += block.n;
    }
  }
  return weight ? total / weight : null;
}

export type Episode = {
  driftIndex: number | null;
  detectedAt: number | null;
  delay: number | null;
  adaptedAt: number | null;
  action: string | null;
  samplesToPromotion: number | null;
  trainedOn: number | null;
  failed: boolean;
  reason?: string;
};

/** Group drift/adaptation events into episodes, newest last. */
export function episodes(events: EventRecord[], method = "adaptive"): Episode[] {
  const list: Episode[] = [];
  const open = (): Episode => ({
    driftIndex: null, detectedAt: null, delay: null, adaptedAt: null,
    action: null, samplesToPromotion: null, trainedOn: null, failed: false,
  });
  let current: Episode | null = null;
  for (const event of events) {
    if (event.type === "drift_true") {
      current = { ...open(), driftIndex: event.i };
      list.push(current);
      continue;
    }
    if (event.method !== method) continue;
    if (event.type === "drift_detected" && event.error_increased) {
      if (!current || current.detectedAt !== null) {
        current = open();
        list.push(current);
      }
      current.detectedAt = event.i;
      if (current.driftIndex !== null) current.delay = event.i - current.driftIndex;
    } else if (event.type === "adaptation_completed" && current) {
      current.adaptedAt = event.i;
      current.action = String(event.action);
      current.samplesToPromotion = Number(event.samples_after_detection ?? 0);
      current.trainedOn = Number(event.trained_on ?? 0);
    } else if (event.type === "adaptation_failed" && current) {
      current.failed = true;
      current.reason = String(event.error ?? "");
    }
  }
  return list;
}

/** Current phase of a method, from its latest events. */
export function phase(events: EventRecord[], method: string, sample: number, recoveryHorizon = 3000): { phase: PipelinePhase; since: number | null } {
  let result: { phase: PipelinePhase; since: number | null } = { phase: "stable", since: null };
  for (const event of events) {
    if (event.method !== method) continue;
    if (event.type === "drift_detected" && event.error_increased) result = { phase: "drift", since: event.i };
    else if (event.type === "adaptation_started") result = { phase: "adapting", since: event.i };
    else if (event.type === "adaptation_completed") result = { phase: "recovery", since: event.i };
    else if (event.type === "adaptation_failed") result = { phase: "stable", since: event.i };
    else if (event.type === "drift_ignored" && result.phase === "drift") result = { phase: "stable", since: event.i };
  }
  if (result.phase === "recovery" && result.since !== null && sample - result.since > recoveryHorizon) {
    return { phase: "stable", since: result.since };
  }
  return result;
}

/** Sample the windowed accuracy series at a sample index (nearest earlier point). */
export function scoreAt(series: WindowedSeries, sample: number | null): number | null {
  if (sample == null) return null;
  let value: number | null = null;
  for (let i = 0; i < series.x.length; i++) {
    if (series.x[i] > sample) break;
    value = series.accuracy[i];
  }
  return value;
}

/** Lowest windowed accuracy in [from, to). */
export function minScoreBetween(series: WindowedSeries, from: number | null, to: number | null): number | null {
  if (from == null) return null;
  let min: number | null = null;
  for (let i = 0; i < series.x.length; i++) {
    if (series.x[i] < from) continue;
    if (to != null && series.x[i] > to) break;
    const value = series.accuracy[i];
    if (value != null && (min == null || value < min)) min = value;
  }
  return min;
}
