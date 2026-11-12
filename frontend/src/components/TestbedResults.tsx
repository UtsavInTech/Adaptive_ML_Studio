/** Research testbed measures for one run: stream-aware scores per method and tier, where the time per
 *  row goes, each attack type and attack period, and what the joint controller decided.
 *
 *  Reads only fields that runs made since the testbed's phases 2-3 store. A run without them shows an
 *  empty state rather than zeros. Nothing here ranks methods or draws a conclusion. */

import { useMemo, useState } from "react";

import type { Manifest } from "../lib/api";
import { DASH, kb, methodLabel, num, pct, samples, us } from "../lib/format";
import { COST_LABELS, COST_TERMS, actionWords, testbedRows, type TestbedRow, type TrialData } from "../lib/testbed";
import { ExplainButton } from "./Explain";
import { EmptyState, Panel, SectionHead } from "./ui";

const fixed = (value: number | null | undefined, digits = 2) => (value == null || Number.isNaN(value) ? DASH : value.toFixed(digits));

/** The tier, said plainly, with the simulated label whenever it applies. */
function TierCell({ row }: { row: TestbedRow }) {
  return (
    <div className="cell-sub">
      {row.tier}
      {row.simulated && <span className="tag sim tiny-tag">simulated · placeholder budgets</span>}
    </div>
  );
}

const rowKey = (row: TestbedRow) => `${row.trialId}:${row.method}`;
const groupKey = (row: TestbedRow) => `${row.tier} · seed ${row.seed}`;

export default function TestbedResults({ manifest, trials }: { manifest: Manifest; trials: Record<string, TrialData> }) {
  const rows = useMemo(() => testbedRows(manifest, trials), [manifest, trials]);
  const groups = useMemo(() => [...new Set(rows.map(groupKey))], [rows]);
  const [group, setGroup] = useState<string | null>(null);
  const chosen = group && groups.includes(group) ? group : groups[0];
  const inGroup = rows.filter((row) => groupKey(row) === chosen);
  const severalSeeds = new Set(rows.map((r) => r.seed)).size > 1;
  const loaded = manifest.trials.every((t) => trials[t.trial_id]);

  if (!rows.length) {
    return (
      <EmptyState
        title={loaded ? "This run has no testbed measures" : "Loading testbed measures"}
        hint={loaded ? "κ-temporal, cost terms and per-attack scores are stored by runs made with the research testbed. Older runs do not have them." : undefined}
      />
    );
  }

  const simulated = rows.some((r) => r.simulated);
  const maxCost = Math.max(...rows.map((r) => (r.costTerms ? COST_TERMS.reduce((s, k) => s + Math.max(0, r.costTerms?.[k] ?? 0), 0) : 0)), 1);
  const typeNames = [...new Set(inGroup.flatMap((r) => Object.keys(r.attackTypes ?? {})))].sort((a, b) => {
    const rowsOf = (name: string) => Math.max(...inGroup.map((r) => r.attackTypes?.[name]?.rows ?? 0));
    return rowsOf(b) - rowsOf(a);
  });
  const periodRows = inGroup.find((r) => r.periods?.length)?.periods ?? [];
  const joints = rows.filter((r) => r.controller);

  const groupPicker = groups.length > 1 && (
    <select value={chosen} onChange={(e) => setGroup(e.target.value)} aria-label="Tier and seed shown">
      {groups.map((g) => <option key={g} value={g}>{g}</option>)}
    </select>
  );

  return (
    <div className="stack testbed-results">
      {simulated && (
        <div className="banner">
          <div>
            <strong>Simulated tiers, placeholder budgets.</strong> Every tier other than <span className="mono">standard</span> enforces
            its budgets in software on this computer. No slower device is emulated, and the budget values are placeholders
            awaiting the research team's decision. <ExplainButton id="deviceTier" />
          </div>
        </div>
      )}

      <section className="stack tight">
        <SectionHead title="Scores and cost per method and tier" hint="after the warm-up · measurements, not a ranking" />
        <Panel bodyClass="flush">
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th><span className="th-inner">Method · tier</span></th>
                  <th><span className="th-inner">Accuracy <ExplainButton id="accuracy" /></span></th>
                  <th><span className="th-inner">κ-temporal <ExplainButton id="kappaTemporal" /></span></th>
                  <th><span className="th-inner">Macro-F1 <ExplainButton id="macroF1" /></span></th>
                  <th><span className="th-inner">Attack recall <ExplainButton id="attackRecall" /></span></th>
                  <th><span className="th-inner">False alarms <ExplainButton id="falseAlarm" /></span></th>
                  <th><span className="th-inner">Mean µs / row <ExplainButton id="latency" /></span></th>
                  <th><span className="th-inner">p99 µs / row <ExplainButton id="p99" /></span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={rowKey(row)}>
                    <td>
                      {methodLabel(row.method)}
                      <TierCell row={row} />
                      {severalSeeds && <div className="cell-sub">seed {row.seed}</div>}
                    </td>
                    <td className="num">{pct(row.accuracy, 2)}</td>
                    <td className="num">{fixed(row.kappaTemporal)}</td>
                    <td className="num">{fixed(row.macroF1, 3)}</td>
                    <td className="num">{pct(row.recall, 1)}</td>
                    <td className="num">{pct(row.falseAlarm, 2)}</td>
                    <td className="num">{num(row.meanUs, 1)}</td>
                    <td className="num">{num(row.p99Us, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tiny muted" style={{ padding: "10px 16px", margin: 0 }}>
            κ-temporal is the gain over repeating the previous row's label: 0 means no better than copying it, below 0 means
            worse.{rows[0]?.noChangeAccuracy != null && ` Copying the previous label scores ${pct(rows[0].noChangeAccuracy, 2)} on these rows.`}{" "}
            One run, one machine: differences between rows can include run-to-run variation, especially for methods whose
            behaviour depends on measured time.
          </p>
        </Panel>
      </section>

      {rows.some((r) => r.costTerms) && (
        <section className="stack tight">
          <SectionHead title="Where the time per row goes" explain="costTerms" hint="mean µs per row, split into the review's cost terms" />
          <Panel>
            <div className="cost-bars">
              {rows.filter((r) => r.costTerms).map((row) => {
                const total = COST_TERMS.reduce((s, k) => s + Math.max(0, row.costTerms?.[k] ?? 0), 0);
                return (
                  <div className="cost-bar-row" key={`cost-${rowKey(row)}`}>
                    <span className="cost-who">
                      {methodLabel(row.method)}
                      <small>{row.tier}{row.simulated ? " · simulated" : ""}{severalSeeds ? ` · seed ${row.seed}` : ""}</small>
                    </span>
                    <span className="cost-track" role="img" aria-label={`${methodLabel(row.method)}: ${COST_TERMS.map((k) => `${k} ${num(row.costTerms?.[k] ?? null, 1)} µs`).join(", ")}`}>
                      {COST_TERMS.map((k, i) => {
                        const value = Math.max(0, row.costTerms?.[k] ?? 0);
                        return value > 0 ? (
                          <span key={k} className={`cost-seg c${i}`} style={{ width: `${(value / maxCost) * 100}%` }} title={`${COST_LABELS[k]}: ${value.toFixed(1)} µs`} />
                        ) : null;
                      })}
                    </span>
                    <span className="cost-total">{us(total, 1)}</span>
                  </div>
                );
              })}
            </div>
            <div className="legend cost-legend">
              {COST_TERMS.map((k, i) => (
                <span className="key" key={k}><span className={`swatch cost-seg c${i}`} /><span className="muted">{COST_LABELS[k]}</span></span>
              ))}
            </div>
            <p className="chart-note">
              C_comm (sending data elsewhere) does not apply: everything runs on one machine. “Unattributed” is measured time
              that no term accounts for. Hover a segment for its value.
            </p>
          </Panel>
        </section>
      )}

      {typeNames.length > 0 && (
        <section className="stack tight">
          <SectionHead title="Each attack type" explain="attackRecall" hint="share of each original label flagged as an attack, after the warm-up" />
          <Panel bodyClass="flush" actions={groupPicker || undefined} title={chosen}>
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th><span className="th-inner">Original label</span></th>
                    <th><span className="th-inner">Rows</span></th>
                    {inGroup.map((row) => <th key={rowKey(row)}><span className="th-inner">{methodLabel(row.method)}</span></th>)}
                  </tr>
                </thead>
                <tbody>
                  {typeNames.map((name) => {
                    const first = inGroup.find((r) => r.attackTypes?.[name])?.attackTypes?.[name];
                    return (
                      <tr key={name}>
                        <td>
                          {name}
                          <div className="cell-sub">{first?.counted_as_attack ? "attack: share flagged = recall" : "benign: share flagged = false alarms"}</div>
                        </td>
                        <td className="num">{samples(first?.rows ?? null)}</td>
                        {inGroup.map((row) => <td className="num" key={rowKey(row)}>{pct(row.attackTypes?.[name]?.flagged_share ?? null, 1)}</td>)}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="tiny muted" style={{ padding: "10px 16px", margin: 0 }}>
              Flows marked “Attempted” count as benign, following the dataset's corrected release.
            </p>
          </Panel>
        </section>
      )}

      {inGroup.some((r) => r.periods) && (
        <section className="stack tight">
          <SectionHead title="Each attack period" explain="attackPeriods" hint="the dataset's dated attacks that start inside the replayed rows" />
          <Panel bodyClass="flush" actions={groupPicker || undefined} title={chosen}>
            {periodRows.length === 0 ? (
              <EmptyState title="No attack period starts inside these rows" hint="Choose a slice that contains an attack to see per-period recall." />
            ) : (
              <div className="table-scroll">
                <table className="table">
                  <thead>
                    <tr className="group-header">
                      <th />
                      <th />
                      {inGroup.map((row) => <th key={rowKey(row)} colSpan={2}>{methodLabel(row.method)}</th>)}
                    </tr>
                    <tr>
                      <th><span className="th-inner">Attack · rows</span></th>
                      <th><span className="th-inner">Attack flows</span></th>
                      {inGroup.flatMap((row) => [
                        <th key={`${rowKey(row)}-r`}><span className="th-inner">Recall</span></th>,
                        <th key={`${rowKey(row)}-f`}><span className="th-inner">Flows before first flagged</span></th>,
                      ])}
                    </tr>
                  </thead>
                  <tbody>
                    {periodRows.map((period, index) => (
                      <tr key={`${period.attack_type}-${period.start_row}`}>
                        <td>
                          {period.attack_type}
                          <div className="cell-sub">rows {samples(period.start_row)}–{samples(period.end_row)}</div>
                        </td>
                        <td className="num">{samples(period.flows)}</td>
                        {inGroup.flatMap((row) => {
                          const mine = row.periods?.find((p) => p.start_row === period.start_row && p.attack_type === period.attack_type) ?? row.periods?.[index];
                          return [
                            <td className="num" key={`${rowKey(row)}-r`}>{pct(mine?.recall ?? null, 1)}</td>,
                            <td className="num" key={`${rowKey(row)}-f`}>{mine?.flows_until_first_flagged == null ? "never" : samples(mine.flows_until_first_flagged)}</td>,
                          ];
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="tiny muted" style={{ padding: "10px 16px", margin: 0 }}>
              Row numbers count from the first replayed row. “Flows before first flagged” counts the period's attack flows that
              passed before the method flagged one; “never” means it flagged none.
            </p>
          </Panel>
        </section>
      )}

      {joints.length > 0 && (
        <section className="stack tight">
          <SectionHead title="What the joint controller decided" hint="rule actions and resource checks, as logged" />
          <div className="controller-grid">
            {joints.map((row) => <ControllerCard key={`ctl-${rowKey(row)}`} row={row} severalSeeds={severalSeeds} />)}
          </div>
        </section>
      )}
    </div>
  );
}

function ControllerCard({ row, severalSeeds }: { row: TestbedRow; severalSeeds: boolean }) {
  const c = row.controller ?? {};
  const actions = Object.entries(c.actions ?? {}).sort((a, b) => b[1] - a[1]);
  const memoryBudget = c.budgets?.model_memory_mib ?? row.memoryBudgetMib;
  const budgetKb = memoryBudget != null ? memoryBudget * 1024 : null;
  const peakKb = c.peak_model_bytes != null ? c.peak_model_bytes / 1024 : null;
  const share = (a: number | null | undefined, b: number | null | undefined) => (a != null && b ? a / b : null);
  return (
    <Panel title={<>{methodLabel(row.method)} <span className="muted small">· {row.tier}{severalSeeds ? ` · seed ${row.seed}` : ""}</span></>}>
      <div className="row wrap" style={{ gap: 6, marginBottom: 10 }}>
        {row.simulated && <span className="tag sim">simulated · placeholder budgets</span>}
        <span className="tag">rules on: {(c.rules ?? []).join(", ") || "none"}</span>
        <span className="tag">resource checks {c.resource_gating === false ? "off" : "on"}</span>
      </div>
      <dl className="kv">
        <dt>Decisions logged</dt><dd>{num(c.decisions ?? null)}</dd>
        <dt>Rows in lightweight mode <ExplainButton id="lightweightMode" /></dt>
        <dd>{samples(c.rows_in_lightweight_mode ?? null)}{share(c.rows_in_lightweight_mode, row.scored) != null && ` (${pct(share(c.rows_in_lightweight_mode, row.scored), 1)} of scored rows)`}</dd>
        <dt>Features at the end</dt><dd>{num(c.final_features ?? null)}{row.nFeatures ? ` of ${row.nFeatures}` : ""}</dd>
        <dt>Learning from</dt><dd>{c.final_update_stride == null ? DASH : c.final_update_stride === 1 ? "every row" : `every ${c.final_update_stride}th row`}</dd>
        <dt>Peak model size</dt><dd>{kb(peakKb)}{budgetKb != null ? ` · budget ${kb(budgetKb)}${peakKb != null ? ` (${(peakKb / budgetKb).toFixed(2)}×)` : ""}` : " · no memory budget"}</dd>
        <dt>Memory checks over budget</dt>
        <dd>{c.memory_probes_over_budget == null || !budgetKb ? DASH : `${samples(c.memory_probes_over_budget)} of ${samples(c.memory_probes ?? null)} (${pct(share(c.memory_probes_over_budget, c.memory_probes), 1)})`}</dd>
        <dt>CPU budget per row</dt>
        <dd>{c.budgets?.cpu_us_per_row == null ? "none" : `${us(c.budgets.cpu_us_per_row, 0)}${c.budgets.cpu_follows_arrival_rate ? `, follows the arrival rate (lowest ${us(c.budgets.cpu_us_per_row_lowest ?? null, 0)})` : ""}`}</dd>
        <dt>Per-row deadline</dt><dd>{c.budgets?.deadline_ms == null ? "none" : `${c.budgets.deadline_ms} ms`}</dd>
      </dl>
      {actions.length ? (
        <table className="table compact-table" style={{ marginTop: 12, width: "100%" }}>
          <thead><tr><th><span className="th-inner">Rule</span></th><th style={{ textAlign: "left" }}><span className="th-inner">Action</span></th><th><span className="th-inner">Times</span></th></tr></thead>
          <tbody>
            {actions.map(([action, count]) => {
              const { rule, what } = actionWords(action);
              return <tr key={action}><td className="mono">{rule || DASH}</td><td style={{ textAlign: "left" }}>{what}</td><td className="num">{samples(count)}</td></tr>;
            })}
          </tbody>
        </table>
      ) : <p className="small muted">No rule fired in this trial.</p>}
    </Panel>
  );
}
