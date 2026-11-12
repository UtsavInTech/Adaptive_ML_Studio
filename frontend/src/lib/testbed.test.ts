import { describe, expect, it } from "vitest";

import type { Manifest } from "./api";
import { parseHash, href } from "./router";
import { aboutDuration, actionWords, buildConfig, estimateSeconds, formIssues, parseSeeds, testbedRows, trialCount, type TestbedForm } from "./testbed";

const FORM: TestbedForm = {
  dataset: "cicids2017", start: 693_702, length: 30_000, sliceLabel: "Wednesday DoS attacks",
  methods: ["no_change", "adaptive", "joint"], tiers: ["small_sim"], labelDelay: 0, labelCoverage: 1,
  arrival: "constant", rateScale: 10, rules: ["R1", "R2", "R4", "R5"], resourceGating: false, seeds: [11], warmup: 1000,
  name: "Testbed check",
};

describe("testbed form", () => {
  it("builds the experiment configuration the API expects", () => {
    const config = buildConfig(FORM) as any;
    expect(config.profiles).toEqual(["small_sim"]);
    expect(config.seeds).toEqual([11]);
    expect(config.base.stream).toEqual({
      scenario: "csv", dataset: "cicids2017", noise: 0, start: 693_702, length: 30_000,
      arrival: "constant", label_delay: 0, label_coverage: 1,
    });
    expect(config.base.controller).toEqual({ rules: ["R1", "R2", "R4", "R5"], resource_gating: false });
    const recorded = buildConfig({ ...FORM, arrival: "recorded", methods: ["adaptive"] }) as any;
    expect(recorded.base.stream.rate_scale).toBe(10);
    expect(recorded.base.controller).toBeUndefined();
  });

  it("counts trials and flags impossible settings", () => {
    expect(trialCount({ ...FORM, tiers: ["standard", "small_sim"], seeds: [1, 2] })).toBe(12);
    expect(formIssues(FORM, 2_099_976)).toEqual([]);
    expect(formIssues({ ...FORM, start: 2_090_000 }, 2_099_976)[0]).toMatch(/ends after the last row/);
    expect(formIssues({ ...FORM, warmup: 30_000 }, 2_099_976)).toContain("The warm-up must be shorter than the slice.");
    expect(formIssues({ ...FORM, methods: [], tiers: [] }, 2_099_976)).toHaveLength(2);
  });

  it("reads seeds", () => {
    expect(parseSeeds("11, 23 37")).toEqual([11, 23, 37]);
    expect(parseSeeds("11, x")).toBeNull();
    expect(parseSeeds("")).toBeNull();
  });

  it("estimates duration from typical cost per row", () => {
    const options = { methods: [{ id: "joint", said: "", us_per_row: 200 }], read_us_per_row: 0 };
    const seconds = estimateSeconds({ methods: ["joint"], tiers: ["a", "b"], seeds: [1], length: 1_000_000, start: 0 }, options);
    expect(seconds).toBeCloseTo(2 * (200 + 2), 0);
    expect(aboutDuration(30)).toBe("about 30 seconds");
    expect(aboutDuration(600)).toBe("about 10 minutes");
    expect(aboutDuration(4 * 3600)).toBe("about 4.0 hours");
  });

  it("names controller actions", () => {
    expect(actionWords("R5_SHRINK_MODEL_56_TO_28")).toEqual({ rule: "R5", what: "shrink model 56 to 28" });
    expect(actionWords("OTHER")).toEqual({ rule: "", what: "other" });
  });
});

describe("testbed results", () => {
  const manifest = {
    trials: [
      { trial_id: "joint__small_sim__max__s11", seed: 11, profile: { name: "small_sim", label: "Small", simulated: true, placeholder: true }, methods: {} },
      { trial_id: "static__standard__max__s11", seed: 11, profile: { name: "standard", label: "Standard", simulated: false, placeholder: false }, methods: {} },
    ],
  } as unknown as Manifest;

  it("reads testbed fields and skips runs without them", () => {
    const rows = testbedRows(manifest, {
      joint__small_sim__max__s11: {
        timing: {}, scenario: { n_features: 83 }, config: { profile: { budgets: { model_memory_mib: 8 } } },
        summaries: {
          joint: {
            scores_after_warmup: { n: 100, accuracy: 0.9, recall: 0.8, fp: 1, tn: 9 },
            latency_us: { mean: 50, p99: 120 },
            stream_scores_after_warmup: { kappa_temporal: 0.5, macro_f1: 0.7, no_change_accuracy: 0.8 },
            cost_terms_us_per_row: { C_pre: 10 },
          } as any,
        },
      },
      // An old run: no testbed fields at all.
      static__standard__max__s11: { timing: {}, scenario: {}, config: {}, summaries: { static: { scores_after_warmup: { accuracy: 0.7 } } as any } },
    });
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ method: "joint", tier: "small_sim", simulated: true, kappaTemporal: 0.5, falseAlarm: 0.1, nFeatures: 83, memoryBudgetMib: 8 });
    expect(testbedRows(manifest, {})).toEqual([]);
  });
});

describe("testbed routes", () => {
  it("round-trips the page and a report", () => {
    expect(parseHash("#/testbed")).toEqual({ page: "testbed" });
    expect(parseHash(href({ page: "testbed", report: "protocol-quick" }))).toEqual({ page: "testbed", report: "protocol-quick" });
  });
});
