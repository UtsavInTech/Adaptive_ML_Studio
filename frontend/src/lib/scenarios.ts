/** Human-readable names for the live presets.
 *
 *  The backend's own `name` and `description` are the exact specification of what will run, and they
 *  stay visible under "what this scenario runs". What they are not is a first thing to read: "Demo —
 *  abrupt concept drift (validated scenario)" tells a visitor nothing until they already know what
 *  the project does. These titles say what the reader will see; nothing here changes what is run.
 */

export type ScenarioCopy = {
  title: string;
  said: string;
  /** What to keep an eye on while it runs — the reason to choose this scenario over another. */
  watch: string;
};

const SCENARIOS: Record<string, ScenarioCopy> = {
  demo_abrupt: {
    title: "Concept drift demonstration",
    said: "Watch the model respond when the data's underlying pattern changes part-way through the stream.",
    watch:
      "Accuracy holds steady, drops sharply after the change, and returns once a replacement model has been promoted. The static baseline does not recover.",
  },
  demo_edge: {
    title: "Simulated edge demonstration",
    said: "The same experiment under tighter processing and memory budgets, enforced in software on this computer.",
    watch:
      "The same drift and recovery, plus the resource governor's decisions — learning from fewer samples, or keeping fewer features, to stay inside the budget.",
  },
  free_play: {
    title: "Free play",
    said: "A stable stream with no scheduled change — inject a concept drift yourself and watch what follows.",
    watch: "Nothing happens until you inject a drift. After that, detection and adaptation proceed as in any other run.",
  },
  hard_scenario: {
    title: "Hard scenario",
    said: "Stronger label noise and an earlier drift — kept on record as a configuration where detection is unreliable.",
    watch:
      "The detector may never fire. That negative result is deliberately preserved rather than tuned away, and is reported as a limitation.",
  },
};

export const scenarioCopy = (key: string, fallback?: string): ScenarioCopy =>
  SCENARIOS[key] ?? { title: fallback ?? key, said: "", watch: "" };
