import { useEffect, useState } from "react";

import ErrorBoundary from "./components/ErrorBoundary";
import { ExplainLayer } from "./components/Explain";
import Logo from "./components/Logo";
import { Badge } from "./components/ui";
import { store, useLive } from "./lib/live";
import { setPresentation, usePresentation } from "./lib/present";
import { href, useRoute } from "./lib/router";
import { setTheme, useTheme } from "./lib/theme";
import ExperimentDetail from "./pages/ExperimentDetail";
import Experiments from "./pages/Experiments";
import Home from "./pages/Home";
import Live from "./pages/Live";
import Method from "./pages/Method";

const TABS = [
  { page: "home" as const, label: "Home" },
  { page: "live" as const, label: "Live" },
  { page: "experiments" as const, label: "Experiments" },
  { page: "method" as const, label: "Method" },
];

/** True once the page has been scrolled away from the very top.
 *
 *  Driven by a sentinel rather than a scroll listener: an observer reports the crossing exactly once
 *  in each direction, costs nothing per frame, and works in environments that do not deliver scroll
 *  events. */
function useScrolledPastTop() {
  const [past, setPast] = useState(false);
  useEffect(() => {
    let frame = 0;
    const measure = () => {
      frame = 0;
      setPast(window.scrollY > 24);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    // The sentinel is a second trigger for the same reading, for the same reason the reveal has one:
    // an observer notices the crossing even where scroll events are coalesced or not delivered.
    const sentinel = document.getElementById("top-sentinel");
    const observer =
      sentinel && typeof IntersectionObserver !== "undefined" ? new IntersectionObserver(onScroll, { threshold: 0 }) : null;
    if (sentinel) observer?.observe(sentinel);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      observer?.disconnect();
    };
  }, []);
  return past;
}

export default function App() {
  useLive();
  const route = useRoute();
  const { choice } = useTheme();
  const present = usePresentation();
  const connection = store.connection;
  const floating = useScrolledPastTop();
  /** Home is the explanation; the other three are the instrument. The top bar is quieter on Home. */
  const lab = route.page !== "home";

  // A hash change keeps the scroll position, which would drop a visitor into the middle of the next
  // page. Every page starts at its own beginning.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [route.page, route.page === "experiment" ? route.id : ""]);

  return (
    <div className={`app${lab ? "" : " app-home"}`}>
      <div id="top-sentinel" aria-hidden="true" />
      <header className={`topbar${floating ? " floating" : ""}`}>
        <div className="topbar-inner">
          <a className="brand" href={href({ page: "home" })} aria-label="AdaptiveML Studio — home">
            <Logo />
            <span className="brand-text">
              <strong>
                Adaptive<span className="brand-accent">ML</span> Studio
              </strong>
              <span className="secondary">Adaptive machine learning under evolving data</span>
            </span>
          </a>
          <nav className="tabs" aria-label="Main">
            {TABS.map((tab) => (
              <a
                key={tab.page}
                className="tab"
                href={href({ page: tab.page })}
                aria-current={route.page === tab.page || (tab.page === "experiments" && route.page === "experiment") ? "page" : undefined}
              >
                {tab.label}
                <span className="tab-dot" aria-hidden="true" />
              </a>
            ))}
          </nav>
          <div className="spacer" />
          {store.job?.status === "running" && <Badge tone="info" pulse>experiment running</Badge>}
          {store.active && <Badge tone="ok" pulse>live run</Badge>}
          {/* A healthy connection is only worth saying inside the instrument; a broken one is worth
              saying everywhere, because nothing on the Live screen will update. */}
          {(lab || connection !== "live") && (
            <Badge tone={connection === "live" ? "ok" : connection === "offline" ? "error" : "idle"}>
              {connection === "live" ? "Connected" : connection === "offline" ? "Reconnecting" : "Connecting"}
            </Badge>
          )}
          {lab && (
            <button
              type="button"
              className={`btn small${present ? " primary" : ""}`}
              aria-pressed={present}
              onClick={() => setPresentation(!present)}
              title="Larger numbers and charts, fewer secondary details — for projecting"
            >
              Presentation mode
            </button>
          )}
          <div className="segmented secondary" role="group" aria-label="Theme">
            {(["system", "light", "dark"] as const).map((option) => (
              <button key={option} type="button" aria-pressed={choice === option} onClick={() => setTheme(option)}>
                {option === "system" ? "Auto" : option === "light" ? "Light" : "Dark"}
              </button>
            ))}
          </div>
        </div>
      </header>

      <ErrorBoundary key={route.page}>
        {route.page === "home" && <Home />}
        {route.page === "live" && <Live />}
        {route.page === "experiments" && <Experiments />}
        {route.page === "experiment" && <ExperimentDetail id={route.id} trial={route.trial} />}
        {route.page === "method" && <Method />}
      </ErrorBoundary>

      <ExplainLayer />
    </div>
  );
}
