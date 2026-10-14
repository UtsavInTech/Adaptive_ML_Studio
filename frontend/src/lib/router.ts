/** Hash routing for five views — no router dependency.
 *
 *  Home is the default: someone opening the app for the first time should meet an explanation of the
 *  project, not the instrument panel. */

import { useSyncExternalStore } from "react";

export type Route =
  | { page: "home" }
  | { page: "live" }
  | { page: "experiments" }
  | { page: "experiment"; id: string; trial?: string }
  | { page: "method" };

export function parseHash(hash: string): Route {
  const [path, query] = hash.replace(/^#\/?/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  if (parts[0] === "experiments" && parts[1]) {
    const trial = new URLSearchParams(query ?? "").get("trial") ?? undefined;
    return { page: "experiment", id: decodeURIComponent(parts[1]), trial };
  }
  if (parts[0] === "experiments") return { page: "experiments" };
  if (parts[0] === "method") return { page: "method" };
  if (parts[0] === "live") return { page: "live" };
  return { page: "home" };
}

export function href(route: Route): string {
  switch (route.page) {
    case "live":
      return "#/live";
    case "experiments":
      return "#/experiments";
    case "experiment":
      return `#/experiments/${encodeURIComponent(route.id)}${route.trial ? `?trial=${encodeURIComponent(route.trial)}` : ""}`;
    case "method":
      return "#/method";
    default:
      return "#/home";
  }
}

export const navigate = (route: Route) => {
  window.location.hash = href(route);
};

const subscribe = (listener: () => void) => {
  window.addEventListener("hashchange", listener);
  return () => window.removeEventListener("hashchange", listener);
};

/** The current page on <html>, so a page can carry its own palette. Registered at import, ahead of
 *  React's own hashchange listener, so the attribute is already set when charts read CSS variables. */
function markPage() {
  document.documentElement.dataset.page = parseHash(window.location.hash).page;
}
window.addEventListener("hashchange", markPage);
markPage();

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash, () => "#/live");
  return parseHash(hash);
}
