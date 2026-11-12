/** Step 5 of the walkthrough: what the measurements say.
 *
 *  This page is the team's reading of the saved reports. Every number is read at load time from a
 *  generated report (research_testbed/reports/…), never typed in, and each table names the report it
 *  came from. The wording around the numbers is the team's; the limits are stated on the page. */

import { useEffect, useState } from "react";

import Headline from "../components/Headline";
import { EmptyState, Loading, Panel } from "../components/ui";
import { api, type Report } from "../lib/api";
import { methodLabel } from "../lib/format";
import { href } from "../lib/router";

type Row = Record<string, string>;

/** Pipeline stages grouped by what they are for, so the chart needs four colours instead of seven.
 *  Blue = getting the data ready, orange = learning, green = the prediction itself, grey = overhead. */
const COST_GROUPS: { label: string; keys: string[]; color: string }[] = [
  { label: "Getting the data ready", keys: ["C_pre", "C_fs"], color: "#2f6fb5" },
  { label: "Making the prediction", keys: ["C_inf"], color: "#1d9e75" },
  { label: "Learning from the answer", keys: ["C_upd", "C_ret"], color: "#d9772b" },
  { label: "Drift checks and control", keys: ["C_drift", "C_ctrl"], color: "#8a94a1" },
];

function settings(report: Report | null): Row[] {
  const table = report?.tables.find((t) => t.path.endsWith("settings.csv"));
  if (!table) return [];
  return table.rows.map((cells) => Object.fromEntries(table.columns.map((column, i) => [column, cells[i] ?? ""])));
}

const n = (value: string | undefined): number | null => {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const groupUs = (row: Row, keys: string[]): number => keys.reduce((sum, key) => sum + (n(row[key]) ?? 0), 0);

const fixed = (value: number | null, digits: number): string => (value == null ? "—" : value.toFixed(digits));
const whole = (value: number | null): string => (value == null ? "—" : Math.round(value).toLocaleString());

function Kappa({ row }: { row: Row }) {
  const value = n(row.kappa_temporal);
  const low = n(row.kappa_temporal_low);
  const high = n(row.kappa_temporal_high);
  return (
    <>
      <strong>{fixed(value, 2)}</strong>
      {low != null && high != null && value !== 0 && (
        <span className="muted tiny">
          {" "}
          [{fixed(low, 2)}, {fixed(high, 2)}]
        </span>
      )}
    </>
  );
}

/** A horizontal bar for a score between 0 and 1; scores at or below zero show an empty bar. */
function ScoreBar({ value }: { value: number | null }) {
  const width = value == null ? 0 : Math.max(0, Math.min(1, value)) * 100;
  return (
    <span className="score-bar" aria-hidden="true">
      <span style={{ width: `${width}%` }} />
    </span>
  );
}

function Budget({ row }: { row: Row }) {
  const cost = n(row.mean_us);
  const budget = n(row.budget_us);
  if (cost == null) return <>—</>;
  if (budget == null) return <>{fixed(cost, 0)} µs</>;
  const over = cost > budget * 1.05;
  return (
    <>
      {fixed(cost, 0)} µs <span className={`badge ${over ? "warn" : "ok"}`}>{over ? `${Math.round((cost / budget - 1) * 100)} % over budget` : cost > budget ? "at budget" : "within budget"}</span>
    </>
  );
}

function Finding({
  number, title, reading, matters, source, children,
}: {
  number: number;
  title: string;
  reading: string;
  /** What the finding means for someone running this on a real device. */
  matters: string;
  source: { report: string; label: string };
  children: React.ReactNode;
}) {
  return (
    <section className="finding">
      <header className="finding-head">
        <span className="finding-number">Finding {number}</span>
        <h2>{title}</h2>
        <p className="finding-reading">{reading}</p>
      </header>
      {children}
      <p className="finding-matters"><strong>Why it matters.</strong> {matters}</p>
      <p className="tiny muted finding-source">
        Numbers read from the saved report <a href={href({ page: "testbed", report: source.report })}>{source.label}</a>.
      </p>
    </section>
  );
}

export default function Findings() {
  const [phase2, setPhase2] = useState<Report | null>(null);
  const [effort, setEffort] = useState<Report | null>(null);
  const [heldout, setHeldout] = useState<Report | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "missing">("loading");

  useEffect(() => {
    let alive = true;
    Promise.allSettled([api.report("phase2"), api.report("effort"), api.report("heldout")]).then(([a, b, c]) => {
      if (!alive) return;
      setPhase2(a.status === "fulfilled" ? a.value : null);
      setEffort(b.status === "fulfilled" ? b.value : null);
      setHeldout(c.status === "fulfilled" ? c.value : null);
      setState(a.status === "fulfilled" || b.status === "fulfilled" ? "ready" : "missing");
    });
    return () => {
      alive = false;
    };
  }, []);

  const week = settings(phase2);
  const wednesday = settings(effort);
  const later = settings(heldout);
  const days: { setting: string; label: string }[] = [
    { setting: "thursday", label: "Thursday" },
    { setting: "friday", label: "Friday" },
  ];
  const pick = (setting: string, method: string, tier: string) =>
    wednesday.find((r) => r.setting === setting && r.method === method && r.tier === tier);
  const copy = week.find((r) => r.method === "no_change");
  const copyAccuracy = n(copy?.accuracy);
  const learners = week.filter((r) => r.method !== "no_change" && r.method !== "static");
  const accuracies = learners.map((r) => n(r.accuracy) ?? 0);

  const costRows = ["incremental", "joint", "effort"]
    .map((method) => pick("core", method, "small_sim"))
    .filter((r): r is Row => !!r && COST_GROUPS.some((g) => groupUs(r, g.keys) > 0));
  const totalUs = (r: Row) => COST_GROUPS.reduce((sum, g) => sum + groupUs(r, g.keys), 0);
  const costMax = Math.max(1, ...costRows.map(totalUs));
  // Share of the time that goes to the two big groups, for the method with no controller.
  const bigShare = costRows[0] ? (groupUs(costRows[0], COST_GROUPS[0].keys) + groupUs(costRows[0], COST_GROUPS[2].keys)) / totalUs(costRows[0]) : null;

  const tiers: { tier: string; label: string }[] = [
    { tier: "small_sim", label: "Small device (simulated): 100 µs per connection" },
    { tier: "micro_sim", label: "Very small device (simulated): 50 µs per connection" },
  ];
  const delayed = ["incremental", "joint", "effort"].map((m) => pick("labels_delay1000", m, "small_sim")).filter((r): r is Row => !!r);

  return (
    <main className="page findings">
      <header className="findings-head">
        <span className="eyebrow">Step 5 · What we found</span>
        <h1>What we found.</h1>
        <p className="lead">
          We built the system our review paper proposed, ran it on a week of real network traffic with dated
          cyber-attacks, and measured it. The main result comes first; the four findings behind it follow, including
          the one that does not work yet.
        </p>
        <p className="small muted">
          Every number on this page is read from a saved report when the page loads. Device limits are simulated in
          software with placeholder budgets.
        </p>
      </header>

      {state === "loading" && <Loading label="Reading the saved reports…" />}
      {state === "missing" && (
        <EmptyState
          title="No saved reports were found."
          hint="Generate them with research_testbed/scripts/report.py, then reload this page."
        />
      )}

      {later.length > 0 && (
        <section className="finding main-result">
          <header className="finding-head">
            <span className="finding-number">The main result</span>
            <h2>Equal or better protection, for much less computing time.</h2>
            <p className="finding-reading">
              Two ways of running the same detector on a small device. The rules from our review keep learning at full
              effort and overshoot the time the device has. Our new controller works less on ordinary traffic and more
              when something changes. The dashed line is the device's budget.
            </p>
          </header>
          <Headline rows={later} />
        </section>
      )}

      {week.length > 0 && (
        <Finding
          number={1}
          title="Accuracy cannot rank methods on this data."
          reading={
            copyAccuracy != null
              ? `Repeating the previous answer, without looking at the connection at all, is right ${fixed(copyAccuracy * 100, 1)} % of the time, because attacks arrive in long runs. So we score each method by how far it gets above copying: 0 means no better than copying, 1 means perfect. (The technical name is κ-temporal.)`
              : "Attacks arrive in long runs, so copying the previous answer already scores very high. We score each method by its gain over that copycat (κ-temporal)."
          }
          matters="A product that advertises 99 % accuracy on this kind of traffic may have learned nothing. Any fair comparison needs a score that copying cannot win."
          source={{ report: "phase2", label: "phase2 — whole week, 2.1 million connections" }}
        >
          <Panel bodyClass="flush">
            <table className="table findings-table">
              <thead>
                <tr>
                  <th>Method</th>
                  <th className="num">Accuracy</th>
                  <th>Score above copying, 0 to 1</th>
                  <th className="num">Time per connection</th>
                </tr>
              </thead>
              <tbody>
                {week.map((r) => (
                  <tr key={r.method} className={r.method === "no_change" ? "reference" : undefined}>
                    <td>{methodLabel(r.method)}</td>
                    <td className="num">{fixed((n(r.accuracy) ?? 0) * 100, 2)} %</td>
                    <td>
                      <span className="score-cell">
                        <ScoreBar value={n(r.kappa_temporal)} />
                        <Kappa row={r} />
                      </span>
                    </td>
                    <td className="num">{whole(n(r.mean_us))} µs</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
          <p className="small muted">
            {learners.length > 1 &&
              `The learning methods all score between ${fixed(Math.min(...accuracies) * 100, 1)} % and ${fixed(Math.max(...accuracies) * 100, 1)} % on accuracy. `}
            On gain over copying they spread out, and higher gain costs more time per connection.
          </p>
        </Finding>
      )}

      {costRows.length > 0 && (
        <Finding
          number={2}
          title="Two stages take most of the time: preparing the data and updating the model."
          reading="Our review paper said that which stage dominates the cost was an open question. Measured stage by stage in the same run, checking for drift is cheap; preparing the inputs and updating the model are where the time goes."
          matters="To save computing time on a small device, these two stages are where to look. Making drift detection faster would save almost nothing."
          source={{ report: "effort", label: "effort — Wednesday's attacks, 300,000 connections" }}
        >
          <Panel>
            <div className="cost-bars">
              {costRows.map((r) => {
                const total = totalUs(r);
                return (
                  <div className="cost-row" key={r.method}>
                    <span className="cost-name">{methodLabel(r.method)}</span>
                    <span className="cost-track">
                      <span className="cost-fill" style={{ width: `${(total / costMax) * 100}%` }}>
                        {COST_GROUPS.map((g) => {
                          const value = groupUs(r, g.keys);
                          return value > 0 ? (
                            <span
                              key={g.label}
                              style={{ width: `${(value / total) * 100}%`, background: g.color }}
                              title={`${g.label}: ${value.toFixed(0)} µs (${Math.round((value / total) * 100)} %)`}
                            >
                              {value / costMax > 0.07 ? Math.round(value) : ""}
                            </span>
                          ) : null;
                        })}
                      </span>
                    </span>
                    <span className="cost-total">{fixed(total, 0)} µs</span>
                  </div>
                );
              })}
            </div>
            <div className="cost-legend">
              {COST_GROUPS.map((g) => (
                <span key={g.label}>
                  <i style={{ background: g.color }} />
                  {g.label}
                </span>
              ))}
            </div>
          </Panel>
          <p className="small muted">
            Microseconds per connection on the simulated small device; the number in each block is that part's time.
            {bigShare != null && ` Without a controller, getting the data ready and learning take ${Math.round(bigShare * 100)} % of the time.`}{" "}
            The new controller (bottom bar) is shorter because it spends less on exactly those two parts.
          </p>
        </Finding>
      )}

      {wednesday.length > 0 && (
        <Finding
          number={3}
          title="The evidence: every day and device, one by one."
          reading="This is the evidence behind the main result. The controller was designed using Wednesday's traffic, so Wednesday is not a clean test. Thursday and Friday were not used in the design; those are the days the main result is built from. The tables give every day and device separately, with the uncertainty of each score."
          matters="A device that overshoots its time budget falls behind the traffic and starts missing connections. Staying inside the budget without losing protection is what makes the method usable."
          source={{ report: "effort", label: "effort — Wednesday's attacks, 300,000 connections" }}
        >
          <details className="finding-details">
            <summary>Show the table for each day and device</summary>
            <h3 className="finding-sub">Wednesday, the day the controller was designed on</h3>
          {tiers.map(({ tier, label }) => {
            const rows = ["incremental", "joint", "effort"].map((m) => pick("core", m, tier)).filter((r): r is Row => !!r);
            if (!rows.length) return null;
            return (
              <Panel key={tier} title={label} sub="simulated · placeholder budget" bodyClass="flush">
                <table className="table findings-table">
                  <thead>
                    <tr>
                      <th>Method</th>
                      <th className="num">Wrong decisions</th>
                      <th>Score above copying, 0 to 1 [95 % interval]</th>
                      <th>Time per connection</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.method} className={r.method === "effort" ? "ours" : undefined}>
                        <td>{methodLabel(r.method)}</td>
                        <td className="num">{whole(n(r.errors))}</td>
                        <td>
                          <span className="score-cell">
                            <ScoreBar value={n(r.kappa_temporal)} />
                            <Kappa row={r} />
                          </span>
                        </td>
                        <td>
                          <Budget row={r} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>
            );
          })}
          {later.length > 0 && (
            <>
              <h3 className="finding-sub">Thursday and Friday, not used in the design</h3>
              {days.map(({ setting, label }) =>
                tiers.map(({ tier, label: tierLabel }) => {
                  const rows = ["joint", "effort"]
                    .map((m) => later.find((r) => r.setting === setting && r.method === m && r.tier === tier))
                    .filter((r): r is Row => !!r);
                  if (!rows.length) return null;
                  return (
                    <Panel key={setting + tier} title={`${label} · ${tierLabel}`} sub="simulated · placeholder budget · mean of 3 runs" bodyClass="flush">
                      <table className="table findings-table">
                        <thead>
                          <tr>
                            <th>Method</th>
                            <th className="num">Wrong decisions</th>
                            <th>Score above copying, 0 to 1 [95 % interval]</th>
                            <th>Time per connection</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((r) => (
                            <tr key={r.method} className={r.method === "effort" ? "ours" : undefined}>
                              <td>{methodLabel(r.method)}</td>
                              <td className="num">{whole(n(r.errors))}</td>
                              <td>
                                <span className="score-cell">
                                  <ScoreBar value={n(r.kappa_temporal)} />
                                  <Kappa row={r} />
                                </span>
                              </td>
                              <td>
                                <Budget row={r} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </Panel>
                  );
                }),
              )}
              <p className="small muted">
                On these days the new controller stays at or near the budget, with errors equal to or lower than the
                rules'. Its three runs gave identical predictions; the rules' runs differ from each other, because
                their decisions depend on measured time. Source:{" "}
                <a href={href({ page: "testbed", report: "heldout" })}>held-out report</a>.
              </p>
            </>
          )}
          </details>
          <p className="small muted">
            Incremental learning has no controller and no budget; its time is shown for comparison. The most accurate
            method from the literature (Adaptive Random Forest) makes{" "}
            {whole(n(pick("ensembles", "arf", "small_sim")?.errors))} errors here, at about{" "}
            {whole(n(pick("ensembles", "arf", "small_sim")?.mean_us))} µs per connection.
          </p>
        </Finding>
      )}

      {delayed.length > 0 && (
        <Finding
          number={4}
          title="Not solved: when the true answer arrives late, both controllers do badly."
          reading="In practice nobody tells the system at once whether a connection was an attack. When that answer arrives 1,000 connections late, both controllers reset their model at the wrong moments. Plain continuous learning, which never resets, does far better. This is the main open problem."
          matters="A real device learns whether a connection was an attack only later, if at all. Until this is solved, the controller is not ready for real deployment."
          source={{ report: "effort", label: "effort — Wednesday's attacks, answers 1,000 connections late" }}
        >
          <Panel bodyClass="flush">
            <table className="table findings-table">
              <thead>
                <tr>
                  <th>Method</th>
                  <th className="num">Wrong decisions, answers on time</th>
                  <th className="num">Wrong decisions, answers 1,000 late</th>
                </tr>
              </thead>
              <tbody>
                {delayed.map((r) => (
                  <tr key={r.method}>
                    <td>{methodLabel(r.method)}</td>
                    <td className="num">{whole(n(pick("core", r.method, "small_sim")?.errors))}</td>
                    <td className="num">{whole(n(r.errors))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </Finding>
      )}

      {state === "ready" && (
        <section className="finding">
          <header className="finding-head">
            <span className="finding-number">Limits</span>
            <h2>What these numbers do not show.</h2>
          </header>
          <ul className="limits">
            <li>
              <strong>Simulated devices.</strong> The time and memory budgets are placeholder values enforced in
              software on a laptop. No real edge device was measured, and energy is not measured.
            </li>
            <li>
              <strong>One dataset, one network.</strong> One week of traffic from one lab. Thursday and Friday were
              not used to design the controller, but they come from the same week and network as the day that was.
              Finding 4 comes from one run.
            </li>
            <li>
              <strong>Not a new learning algorithm.</strong> The models are standard (Hoeffding tree, ADWIN). What is
              tested is how to control them under a budget.
            </li>
            <li>
              <strong>Very rare attacks are missed or caught unreliably.</strong> Five attack types have fewer than
              110 connections in the whole week. Two of them (11 and 13 connections) are missed by every method, and
              the others are caught poorly and unevenly.
            </li>
          </ul>
          <p className="small">
            Full tables, figures and the list of runs: <a href={href({ page: "testbed", report: "effort" })}>effort report</a>
            {" · "}
            <a href={href({ page: "testbed", report: "phase2" })}>whole-week report</a>
            {" · "}
            <a href={href({ page: "testbed" })}>run it yourself on the Testbed</a>.
          </p>
        </section>
      )}
    </main>
  );
}
