/** Home — the explanation that has to land before the instrument makes any sense.
 *
 *  A visitor arriving here should understand, in about a minute of scrolling: what evolving data is,
 *  why a model trained once stops fitting it, what this pipeline does about that, what gets measured,
 *  and what the project does *not* claim. No measured value appears on this page: the numbers belong
 *  to a run, and a run belongs to the Live and Experiments screens.
 */

import { useRef } from "react";

import { ExplainButton } from "../components/Explain";
import Reveal from "../components/Reveal";
import RunPreview from "../components/RunPreview";
import { useGlow } from "../lib/glow";
import { href } from "../lib/router";

const PROBLEM_STEPS = [
  { k: "Stable data", v: "The model matches the stream it was trained on, and accuracy holds steady." },
  { k: "The stream moves on", v: "Observations arrive from conditions the training data never described." },
  { k: "Concept drift", v: "The same inputs now map to different correct answers." },
  { k: "Performance degrades", v: "Predictions keep following a relationship the data has left behind." },
  { k: "The model has to adapt", v: "Either someone notices and retrains it, or the pipeline handles it while it runs." },
];

const PIPELINE = [
  { k: "Data stream", v: "New observations arrive continuously, one at a time." },
  { k: "Preprocessing", v: "Scaling and imputation statistics update as the stream evolves." },
  { k: "Feature selection", v: "Feature relevance is re-estimated online and the most useful ones are kept." },
  { k: "Prediction", v: "The current model predicts each sample before it is allowed to learn from it." },
  { k: "Drift detection", v: "ADWIN watches for a sustained change in the model's own prediction error." },
  { k: "Adaptation", v: "When drift is confirmed, a replacement model can be prepared and promoted." },
  { k: "Monitoring", v: "Accuracy and the cost of every step are recorded throughout the run." },
] as const;

const MEASURES = [
  {
    group: "Predictive performance",
    why: "Whether the model still fits the data it is being asked about.",
    items: [
      { label: "Accuracy", explain: "accuracy" },
      { label: "F1", explain: "f1" },
    ],
  },
  {
    group: "System performance",
    why: "Whether it can keep up with the rate the stream actually arrives at.",
    items: [
      { label: "Processing time", explain: "latency" },
      { label: "Throughput", explain: "throughput" },
    ],
  },
  {
    group: "Resource use",
    why: "What the pipeline costs to run — the limit on any constrained device.",
    items: [
      { label: "CPU", explain: "cpuPerSample" },
      { label: "Memory", explain: "rss" },
      { label: "Model size", explain: "modelSize" },
    ],
  },
  {
    group: "Adaptation",
    why: "Whether the change was noticed, how late, and what the response was.",
    items: [
      { label: "Drift detection", explain: "adwin" },
      { label: "Detection delay", explain: "detectionDelay" },
      { label: "Model adaptation", explain: "adaptation" },
    ],
  },
] as const;

const EXISTING_WORK = [
  "Adaptive preprocessing",
  "Online feature selection",
  "Drift detection",
  "Incremental learning",
  "Resource-aware and edge-oriented methods",
];

const IMPLEMENTED = [
  "A controlled evolving stream with drift at a known position",
  "Adaptive preprocessing and online feature selection",
  "Drift detection with ADWIN",
  "Model adaptation with a background replacement model",
  "Accuracy, latency, CPU, memory and model size from the same run",
  "A simulated resource-constrained profile",
  "Fixed seeds, stored configuration and a reproducibility check",
];

const NEXT_STEPS = [
  "Real-world evolving datasets rather than a synthetic generator",
  "Measurement on physical edge hardware",
  "Adaptation that responds to more than one resource at once",
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
  const how = useRef<HTMLDivElement>(null);
  useGlow(how);

  return (
    <div className="home">
      <section className="home-hero">
        <div className="home-hero-text">
          <Reveal>
            <span className="eyebrow">Adaptive ML for evolving data streams</span>
          </Reveal>
          <Reveal delay={40}>
            <h1 className="hero-type">
              See a machine-learning model <em>adapt</em> as the data changes.
            </h1>
          </Reveal>
          <Reveal delay={80}>
            <p className="lead">
              An experimental platform for studying adaptive machine learning under evolving data streams — from
              concept drift and model adaptation to latency and resource constraints.
            </p>
          </Reveal>
          <Reveal delay={120}>
            <div className="home-cta">
              <a className="btn primary lg" href={href({ page: "live" })}>
                Explore the live system
              </a>
              <button
                type="button"
                className="btn lg quiet"
                onClick={() => how.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
              >
                How it works
              </button>
            </div>
          </Reveal>
          <Reveal delay={160}>
            <p className="home-hero-note">
              A research prototype. Every figure it reports is measured on the machine that ran it, from a
              reproducible, seeded configuration.
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

      <section className="band dark glow" ref={how}>
        <div className="band-inner">
          <Reveal className="section-intro">
            <span className="eyebrow">What the studio does</span>
            <h2 className="section-type">
              Instead of training once and hoping the world stays the same, watch a model respond as the stream
              evolves.
            </h2>
            <p className="lead">
              Every sample travels the same seven steps. Each step's decision, and the time it took, is recorded
              while the run happens.
            </p>
          </Reveal>

          <ol className="pipeline-flow">
            {PIPELINE.map((stage, index) => (
              <Reveal as="li" key={stage.k} delay={index * 60}>
                <span className="pipeline-flow-rail" aria-hidden="true">
                  <span className="pipeline-flow-dot" />
                </span>
                <span className="pipeline-flow-body">
                  <span className="pipeline-flow-step">Step {index + 1}</span>
                  <strong>{stage.k}</strong>
                  <span className="pipeline-flow-said">{stage.v}</span>
                </span>
              </Reveal>
            ))}
          </ol>

          <Reveal className="band-foot">
            <p>
              The same stream is also given to a model that trains once and then stops, so the difference between
              adapting and not adapting is visible in one run.{" "}
              <a href={href({ page: "live" })}>Watch it happen →</a>
            </p>
          </Reveal>
        </div>
      </section>

      <section className="band">
        <div className="band-inner">
          <Reveal className="section-intro">
            <span className="eyebrow">What we measure</span>
            <h2 className="section-type">Accuracy alone does not describe a system that has to keep up.</h2>
            <p className="lead">
              Adaptation is not free: detecting drift, re-selecting features and training a replacement all cost
              processing time and memory. Both sides are recorded in the same run, on the same machine.
            </p>
          </Reveal>

          <div className="measure-grid">
            {MEASURES.map((group, index) => (
              <Reveal key={group.group} delay={index * 70} className="measure-card">
                <h3>{group.group}</h3>
                <p>{group.why}</p>
                <ul className="measure-items">
                  {group.items.map((item) => (
                    <li key={item.label}>
                      <span>{item.label}</span>
                      <ExplainButton id={item.explain} />
                    </li>
                  ))}
                </ul>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="band">
        <div className="band-inner">
          <Reveal className="section-intro">
            <span className="eyebrow">Research motivation</span>
            <h2 className="section-type">The parts exist. Evaluating them together is what is missing.</h2>
          </Reveal>

          <div className="gap-flow">
            <Reveal className="gap-col">
              <span className="gap-cap">Existing work</span>
              <ul className="ticks plain">
                {EXISTING_WORK.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <p className="gap-note">Each is well studied — most often on its own, and most often on accuracy alone.</p>
            </Reveal>

            <span className="gap-arrow" aria-hidden="true">
              →
            </span>

            <Reveal delay={80} className="gap-col gap-question">
              <span className="gap-cap">The gap</span>
              <p className="gap-statement">
                How do adaptive behaviour, predictive performance and computational cost interact when they are
                measured together, under one controlled experimental protocol?
              </p>
            </Reveal>

            <span className="gap-arrow" aria-hidden="true">
              →
            </span>

            <Reveal delay={160} className="gap-col">
              <span className="gap-cap">This platform</span>
              <p className="gap-statement">
                A unified environment for <strong>exploring</strong> that interaction: one pipeline, one stream, and
                accuracy, latency and resource cost recorded side by side in every run.
              </p>
              <p className="gap-note">
                It provides a framework for evaluating the question. It does not claim to settle it — the analysis
                belongs to the research workstream.
              </p>
            </Reveal>
          </div>
        </div>
      </section>

      <section className="band">
        <div className="band-inner">
          <Reveal className="section-intro">
            <span className="eyebrow">Explore</span>
            <h2 className="section-type">Three ways into the system.</h2>
          </Reveal>
          <div className="explore-grid">
            {[
              {
                to: href({ page: "live" }),
                cap: "Live",
                title: "Watch a model adapt as the stream changes.",
                text: "Run the validated scenario and follow drift, detection, adaptation and recovery as they happen.",
              },
              {
                to: href({ page: "experiments" }),
                cap: "Experiments",
                title: "Compare methods under controlled conditions.",
                text: "Static, incremental, adaptive and ARF on the same stream, each in its own process, with every run stored.",
              },
              {
                to: href({ page: "method" }),
                cap: "Method",
                title: "Understand the architecture and the methodology.",
                text: "How each component works, how every number is measured, and which research gap it addresses.",
              },
            ].map((card, index) => (
              <Reveal key={card.cap} delay={index * 70}>
                <a className="explore-card" href={card.to}>
                  <span className="explore-cap">{card.cap}</span>
                  <strong>{card.title}</strong>
                  <span className="explore-text">{card.text}</span>
                  <span className="explore-go" aria-hidden="true">
                    →
                  </span>
                </a>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="band">
        <div className="band-inner">
          <Reveal className="section-intro">
            <span className="eyebrow">Current scope</span>
            <h2 className="section-type">What the prototype does, and what it does not.</h2>
            <p className="lead">
              The constrained profile is enforced in software on this computer. No edge device is involved, no
              energy is measured, and the stream is synthetic — the interface says so wherever such a run appears.
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
