/** Home — step 1 of the walkthrough. A visitor should understand, in about a minute: the real case
 *  (catching attacks on a small network device), why a model trained once stops working there, what
 *  the project built and tested, and the main result. The result's numbers are read from the saved
 *  held-out report; nothing on this page is typed in. Detail belongs to the Method page.
 */

import { ExplainButton } from "../components/Explain";
import Headline, { useHeldout } from "../components/Headline";
import Reveal from "../components/Reveal";
import RunPreview from "../components/RunPreview";
import { JOURNEY } from "../lib/journey";
import { href } from "../lib/router";

const PROBLEM_STEPS = [
  { k: "Stable data", v: "The model matches the stream it was trained on, and accuracy holds steady." },
  { k: "The stream moves on", v: "Observations arrive from conditions the training data never described." },
  { k: "Concept drift", v: "The same inputs now map to different correct answers." },
  { k: "Performance degrades", v: "Predictions keep following a relationship the data has left behind." },
  { k: "The model has to adapt", v: "Either someone notices and retrains it, or the pipeline handles it while it runs." },
];

const CASE = [
  {
    k: "Where it runs",
    title: "A small network device",
    v: "A home router or an office gateway. It has a slow processor and little memory, and it must decide about every connection as it passes.",
  },
  {
    k: "What it decides",
    title: "Normal, or an attack?",
    v: "For each connection, one answer. Missing an attack is costly; so is raising alarms about normal traffic.",
  },
  {
    k: "Why it is hard",
    title: "The attacks keep changing",
    v: "Monday's traffic does not look like Wednesday's. A model trained once goes out of date, so it has to keep learning on the device itself.",
  },
  {
    k: "The catch",
    title: "Learning costs computing time",
    v: "Every update uses processor time the device barely has. Spend too much and it cannot keep up with the traffic.",
  },
];

const IMPLEMENTED = [
  "One pipeline: adaptive preprocessing, online feature selection, ADWIN drift detection, model adaptation",
  "Three real datasets (electricity prices, room occupancy, network intrusions) and a synthetic stream",
  "A week of real network traffic, 2.1 million connections, with dated attack periods",
  "The review's five decision rules (R1–R5) as a working controller, each rule switchable",
  "A new budgeted effort controller, with a switch for each of its parts",
  "Accuracy, per-stage time, CPU, memory and model size from the same run",
  "Simulated device tiers, late and partial labels, fixed seeds and saved reports",
];

const NEXT_STEPS = [
  "Test the new controller on days it was not designed on, with repeated seeds",
  "Adaptation that still works when the true answers arrive late",
  "A second dataset from a different network",
  "Measurement on physical edge hardware, including energy",
];

/** The project in three moves. Wording only: the measurements are on the Findings page. */
const ARC = [
  {
    cap: "1 · The review",
    title: "A proposal without a test.",
    text: "Our review of adaptive machine learning found the parts studied separately and mostly on accuracy alone. It proposed five decision rules for adapting to drift and to resources together, and left them untested.",
  },
  {
    cap: "2 · The testbed",
    title: "A real case under device limits.",
    text: "We replay a week of real network traffic with dated cyber-attacks, on simulated small devices with a time and memory budget, and record accuracy and the cost of every pipeline stage in the same run.",
  },
  {
    cap: "3 · The controller",
    title: "Spend the budget where it matters.",
    text: "The measurements showed where the rules fall short. A new controller does less work on easy connections and more during attacks, while holding the device's time budget on average.",
  },
];

/** A schematic of the story the platform exists to show. Explicitly not data: it is drawn from
 *  constants, and the caption says so, because an illustration that looks like a result is a claim. */
function StoryCurve() {
  return (
    <figure className="story-curve">
      <div className="story-card">
        <div className="story-card-head">
          <span className="story-axis">Accuracy</span>
          <span className="tag">Schematic</span>
        </div>
        <svg
          viewBox="0 0 520 210"
          role="img"
          aria-label="Schematic: after a concept drift a model that trains once stays degraded, while an adaptive pipeline detects the change, replaces its model and recovers"
        >
          <defs>
            <linearGradient id="driftfade" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--drift)" stopOpacity="0.14" />
              <stop offset="100%" stopColor="var(--drift)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[46, 92, 138, 184].map((y) => (
            <line key={y} x1="0" x2="520" y1={y} y2={y} className="story-grid" />
          ))}
          <rect x="250" y="0" width="270" height="184" fill="url(#driftfade)" />
          <line x1="250" x2="250" y1="0" y2="192" className="story-drift-line" />
          <text x="257" y="13" className="story-flag drift">DRIFT</text>

          <path className="story-path static" d="M8 58 L250 54 L282 148 L520 154" />
          <path className="story-path adaptive" d="M8 70 L250 66 L286 156 L322 151 L372 106 L430 78 L520 70" />

          <circle className="story-dot detect" cx="306" cy="153" r="5" />
          <text x="292" y="178" className="story-flag detect">DETECTED</text>
          <circle className="story-dot adapt" cx="372" cy="106" r="5" />
          <text x="348" y="90" className="story-flag adapt">ADAPTED</text>
        </svg>
        <div className="story-legend">
          <span className="key">
            <i className="swatch adaptive" /> Keeps learning
          </span>
          <span className="key">
            <i className="swatch static" /> Trained once, then frozen
          </span>
          <span className="story-axis right">Position in the stream →</span>
        </div>
      </div>
      <figcaption>
        A schematic of the effect under study — not measured data. Real runs, with their own numbers, are on the{" "}
        <a href={href({ page: "live" })}>Live</a> screen.
      </figcaption>
    </figure>
  );
}

export default function Home() {
  const heldout = useHeldout();

  return (
    <div className="home">
      <section className="home-hero">
        <div className="home-hero-text">
          <Reveal>
            <span className="eyebrow">B.Tech research project · adaptive machine learning</span>
          </Reveal>
          <Reveal delay={40}>
            <h1 className="hero-type">
              Catching cyber-attacks on a small device, when the attacks keep changing.
            </h1>
          </Reveal>
          <Reveal delay={80}>
            <p className="lead">
              A model trained once goes out of date as the traffic changes. Keeping it up to date costs computing
              time a small device does not have. We built a system that does both within the device's limits, and
              tested it on a week of real network traffic.
            </p>
          </Reveal>
          <Reveal delay={120}>
            <div className="home-cta">
              <a className="btn primary lg" href={href({ page: "live" })}>
                Start the walkthrough
              </a>
              <a className="btn lg quiet" href={href({ page: "findings" })}>
                See the main result
              </a>
            </div>
          </Reveal>
          <Reveal delay={160}>
            <p className="home-hero-note">
              A research prototype, built to test a proposal from the team's published review paper. Device limits
              are simulated in software.
            </p>
          </Reveal>
        </div>
        <Reveal delay={100} className="home-hero-visual">
          <RunPreview fallback={<StoryCurve />} />
        </Reveal>
      </section>

      <section className="band">
        <div className="band-inner">
          <Reveal className="section-intro">
            <span className="eyebrow">The real-world case</span>
            <h2 className="section-type">A small device that guards a network.</h2>
            <p className="lead">
              Think of the small box that connects a home or an office to the internet. It sees every connection, and
              it is the natural place to stop an attack.
            </p>
          </Reveal>
          <div className="case-grid">
            {CASE.map((item, index) => (
              <Reveal as="article" key={item.k} delay={index * 60} className="case-card">
                <span className="eyebrow">{item.k}</span>
                <h3>{item.title}</h3>
                <p>{item.v}</p>
              </Reveal>
            ))}
          </div>
          <Reveal className="case-question">
            <span className="eyebrow">The research question</span>
            <p>
              How should a small device divide its limited computing time between <strong>checking connections</strong>{" "}
              and <strong>keeping its model up to date</strong>, so that it still catches attacks as they change?
            </p>
          </Reveal>
        </div>
      </section>

      <section className="band">
        <div className="band-inner">
          <Reveal className="section-intro">
            <span className="eyebrow">The problem</span>
            <h2 className="section-type">Machine learning assumes the world holds still.</h2>
            <p className="lead">
              Real data does not. When the relationship between the inputs and the correct answer moves, a model
              trained once keeps applying a rule that no longer holds — and nothing about the incoming data looks
              wrong.
            </p>
          </Reveal>

          <ol className="progression">
            {PROBLEM_STEPS.map((step, index) => (
              <Reveal as="li" key={step.k} delay={index * 70}>
                <span className="progression-no">{String(index + 1).padStart(2, "0")}</span>
                <span className="progression-body">
                  <strong>{step.k}</strong>
                  <span>{step.v}</span>
                </span>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      <section className="band">
        <div className="band-inner">
          <Reveal className="section-intro">
            <span className="eyebrow">This project</span>
            <h2 className="section-type">From a review paper to a tested system.</h2>
            <p className="lead">
              Our published review ended with a proposal it did not test: a pipeline that adapts to changing data and
              to a device's limited resources at the same time. This project builds that proposal and measures it.
            </p>
          </Reveal>
          <div className="arc-grid">
            {ARC.map((card, index) => (
              <Reveal key={card.cap} delay={index * 70}>
                <div className="arc-card">
                  <span className="gap-cap">{card.cap}</span>
                  <strong>{card.title}</strong>
                  <p>{card.text}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {heldout && heldout.length > 0 && (
        <section className="band">
          <div className="band-inner">
            <Reveal className="section-intro">
              <span className="eyebrow">The main result</span>
              <h2 className="section-type">Equal or better protection, for much less computing time.</h2>
              <p className="lead">
                The rules proposed in our review catch the attacks but spend more time than the device has. Our new
                controller works less on ordinary traffic and more when something changes.
              </p>
            </Reveal>
            <Reveal>
              <Headline rows={heldout} compact />
            </Reveal>
          </div>
        </section>
      )}

      <section className="band">
        <div className="band-inner">
          <Reveal className="section-intro">
            <span className="eyebrow">Walkthrough</span>
            <h2 className="section-type">The project in six steps.</h2>
            <p className="lead">
              The pages follow the order of the work. Each one ends with a link to the next.
            </p>
          </Reveal>
          <Reveal>
            <ol className="step-list">
              {JOURNEY.map((step, index) => (
                <li key={step.page}>
                  <a href={href({ page: step.page })} aria-current={index === 0 ? "step" : undefined}>
                    <span className="step-n">{index + 1}</span>
                    <strong>
                      {step.label} — {step.title.toLowerCase()}
                    </strong>
                    <span className="step-shows">{step.shows}</span>
                    <span className="step-go" aria-hidden="true">
                      {index === 0 ? "you are here" : "→"}
                    </span>
                  </a>
                </li>
              ))}
            </ol>
          </Reveal>
        </div>
      </section>

      <section className="band">
        <div className="band-inner">
          <Reveal className="section-intro">
            <span className="eyebrow">Current scope</span>
            <h2 className="section-type">What the prototype does, and what it does not.</h2>
            <p className="lead">
              Device limits are enforced in software on this computer, with placeholder budgets. No edge device is
              involved and no energy is measured — the interface says so wherever such a run appears.
            </p>
          </Reveal>
          <div className="scope-grid">
            <Reveal className="scope-col">
              <span className="gap-cap">In the current prototype</span>
              <ul className="ticks">
                {IMPLEMENTED.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </Reveal>
            <Reveal delay={90} className="scope-col next">
              <span className="gap-cap">Next research steps</span>
              <ul className="arrows">
                {NEXT_STEPS.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </Reveal>
          </div>
          <Reveal className="scope-note">
            <p>
              Every run is started from a <strong>seed</strong> — a single number that fixes the stream, the model and
              every random choice the run makes, so the same configuration can be run again and compared.{" "}
              <ExplainButton id="seed" variant="text" label="What is a seed?" />{" "}
              <ExplainButton id="reproducibility" variant="text" label="How reproducibility is checked" />
            </p>
          </Reveal>
        </div>
      </section>

      <footer className="home-footer">
        <div className="band-inner">
          <p>
            <strong>AdaptiveML Studio</strong> — the experimental instrument for a B.Tech project on adaptive
            machine learning for evolving data streams, built from the techniques surveyed in the team's review
            paper.
          </p>
          <p className="muted">
            Three workstreams: review and literature, implementation, and research and experimentation. The platform
            records measurements; the conclusions drawn from them belong to the research workstream.
          </p>
        </div>
      </footer>
    </div>
  );
}
