/** Placement maths for the explanation popover.
 *
 * Deliberately free of the DOM. Every boundary case — middle of the viewport, hard against the
 * bottom, hard against the top, a panel taller than the screen, narrow widths — is a plain function
 * call, so it can be tested deterministically instead of by simulating scrolls in a browser.
 *
 * The result is in DOCUMENT coordinates: the panel is absolutely positioned, so it scrolls with the
 * page without any scroll listener.
 */

export type Box = { top: number; left: number; width: number; height: number };
export type Size = { width: number; height: number };
export type Scroll = { x: number; y: number };

export type Placement = {
  top: number;
  left: number;
  /** Which side of the trigger the panel ended up on. */
  side: "below" | "above";
  /** True when the panel had to be pushed off its preferred spot to stay on screen. */
  clamped: boolean;
};

/** Distance kept from the viewport edges. */
export const MARGIN = 12;
/** Distance between the trigger and the panel. */
export const GAP = 8;

export function placePopover(
  anchor: Box,
  panel: Size,
  viewport: Size,
  scroll: Scroll = { x: 0, y: 0 },
  margin = MARGIN,
  gap = GAP,
): Placement {
  const below = anchor.top + anchor.height + gap;
  const above = anchor.top - panel.height - gap;
  // The lowest top edge that still leaves the whole panel on screen. Negative when the panel is
  // taller than the viewport, which is why every use of it is guarded with `margin`.
  const lowest = viewport.height - panel.height - margin;

  let side: Placement["side"] = "below";
  let top = below;
  // Flip above only when below overflows AND above genuinely has room; otherwise stay below and clamp,
  // which keeps the panel attached to the trigger rather than jumping across it for no gain.
  if (below > lowest && above >= margin) {
    side = "above";
    top = above;
  }
  const wantedTop = top;
  top = Math.min(Math.max(margin, top), Math.max(margin, lowest));

  let left = anchor.left + anchor.width / 2 - panel.width / 2;
  const wantedLeft = left;
  const rightmost = viewport.width - panel.width - margin;
  left = Math.min(Math.max(margin, left), Math.max(margin, rightmost));

  return {
    top: top + scroll.y,
    left: left + scroll.x,
    side,
    clamped: top !== wantedTop || left !== wantedLeft,
  };
}
