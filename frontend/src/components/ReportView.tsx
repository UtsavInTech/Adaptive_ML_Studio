/** One generated testbed report: its text, tables and figures, with every file downloadable.
 *
 *  The report is written by `research_testbed/scripts/report.py`. It is shown as written; the page adds
 *  nothing to it. Markdown is parsed into data and rendered by React, so no part of it is inserted as HTML. */

import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, type Report } from "../lib/api";
import { parseMarkdown, safeHref, type Inline } from "../lib/markdown";
import { ErrorState, Loading, Panel, SectionHead } from "./ui";

function InlineText({ parts }: { parts: Inline[] }): ReactNode {
  return parts.map((part, i) => {
    switch (part.kind) {
      case "code": return <code key={i} className="mono">{part.text}</code>;
      case "strong": return <strong key={i}><InlineText parts={part.children} /></strong>;
      case "em": return <em key={i}><InlineText parts={part.children} /></em>;
      case "link": {
        const href = safeHref(part.href);
        // Relative links point into the repository, which this page does not serve: show them as text.
        return href && /^https?:\/\//.test(href)
          ? <a key={i} href={href} target="_blank" rel="noreferrer"><InlineText parts={part.children} /></a>
          : <span key={i}><InlineText parts={part.children} /></span>;
      }
      default: return <Fragment key={i}>{part.text}</Fragment>;
    }
  });
}

/** A figure path from the report ("figures/x.png") as a URL the API serves, or null if it is not one. */
const figureUrl = (name: string, src: string): string | null =>
  /^figures\/[\w.-]+\.png$/.test(src) ? api.reportFileUrl(name, src) : null;

export default function ReportView({ name }: { name: string }) {
  const [report, setReport] = useState<Report | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const load = () => {
    setReport(null);
    setProblem(null);
    api.report(name).then(setReport).catch((e: Error) => setProblem(e.message));
  };
  useEffect(load, [name]);

  const blocks = useMemo(() => (report ? parseMarkdown(report.markdown) : []), [report]);

  if (problem) {
    return <ErrorState title="This report could not be loaded." why="The report folder may have been moved or regenerated." technical={problem}
      action={<button type="button" className="btn small" onClick={load}>Retry</button>} />;
  }
  if (!report) return <Panel title="Loading report"><Loading /></Panel>;

  const shown = new Set(blocks.flatMap((b) => (b.kind === "image" ? [b.src] : [])));
  const extraFigures = report.figures.filter((f) => !shown.has(f.path));

  return (
    <div className="stack report-view">
      <Panel
        title={<span className="mono">{report.name}</span>}
        sub="generated report"
        actions={<a className="btn small" href={api.reportFileUrl(name, "report.md", true)}>Download report.md</a>}
      >
        <p className="small muted" style={{ marginTop: 0 }}>
          Shown as the report generator wrote it. Device tiers other than standard are simulated, with placeholder budgets.
        </p>
        <article className="report-body">
          {blocks.map((block, i) => {
            switch (block.kind) {
              case "heading": {
                const Tag = (`h${Math.min(6, block.level + 1)}`) as "h2" | "h3" | "h4" | "h5" | "h6";
                return <Tag key={i}><InlineText parts={block.text} /></Tag>;
              }
              case "paragraph": return <p key={i}><InlineText parts={block.text} /></p>;
              case "list": return <ul key={i}>{block.items.map((item, k) => <li key={k}><InlineText parts={item} /></li>)}</ul>;
              case "code": return <pre key={i} className="mono">{block.text}</pre>;
              case "table":
                return (
                  <div className="table-scroll" key={i}>
                    <table className="table report-table">
                      <thead><tr>{block.header.map((cell, k) => <th key={k} style={{ textAlign: block.align[k] }}><InlineText parts={cell} /></th>)}</tr></thead>
                      <tbody>
                        {block.rows.map((row, r) => (
                          <tr key={r}>{row.map((cell, k) => <td key={k} className={block.align[k] === "right" ? "num" : undefined} style={{ textAlign: block.align[k] }}><InlineText parts={cell} /></td>)}</tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              case "image": {
                const url = figureUrl(name, block.src);
                const svg = report.figures.find((f) => f.path === block.src)?.svg;
                return url ? (
                  <figure key={i} className="report-figure">
                    <img src={url} alt={block.alt} loading="lazy" />
                    <figcaption>
                      <span className="mono">{block.src}</span>
                      <a href={api.reportFileUrl(name, block.src, true)}>PNG</a>
                      {svg && <a href={api.reportFileUrl(name, svg, true)}>SVG</a>}
                    </figcaption>
                  </figure>
                ) : <p key={i} className="small muted">[figure {block.alt}: {block.src}]</p>;
              }
            }
          })}
        </article>
      </Panel>

      {extraFigures.length > 0 && (
        <section className="stack tight">
          <SectionHead title="Other figures" hint="in the report folder but not referenced in its text" />
          <div className="report-figures">
            {extraFigures.map((f) => (
              <figure key={f.path} className="report-figure">
                <img src={api.reportFileUrl(name, f.path)} alt={f.path} loading="lazy" />
                <figcaption>
                  <span className="mono">{f.path}</span>
                  <a href={api.reportFileUrl(name, f.path, true)}>PNG</a>
                  {f.svg && <a href={api.reportFileUrl(name, f.svg, true)}>SVG</a>}
                </figcaption>
              </figure>
            ))}
          </div>
        </section>
      )}

      {report.tables.length > 0 && (
        <section className="stack tight">
          <SectionHead title="Data tables" hint="the CSV files the figures and tables were made from · long decimals shown to 4 significant digits; the downloads are exact" />
          {report.tables.map((table) => (
            <Panel key={table.path} title={<span className="mono">{table.path}</span>} sub={`${table.rows.length.toLocaleString()} rows · ${table.columns.length} columns`}
              actions={<a className="btn small" href={api.reportFileUrl(name, table.path, true)}>Download CSV</a>} bodyClass="flush">
              <details className="csv-details">
                <summary>Show the table</summary>
                <div className="table-scroll csv-scroll">
                  <table className="table">
                    <thead><tr>{table.columns.map((c) => <th key={c}><span className="th-inner">{c}</span></th>)}</tr></thead>
                    <tbody>
                      {table.rows.map((row, r) => (
                        <tr key={r}>{row.map((cell, k) => <td key={k} className={/^-?\d/.test(cell) ? "num" : undefined}>{/^-?\d+\.\d{5,}$/.test(cell) ? Number(cell).toPrecision(4) : cell}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </Panel>
          ))}
        </section>
      )}
    </div>
  );
}
