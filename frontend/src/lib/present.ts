/** Presentation mode: bigger numbers, bigger charts, secondary detail hidden — for the projector.
 *  It is the same application with a different density, not a separate view. */

import { useSyncExternalStore } from "react";

const KEY = "adaptiveml.presentation";
const listeners = new Set<() => void>();
let on = localStorage.getItem(KEY) === "1";

function apply() {
  document.documentElement.classList.toggle("present", on);
  listeners.forEach((listener) => listener());
}

apply();

export function setPresentation(next: boolean) {
  on = next;
  localStorage.setItem(KEY, next ? "1" : "0");
  apply();
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export const usePresentation = (): boolean => useSyncExternalStore(subscribe, () => on, () => false);
