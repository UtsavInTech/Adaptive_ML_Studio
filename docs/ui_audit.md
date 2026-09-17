# UI/UX audit and refinement pass

**Scope:** interface only. No ML algorithm, experiment definition, measurement, validation result or backend
semantic was changed. One backend line changed for a UI-driven bug (an unmatched `/api/...` path fell through
to the single-page app and returned HTTP 200).

**Goal:** a faculty member should understand any screen in about 30 seconds, while a technical reviewer can still
drill down to the detail.

---

## 1. Audit — what was wrong

Evidence was collected from the running app (DOM measurements at 1280/1440/1920, console inspection), not from memory.

| # | Issue | Why it hurt usability | Fix | Files |
|---|---|---|---|---|
| 1 | **Explanations were clipped.** The tooltip rendered inside `.pipeline`, which has `overflow-x: auto`; measured tooltip bottom 341 px against a container ending at 278 px | The explanation for a term was cut off exactly where a newcomer needed it. The event log (`overflow-y: auto`) had the same trap | One shared popover rendered through a **portal at the document root**, positioned from the trigger's rect and clamped to the viewport | `components/Explain.tsx`, `lib/explain.ts` |
| 2 | **Hover-only tooltips** with no close behaviour, re-implemented per component | Not reachable by keyboard in a predictable way, no Escape, no outside-click, two could stack | Click-to-open popover: Escape closes, outside click closes, opening another closes the previous, focus returns to the trigger | `components/Explain.tsx` |
| 3 | **Explanations were one line.** "Detected when the statistical characteristics change…" | A faculty member could not tell *what it is* from *how it is measured* from *why it matters* | Every entry now answers three questions and shows a formula where one exists — 39 entries | `lib/explain.ts` |
| 4 | **Flat hierarchy:** 10 KPI tiles and 8 panels of equal weight on one 1280 screen | Nothing told the eye where to start; the drift story had to be reconstructed from six cards | Explicit order: state banner → hero chart + "What happened?" → grouped metrics → pipeline → secondary charts → technical details | `pages/Live.tsx`, `styles.css` |
| 5 | **No plain-language state.** A step-strip of phase chips only | "Stable / Drift detected / Adapting" meant nothing on its own | Large state banner with a sentence: *"Adaptation completed at sample 10,478. Watching how accuracy behaves afterwards."* | `components/ui.tsx` (`StateBanner`) |
| 6 | **Numbers too small for a projector:** metric values 17 px, smallest text 11 px | Unreadable from the back of a room | Metric values 30 px (40 px in presentation mode), body 14 px, smallest 11.5 px; a **Presentation mode** toggle enlarges and hides secondary detail | `styles.css`, `lib/present.ts`, `App.tsx` |
| 7 | **Chart event markers were thin 1 px lines with 11 px labels** | The drift → detection → adaptation story was invisible on a projector | 2–3 px markers with filled label chips, alternating lanes so labels never overlap | `charts/plots.ts` |
| 8 | **"What happened?" did not exist.** The episode card showed raw fields and went blank when the latest episode had no ground truth | The single most important question had no answer on screen | Numbered factual timeline (drift → detector responded → adaptation → monitoring) plus before/lowest/after cells | `components/Cards.tsx` |
| 9 | **Pipeline strip dumped all detail permanently**, and its tiles nested a `<button>` inside a `<button>` | Invalid HTML, poor for keyboard users, and a wall of text | Seven numbered steps with status and cost; a drawer gives what it does / technique / cost / reference / gap. Explain control sits beside the tile, never inside it | `components/PipelineStrip.tsx` |
| 10 | **Comparison table:** 14 undifferentiated columns, abbreviations, no grouping | A reviewer could not tell performance from cost from resources | Column groups (Predictive performance · Processing cost · Resources · Drift and adaptation), sticky first column, ⓘ on every technical header, scrolling confined to the table | `pages/ExperimentDetail.tsx`, `styles.css` |
| 11 | **Trade-off chart rendered blank** (built with a zero-width line) | The project's central accuracy-vs-cost message was missing | Real scatter: one series per method, colour-coded, x sorted, axis hints "→ more computation" / "↑ higher is more accurate" | `charts/plots.ts` (`pointsChart`), `pages/ExperimentDetail.tsx` |
| 12 | **Empty and error states said "No data"** and surfaced raw messages | A blank panel looks broken; a stack trace is meaningless to faculty | `EmptyState` explains what will appear and how to get it; `ErrorState` gives what happened / why / what to do, with the raw error behind "View technical error" | `components/ui.tsx`, all pages |
| 13 | **Demo narration was a thin banner** | Easy to miss during a presentation | Presentation card: step counter, progress dots, title, sentence, the sample it happened at, and "Why this matters" | `components/DemoCard.tsx` |
| 14 | **Method page was a reference dump** | Unreadable as an introduction | Mini research guide: the problem → what drift is → static vs adaptive flow diagrams → how each number is measured → traceability → glossary, with implementation detail behind disclosure | `pages/Method.tsx` |
| 15 | **A popover could open outside the visible area, and any scroll dismissed it.** Found while verifying, not from memory: a trigger below the fold produced a panel with `withinViewport: false`, and because a click that scrolls the control into view fires a scroll, the panel could be dismissed the instant it opened | The explanation for a term could be unreachable exactly when a reader went looking for it — the worst possible failure for the feature this pass is built around | Placement clamps into the viewport (flip above, then clamp both axes); the panel is positioned in **document** coordinates so it scrolls with its term, and the scroll handler is gone entirely rather than merely re-measuring | `components/Explain.tsx`, `styles.css` |
| 16 | **Provenance badges were cryptic** (`MEASURED · APPLE M1 …`) | A visitor could not tell measured from simulated | `Measured on this machine`, `Simulated edge — not edge hardware`, `Placeholder budgets`, each with an explanation | `components/ui.tsx` (`ProvenanceBadge`) |

| 17 | **A mistyped explanation id crashed the whole page.** `explanation()` returned `undefined` and `ExplainButton` read `.term` from it, throwing into the error boundary — the entire Live screen was lost, not just one ⓘ | A one-character mistake would show faculty an error screen instead of the app | `explanation()` falls back to a visible placeholder, and `lib/explain.test.ts` fails the build if any id used in the UI has no entry | `lib/explain.ts`, `lib/explain.test.ts` |
| 18 | **An empty or malformed server-sent frame threw out of the stream handler** (`JSON.parse(undefined)`) | An uncaught error during a live run, with no recovery path | Empty frames are ignored and malformed ones caught; the stream keeps running and the next resync restores the true state | `lib/live.ts` |
| 19 | **The top bar could not wrap**, so its controls ran past the right edge on a narrow window (76 px of page overflow at 572 px) | Horizontal scrolling of the whole page, and clipped controls | `flex-wrap` with a minimum height instead of a fixed one | `styles.css` |
| 20 | **An open explanation survived navigation.** Opening a popover on Method and then moving to another screen left it floating over the new page, pinned at stale coordinates and covering the comparison table | It looks broken, and it hides the very content the reader just navigated to — in front of an audience | The panel closes on a route change, and refuses to place itself against a trigger that has left the document | `components/Explain.tsx` |
| 21 | **Recorded-run rows were buttons**, while the "open results" control beside them was a link | A navigation target that cannot be opened in a new tab or have its link copied, and two different affordances for the same action | The rows are anchors with a real `href` — still keyboard-activatable, now also middle-clickable | `pages/Experiments.tsx`, `styles.css` |

### Severity

| Severity | Issues | Meaning |
|---|---|---|
| **Critical** | 17 | The app showed an error screen instead of the page. Fixed, with a test that fails the build if it recurs. |
| **High** | 1, 8, 11, 15, 18, 20 | A central piece of the story was missing, unreachable or crashed mid-run: clipped explanations, a blank "what happened" card, a blank trade-off chart, a popover that opened off-screen or dismissed itself, an uncaught stream error. All fixed. |
| **Medium** | 2, 3, 4, 5, 6, 7, 9, 10, 12, 14, 16 | The screen worked but could not be read quickly or understood by a non-specialist: flat hierarchy, one-line explanations, small type, faint chart markers, undifferentiated table columns, bare empty states, a reference-dump Method page, cryptic provenance. All fixed. |
| **Low** | 13, 19, 21 | Polish: demo narration was easy to miss; the top bar did not wrap below ~600 px. Both fixed. |

---

## 2. What did not change

Deliberately preserved: paper references, gaps G1–G6, provenance rules, the measured/simulated distinction,
run ids, configuration hashes, environment capture, reproducibility reporting, latency definitions, and the
honesty rules — the UI still reports measurements and never concludes that one method is better.

Pending definitions stay pending and say so: **recovery/stability** and **computational overhead** render a
warning line ("definition pending the team's decision") instead of a formula.

---

## 3. Before → after

| Aspect | Before | After |
|---|---|---|
| Explanation system | Hover tooltip, clipped by its container, one line | Portal popover: what it is / how it is measured / why it matters, plus formula; Escape, outside-click, single-open |
| Terms explained | 18 short glossary entries | **39** entries, all reachable from the ⓘ next to the term |
| Largest metric type | 17 px | 30 px (40 px in presentation mode) |
| Cards on first screen | 10 KPI tiles, equal weight | State banner + hero + "What happened?", then grouped sections |
| Drift story | Spread across six cards | One banner sentence, marked chart, numbered timeline |
| Trade-off chart | Blank | 4-point scatter with legend and axis hints |
| Table | 14 flat columns | 4 labelled groups, sticky first column, ⓘ per header |
| Empty/error | "No data" / raw message | Explained states with a recovery action and hidden technical detail |
| Projector support | None | Presentation mode (larger type, larger charts, secondary detail hidden) |
| Nested buttons | Present in pipeline tiles | None |
| Page-level horizontal scroll | None | None (verified at 1280/1440/1920) |

---

## 4. Verification performed

- **Type-check** clean; **12 frontend tests** and **73 backend tests** pass; production build succeeds (367 kB JS, 24 kB CSS).
- **Popover contract measured in the browser:** rendered in `document.body` (bottom 1143 px against a pipeline
  container ending at 1214 px — no clipping), inside the viewport, three sections present, Escape closes,
  outside click closes, a second trigger replaces the first (never two open), focus returns to the trigger.
- **Popover placement re-measured after the positioning change:** the panel sits exactly 8 px below its trigger
  and inside the viewport (top 330, bottom 643 of 900), with `aria-expanded="true"` and exactly one panel in the
  document. It is positioned in document coordinates, so it moves with the page: scrolling ∓200 px moved the
  panel by exactly ∓200 px while the 8 px gap to its trigger stayed constant, and no scroll dismisses it.
- **Layout:** no page-level horizontal overflow at 1280, 1440 or 1920; content capped at 1600 px; table scrolls
  inside its own container.
- **Console:** the remaining errors are stale entries from earlier in the session — a marker logged during the
  checks is the last error in the buffer, and the DOM shows every page rendering (14 metric cards, 7 pipeline
  steps, no error banner).
- **Both themes** render correctly (dark background `rgb(11,15,21)`), and the theme choice persists.
- **Popover lifecycle:** opening one on Method and then navigating leaves **0** panels in the document; the panel
  also refuses to place itself against a trigger that is no longer connected.
- **Recorded-run rows** are `<a>` elements carrying a real `#/experiments/<id>` href and remain keyboard-focusable.
- **Console after a clean reload is empty.** Errors seen earlier in the session sit above a logged marker and
  were stale hot-reload artifacts (deleted modules, a since-fixed explanation id, a mid-edit 500 from Vite);
  nothing is logged after the marker.
- **Suite:** 29 frontend tests across 3 files (12 derivation, 14 placement, 3 explanation-id integrity), backend
  unchanged at its last green run of 73. Production build 367.9 kB JS / 24.0 kB CSS.
- **Screens exercised:** Live (idle, stable, drift, adaptation), Experiments list, Experiment detail (table,
  trade-off, accuracy over time, events), Method.
- **Screenshots captured:** Live after adaptation, Experiments list, Method, an open explanation popover (all at
  1280), and the comparison table plus the trade-off scatter at the pane's own width. Emulating a 1280 viewport
  inside a narrower pane scales the image down until the type is unreadable, so the wide-layout claims rest on
  DOM measurement rather than on the images.

## 5. Explanation popover — full verification

Placement maths lives in `src/lib/place.ts` as a pure function, so the geometry is tested without a browser:
**14 deterministic cases** in `src/lib/place.test.ts` (middle, bottom flip, top edge, no room either side, panel
taller than the viewport, both horizontal edges, document-coordinate conversion, and every trigger position at
1280 / 1440 / 1920). The browser is then used only for what genuinely needs a DOM.

| # | Situation | Result | Evidence |
|---|---|---|---|
| 1 | Trigger mid-viewport | Below, attached | Trigger at 450 of 900; panel 475–749; gap 8; zero scroll drift during the measurement |
| 2 | Trigger near the bottom edge | **Flips above** | Trigger at 601; panel 319–593; gap 8; inside the viewport |
| 3 | Trigger near the top edge | Stays below | Trigger at 40; panel 65–339; gap 8; inside the viewport |
| 4 | Trigger in a scrolling container | **Follows the trigger** | `.pipeline` (133 px of overflow): scrolled 120 px → trigger moved −120, panel moved −120, gap still 8 |
| 5 | Page scrolled while open | Moves with the document | Page moved 250 → panel moved 250; stored document `top` unchanged; gap 8; stays open |
| 6 | Click outside | Closes | Panel count 1 → 0 |
| 7 | Escape | Closes, focus returns | `document.activeElement === trigger` afterwards |
| 8 | Open another explanation | Replaces the first | Count stays 1; `aria-expanded` flips `false` / `true` |
| 9 | Viewport resized while open | Re-anchors, stays on screen | 1920 → 1280: still open, left 193 → 41, gap 8, inside the viewport |
| 10 | 1280 / 1440 / 1920 | No page overflow; panel on screen | `scrollWidth − clientWidth = 0` at all three widths |

Also verified: the panel's parent is `document.body` (so no ancestor's `overflow` can clip it), it is positioned
`absolute` in document coordinates, and the page contains **zero nested buttons**.

Why there is no page-scroll listener: document-coordinate positioning moves the panel with the page natively.
The only scrolling that needs following is a container that moves the trigger *without* moving the document, so
listeners are attached to those specific ancestors and nothing else.

## 6. Presentation redesign pass

A second pass turned the working interface into something a faculty member can read in about 30 seconds,
without removing any technical detail. No algorithm, metric, experiment definition or backend semantic changed.

**Design system.** `styles.css` now carries real tokens — a spacing scale, three radii, three elevations, a
typography scale and motion tokens — instead of ad-hoc values. One accent, one success, one attention, one error;
per-method and per-event colours kept separate from status colour.

**Live screen.** The hero leads the page: a state label, one large plain-English sentence ("The model adapted at
sample 10,478."), a supporting sentence, and a four-stage track — Drift 10,000 → Detected 10,311 → Adapted 10,478
→ Monitoring — with the sample index under each stage. The run controls moved *below* the hero: previously the
first thing on the screen was a configuration form.

**Story over fragments.** The "what happened" timeline now reads as sentences ("ADWIN detected a sustained
increase in the model's prediction errors", "The new model was trained on the 200 most recent samples from after
the change") instead of compressed fragments. Microcopy was rewritten throughout: *"what the predictions cost"* →
*"How much processing does each prediction require?"*, *"model v3"* → *"Adaptive model · version 3"*,
*"recovery criterion: pending"* → *"The recovery definition will be finalised by the research team."*

**Also added:** chart hover tooltips (sample, each method's value, the nearby event); headline measurement cards
on a comparison, labelled "highest measured accuracy" and "lowest measured processing cost" — never "best";
a reading hint under the trade-off chart; an SVG logo and favicon (a flat static baseline, an adaptive curve that
dips and recovers); progressive disclosure of what an experiment preset will actually run; and Method sections on
simulated edge and reproducibility.

### Defects found during this pass

| # | Issue | Severity | Fix |
|---|---|---|---|
| 22 | **Entrance animations hid content permanently.** `animation: rise … both` over `from { opacity: 0 }` left every `.flow-step` pinned at `opacity: 0` when the animation did not run — the Method page's diagrams rendered as empty boxes. Measured: `opacity 0`, `fill-mode both`, `delay 0s`, reduced-motion off | **Critical** | No `animation-fill-mode: both` and no start delay anywhere: animation may add polish, it must never decide whether content is visible |
| 23 | **The experiment "advanced" panel rendered nothing.** It read `config.stream` / `config.methods` / `config.seed`, but the real preset shape nests them under `base`, with `seeds` beside it | **High** | `describe()` rewritten against the actual payload; now lists methods, samples, noise, the concept change and the seed |
| 24 | **The comparison table's rows were only clickable, not reachable.** `onClick` on `<tr>` with no keyboard path | Medium | The method name is a real link; the row click still works for the mouse |
| 25 | **Presentation mode appeared broken** in a screenshot — text clipped, half the hero blank | — | **Not a defect.** Geometry measured sound (hero 20→1405, h1 739 px, page overflow 0); the artifact was issue 22. Measuring it prevented a fix to something that was not wrong |

### Verified after the redesign

- Type-check clean · **29 frontend tests** · build 380.47 kB JS / 33.69 kB CSS · console empty after a clean reload.
- The hero is the first element on the page, with all four phase stages and their sample indices.
- All 12 flow-diagram steps render at `opacity: 1`; the advanced disclosure produces 5 correct rows.
- Chart tooltip returns *"Sample 9,925 · Static 93.6 % · Adaptive 94.0 % · Event: drift in data"*.
- Presentation mode: hero headline 40 px, metric values 42 px, secondary controls hidden.
- No page-level horizontal overflow at 1440, and none at 572.

## 7. Known issues and limitations

1. **Keyboard activation could not be verified through the automation tool.** Synthetic Return/Space presses did
   not activate *any* button — including a plain native button the refactor never touched — so this is a
   limitation of the test harness, not evidence of a defect. What was verified: the control is a real
   `<button type="button">` (native Enter/Space activation), it is focusable, it carries `aria-label` and
   `aria-expanded`, Escape closes the popover and focus returns to the trigger. Worth one manual check on the
   demo machine.
2. **Window-level scroll events were unreliable in the automation tool** (a probe listener recorded zero events
   for a programmatic scroll that demonstrably moved the page), which is one reason the design does not depend
   on them. Element-level scroll events are fine and were exercised directly in scenario 4. Page-scroll
   behaviour is verified by measurement rather than by event counting: the panel moved by exactly the distance
   the page moved.
3. **Paced live runs show inflated per-sample times** (cold caches). Unchanged by this pass and documented in
   `docs/performance.md`; the figures of record come from isolated max-speed trials.
4. **Screenshots in the automation pane are downscaled**, so small type is hard to read in them; DOM measurements
   were used as the real evidence. The pane also resized itself and reset the scroll position during the checks
   (`innerHeight` changed from 900 to 814 mid-measurement, and a scroll to 900 had snapped back to 0 by the time
   the next read ran), so any measurement taken while scrolled had to be re-established at a known scroll
   position before it could be trusted. Placement is therefore verified without scrolling.
5. **Narrow windows are exercised but not designed for.** At 572 px the layout collapses to a single column with
   zero page overflow, the top bar wraps, and the comparison table scrolls inside its own container. Nothing
   breaks, but the spacing and chart sizes were tuned for a projector, which remains the demo target.
