/// <reference types="vite/client" />

import { describe, expect, it } from "vitest";

import { EXPLANATIONS } from "./explain";

/** Every source file in the app, as text. Uses Vite's own glob rather than node's `fs` so the test
 *  runs under the app's TypeScript configuration without pulling in extra type packages. */
const SOURCES = import.meta.glob("../**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/** Every way an explanation id reaches the UI: the button, the `explain` prop, and the tables that
 *  carry one per row. A typo in any of them used to crash the page it sat on. */
const PATTERNS = [
  /ExplainButton\s+id="([A-Za-z0-9_]+)"/g,
  /\bexplain="([A-Za-z0-9_]+)"/g,
  /\bexplain:\s*"([A-Za-z0-9_]+)"/g,
];

const referenced = new Map<string, string>();
for (const [path, text] of Object.entries(SOURCES)) {
  if (/\.test\.tsx?$/.test(path)) continue;
  for (const pattern of PATTERNS) {
    for (const match of text.matchAll(pattern)) referenced.set(match[1], path);
  }
}

describe("explanation ids", () => {
  it("finds the ids used across the app", () => {
    expect(referenced.size).toBeGreaterThan(10);
  });

  it("every id used in the UI has an explanation", () => {
    const missing = [...referenced]
      .filter(([id]) => !(id in EXPLANATIONS))
      .map(([id, path]) => `${id} (${path})`);
    expect(missing).toEqual([]);
  });

  it("every explanation says what it is", () => {
    for (const [id, entry] of Object.entries(EXPLANATIONS)) {
      expect(entry.term, `${id} needs a term`).toBeTruthy();
      expect(entry.what, `${id} needs a "what it is"`).toBeTruthy();
    }
  });
});
