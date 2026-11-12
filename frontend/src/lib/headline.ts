/** The project's main comparison, in plain terms: the review's rules against the new controller on
 *  the days that were not used to design it. Pure functions over a report's settings table, so the
 *  Home and Findings pages show the same numbers and the wording follows the data. */

export type Row = Record<string, string>;

export type Side = {
  /** Mean time per connection, µs. */
  us: number;
  /** Share of attack connections flagged, 0–1. */
  caught: number;
  /** Share of normal connections flagged, 0–1. */
  falseAlarms: number;
  /** Mean wrong decisions per day. */
  mistakes: number;
};

export type Headline = {
  days: string[];
  budgetUs: number;
  rules: Side;
  ours: Side;
  /** How much less time per connection the new controller used, 0–1 (negative if it used more). */
  timeSaved: number;
  /** Time over the budget as a share of it; 0 or below means inside the budget. */
  rulesOver: number;
  oursOver: number;
};

const num = (value: string | undefined): number | null => {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const mean = (values: number[]): number => values.reduce((a, b) => a + b, 0) / values.length;

function side(rows: Row[]): Side | null {
  const pick = (key: string) => rows.map((r) => num(r[key]));
  const fields = { us: pick("mean_us"), caught: pick("recall"), falseAlarms: pick("false_alarm_rate"), mistakes: pick("errors") };
  if (!rows.length || Object.values(fields).some((values) => values.some((v) => v == null))) return null;
  return {
    us: mean(fields.us as number[]), caught: mean(fields.caught as number[]),
    falseAlarms: mean(fields.falseAlarms as number[]), mistakes: mean(fields.mistakes as number[]),
  };
}

/** Averages over the days present for one device tier; null when either method or the budget is missing. */
export function headline(rows: Row[], tier: string, days: string[] = ["thursday", "friday"]): Headline | null {
  const of = (method: string) => rows.filter((r) => r.tier === tier && r.method === method && days.includes(r.setting));
  const rulesRows = of("joint");
  const oursRows = of("effort");
  const present = days.filter((d) => rulesRows.some((r) => r.setting === d) && oursRows.some((r) => r.setting === d));
  const rules = side(rulesRows.filter((r) => present.includes(r.setting)));
  const ours = side(oursRows.filter((r) => present.includes(r.setting)));
  const budgetUs = num(oursRows[0]?.budget_us);
  if (!rules || !ours || budgetUs == null || budgetUs <= 0) return null;
  return {
    days: present, budgetUs, rules, ours,
    timeSaved: 1 - ours.us / rules.us,
    rulesOver: rules.us / budgetUs - 1,
    oursOver: ours.us / budgetUs - 1,
  };
}

/** Connections one processor core can check per second at a given time per connection. */
export const perSecond = (us: number): number => 1e6 / us;

/** "inside the budget", "at the budget" (within 5 %), or "38 % over the budget". */
export function budgetWords(over: number): string {
  if (over <= 0) return "inside the budget";
  if (over <= 0.05) return "at the budget";
  return `${Math.round(over * 100)} % over the budget`;
}

/** How the new controller's mistakes compare, in words chosen by the data (10 % counts as "about the same"). */
export function mistakesWords(h: Headline): string {
  const ratio = h.ours.mistakes / h.rules.mistakes;
  if (ratio < 0.9) return `${Math.round((1 - ratio) * 100)} % fewer mistakes`;
  if (ratio > 1.1) return `${Math.round((ratio - 1) * 100)} % more mistakes`;
  return "about the same number of mistakes";
}

/** One sentence that states the comparison and nothing the numbers do not show. */
export function headlineSentence(h: Headline): string {
  const time = h.timeSaved > 0.02
    ? `${Math.round(h.timeSaved * 100)} % less computing time`
    : h.timeSaved < -0.02 ? `${Math.round(-h.timeSaved * 100)} % more computing time` : "the same computing time";
  return `The new controller made ${mistakesWords(h)} using ${time}. It ran ${budgetWords(h.oursOver)}; the review's rules ran ${budgetWords(h.rulesOver)}.`;
}
