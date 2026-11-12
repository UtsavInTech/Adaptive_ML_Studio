/** The main comparison as one picture: time per connection against the device's budget, with the
 *  quality figures a non-specialist asks for (attacks caught, false alarms). Numbers are read from the
 *  saved held-out report; nothing is typed in. Renders nothing when the report is missing. */

import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { budgetWords, headline, headlineSentence, perSecond, type Headline as Data, type Row } from "../lib/headline";
import { href } from "../lib/router";

const TIERS = [
  { tier: "small_sim", label: "Small device", said: "Raspberry Pi class" },
  { tier: "micro_sim", label: "Very small device", said: "IoT gateway class" },
];

export function useHeldout(): Row[] | null {
  const [rows, setRows] = useState<Row[] | null>(null);
  useEffect(() => {
    let alive = true;
    api.report("heldout")
      .then((report) => {
        const table = report.tables.find((t) => t.path.endsWith("settings.csv"));
        if (alive) setRows(table ? table.rows.map((cells) => Object.fromEntries(table.columns.map((c, i) => [c, cells[i] ?? ""]))) : []);
      })
      .catch(() => alive && setRows([]));
    return () => { alive = false; };
  }, []);
  return rows;
}

const pct = (value: number, digits = 1) => `${(value * 100).toFixed(digits)} %`;
const whole = (value: number) => Math.round(value).toLocaleString();

function Bar({ name, tag, us, max, budget, over, ours }: { name: string; tag: string; us: number; max: number; budget: number; over: number; ours?: boolean }) {
  return (
    <div className={`hl-bar${ours ? " ours" : ""}`}>
      <div className="hl-bar-name">
        <strong>{name}</strong>
        <span>{tag}</span>
      </div>
      <div className="hl-track" role="img" aria-label={`${name}: ${Math.round(us)} microseconds per connection, ${budgetWords(over)} of ${Math.round(budget)}`}>
        <span className={`hl-fill${over > 0.05 ? " over" : ""}`} style={{ width: `${(us / max) * 100}%` }} />
        <span className="hl-budget" style={{ left: `${(budget / max) * 100}%` }} />
      </div>
      <div className="hl-bar-value">
        <strong>{Math.round(us)} µs</strong>
        <span className={`badge ${over > 0.05 ? "warn" : "ok"}`}>{budgetWords(over)}</span>
      </div>
    </div>
  );
}

function Comparison({ data, label, said }: { data: Data; label: string; said: string }) {
  const max = Math.max(data.rules.us, data.ours.us, data.budgetUs) * 1.08;
  const figures: { k: string; hint: string; rules: string; ours: string }[] = [
    { k: "Attacks caught", hint: "of all attack connections", rules: pct(data.rules.caught), ours: pct(data.ours.caught) },
    { k: "False alarms", hint: "of all normal connections", rules: pct(data.rules.falseAlarms, 2), ours: pct(data.ours.falseAlarms, 2) },
    { k: "Wrong decisions", hint: "per day, both kinds", rules: whole(data.rules.mistakes), ours: whole(data.ours.mistakes) },
    { k: "Connections per second", hint: "one processor core can check", rules: whole(perSecond(data.rules.us)), ours: whole(perSecond(data.ours.us)) },
  ];
  return (
    <div className="hl-card">
      <div className="hl-card-head">
        <h3>{label} <span>{said}, simulated</span></h3>
        <span className="hl-budget-key"><i /> budget: {Math.round(data.budgetUs)} µs per connection</span>
      </div>
      <p className="hl-axis">Computing time spent on each connection (shorter is cheaper)</p>
      <Bar name="Rules from our review" tag="R1–R5" us={data.rules.us} max={max} budget={data.budgetUs} over={data.rulesOver} />
      <Bar name="Our new controller" tag="proposed" us={data.ours.us} max={max} budget={data.budgetUs} over={data.oursOver} ours />
      <table className="hl-figures">
        <thead>
          <tr><th /><th>Rules from our review</th><th>Our new controller</th></tr>
        </thead>
        <tbody>
          {figures.map((f) => (
            <tr key={f.k}>
              <th scope="row">{f.k}<span>{f.hint}</span></th>
              <td>{f.rules}</td>
              <td className="ours">{f.ours}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hl-sentence">{headlineSentence(data)}</p>
    </div>
  );
}

export default function Headline({ rows, compact }: { rows: Row[] | null; compact?: boolean }) {
  if (!rows) return null;
  const cards = TIERS.map((t) => ({ ...t, data: headline(rows, t.tier) })).filter((t): t is typeof t & { data: Data } => !!t.data);
  if (!cards.length) return null;
  const shown = compact ? cards.slice(0, 1) : cards;
  const days = shown[0].data.days.map((d) => d[0].toUpperCase() + d.slice(1)).join(" and ");
  return (
    <div className="hl">
      <div className={`hl-grid${shown.length === 1 ? " one" : ""}`}>
        {shown.map((c) => <Comparison key={c.tier} data={c.data} label={c.label} said={c.said} />)}
      </div>
      <p className="hl-note">
        Averages over {days}, two days of real traffic that were not used to design the controller; three runs each.
        Device limits are simulated in software with placeholder budgets, on one dataset.{" "}
        {compact && <a href={href({ page: "findings" })}>All findings, including what does not work →</a>}
      </p>
    </div>
  );
}
