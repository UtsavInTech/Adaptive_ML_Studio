import { describe, expect, it } from "vitest";

import { budgetWords, headline, headlineSentence, mistakesWords, perSecond, type Row } from "./headline";

const row = (setting: string, method: string, tier: string, us: number, errors: number, extra: Partial<Row> = {}): Row => ({
  setting, method, tier, mean_us: String(us), errors: String(errors), recall: "0.99", false_alarm_rate: "0.004",
  budget_us: "100.0", ...extra,
});

const ROWS = [
  row("thursday", "joint", "small_sim", 150, 2000), row("thursday", "effort", "small_sim", 70, 2100),
  row("friday", "joint", "small_sim", 140, 2000), row("friday", "effort", "small_sim", 90, 1900),
  row("friday", "joint", "micro_sim", 80, 3000, { budget_us: "50.0" }),
  row("thursday", "incremental", "small_sim", 160, 2500),
];

describe("headline", () => {
  it("averages the two days for one device tier", () => {
    const h = headline(ROWS, "small_sim")!;
    expect(h.days).toEqual(["thursday", "friday"]);
    expect(h.rules.us).toBe(145);
    expect(h.ours.us).toBe(80);
    expect(h.ours.mistakes).toBe(2000);
    expect(h.budgetUs).toBe(100);
    expect(h.timeSaved).toBeCloseTo(1 - 80 / 145);
    expect(h.rulesOver).toBeCloseTo(0.45);
    expect(h.oursOver).toBeCloseTo(-0.2);
  });

  it("is null when a method or the budget is missing, and never invents a number", () => {
    expect(headline(ROWS, "micro_sim")).toBeNull();
    expect(headline([], "small_sim")).toBeNull();
    expect(headline(ROWS.map((r) => ({ ...r, budget_us: "" })), "small_sim")).toBeNull();
    expect(headline(ROWS.map((r) => ({ ...r, recall: "" })), "small_sim")).toBeNull();
  });

  it("uses only days where both methods ran", () => {
    const h = headline(ROWS.filter((r) => !(r.setting === "friday" && r.method === "effort")), "small_sim")!;
    expect(h.days).toEqual(["thursday"]);
    expect(h.rules.us).toBe(150);
  });
});

describe("wording follows the numbers", () => {
  it("names the budget status", () => {
    expect(budgetWords(-0.2)).toBe("inside the budget");
    expect(budgetWords(0.03)).toBe("at the budget");
    expect(budgetWords(0.45)).toBe("45 % over the budget");
  });

  it("says about the same within 10 %, otherwise fewer or more", () => {
    const h = headline(ROWS, "small_sim")!;
    expect(mistakesWords(h)).toBe("about the same number of mistakes");
    expect(mistakesWords({ ...h, ours: { ...h.ours, mistakes: 1000 } })).toBe("50 % fewer mistakes");
    expect(mistakesWords({ ...h, ours: { ...h.ours, mistakes: 3000 } })).toBe("50 % more mistakes");
  });

  it("builds one sentence and does not claim a saving that is not there", () => {
    const h = headline(ROWS, "small_sim")!;
    expect(headlineSentence(h)).toBe(
      "The new controller made about the same number of mistakes using 45 % less computing time. It ran inside the budget; the review's rules ran 45 % over the budget.",
    );
    expect(headlineSentence({ ...h, timeSaved: -0.2 })).toContain("20 % more computing time");
  });

  it("converts time per connection to connections per second", () => {
    expect(perSecond(100)).toBe(10_000);
  });
});
