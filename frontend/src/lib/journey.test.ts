import { describe, expect, it } from "vitest";

import { JOURNEY, journeyIndex } from "./journey";
import { href, parseHash } from "./router";

describe("walkthrough", () => {
  it("has six steps, each with a page that routes to itself", () => {
    expect(JOURNEY.map((s) => s.page)).toEqual(["home", "live", "experiments", "testbed", "findings", "method"]);
    for (const step of JOURNEY) expect(parseHash(href({ page: step.page })).page).toBe(step.page);
  });

  it("counts a single saved run as part of Experiments", () => {
    expect(journeyIndex({ page: "experiment", id: "x" })).toBe(2);
    expect(journeyIndex({ page: "findings" })).toBe(4);
  });
});

describe("a saved run belongs to the step it was opened from", () => {
  it("is part of the Testbed when opened from there, otherwise Experiments", () => {
    const run = { page: "experiment", id: "x" } as const;
    expect(JOURNEY[journeyIndex(run, "testbed")].page).toBe("testbed");
    expect(JOURNEY[journeyIndex(run, "experiments")].page).toBe("experiments");
    expect(JOURNEY[journeyIndex(run)].page).toBe("experiments");
  });
});
