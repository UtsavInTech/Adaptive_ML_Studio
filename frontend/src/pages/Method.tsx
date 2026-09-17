/** Method — the research explanation, laid out as a short paper rather than a wall of cards.
 *
 *  Nine numbered sections, a table of contents that follows the reader down the page, and the
 *  traceability table the review workstream maintains. Every claim here is either about what the
 *  implementation does, or explicitly labelled as something it does not do.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { ExplainButton } from "../components/Explain";
import Reveal from "../components/Reveal";
import { EmptyState, Loading, Panel, TechnicalDetails } from "../components/ui";
import { api } from "../lib/api";
import { EXPLANATIONS, EXPLANATION_MAP, type Explanation } from "../lib/explain";

type Traceability = {
  gaps: Record<string, string>;
  components: {
    component: string; technique: string; references: string[]; gaps: string[];
    implemented_in: string; status: string; verified_by: string;
  }[];
};

const SECTIONS = [
  { id: "problem", title: "The problem" },
  { id: "drift", title: "Concept drift" },
  { id: "pipeline", title: "The adaptive pipeline" },
  { id: "detection", title: "Drift detection" },
  { id: "adaptation", title: "Model adaptation" },
  { id: "resources", title: "Resource awareness" },
  { id: "evaluation", title: "Evaluation" },
  { id: "gap", title: "Research gap" },
  { id: "limits", title: "Current limitations" },
  { id: "glossary", title: "Glossary" },
] as const;

const MEASUREMENTS: { term: string; text: string; explain?: keyof typeof EXPLANATIONS }[] = [
  { term: "Accuracy and F1", text: "Each sample is predicted first and learned from afterwards; scores are reported over a recent window and over the whole run after warm-up.", explain: "prequential" },
  { term: "Processing time", text: "Engine time for one sample across the six pipeline steps. Network, display and the cost of recording are excluded.", explain: "latency" },
  { term: "p95 and p99", text: "The slower end of normal behaviour, taken from the per-sample times recorded after warm-up.", explain: "p95" },
  { term: "Throughput", text: "Samples per second the engine sustains at full speed.", explain: "throughput" },
  { term: "Processor time per sample", text: "The engine process's own CPU accounting divided by the samples it processed.", explain: "cpuPerSample" },
  { term: "Memory", text: "Sampled once a second from outside the engine process, so observing it costs the engine nothing.", explain: "rss" },
  { term: "Model size", text: "River's estimate of the learned model's memory; it varies slightly between identical runs.", explain: "modelSize" },
  { term: "Detection delay", text: "Samples between the scheduled change and the detector's response — measurable because the drift position is known.", explain: "detectionDelay" },
  { term: "Recovery and stability", text: "Reported as reference computations; the final definition is a team decision.", explain: "recovery" },
  { term: "Computational overhead", text: "Definition pending the team's decision; the platform records the candidate measurements.", explain: "overhead" },
  { term: "Monitoring overhead", text: "The cost of measuring, reported separately so it never inflates the numbers it reports.", explain: "monitor" },
];

const LIMITS = [
  {
    k: "The constrained profile is simulated",
    v: "Budgets are enforced in software on this computer, with placeholder values. No edge hardware has been measured and no slower processor is emulated.",
  },
  { k: "Energy is not measured", v: "Nothing in the platform observes power draw, so no energy-aware claim is made anywhere." },
  {
    k: "Detection is not reliable in every scenario",
    v: "At the original check-4 configuration the detector found the drift in 1 of 10 seeds. That configuration is kept as a documented hard case rather than quietly retuned.",
  },
  {
    k: "Timed runs are not bit-reproducible",
    v: "When the resource governor reacts to measured time, the same seed can take a different path. Runs without a time budget reproduce exactly.",
  },
  { k: "One synthetic scenario family", v: "SEA concepts only, binary classification only. A real benchmark stream is the next data step." },
  {
    k: "Stability and overhead have no agreed formula",
    v: "The platform reports the component measurements and labels them as reference computations; the definitions are the research workstream's decision.",
  },
];

/** Which section the reader is currently in, for the contents list.
 *
 *  Deliberately a reading line rather than intersection ratios: sections here differ in height by
 *  several screens, and the tallest section is the one with the *lowest* ratio, so comparing ratios
 *  marks the wrong entry. The last heading to have passed the line is the one being read. */
function useActiveSection(ids: readonly string[]) {
  const [active, setActive] = useState<string>(ids[0]);
  useEffect(() => {
    let frame = 0;
    const measure = () => {
      frame = 0;
      const line = 140;
      let current = ids[0];
      for (const id of ids) {
        const element = document.getElementById(id);
        if (element && element.getBoundingClientRect().top <= line) current = id;
      }
      setActive(current);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    // A second trigger for the same measurement: an observer notices a section crossing the viewport
    // even when no scroll event is delivered — which is the case for programmatic scrolling in some
    // environments, and would otherwise leave the contents list pointing at the wrong section.
    const observer =
      typeof IntersectionObserver === "undefined"
        ? null
        : new IntersectionObserver(onScroll, { threshold: [0, 0.5, 1], rootMargin: "-140px 0px 0px 0px" });
    ids.forEach((id) => {
      const element = document.getElementById(id);
      if (element) observer?.observe(element);
    });
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      observer?.disconnect();
    };
  }, [ids]);
  return active;
}

function Section({
  id, no, title, children,
}: {
  id: string;
  no: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="paper-section" id={id}>
      <header className="paper-section-head">
        <span className="paper-no">{String(no).padStart(2, "0")}</span>
        <h2>{title}</h2>
      </header>
      {children}
    </section>
  );
}

export default function Method() {
  const [data, setData] = useState<Traceability | null>(null);
  const [failed, setFailed] = useState(false);
  const ids = useMemo(() => SECTIONS.map((section) => section.id), []);
  const active = useActiveSection(ids);
  const top = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.traceability().then((t) => setData(t as Traceability)).catch(() => setFailed(true));
  }, []);

  return (
    <div className="page paper-page" ref={top}>
      <header className="paper-head">
        <span className="eyebrow">Method</span>
        <h1 className="section-type">How the platform works, and how every number on it is produced.</h1>
        <p className="lead">
          A prototype built from techniques surveyed in the team's review paper. It is not a new algorithm: the
          contribution is running these components together on one stream and measuring what that costs.
        </p>
      </header>

      <div className="paper">
        <nav className="paper-toc" aria-label="Sections">
          {SECTIONS.map((section, index) => (
            <button
              key={section.id}
              type="button"
              className={`paper-toc-link${active === section.id ? " active" : ""}`}
              onClick={() => document.getElementById(section.id)?.scrollIntoView({ behavior: "smooth", block: "start" })}
            >
              <span className="no">{String(index + 1).padStart(2, "0")}</span>
              <span>{section.title}</span>
            </button>
          ))}
        </nav>

        <div className="paper-body">
          <Section id="problem" no={1} title="The problem">
            <div className="prose">
              <p>
                A model trained once on historical data can become less accurate when the data keeps changing. This
                prototype runs a complete adaptive pipeline on a changing stream and measures, in the same run,{" "}
                <strong>how well it predicts</strong> and <strong>what that costs</strong> in processing time and memory.
              </p>
              <p className="muted">
                The literature usually reports the first without the second. Reporting them together, from one run on one
                machine, is what this instrument exists to make possible.
              </p>
            </div>
          </Section>

          <Section id="drift" no={2} title="Concept drift">
            <div className="prose">
              <p>
                The inputs can keep exactly the same shape while the <em>correct answer</em> for them changes. A model
                that learned the old relationship then starts making mistakes, even though nothing looks different in the
                incoming data. <ExplainButton id="drift" />
              </p>
            </div>
            <div className="flow">
              <div className="flow-step">
                <span className="k">Before the change</span>
                <span className="v">The model matches the data and accuracy is steady.</span>
              </div>
              <span className="flow-arrow" aria-hidden="true">→</span>
              <div className="flow-step warn">
                <span className="k">Concept changes</span>
                <span className="v">Same inputs, different correct labels.</span>
              </div>
              <span className="flow-arrow" aria-hidden="true">→</span>
              <div className="flow-step">
                <span className="k">After the change</span>
                <span className="v">Predictions based on the old relationship start to be wrong.</span>
              </div>
            </div>
            <p className="chart-note">
              In these runs the change is scheduled at a known sample index, which is the only reason detection delay can
              be measured at all. On a real stream nobody would know when it happened.{" "}
              <ExplainButton id="driftTrue" />
            </p>
          </Section>

          <Section id="pipeline" no={3} title="The adaptive pipeline">
            <div className="prose">
              <p>
                Every sample takes the same path:{" "}
                <code>preprocess → select → predict → detect → adapt → learn</code>. Prediction happens before the label
                is used, so no score is inflated by data the model has already seen.{" "}
                <ExplainButton id="prequential" />
              </p>
            </div>
            <div className="two-col">
              <Panel title="Static baseline" explain="staticMethod">
                <div className="flow" style={{ flexDirection: "column" }}>
                  <div className="flow-step"><span className="k">Train once</span><span className="v">Learns from the first samples only.</span></div>
                  <span className="flow-arrow" aria-hidden="true">↓</span>
                  <div className="flow-step"><span className="k">Predict for the rest of the stream</span><span className="v">Never learns again.</span></div>
                  <span className="flow-arrow" aria-hidden="true">↓</span>
                  <div className="flow-step warn"><span className="k">After a drift</span><span className="v">Keeps applying the old relationship.</span></div>
                </div>
              </Panel>
              <Panel title="Adaptive pipeline" explain="adaptiveMethod">
                <div className="flow" style={{ flexDirection: "column" }}>
                  <div className="flow-step"><span className="k">Predict, then learn</span><span className="v">Every labelled sample updates the model.</span></div>
                  <span className="flow-arrow" aria-hidden="true">↓</span>
                  <div className="flow-step"><span className="k">Watch its own errors</span><span className="v">A detector looks for a rising error rate.</span></div>
                  <span className="flow-arrow" aria-hidden="true">↓</span>
                  <div className="flow-step ok"><span className="k">Adapt when drift is confirmed</span><span className="v">A replacement model trains on data from after the change and takes over.</span></div>
                </div>
              </Panel>
            </div>
            <p className="chart-note">
              Both see exactly the same samples, in the same order, and are measured the same way. Preprocessing statistics
              and the selected feature set update online in the adaptive pipeline.{" "}
              <ExplainButton id="featureSelection" />
            </p>
          </Section>

          <Section id="detection" no={4} title="Drift detection">
            <div className="prose">
              <p>
                The pipeline has no privileged knowledge that the data changed — it only sees whether its own predictions
                were right. Those correct/incorrect outcomes form an error stream, and ADWIN watches that stream for a
                statistically significant change. <ExplainButton id="adwin" />
              </p>
              <p>
                Two detectors run at different sensitivities: a lenient one raises a <strong>warning</strong>, which is
                when a replacement model starts training, and a stricter one <strong>confirms</strong> the drift, which is
                what allows a replacement to be promoted. The pipeline acts only when the error rate has risen, never when
                it has improved.
              </p>
              <p className="muted">
                Detection is not guaranteed. With enough label noise, or a small enough change, the error increase may
                never become significant — the hard scenario on the Live screen is kept precisely because detection fails
                there. <ExplainButton id="detectionDelay" />
              </p>
            </div>
          </Section>

          <Section id="adaptation" no={5} title="Model adaptation">
            <div className="prose">
              <p>
                Confirming a drift does not by itself fix anything: the model still carries what it learned from the old
                concept. The pipeline's response is to build a new one.{" "}
                <ExplainButton id="adaptation" />
              </p>
            </div>
            <div className="flow">
              <div className="flow-step">
                <span className="k">Warning</span>
                <span className="v">A replacement model begins learning from samples that arrived after the warning.</span>
              </div>
              <span className="flow-arrow" aria-hidden="true">→</span>
              <div className="flow-step">
                <span className="k">Meanwhile</span>
                <span className="v">The current model keeps serving predictions, so no sample goes unanswered.</span>
              </div>
              <span className="flow-arrow" aria-hidden="true">→</span>
              <div className="flow-step ok">
                <span className="k">Promotion</span>
                <span className="v">Once the replacement has seen enough post-change samples, it takes over and the model version increments.</span>
              </div>
            </div>
            <p className="chart-note">
              A cooldown prevents a second adaptation immediately following the first. If the profile disallows background
              models, the pipeline resets the existing model instead — a cheaper response with a sharper accuracy cost.{" "}
              <ExplainButton id="replacement" />
            </p>
          </Section>

          <Section id="resources" no={6} title="Resource awareness">
            <div className="prose">
              <p>
                Adaptive methods are often proposed for small devices, where processing time and memory are limited. This
                project does not have such a device, so it does not claim to have measured one.{" "}
                <ExplainButton id="edge" />
              </p>
              <p>
                Instead, the constrained profile is <strong>simulated in software on this computer</strong>: a per-sample
                time budget is enforced, and when the pipeline exceeds it, the resource governor reduces the work it does —
                learning from fewer samples, or keeping fewer features. Every screen that shows such a run labels it as
                simulated. <ExplainButton id="stride" />
              </p>
              <p className="muted">
                What this shows is how the pipeline <em>behaves</em> when it must give something up. What it does not show
                is how fast the pipeline would run on real edge hardware; that would need the hardware.
              </p>
            </div>
          </Section>

          <Section id="evaluation" no={7} title="Evaluation">
            <div className="prose">
              <p>
                Each figure below is produced in the same run as every other, on the machine named in the run's stored
                environment. Click any ⓘ for the formula and the reason it is reported.
              </p>
            </div>
            <Panel bodyClass="flush">
              <div className="table-scroll">
                <table className="table">
                  <tbody>
                    {MEASUREMENTS.map((row) => (
                      <tr key={row.term}>
                        <td style={{ width: 240 }}>
                          <span className="row" style={{ gap: 6 }}>
                            <strong>{row.term}</strong>
                            {row.explain && <ExplainButton id={row.explain} />}
                          </span>
                        </td>
                        <td style={{ textAlign: "left", whiteSpace: "normal" }}>{row.text}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
            <div className="flow">
              <div className="flow-step">
                <span className="k">Fix the starting point</span>
                <span className="v">One seed decides the data, the model and every random choice in the run.</span>
              </div>
              <span className="flow-arrow" aria-hidden="true">→</span>
              <div className="flow-step">
                <span className="k">Record everything</span>
                <span className="v">Settings, machine, library versions and a hash of the predictions are stored with the results.</span>
              </div>
              <span className="flow-arrow" aria-hidden="true">→</span>
              <div className="flow-step ok">
                <span className="k">Run it again</span>
                <span className="v">Predictions are compared hash to hash. Timings are expected to differ; predictions are not.</span>
              </div>
            </div>
            <p className="chart-note row" style={{ gap: 6 }}>
              Timing varies between runs because the machine is shared with everything else on it. Predictions do not,
              which is why they are what the reproducibility check compares. <ExplainButton id="reproducibility" />
            </p>
          </Section>

          <Section id="gap" no={8} title="Research gap">
            <div className="prose">
              <p>
                The review found adaptive techniques for every stage of a stream pipeline, but rarely evaluated together,
                and rarely with their computational cost. The table below is maintained by the review workstream: which
                technique this implementation uses for each component, where it came from, and which gap it speaks to.
              </p>
            </div>
            {failed ? (
              <Panel>
                <EmptyState title="The traceability table could not be loaded" hint="It is served from docs/traceability.yaml by the backend." />
              </Panel>
            ) : !data ? (
              <Panel><Loading /></Panel>
            ) : (
              <>
                <Panel bodyClass="flush">
                  <div className="table-scroll">
                    <table className="table">
                      <thead>
                        <tr>
                          <th><span className="th-inner">Pipeline component</span></th>
                          <th><span className="th-inner" style={{ justifyContent: "flex-start" }}>Technique used here</span></th>
                          <th><span className="th-inner" style={{ justifyContent: "flex-start" }}>Paper reference</span></th>
                          <th><span className="th-inner" style={{ justifyContent: "flex-start" }}>Gap</span></th>
                          <th><span className="th-inner" style={{ justifyContent: "flex-start" }}>Reviewed</span></th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.components.map((component) => (
                          <tr key={component.component}>
                            <td><strong>{component.component}</strong></td>
                            <td style={{ textAlign: "left", whiteSpace: "normal", maxWidth: 420 }}>{component.technique}</td>
                            <td style={{ textAlign: "left", whiteSpace: "normal" }} className="small">{component.references.join("; ")}</td>
                            <td style={{ textAlign: "left" }} className="mono small">{component.gaps.join(", ")}</td>
                            <td style={{ textAlign: "left" }} className="small muted">{component.verified_by}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
                <div className="gap-list">
                  {Object.entries(data.gaps).map(([key, text]) => (
                    <Reveal key={key} className="gap-item">
                      <span className="gap-key mono">{key}</span>
                      <span>{text}</span>
                    </Reveal>
                  ))}
                </div>
                <TechnicalDetails summary="View implementation details">
                  <dl className="kv">
                    {data.components.map((component) => (
                      <div key={component.component} style={{ display: "contents" }}>
                        <dt>{component.component}</dt>
                        <dd>{component.implemented_in} · {component.status}</dd>
                      </div>
                    ))}
                  </dl>
                </TechnicalDetails>
              </>
            )}
          </Section>

          <Section id="limits" no={9} title="Current limitations">
            <div className="prose">
              <p>
                Stated plainly, because a prototype that hides its boundaries cannot be evaluated. None of these are
                worked around in the interface: where a definition is open, the screen says so instead of choosing one.
              </p>
            </div>
            <dl className="limits">
              {LIMITS.map((limit) => (
                <Reveal key={limit.k} className="limit">
                  <dt>{limit.k}</dt>
                  <dd>{limit.v}</dd>
                </Reveal>
              ))}
            </dl>
          </Section>

          <Section id="glossary" no={10} title="Glossary">
            <div className="prose">
              <p>
                Every term the interface uses, with the same wording as the ⓘ explanations beside it. A term whose
                definition is still a team decision says so here rather than presenting a settled answer.
              </p>
            </div>
            <Panel bodyClass="flush">
              <div className="table-scroll">
                <table className="table">
                  <tbody>
                    {(Object.entries(EXPLANATION_MAP) as [keyof typeof EXPLANATIONS, Explanation][]).map(([key, entry]) => (
                      <tr key={key}>
                        <td style={{ width: 250 }}>
                          <span className="row" style={{ gap: 6 }}>
                            <strong>{entry.term}</strong>
                            <ExplainButton id={key} />
                          </span>
                        </td>
                        <td style={{ textAlign: "left", whiteSpace: "normal" }}>
                          {entry.what}
                          {entry.pending && <div className="tiny" style={{ color: "var(--warn)", marginTop: 4 }}>⚠ {entry.pending}</div>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </Section>
        </div>
      </div>
    </div>
  );
}
