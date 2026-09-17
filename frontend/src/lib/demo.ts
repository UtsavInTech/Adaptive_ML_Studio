/** Demo narration. Steps advance on real events and measurements, never on a timer, so the caption
 *  can only claim something that actually happened. */

import type { EventRecord, Lifecycle } from "./api";
import type { Episode } from "./derive";

export type DemoContext = {
  lifecycle: Lifecycle;
  sample: number;
  warmup: number;
  events: EventRecord[];
  episode: Episode | undefined;
  preAccuracy: number | null;
  minAccuracy: number | null;
};

export type DemoStep = { title: string; text: string; done: (ctx: DemoContext) => boolean };

const has = (ctx: DemoContext, type: string) => ctx.events.some((e) => e.type === type);

export const DEMO_STEPS: DemoStep[] = [
  {
    title: "Warming up",
    text: "Every method trains on the first samples. Measurement starts after the warm-up.",
    done: (ctx) => ctx.sample > ctx.warmup,
  },
  {
    title: "Stable operation",
    text: "Both methods predict the same samples. Watch accuracy, processing time and memory settle.",
    done: (ctx) => has(ctx, "drift_true"),
  },
  {
    title: "The data changed",
    text: "A concept change occurred: the inputs look the same, but their correct labels moved.",
    done: (ctx) => ctx.preAccuracy != null && ctx.minAccuracy != null && ctx.minAccuracy < ctx.preAccuracy - 0.02,
  },
  {
    title: "Performance drops",
    text: "Both models start predicting the old concept, so accuracy falls.",
    done: (ctx) => ctx.episode?.detectedAt != null,
  },
  {
    title: "Drift detected",
    text: "ADWIN flagged the rise in the adaptive pipeline's own error rate.",
    done: (ctx) => has(ctx, "adaptation_started") || ctx.episode?.adaptedAt != null,
  },
  {
    title: "Adapting",
    text: "A replacement model trains on the new concept while the current model keeps serving predictions.",
    done: (ctx) => ctx.episode?.adaptedAt != null,
  },
  {
    title: "Model replaced",
    text: "The replacement is promoted. The static baseline keeps the old concept — compare the two lines.",
    done: (ctx) => ctx.episode?.adaptedAt != null && ctx.sample - ctx.episode.adaptedAt > 1500,
  },
  {
    title: "Cost of adapting",
    text: "The cost panel shows what detection and adaptation added per sample.",
    done: (ctx) => ctx.lifecycle === "completed" || ctx.lifecycle === "stopped",
  },
  {
    title: "Run finished",
    text: "The run is saved. Open Experiments to compare methods and profiles and to re-run it for reproducibility.",
    done: () => false,
  },
];

export function demoProgress(ctx: DemoContext): { index: number; total: number; step: DemoStep } {
  let index = 0;
  while (index < DEMO_STEPS.length - 1 && DEMO_STEPS[index].done(ctx)) index += 1;
  return { index, total: DEMO_STEPS.length, step: DEMO_STEPS[index] };
}
