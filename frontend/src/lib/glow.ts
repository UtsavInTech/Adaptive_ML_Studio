/** A soft accent glow that follows the cursor across a panel.
 *
 *  The element's `--mx` / `--my` are the cursor's position within it; CSS paints the glow from them.
 *  Updates are coalesced into one animation frame, the listener is only attached on devices with a
 *  pointer that hovers, and readers who ask for reduced motion get nothing at all.
 */

import { useEffect, type RefObject } from "react";

const OFFSCREEN = "-500px";

export function useGlow(ref: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof window === "undefined") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;

    let frame = 0;
    let x = 0;
    let y = 0;
    const paint = () => {
      frame = 0;
      element.style.setProperty("--mx", `${x}px`);
      element.style.setProperty("--my", `${y}px`);
    };
    const onMove = (event: MouseEvent) => {
      const box = element.getBoundingClientRect();
      x = event.clientX - box.left;
      y = event.clientY - box.top;
      if (!frame) frame = requestAnimationFrame(paint);
    };
    const onLeave = () => {
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      element.style.setProperty("--mx", OFFSCREEN);
      element.style.setProperty("--my", OFFSCREEN);
    };

    element.addEventListener("mousemove", onMove);
    element.addEventListener("mouseleave", onLeave);
    return () => {
      element.removeEventListener("mousemove", onMove);
      element.removeEventListener("mouseleave", onLeave);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [ref]);
}
