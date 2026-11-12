import { describe, expect, it } from "vitest";

import { verdict } from "./verdict";

describe("verdict of a two-model replay", () => {
  it("counts wrong predictions and says who made fewer", () => {
    const v = verdict(0.98, 0.93, 11_000, true)!;
    expect(v.learner.wrong).toBe(220);
    expect(v.frozen.wrong).toBe(770);
    expect(v.sentence).toBe("The model that keeps learning made 550 fewer wrong predictions (220 against 770, out of 11,000 rows).");
  });

  it("does not claim a difference below half a point", () => {
    expect(verdict(0.981, 0.979, 10_000, true)!.sentence).toContain("about the same");
  });

  it("says so when keeping on learning did worse, and marks an unfinished run", () => {
    const v = verdict(0.9, 0.95, 1_000, false)!;
    expect(v.sentence).toContain("The model trained once made 50 fewer wrong predictions so far");
    expect(v.sentence).toContain("did not help");
  });

  it("is null before anything is scored", () => {
    expect(verdict(null, 0.9, 100, true)).toBeNull();
    expect(verdict(0.9, 0.9, 0, true)).toBeNull();
  });
});
