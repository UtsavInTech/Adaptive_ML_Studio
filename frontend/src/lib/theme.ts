/** Theme: light, dark, or the system setting. Charts read CSS variables, so they are rebuilt when the
 *  resolved theme changes. */

import { useSyncExternalStore } from "react";

export type ThemeChoice = "system" | "light" | "dark";

const KEY = "adaptiveml.theme";
const listeners = new Set<() => void>();
const media = window.matchMedia("(prefers-color-scheme: dark)");

let choice: ThemeChoice = (localStorage.getItem(KEY) as ThemeChoice) ?? "system";

const resolved = (): "light" | "dark" => (choice === "system" ? (media.matches ? "dark" : "light") : choice);

function apply() {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
  listeners.forEach((listener) => listener());
}

media.addEventListener("change", () => {
  if (choice === "system") listeners.forEach((listener) => listener());
});
apply();

export function setTheme(next: ThemeChoice) {
  choice = next;
  localStorage.setItem(KEY, next);
  apply();
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

/** The choice plus the resolved theme; the resolved value is a stable key for chart rebuilds. */
export function useTheme(): { choice: ThemeChoice; resolved: "light" | "dark" } {
  const key = useSyncExternalStore(
    subscribe,
    () => `${choice}:${resolved()}`,
    () => "system:light",
  );
  const [storedChoice, storedResolved] = key.split(":");
  return { choice: storedChoice as ThemeChoice, resolved: storedResolved as "light" | "dark" };
}
