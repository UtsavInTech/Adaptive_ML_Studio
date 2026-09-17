/** Explanation registry — one place for every concept, metric and formula the UI exposes.
 *
 * Each entry answers three questions, in the order a reader needs them:
 *   what  — what is it, in plain language
 *   how   — how *this project* measures or computes it (with a formula when there is one)
 *   why   — why it matters for the research
 *
 * `pending` marks measures whose final definition is a team decision; the UI must say so rather
 * than imply a settled result.
 */

export type Explanation = {
  term: string;
  what: string;
  how?: string;
  why?: string;
  formula?: string;
  pending?: string;
  ref?: string;
};

export const EXPLANATIONS = {
  // ---------------------------------------------------------------- concepts
  drift: {
    term: "Concept drift",
    what: "The relationship between the input data and the correct answer changes part-way through the stream.",
    how: "In these runs the change is scheduled at a known sample, so the inputs keep the same distribution and only the correct labels move.",
    why: "A model trained only on earlier data can become less accurate after the change. Handling this is the subject of the project.",
  },
  driftTrue: {
    term: "Drift in the data (ground truth)",
    what: "The exact sample where the scheduled concept change happens.",
    how: "Known only because the stream is synthetic: the generator switches concept at a sample index we choose.",
    why: "It is the reference point for measuring how long the detector took to react.",
  },
  prequential: {
    term: "Prequential evaluation",
    what: "Every sample is first predicted, and only afterwards — once its label is known — used for learning.",
    how: "The pipeline never learns from a sample before predicting it, so no result is inflated by data the model already saw.",
    why: "It is the standard way to score a model on a stream, where there is no separate test set.",
  },
  adwin: {
    term: "ADWIN",
    what: "A drift detector that watches recent prediction errors through a window that grows and shrinks.",
    how: "When the older and newer halves of that window differ by more than a statistical bound, it reports a change. The pipeline acts only when the error rate has risen.",
    why: "It gives the pipeline a signal to adapt, without anyone telling it that the data changed.",
    ref: "[5] Bifet & Gavaldà, 2007",
  },
  staticMethod: {
    term: "Static baseline (train once)",
    what: "A model trained on the first samples and then frozen — it never learns again.",
    how: "It sees exactly the same samples as the adaptive pipeline and is measured the same way.",
    why: "It stands for the conventional pipeline the review paper contrasts with: train once, deploy, retrain occasionally.",
  },
  adaptiveMethod: {
    term: "Adaptive pipeline",
    what: "Keeps learning from each labelled sample, watches its own error rate, and replaces its model when drift is detected.",
    how: "Preprocessing, feature selection, detection, adaptation and prediction all run on the same stream, and each step's cost is measured.",
    why: "This is the integrated pipeline the review paper proposes (gap G1).",
  },
  incremental: {
    term: "Incremental learning",
    what: "The model updates itself one sample at a time instead of being retrained from scratch.",
    how: "A Hoeffding tree learns from each labelled sample as it arrives.",
    why: "It keeps adaptation affordable on a stream, where retraining on all past data would be too slow.",
  },
  arf: {
    term: "Adaptive Random Forest",
    what: "An ensemble of trees, each with its own drift detector, from the streaming literature.",
    how: "Included as a comparator from our own references, measured under identical conditions.",
    why: "It shows what a stronger, heavier adaptive method costs in time and memory.",
    ref: "[20] Gomes et al., 2017",
  },
  featureSelection: {
    term: "Online feature selection",
    what: "Continuously ranks the input features and keeps only the most useful ones.",
    how: "Features are ranked by the size of their weight in an online linear model; the top k are kept. The applied set changes only when a model is (re)built.",
    why: "Fewer features mean less computation per sample — one of the levers under a resource budget.",
    ref: "[4] Hoi et al., 2012 (truncation step)",
  },
  adaptation: {
    term: "Model adaptation",
    what: "What the pipeline does once drift is confirmed: it puts a new model in charge.",
    how: "A replacement model trains on samples after the warning while the current model keeps serving; it is promoted once it has enough of them.",
    why: "Adapting has a cost in time and memory, which is exactly what this project measures alongside accuracy.",
  },
  replacement: {
    term: "Replacement model",
    what: "The candidate model being trained in the background during adaptation.",
    how: "It learns only from samples after the warning, so it is not shaped by the outdated concept, and is promoted after a fixed number of samples.",
    why: "Training it in parallel avoids a blind spot: the old model keeps predicting until the new one is ready.",
    ref: "background-learner strategy of [20]",
  },

  // ---------------------------------------------------------------- performance metrics
  accuracy: {
    term: "Accuracy",
    what: "The share of predictions that were correct.",
    formula: "accuracy = correct predictions ÷ total predictions",
    how: "Computed over a sliding window of recent samples, and separately over the whole run after warm-up.",
    why: "It is the headline measure of whether the model still fits the current data.",
  },
  windowedAccuracy: {
    term: "Windowed accuracy",
    what: "Accuracy measured over the most recent N samples rather than the whole run.",
    formula: "accuracy = correct ÷ N   (N = the selected window)",
    how: "The window slides forward with the stream, so a drop right after a drift is visible instead of being diluted by the run's history.",
    why: "A whole-run average would hide the very effect this project is about.",
  },
  f1: {
    term: "F1 score",
    what: "A single number balancing how often the positive predictions are right and how many positives are found.",
    formula: "F1 = 2 × precision × recall ÷ (precision + recall)",
    how: "Precision is correct positives ÷ all predicted positives; recall is correct positives ÷ all actual positives. Both come from the same confusion counts as accuracy.",
    why: "Accuracy alone can look good when classes are uneven; F1 does not.",
  },
  latency: {
    term: "Processing time per sample",
    what: "How long the pipeline takes to handle one sample.",
    formula: "preprocess + select + predict + detect + adapt + update",
    how: "Measured inside the engine with a high-resolution clock. It excludes network, display and the cost of recording measurements.",
    why: "Real-time and edge settings care about time per sample, not just accuracy — the pairing this project exists to measure.",
  },
  p95: {
    term: "p95 processing time",
    what: "95 % of samples were processed faster than this.",
    how: "Taken from the per-sample times recorded after warm-up, excluding monitoring.",
    why: "The average hides occasional slow samples; p95 shows the slower end of normal behaviour.",
  },
  p99: {
    term: "p99 processing time",
    what: "99 % of samples were processed faster than this.",
    how: "Same measurement as p95, at a stricter percentile.",
    why: "Shows the rare worst cases, such as the moment a model is rebuilt.",
  },
  throughput: {
    term: "Throughput",
    what: "How many samples the engine can process per second.",
    formula: "throughput = samples ÷ engine running time",
    how: "Measured at full speed; during a paced run it simply follows the configured stream rate.",
    why: "It sets the ceiling on the stream rate a deployment could keep up with.",
  },
  cpuPerSample: {
    term: "CPU time per sample",
    what: "Approximate processor time used to handle one sample.",
    formula: "CPU time per sample = process CPU time ÷ samples",
    how: "Read from the engine process's own CPU accounting over the run.",
    why: "It is the cost side of the accuracy–cost comparison, and less sensitive to waiting than wall-clock time.",
  },
  rss: {
    term: "Memory (RSS)",
    what: "How much memory the running engine process occupies.",
    how: "Sampled once a second from outside the engine, so watching it costs the engine nothing. It includes Python and the libraries (~120 MB before any model).",
    why: "Memory is a hard limit on constrained devices, which is why it is reported next to accuracy.",
  },
  modelSize: {
    term: "Model size",
    what: "An estimate of the memory the learned model itself occupies.",
    how: "River's own estimate. It varies by about 0.1 % between identical runs, so it counts as a measurement rather than an exact value.",
    why: "It separates the model's footprint from the process overhead — an ensemble can be hundreds of times larger than a single tree.",
  },
  monitor: {
    term: "Monitoring overhead",
    what: "The time the system spends recording its own measurements.",
    how: "Measured separately and never counted inside the processing time it reports.",
    why: "Measuring a system changes it; reporting this number keeps the other numbers honest.",
  },
  response: {
    term: "Response time",
    what: "From a sample's scheduled arrival to the moment it is finished, including any waiting.",
    how: "Only meaningful in paced runs, where samples arrive on a schedule rather than as fast as possible.",
    why: "It shows whether the pipeline keeps up with the incoming rate.",
  },
  backlog: {
    term: "Backlog",
    what: "Samples that have arrived but are not processed yet.",
    how: "Counted at the end of each block in paced runs.",
    why: "A growing backlog means the stream is arriving faster than the pipeline can handle.",
  },

  // ---------------------------------------------------------------- drift/adaptation measures
  detectionDelay: {
    term: "Detection delay",
    what: "How many samples passed between the change in the data and the detector reacting.",
    formula: "detection delay = detection sample − true drift sample",
    how: "Measurable because the stream is synthetic and the drift position is known in advance.",
    why: "Every sample of delay is a sample predicted with an out-of-date model.",
  },
  recovery: {
    term: "Recovery measure",
    what: "How long it takes accuracy to return to roughly its pre-drift level.",
    how: "Shown as a reference computation: samples until windowed accuracy comes back within a tolerance of the pre-drift level and stays there.",
    pending: "The final recovery and stability definition is pending the team's decision, so this is reported as a reference computation, not as a result.",
    why: "It is the natural way to express how quickly adaptation takes effect — once the team fixes the definition.",
  },
  stability: {
    term: "Accuracy stability",
    what: "How steady accuracy stays as the data changes.",
    how: "Reported through measured quantities: accuracy before the drift, the lowest point after it, and accuracy after adaptation.",
    pending: "No single formula is claimed: the definition is a team decision.",
    why: "It is the title concept of the project, kept as measurements until the team agrees on the formula.",
  },
  overhead: {
    term: "Computational overhead",
    what: "The extra computation that continuous adaptation costs.",
    pending: "Definition pending the team's decision. Candidate measurements: CPU time per sample, or the adaptive pipeline's processing time minus the static baseline's.",
    why: "The review paper asks for accuracy and cost together; the platform records both candidates so either definition can be computed later.",
  },

  // ---------------------------------------------------------------- resources / profiles
  edge: {
    term: "Simulated edge profile",
    what: "A constrained setting imposed in software on this computer.",
    how: "Budgets (compute share, memory, features) are enforced by the pipeline itself. No edge device is involved and no slower CPU is emulated.",
    why: "It exercises resource-aware adaptation honestly, without claiming hardware results the project does not have.",
  },
  budget: {
    term: "Compute budget",
    what: "The processing time per sample the simulated profile allows.",
    formula: "budget per sample = compute share ÷ stream rate",
    how: "Derived from a share of one CPU core at the configured rate. Current values are placeholders until the research member sets them.",
    why: "It is what makes adaptation depend on resources as well as drift (gap G5).",
  },
  stride: {
    term: "Update stride",
    what: "Learning from every n-th labelled sample instead of every one.",
    how: "Raised by the governor when measured processing time stays above the budget, and lowered again when there is room.",
    why: "It is the cheapest way to shed work, and it makes the accuracy–cost trade-off visible in a single run.",
  },

  // ---------------------------------------------------------------- method / provenance
  sampleIndex: {
    term: "Why the sample index?",
    what: "Charts use the position in the stream rather than clock time.",
    how: "Drift is placed at a sample index and every sample is processed, so the same run at a different stream rate produces the same predictions.",
    why: "It keeps runs comparable across stream rates — which is what the cross-scale comparison needs.",
  },
  provenance: {
    term: "Where these numbers come from",
    what: "Every figure is measured on the machine named here, in a run whose configuration is stored.",
    how: "The environment (CPU, memory, OS, power source), the configuration and the seeds are saved with each run.",
    why: "Timings depend on hardware, so a result without its environment cannot be compared to anything.",
  },
  seed: {
    term: "Seed",
    what: "The number that fixes every random choice in a run.",
    how: "Derived per component, so the same seed reproduces the same stream and the same predictions.",
    why: "It is what makes a run repeatable rather than a one-off observation.",
  },
  configHash: {
    term: "Configuration hash",
    what: "A fingerprint of the exact settings a run used.",
    how: "A SHA-256 over the resolved configuration, defaults included.",
    why: "Two runs with the same fingerprint were configured identically — no need to compare files by eye.",
  },
  reproducibility: {
    term: "Reproducibility check",
    what: "Running the same configuration again and comparing the predictions.",
    how: "Each trial is re-run in a fresh process; predictions are compared by hash. Timings are expected to differ.",
    why: "It demonstrates that a result can be reproduced, which the review paper lists as a gap (G6).",
  },
  warmup: {
    term: "Warm-up",
    what: "The first samples of a run, used to train every method before measurement starts.",
    how: "Metrics exclude these samples so a method is not judged on its first minutes of learning.",
    why: "It puts every method on equal footing before the comparison begins.",
  },
  tradeoff: {
    term: "Accuracy vs cost",
    what: "Each point is one method: how accurate it was, and how much processor time it used per sample.",
    how: "Both axes are measured in the same runs, on the same machine, with trials run one at a time.",
    why: "The review paper's central gap is that accuracy is usually reported without its cost. This chart puts them side by side.",
  },
  flip: {
    term: "Label-flip fraction",
    what: "How large a concept change is: the share of the input space whose correct label changes.",
    formula: "flip fraction = |θ_after² − θ_before²| ÷ 200",
    how: "Known exactly for this generator, because the two concepts are simple thresholds over uniformly drawn inputs.",
    why: "It puts a number on 'how big was the drift', so detection results can be compared between scenarios.",
  },
} satisfies Record<string, Explanation>;

/** Keys stay a narrow union for type-safe ids, while values widen to Explanation so that optional
 *  fields (formula, how, why, pending, ref) are accessible to consumers. */
export type ExplainId = keyof typeof EXPLANATIONS;

export const EXPLANATION_MAP: Record<ExplainId, Explanation> = EXPLANATIONS;

/** Never throws. An id with no entry renders a visible placeholder instead of taking down the page it
 *  sits on — a mistyped id cost the whole Live screen once. `explain.test.ts` catches them in CI. */
export const explanation = (id: ExplainId): Explanation =>
  EXPLANATION_MAP[id] ?? { term: String(id), what: "No explanation has been written for this term yet." };
