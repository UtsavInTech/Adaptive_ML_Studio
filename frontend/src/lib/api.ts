/** Typed access to the backend. Every number shown in the UI comes from these responses. */

export type Lifecycle =
  | "starting" | "loading" | "warming_up" | "running" | "paused" | "summarizing" | "completed" | "stopped" | "error";

export type BlockRecord = {
  method: string;
  block: number;
  start: number;
  n: number;
  tp: number; fp: number; tn: number; fn: number;
  service_mean_ns: number;
  service_p95_ns: number;
  service_max_ns: number;
  model_version: number;
  n_features: number;
  model_size_bytes: number | null;
  background: boolean;
  adapting: boolean;
  learning: boolean;
  update_stride: number;
  over_budget?: boolean;
  [stage: string]: number | boolean | string | null | undefined;
};

export type EngineBlock = {
  block: number; start: number; n: number; cpu_ms: number; wall_ms: number; lifecycle: Lifecycle;
  response_mean_ms?: number | null; response_max_ms?: number | null; backlog?: number;
};

export type EventRecord = {
  i: number;
  method: string | null;
  type: string;
  reason?: string;
  action?: string;
  [field: string]: unknown;
};

export type ResourceSample = { t: number; cpu_percent: number; rss_mb: number };

export type Extras = {
  sample: number;
  concept: { variant: number; threshold: number | null };
  axes: [string, string];
  points: [number, number, number][];
  methods: Record<string, {
    model_version: number;
    features: string[];
    ranking: [string, number][];
    update_stride: number;
    adapting: boolean;
    replacement_trained: number | null;
    learning: boolean;
    detector?: { width: number; error_estimate: number };
    governor?: { constrained: boolean; budget_us: number };
  }>;
};

export type Scores = { n: number; accuracy: number | null; f1: number | null; precision: number | null; recall: number | null };
export type Latency = { mean: number | null; p50: number | null; p95: number | null; p99: number | null; max: number | null };

export type MethodSummary = {
  method: string;
  scores_after_warmup: Scores;
  latency_us: Latency;
  stage_mean_us: Record<string, number>;
  adaptations: { count: number; failed: number; by_action: Record<string, number>; duration_us_mean: number | null };
  drift_detections_error_increase: number;
  final_model: { version: number; features: string[]; size_bytes: number | null };
  stability_reference: StabilityReference | null;
  predictions_sha256: string;
};

export type Segment = { range: [number, number]; accuracy: number | null; f1: number | null } | null;

export type StabilityReference = {
  reference_computation: true;
  parameters: Record<string, number>;
  drift_index: number;
  pre_drift: Segment;
  post_drift_early: Segment;
  post_drift_late: Segment;
  post_adaptation: Segment;
  min_windowed_accuracy: number | null;
  detection_delay_samples: number | null;
  adaptation_index: number | null;
  recovery_samples: number | null;
};

export type Timing = {
  samples: number; rate: number | null; total_ms: number; paused_ms: number;
  engine_throughput_per_s: number | null; monitor_us_per_sample: number | null; monitor_share_of_total: number | null;
  cpu_us_per_sample: number | null; peak_rss_mb: number; response_ms: { mean: number; p95: number; max: number } | null;
  budget_us_per_sample: number | null; timing_dependent_behaviour: boolean;
  governor_decisions: Record<string, number>;
};

export type Profile = { name: string; label: string; simulated: boolean; placeholder: boolean; budgets: Record<string, unknown> };

export type Manifest = {
  id: string; kind: string; name: string; status: string; error: string | null;
  created_utc: string; finished_utc: string | null; config_hash: string;
  provenance: { measured_on: string; simulated_profiles: string[]; placeholder_budgets: boolean; real_data: boolean };
  environment: Record<string, unknown>;
  app_version: { commit: string | null; uncommitted_changes: boolean };
  trials: TrialEntry[];
  reproducibility?: {
    rerun_of: string; trials_compared: number; identical: number;
    per_trial: { trial_id: string; identical_predictions: boolean; timing_dependent: boolean }[]; note: string;
  };
  note: string;
};

export type TrialEntry = {
  trial_id: string; status: string; seed: number; rate: number | null;
  profile: { name: string; label: string; simulated: boolean; placeholder: boolean };
  scenario: { name: string; real: boolean; length: number; noise: number; drifts: GroundTruthDrift[] };
  timing: Partial<Timing>;
  methods: Record<string, { accuracy: number | null; f1: number | null; latency_us: Latency; adaptations: number; predictions_sha256: string }>;
};

export type GroundTruthDrift = {
  index: number; width: number; from_variant: number; to_variant: number; label_flip_fraction: number; kind: string;
};

export type Preset = { name: string; description: string; config: Record<string, unknown> };

export type LiveSnapshot = {
  active: boolean;
  name: string;
  config: Record<string, any>;
  status: { lifecycle: Lifecycle; sample: number; total: number };
  blocks: Record<string, BlockRecord[]>;
  engine: EngineBlock[];
  events: EventRecord[];
  resources: ResourceSample[];
  extras: Extras | null;
  final: { experiment_id: string; status: string; summaries: Record<string, MethodSummary>; timing: Timing; config: any } | null;
  error: { message: string; traceback?: string } | null;
};

export type TrialSeries = {
  window: number;
  methods: Record<string, {
    x: number[]; accuracy: (number | null)[]; f1: (number | null)[];
    service_mean_us: number[]; service_p95_us: number[]; model_size_kb: (number | null)[];
    n_features: number[]; update_stride: number[]; model_version: number[];
    stage_mean_us: Record<string, number[]>;
  }>;
};

export class ApiError extends Error {
  constructor(readonly status: number, readonly detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json", ...init?.headers } : init?.headers,
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) throw new ApiError(response.status, payload?.detail ?? payload ?? response.statusText);
  return payload as T;
}

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });

export const api = {
  health: () => request<{ status: string; python: string; river: string; live_active: boolean; experiment_active: boolean }>("/api/health"),
  presets: () => request<{ live: Record<string, Preset>; experiments: Record<string, Preset> }>("/api/presets"),
  profiles: () => request<Record<string, Profile>>("/api/profiles"),
  scenarios: () => request<{ sea: { thresholds: Record<string, number>; label_flip_fraction: Record<string, number> } }>("/api/scenarios"),
  traceability: () => request<{ gaps: Record<string, string>; components: any[] }>("/api/method/traceability"),
  validate: (body: unknown) => post<{ valid: boolean; config: unknown; trials?: number }>("/api/config/validate", body),

  liveState: () => request<LiveSnapshot | { active: false }>("/api/live/state"),
  startLive: (body: { preset?: string; profile?: string; config?: unknown; name?: string }) => post<{ name: string }>("/api/live", body),
  liveCommand: (command: "pause" | "resume" | "stop" | "inject-drift", body?: unknown) => post(`/api/live/${command}`, body),

  experiments: () => request<Manifest[]>("/api/experiments"),
  experiment: (id: string) => request<Manifest>(`/api/experiments/${encodeURIComponent(id)}`),
  trialSummary: (id: string, trial: string) =>
    request<{ status: string; config: any; scenario: any; timing: Timing; summaries: Record<string, MethodSummary> }>(
      `/api/experiments/${encodeURIComponent(id)}/trials/${encodeURIComponent(trial)}/summary`),
  trialSeries: (id: string, trial: string, window = 500) =>
    request<TrialSeries>(`/api/experiments/${encodeURIComponent(id)}/trials/${encodeURIComponent(trial)}/series?window=${window}`),
  trialEvents: (id: string, trial: string) =>
    request<EventRecord[]>(`/api/experiments/${encodeURIComponent(id)}/trials/${encodeURIComponent(trial)}/events`),
  startExperiment: (body: { preset?: string; config?: unknown }) => post<{ started: string; trials: number }>("/api/experiments", body),
  job: () => request<{ active: boolean; progress: JobProgress | null }>("/api/experiments/job"),
  stopJob: () => post("/api/experiments/job/stop"),
  rerun: (id: string) => post<{ rerun_of: string }>(`/api/experiments/${encodeURIComponent(id)}/rerun`),
  exportUrl: (id: string) => `/api/experiments/${encodeURIComponent(id)}/export`,
};

export type JobProgress = {
  name: string; status: string; done: number; total: number | null;
  trial: string | null; experiment_id: string | null; error?: string | null;
};
