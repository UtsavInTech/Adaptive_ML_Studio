/** Scroll-driven reveal.
 *
 *  Two rules, both learned from defects:
 *
 *  1. Content is visible by default and only *becomes* hidden once this component has registered a
 *     way to un-hide it. An earlier pass shipped an entrance animation that left whole sections
 *     pinned at `opacity: 0` when it never ran, so here animation can never decide whether something
 *     can be read.
 *  2. Revealing is decided by a sweep over element positions, not by an observer entry alone. An
 *     element scrolled past between two frames — a jump to an anchor, End, or a restored scroll
 *     position — never reports as intersecting, and an observer-only implementation leaves it
 *     invisible for good. The sweep asks "is this above the reveal line?", which is true both for
 *     something entering the viewport and for something already scrolled past.
 *
 *  Readers who ask for reduced motion skip all of it.
 */

import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

type Tag = "div" | "section" | "article" | "li" | "header" | "p";

/** How far down the viewport an element must reach before it is revealed. */
const LINE = 0.92;

type Entry = { element: HTMLElement; show: () => void };

const pending = new Set<Entry>();
let observer: IntersectionObserver | null = null;
let frame = 0;

function sweep() {
  frame = 0;
  const limit = window.innerHeight * LINE;
  for (const entry of [...pending]) {
    if (entry.element.getBoundingClientRect().top < limit) {
      pending.delete(entry);
      observer?.unobserve(entry.element);
      entry.show();
    }
  }
}

const schedule = () => {
  if (!frame) frame = requestAnimationFrame(sweep);
};

/** One observer and one scroll listener for the whole page, whichever fires first. */
function register(element: HTMLElement, show: () => void) {
  const entry: Entry = { element, show };
  pending.add(entry);
  if (!observer) {
    observer = new IntersectionObserver(schedule, { threshold: [0, 0.05, 0.5] });
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
  }
  observer.observe(element);
  return () => {
    pending.delete(entry);
    observer?.unobserve(element);
  };
}

const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

export default function Reveal({
  children,
  delay = 0,
  className = "",
  as = "div",
}: {
  children: ReactNode;
  /** Stagger, in milliseconds, for items revealed as a group. */
  delay?: number;
  className?: string;
  as?: Tag;
}) {
  const ref = useRef<HTMLElement | null>(null);
  const [state, setState] = useState<"idle" | "armed" | "in">("idle");

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (typeof IntersectionObserver === "undefined" || prefersReducedMotion()) {
      setState("in");
      return;
    }
    // Content already on screen when the page opens is not "revealed on scroll" — it is just the
    // page. Animating it in would make the first thing a visitor sees half a second of nothing.
    if (element.getBoundingClientRect().top < window.innerHeight * LINE) {
      setState("in");
      return;
    }
    setState("armed");
    return register(element, () => setState("in"));
  }, []);

  const Element = as as "div";
  return (
    <Element
      ref={ref as React.Ref<HTMLDivElement>}
      className={`reveal ${state}${className ? ` ${className}` : ""}`}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </Element>
  );
}
