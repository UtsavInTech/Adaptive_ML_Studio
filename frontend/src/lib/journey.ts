/** The order in which the project is meant to be walked through, e.g. in front of a panel.
 *
 *  One list drives the numbered navigation, the "next step" bar under every page and the step list
 *  on Home, so the three can never disagree. */

import type { Route } from "./router";

export type JourneyPage = "home" | "live" | "experiments" | "testbed" | "findings" | "method";

export type JourneyStep = {
  page: JourneyPage;
  /** Short label for the navigation. */
  label: string;
  /** What this step is for, as a phrase. */
  title: string;
  /** One sentence: what a visitor sees here. */
  shows: string;
};

export const JOURNEY: JourneyStep[] = [
  {
    page: "home",
    label: "Home",
    title: "The problem",
    shows: "The real case: a small device that must catch cyber-attacks as they change, with very little computing time.",
  },
  {
    page: "live",
    label: "Live demo",
    title: "See it happen",
    shows: "One stream, two models: one trained once, one that adapts. Watch accuracy fall, the change get detected, and the model recover.",
  },
  {
    page: "experiments",
    label: "Experiments",
    title: "Compare methods",
    shows: "Several methods on the same data, each run alone, with accuracy and cost recorded together and every run saved.",
  },
  {
    page: "testbed",
    label: "Testbed",
    title: "A real case",
    shows: "2.1 million real network connections with dated cyber-attacks, replayed on simulated small devices with limited time and memory.",
  },
  {
    page: "findings",
    label: "Findings",
    title: "What we found",
    shows: "The main result first: equal or better protection for much less computing time. Then the four findings behind it, including the one that does not work yet.",
  },
  {
    page: "method",
    label: "Method",
    title: "How it works",
    shows: "Each component, how every number is measured, which research gap it addresses, and the limits of the work.",
  },
];

/** The journey page a route belongs to. A single saved run belongs to the step it was opened from:
 *  the Testbed when the visitor came from there, otherwise Experiments. */
export function journeyPage(route: Route, cameFrom?: JourneyPage): JourneyPage {
  if (route.page !== "experiment") return route.page;
  return cameFrom === "testbed" ? "testbed" : "experiments";
}

export function journeyIndex(route: Route, cameFrom?: JourneyPage): number {
  const page = journeyPage(route, cameFrom);
  return JOURNEY.findIndex((step) => step.page === page);
}
