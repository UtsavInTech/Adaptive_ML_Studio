/** One explanation system for the whole app.
 *
 * `<ExplainButton id="p95" />` opens a popover rendered in a portal at the document root, so it is
 * never clipped by a card, a scrolling table or the sticky side column. Only one popover can be
 * open: opening another closes the previous one. Escape closes it, a click outside closes it, and
 * focus returns to the button that opened it.
 *
 * The panel is absolutely positioned in document coordinates (see `lib/place.ts`), so it scrolls
 * with the page without a scroll listener. Placement maths lives in that module so it can be tested
 * without a browser.
 */

import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import { explanation, type ExplainId } from "../lib/explain";
import { placePopover } from "../lib/place";

type OpenState = { id: ExplainId; trigger: HTMLElement } | null;

let current: OpenState = null;
const listeners = new Set<() => void>();

const emit = () => listeners.forEach((listener) => listener());

const open = (id: ExplainId, trigger: HTMLElement) => {
  current = { id, trigger };
  emit();
};

export const closeExplain = () => {
  if (!current) return;
  const { trigger } = current;
  current = null;
  emit();
  // Only restore focus if the trigger is still on the page: after a route change it has been
  // unmounted, and focusing a detached node would drop focus rather than return it.
  if (trigger.isConnected) trigger.focus?.();
};

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

const useOpen = () => useSyncExternalStore(subscribe, () => current, () => null);

/** Containers between the trigger and the page that scroll on their own — a wide table, the pipeline
 *  strip, the event log. Page scrolling moves the panel for free; these move the trigger *without*
 *  moving the document, so they are the only scrolling that needs to be followed. */
const scrollableAncestors = (element: HTMLElement): HTMLElement[] => {
  const found: HTMLElement[] = [];
  for (let node = element.parentElement; node && node !== document.body; node = node.parentElement) {
    const { overflowX, overflowY } = getComputedStyle(node);
    if (/(auto|scroll|overlay)/.test(`${overflowX} ${overflowY}`)) found.push(node);
  }
  return found;
};

/** The small ⓘ control. Never render it inside another button. */
export function ExplainButton({
  id,
  label,
  variant = "icon",
}: {
  id: ExplainId;
  label?: string;
  variant?: "icon" | "text";
}) {
  const state = useOpen();
  const isOpen = state?.id === id;
  const { term } = explanation(id);
  return (
    <button
      type="button"
      className={`explain-btn ${variant}${isOpen ? " open" : ""}`}
      aria-label={`Explain: ${term}`}
      aria-expanded={isOpen}
      onClick={(event) => {
        event.stopPropagation();
        if (isOpen) closeExplain();
        else open(id, event.currentTarget);
      }}
    >
      <span aria-hidden="true">i</span>
      {variant === "text" && <span className="explain-text">{label ?? "Explain"}</span>}
    </button>
  );
}

/** Mounted once, at the app root. */
export function ExplainLayer() {
  const state = useOpen();
  const panel = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const [tick, setTick] = useState(0);

  useLayoutEffect(() => {
    if (!state) setPosition(null);
  }, [state]);

  useLayoutEffect(() => {
    if (!state || !panel.current) return;
    // The trigger can vanish while the panel is open — a route change unmounts the page it sat on.
    // Never place the panel against a trigger that has left the document.
    if (!state.trigger.isConnected) {
      closeExplain();
      return;
    }
    const box = panel.current.getBoundingClientRect();
    const anchor = state.trigger.getBoundingClientRect();
    const { top, left } = placePopover(
      { top: anchor.top, left: anchor.left, width: anchor.width, height: anchor.height },
      { width: box.width, height: box.height },
      { width: window.innerWidth, height: window.innerHeight },
      { x: window.scrollX, y: window.scrollY },
    );
    setPosition({ top, left });
  }, [state, tick]);

  useEffect(() => {
    if (!state) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        closeExplain();
      }
    };
    const onPointer = (event: MouseEvent) => {
      if (!panel.current?.contains(event.target as Node) && event.target !== state.trigger) closeExplain();
    };
    // A resize changes what fits on screen; an inner container's scroll moves the trigger under the
    // panel. Both re-measure. Page scrolling is handled by document-coordinate positioning instead.
    const reposition = () => setTick((n) => n + 1);
    const containers = scrollableAncestors(state.trigger);
    // An explanation must not outlive the screen it explains.
    window.addEventListener("hashchange", closeExplain);
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("mousedown", onPointer, true);
    window.addEventListener("resize", reposition);
    containers.forEach((container) => container.addEventListener("scroll", reposition, { passive: true }));
    // `preventScroll` is the whole point: focusing a panel positioned in document coordinates makes
    // the browser scroll it into view, which moved the page out from under the term being explained.
    panel.current?.focus({ preventScroll: true });
    return () => {
      window.removeEventListener("hashchange", closeExplain);
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("mousedown", onPointer, true);
      window.removeEventListener("resize", reposition);
      containers.forEach((container) => container.removeEventListener("scroll", reposition));
    };
  }, [state]);

  if (!state) return null;
  const entry = explanation(state.id);
  return createPortal(
    <div
      ref={panel}
      className="explain-popover"
      // Hidden for the one frame between mounting (needed to measure the panel) and placing it, so
      // the panel never flashes at the top-left of the document before it reaches the trigger.
      style={{ top: position?.top ?? 0, left: position?.left ?? 0, visibility: position ? undefined : "hidden" }}
      role="dialog"
      aria-label={`About ${entry.term}`}
      tabIndex={-1}
    >
      <div className="explain-head">
        <h3>{entry.term}</h3>
        <button type="button" className="explain-close" onClick={closeExplain} aria-label="Close explanation">
          ✕
        </button>
      </div>
      {entry.formula && <p className="explain-formula mono">{entry.formula}</p>}
      <dl className="explain-body">
        <dt>What it is</dt>
        <dd>{entry.what}</dd>
        {entry.how && (
          <>
            <dt>How it works</dt>
            <dd>{entry.how}</dd>
          </>
        )}
        {entry.why && (
          <>
            <dt>Why it matters</dt>
            <dd>{entry.why}</dd>
          </>
        )}
      </dl>
      {entry.pending && <p className="explain-pending">⚠ {entry.pending}</p>}
      {entry.ref && <p className="explain-ref">Reference: {entry.ref}</p>}
    </div>,
    document.body,
  );
}
