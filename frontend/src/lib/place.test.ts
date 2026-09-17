import { describe, expect, it } from "vitest";

import { GAP, MARGIN, placePopover, type Box, type Size } from "./place";

/** A 360x274 panel is what the real popover measures at its common size. */
const PANEL: Size = { width: 360, height: 274 };
const TRIGGER = (top: number, left: number): Box => ({ top, left, width: 16, height: 16 });
const SCREEN = (width: number, height = 900): Size => ({ width, height });

/** The panel must sit entirely on screen, clear of the margins, whenever it possibly can. */
const assertOnScreen = (top: number, left: number, panel: Size, viewport: Size) => {
  expect(top).toBeGreaterThanOrEqual(MARGIN);
  expect(left).toBeGreaterThanOrEqual(MARGIN);
  expect(top + panel.height).toBeLessThanOrEqual(viewport.height - MARGIN);
  expect(left + panel.width).toBeLessThanOrEqual(viewport.width - MARGIN);
};

describe("placePopover", () => {
  it("sits just below a trigger in the middle of the viewport", () => {
    const anchor = TRIGGER(400, 700);
    const { top, left, side, clamped } = placePopover(anchor, PANEL, SCREEN(1440));
    expect(side).toBe("below");
    expect(clamped).toBe(false);
    expect(top).toBe(anchor.top + anchor.height + GAP);
    // Horizontally centred on the trigger.
    expect(left).toBe(anchor.left + anchor.width / 2 - PANEL.width / 2);
    assertOnScreen(top, left, PANEL, SCREEN(1440));
  });

  it("flips above a trigger near the bottom edge", () => {
    const anchor = TRIGGER(850, 700);
    const { top, side } = placePopover(anchor, PANEL, SCREEN(1440));
    expect(side).toBe("above");
    expect(top).toBe(anchor.top - PANEL.height - GAP);
    assertOnScreen(top, 0 + MARGIN, PANEL, SCREEN(1440));
  });

  it("stays below a trigger near the top edge, where there is no room above", () => {
    const anchor = TRIGGER(10, 700);
    const { top, side } = placePopover(anchor, PANEL, SCREEN(1440));
    expect(side).toBe("below");
    expect(top).toBe(anchor.top + anchor.height + GAP);
    assertOnScreen(top, 0 + MARGIN, PANEL, SCREEN(1440));
  });

  it("clamps into view when neither side has room", () => {
    // A short viewport: below overflows and above would be off the top.
    const anchor = TRIGGER(160, 700);
    const viewport = SCREEN(1440, 320);
    const { top, clamped } = placePopover(anchor, PANEL, viewport);
    expect(clamped).toBe(true);
    assertOnScreen(top, 0 + MARGIN, PANEL, viewport);
  });

  it("never positions the panel off the top when it is taller than the viewport", () => {
    const tall: Size = { width: 360, height: 1000 };
    const { top, clamped } = placePopover(TRIGGER(400, 700), tall, SCREEN(1440));
    expect(clamped).toBe(true);
    expect(top).toBe(MARGIN);
  });

  it("clamps horizontally against the left edge", () => {
    const { left } = placePopover(TRIGGER(400, 4), PANEL, SCREEN(1440));
    expect(left).toBe(MARGIN);
  });

  it("clamps horizontally against the right edge", () => {
    const viewport = SCREEN(1280);
    const { left } = placePopover(TRIGGER(400, 1270), PANEL, viewport);
    expect(left).toBe(viewport.width - PANEL.width - MARGIN);
    assertOnScreen(400 + 16 + GAP, left, PANEL, viewport);
  });

  it("returns document coordinates by adding the scroll offset", () => {
    const anchor = TRIGGER(400, 700);
    const unscrolled = placePopover(anchor, PANEL, SCREEN(1440));
    const scrolled = placePopover(anchor, PANEL, SCREEN(1440), { x: 40, y: 900 });
    // Same visual position, expressed relative to the document instead of the viewport.
    expect(scrolled.top).toBe(unscrolled.top + 900);
    expect(scrolled.left).toBe(unscrolled.left + 40);
  });

  it.each([1280, 1440, 1920])("keeps the panel on screen at %ipx wide", (width) => {
    const viewport = SCREEN(width);
    // Triggers across the full width, including both extremes.
    for (const x of [0, 8, width / 2, width - 40, width - 1]) {
      const { top, left } = placePopover(TRIGGER(400, x), PANEL, viewport);
      assertOnScreen(top, left, PANEL, viewport);
    }
  });

  it.each([1280, 1440, 1920])("keeps the panel on screen at every height at %ipx wide", (width) => {
    const viewport = SCREEN(width);
    // Triggers from the top edge to the bottom edge: one of below / above / clamped must always work.
    for (let y = 0; y <= viewport.height - 16; y += 37) {
      const { top, left } = placePopover(TRIGGER(y, width / 2), PANEL, viewport);
      assertOnScreen(top, left, PANEL, viewport);
    }
  });
});
