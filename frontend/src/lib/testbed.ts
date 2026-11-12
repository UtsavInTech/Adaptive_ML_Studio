/** Research testbed: the setup form's arithmetic and the rows of the results view.
 *
 *  Pure functions, so they can be tested without a browser. Nothing here judges a result: it only
 *  builds the configuration that is sent, estimates how long it will take, and reads stored numbers. */

import type { AttackPeriodScore, AttackTypeScore, ControllerSummary, Manifest, MethodSummary, TestbedOptions } from "./api";

export type TestbedForm = {
  dataset: string;
  sha256?: string;
  start: number;
  length: number;
  sliceLabel: string;
  methods: string[];
  tiers: string[];
  labelDelay: number;
  labelCoverage: number;
  arrival: "constant" | "recorded";
  rateScale: number;
  rules: string[];
  resourceGating: boolean;
  seeds: number[];
  warmup: number;
  name: string;
};

export const ALL_RULES = ["R1", "R2", "R3", "R4", "R5"];

/** "11, 23, 37" → [11, 23, 37]; null when any entry is not a whole number ≥ 0. */
export function parseSeeds(text: string): number[] | null {
  const parts = text.split(/[\s,]+/).filter(Boolean);
  if (!parts.length) return null;
  const seeds = parts.map(Number);
  if (seeds.some((s) => !Number.isInteger(s) || s < 0)) return null;
  return [...new Set(seeds)];
}

export const trialCount = (form: Pick<TestbedForm, "methods" | "tiers" | "seeds">): number =>
  form.methods.length * form.tiers.length * form.seeds.length;

/** Rough wall time in seconds: rows × (each method's typical µs per row + reading the file), for every
 *  tier and seed, plus skipping to the first row. From earlier runs on one machine; a guide only. */
export function estimateSeconds(form: Pick<TestbedForm, "methods" | "tiers" | "seeds" | "length" | "start">, options: Pick<TestbedOptions, "methods" | "read_us_per_row">): number {
  const perRow = form.methods.reduce((sum, id) => sum + (options.methods.find((m) => m.id === id)?.us_per_row ?? 200) + options.read_us_per_row, 0);
  const perTierSeed = (form.length * perRow) / 1e6 + form.methods.length * (form.start * 0.5e-6 + 2);
  return perTierSeed * form.tiers.length * form.seeds.length;
}

export function aboutDuration(seconds: number): string {
  if (seconds < 90) return `about ${Math.max(1, Math.round(seconds / 5) * 5)} seconds`;
  const minutes = seconds / 60;
  if (minutes < 90) return `about ${Math.round(minutes)} minutes`;
  const hours = minutes / 60;
  if (hours < 36) return `about ${hours < 10 ? hours.toFixed(1) : Math.round(hours)} hours`;
  return `about ${(hours / 24).toFixed(1)} days`;
}

export function formIssues(form: TestbedForm, rows: number): string[] {
  const out: string[] = [];
  const whole = Number.isInteger;
  if (!whole(form.start) || form.start < 0) out.push("The first row must be a whole number, 0 or more.");
  if (!whole(form.length) || form.length < 2) out.push("Replay at least 2 rows.");
  if (form.start + form.length > rows) out.push(`The slice ends after the last row (${rows.toLocaleString()}).`);
  if (!whole(form.warmup) || form.warmup < 1 || form.warmup >= form.length) out.push("The warm-up must be shorter than the slice.");
  if (!form.methods.length) out.push("Choose at least one method.");
  if (!form.tiers.length) out.push("Choose at least one device tier.");
  if (!form.seeds.length) out.push("Give at least one seed, as whole numbers separated by commas.");
  if (!whole(form.labelDelay) || form.labelDelay < 0) out.push("The label delay must be a whole number of rows, 0 or more.");
  if (!(form.labelCoverage > 0 && form.labelCoverage <= 1)) out.push("Label coverage must be above 0 % and at most 100 %.");
  if (form.arrival === "recorded" && !(form.rateScale > 0)) out.push("The speed-up must be above 0.");
  if (!form.name.trim()) out.push("Give the run a name.");
  return out;
}

/** The ExperimentConfig the Experiments page would post, for a slice of a large dataset. */
export function buildConfig(form: TestbedForm): Record<string, unknown> {
  const stream: Record<string, unknown> = {
    scenario: "csv", dataset: form.dataset, noise: 0, start: form.start, length: form.length,
    arrival: form.arrival, label_delay: form.labelDelay, label_coverage: form.labelCoverage,
  };
  if (form.sha256) stream.dataset_sha256 = form.sha256;
  if (form.arrival === "recorded") stream.rate_scale = form.rateScale;
  const base: Record<string, unknown> = {
    methods: form.methods, stream, evaluation: { warmup: form.warmup, block_size: 100 },
  };
  // The controller only steers the joint method; leaving it out otherwise keeps other runs' configs plain.
  if (form.methods.includes("joint")) {
    base.controller = { rules: ALL_RULES.filter((r) => form.rules.includes(r)), resource_gating: form.resourceGating };
  }
  return { name: form.name.trim().slice(0, 120), base, profiles: form.tiers, seeds: form.seeds };
}

// ---------------------------------------------------------------- results

export type TrialData = { summaries: Record<string, MethodSummary>; timing: any; scenario: any; config: any };

export type TestbedRow = {
  trialId: string;
  method: string;
  tier: string;
  tierLabel: string;
  simulated: boolean;
  placeholder: boolean;
  seed: number;
  accuracy: number | null;
  kappaTemporal: number | null;
  noChangeAccuracy: number | null;
  macroF1: number | null;
  recall: number | null;
  falseAlarm: number | null;
  meanUs: number | null;
  p99Us: number | null;
  costTerms: Record<string, number | null> | null;
  attackTypes: Record<string, AttackTypeScore> | null;
  periods: AttackPeriodScore[] | null;
  controller: ControllerSummary | null;
  scored: number | null;
  nFeatures: number | null;
  memoryBudgetMib: number | null;
};

export const hasTestbedFields = (summary: MethodSummary | undefined): boolean =>
  !!summary && (summary.stream_scores_after_warmup != null || summary.cost_terms_us_per_row != null || summary.attack_periods != null);

/** Benign rows flagged as attacks: from the confusion counts, or else from the per-label table. */
function falseAlarmRate(summary: MethodSummary): number | null {
  const s = summary.scores_after_warmup as unknown as Record<string, number | null | undefined>;
  if (s.fp != null && s.tn != null && s.fp + s.tn > 0) return s.fp / (s.fp + s.tn);
  const types = summary.attack_types_after_warmup;
  if (!types) return null;
  let rows = 0;
  let flagged = 0;
  for (const t of Object.values(types)) if (!t.counted_as_attack) { rows += t.rows; flagged += t.flagged; }
  return rows ? flagged / rows : null;
}

export function testbedRows(manifest: Manifest, trials: Record<string, TrialData>): TestbedRow[] {
  const out: TestbedRow[] = [];
  for (const entry of manifest.trials) {
    if (entry.control) continue;
    const data = trials[entry.trial_id];
    for (const [method, summary] of Object.entries(data?.summaries ?? {})) {
      if (!hasTestbedFields(summary)) continue;
      const stream = summary.stream_scores_after_warmup ?? {};
      out.push({
        trialId: entry.trial_id, method,
        tier: entry.profile?.name ?? "standard", tierLabel: entry.profile?.label ?? "Standard",
        simulated: !!entry.profile?.simulated, placeholder: !!entry.profile?.placeholder,
        seed: entry.seed,
        accuracy: summary.scores_after_warmup?.accuracy ?? null,
        kappaTemporal: stream.kappa_temporal ?? null,
        noChangeAccuracy: stream.no_change_accuracy ?? null,
        macroF1: stream.macro_f1 ?? null,
        recall: summary.scores_after_warmup?.recall ?? null,
        falseAlarm: falseAlarmRate(summary),
        meanUs: summary.latency_us?.mean ?? null,
        p99Us: summary.latency_us?.p99 ?? null,
        costTerms: summary.cost_terms_us_per_row ?? null,
        attackTypes: summary.attack_types_after_warmup ?? null,
        periods: summary.attack_periods ?? null,
        controller: summary.controller ?? null,
        scored: summary.scores_after_warmup?.n ?? null,
        nFeatures: data?.scenario?.n_features ?? null,
        memoryBudgetMib: data?.config?.profile?.budgets?.model_memory_mib ?? null,
      });
    }
  }
  const order = ["no_change", "static", "incremental", "adaptive", "joint", "arf", "srp", "lev_bag"];
  const tierOrder = ["standard", "small_sim", "micro_sim", "memory_sim"];
  const rank = (list: string[], v: string) => (list.indexOf(v) < 0 ? list.length : list.indexOf(v));
  return out.sort((a, b) => rank(order, a.method) - rank(order, b.method) || rank(tierOrder, a.tier) - rank(tierOrder, b.tier) || a.seed - b.seed);
}

export const COST_TERMS = ["C_pre", "C_fs", "C_inf", "C_drift", "C_upd", "C_ret", "C_ctrl", "unattributed"] as const;

export const COST_LABELS: Record<(typeof COST_TERMS)[number], string> = {
  C_pre: "Preparing the data (C_pre)",
  C_fs: "Choosing features (C_fs)",
  C_inf: "Predicting (C_inf)",
  C_drift: "Checking for drift (C_drift)",
  C_upd: "Updating the model (C_upd)",
  C_ret: "Replacing the model (C_ret)",
  C_ctrl: "Controller decisions (C_ctrl)",
  unattributed: "Not attributed to a stage",
};

/** Names of the controller's actions in words: "R5_SHRINK_MODEL_56_TO_28" → R5, "shrink model 56 to 28". */
export function actionWords(action: string): { rule: string; what: string } {
  const match = /^(R\d)_(.*)$/.exec(action);
  if (!match) return { rule: "", what: action.replace(/_/g, " ").toLowerCase() };
  return { rule: match[1], what: match[2].replace(/_/g, " ").toLowerCase() };
}
