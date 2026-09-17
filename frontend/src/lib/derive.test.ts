import { describe, expect, it } from "vitest";

import type { BlockRecord, EventRecord } from "./api";
import { demoProgress, type DemoContext } from "./demo";
import { episodes, minScoreBetween, overallScores, phase, scoreAt, windowedScores } from "./derive";

const block = (start: number, tp: number, fp: number, tn: number, fn: number): BlockRecord =>
  ({ start, n: tp + fp + tn + fn, tp, fp, tn, fn, method: "adaptive" }) as unknown as BlockRecord;

const event = (i: number, type: string, extra: Record<string, unknown> = {}): EventRecord =>
  ({ i, type, method: type === "drift_true" ? null : "adaptive", ...extra }) as EventRecord;

describe("windowedScores", () => {
  it("uses only the blocks inside the window", () => {
    const blocks = [block(0, 10, 0, 0, 0), block(10, 5, 0, 0, 5), block(20, 0, 0, 10, 0)];
    const series = windowedScores(blocks, 20);
    expect(series.x).toEqual([10, 20, 30]);
    expect(series.accuracy[0]).toBe(1);
    expect(series.accuracy[1]).toBeCloseTo(0.75); // both blocks: 15 of 20 correct
    expect(series.accuracy[2]).toBeCloseTo(0.75); // first block dropped out
  });

  it("reports F1 of the positive class", () => {
    const series = windowedScores([block(0, 3, 1, 4, 2)], 10);
    expect(series.f1[0]).toBeCloseTo(2 / 3);
  });
});

describe("overallScores", () => {
  it("skips blocks before the warm-up", () => {
    const scores = overallScores([block(0, 0, 10, 0, 0), block(10, 10, 0, 0, 0)], 10);
    expect(scores.n).toBe(10);
    expect(scores.accuracy).toBe(1);
  });
});

describe("episodes", () => {
  const events = [
    event(1000, "selection_applied", { selected: ["x0"], dropped: [] }),
    event(10000, "drift_true", { from_variant: 0, to_variant: 3, label_flip_fraction: 0.13 }),
    event(10300, "drift_detected", { error_increased: true, width: 2000 }),
    event(10478, "adaptation_completed", { action: "swap", samples_after_detection: 178, trained_on: 200 }),
    event(14000, "drift_detected", { error_increased: true, width: 1500 }),
    event(14094, "adaptation_completed", { action: "swap", samples_after_detection: 0, trained_on: 224 }),
  ];

  it("anchors the first episode to the drift in the data", () => {
    const [first] = episodes(events);
    expect(first.driftIndex).toBe(10000);
    expect(first.detectedAt).toBe(10300);
    expect(first.delay).toBe(300);
    expect(first.adaptedAt).toBe(10478);
    expect(first.action).toBe("swap");
  });

  it("keeps a later detection without ground truth as its own episode", () => {
    const list = episodes(events);
    expect(list).toHaveLength(2);
    expect(list[1].driftIndex).toBeNull();
    expect(list[1].detectedAt).toBe(14000);
    // The Live page prefers the episode that has a drift in the data.
    const preferred = [...list].reverse().find((e) => e.driftIndex != null);
    expect(preferred?.driftIndex).toBe(10000);
  });

  it("records a failed adaptation without inventing an adaptation point", () => {
    const [only] = episodes([
      event(5000, "drift_true"),
      event(5100, "drift_detected", { error_increased: true }),
      event(5100, "adaptation_failed", { error: "boom" }),
    ]);
    expect(only.failed).toBe(true);
    expect(only.adaptedAt).toBeNull();
  });
});

describe("phase", () => {
  const events = [
    event(10300, "drift_detected", { error_increased: true }),
    event(10300, "adaptation_started", { action: "prepare" }),
    event(10478, "adaptation_completed", { action: "swap" }),
  ];

  it("is adapting while a replacement is being prepared", () => {
    expect(phase(events.slice(0, 2), "adaptive", 10400).phase).toBe("adapting");
  });

  it("watches for recovery after an adaptation and settles back to stable", () => {
    expect(phase(events, "adaptive", 11000).phase).toBe("recovery");
    expect(phase(events, "adaptive", 20000).phase).toBe("stable");
  });
});

describe("series sampling", () => {
  const series = windowedScores([block(0, 10, 0, 0, 0), block(10, 5, 0, 0, 5), block(20, 8, 0, 0, 2)], 10);

  it("samples the value at or before a sample index", () => {
    expect(scoreAt(series, 15)).toBe(1);
    expect(scoreAt(series, null)).toBeNull();
  });

  it("finds the lowest value in a range", () => {
    expect(minScoreBetween(series, 10, 30)).toBeCloseTo(0.5);
  });
});

describe("demo narration", () => {
  const base: DemoContext = {
    lifecycle: "running",
    sample: 12000,
    warmup: 1000,
    events: [event(10000, "drift_true")],
    episode: undefined,
    preAccuracy: null,
    minAccuracy: null,
  };

  it("waits at the data-change step until a measured drop exists", () => {
    expect(demoProgress(base).index).toBe(2);
  });

  it("advances once the drop and the adaptation are measured", () => {
    const progressed = demoProgress({
      ...base,
      preAccuracy: 0.93,
      minAccuracy: 0.78,
      episode: { driftIndex: 10000, detectedAt: 10300, delay: 300, adaptedAt: 10478, action: "swap", samplesToPromotion: 178, trainedOn: 200, failed: false },
      events: [...base.events, event(10300, "adaptation_started")],
    });
    expect(progressed.index).toBeGreaterThan(4);
    expect(progressed.step.title).toBeTruthy();
  });
});
