import { describe, expect, it } from "vitest";

import { parseInline, parseMarkdown, safeHref } from "./markdown";

describe("parseMarkdown", () => {
  it("reads headings, paragraphs, lists, images and tables", () => {
    const blocks = parseMarkdown([
      "# Report — quick",
      "",
      "69 trials. **Simulated** tiers,",
      "placeholder budgets.",
      "",
      "| Method | κ-temporal | Mean µs |",
      "|---|--:|:-:|",
      "| Joint | 0.65 | 227.3 |",
      "| ARF | 0.92 | 1270.7 |",
      "",
      "![fig1](figures/fig1.png)",
      "",
      "- `core`: `run-1`",
      "- second item",
      "  continues here",
    ].join("\n"));
    expect(blocks.map((b) => b.kind)).toEqual(["heading", "paragraph", "table", "image", "list"]);
    expect(blocks[1]).toEqual({
      kind: "paragraph",
      text: [{ kind: "text", text: "69 trials. " }, { kind: "strong", children: [{ kind: "text", text: "Simulated" }] }, { kind: "text", text: " tiers, placeholder budgets." }],
    });
    const table = blocks[2] as Extract<(typeof blocks)[number], { kind: "table" }>;
    expect(table.align).toEqual(["left", "right", "center"]);
    expect(table.rows).toHaveLength(2);
    expect(table.rows[1][2]).toEqual([{ kind: "text", text: "1270.7" }]);
    expect(blocks[3]).toEqual({ kind: "image", alt: "fig1", src: "figures/fig1.png" });
    const list = blocks[4] as Extract<(typeof blocks)[number], { kind: "list" }>;
    expect(list.items).toHaveLength(2);
    expect(list.items[1]).toEqual([{ kind: "text", text: "second item continues here" }]);
  });

  it("keeps raw HTML as text", () => {
    expect(parseMarkdown("<script>alert(1)</script>")).toEqual([
      { kind: "paragraph", text: [{ kind: "text", text: "<script>alert(1)</script>" }] },
    ]);
  });

  it("reads inline code, emphasis and links", () => {
    expect(parseInline("see *this* and [the plan](PLAN.md) `x`")).toEqual([
      { kind: "text", text: "see " },
      { kind: "em", children: [{ kind: "text", text: "this" }] },
      { kind: "text", text: " and " },
      { kind: "link", href: "PLAN.md", children: [{ kind: "text", text: "the plan" }] },
      { kind: "text", text: " " },
      { kind: "code", text: "x" },
    ]);
  });

  it("refuses links that could run script", () => {
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("data:text/html,x")).toBeNull();
    expect(safeHref("https://example.org/a")).toBe("https://example.org/a");
    expect(safeHref("PLAN.md")).toBe("PLAN.md");
  });
});
