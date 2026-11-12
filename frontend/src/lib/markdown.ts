/** A small Markdown reader for the testbed's generated reports — no dependency, no raw HTML.
 *
 *  It understands what `research_testbed/scripts/report.py` writes: headings, paragraphs, bullet
 *  lists, pipe tables, images on a line of their own, and inline code, bold, italic and links. Anything
 *  else is shown as plain text. The output is data; the page renders it with React, so nothing in a
 *  report is ever inserted as HTML. */

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "code"; text: string }
  | { kind: "strong"; children: Inline[] }
  | { kind: "em"; children: Inline[] }
  | { kind: "link"; href: string; children: Inline[] };

export type Block =
  | { kind: "heading"; level: number; text: Inline[] }
  | { kind: "paragraph"; text: Inline[] }
  | { kind: "list"; items: Inline[][] }
  | { kind: "table"; header: Inline[][]; align: ("left" | "right" | "center")[]; rows: Inline[][][] }
  | { kind: "image"; alt: string; src: string }
  | { kind: "code"; text: string };

const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\[[^\]]+\]\([^)\s]+\))|(\*[^*\s][^*]*\*)/;

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let rest = text;
  while (rest) {
    const match = INLINE.exec(rest);
    if (!match) {
      out.push({ kind: "text", text: rest });
      break;
    }
    if (match.index > 0) out.push({ kind: "text", text: rest.slice(0, match.index) });
    const token = match[0];
    if (match[1]) out.push({ kind: "code", text: token.slice(1, -1) });
    else if (match[2]) out.push({ kind: "strong", children: parseInline(token.slice(2, -2)) });
    else if (match[3]) {
      const split = token.indexOf("](");
      out.push({ kind: "link", href: token.slice(split + 2, -1), children: parseInline(token.slice(1, split)) });
    } else out.push({ kind: "em", children: parseInline(token.slice(1, -1)) });
    rest = rest.slice(match.index + token.length);
  }
  return out;
}

const cells = (line: string): string[] =>
  line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());

const isDivider = (line: string) => /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(line);

export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: "paragraph", text: parseInline(paragraph.join(" ")) });
    paragraph = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed) { flush(); continue; }
    if (trimmed.startsWith("```")) {
      flush();
      const body: string[] = [];
      for (i++; i < lines.length && !lines[i].trim().startsWith("```"); i++) body.push(lines[i]);
      blocks.push({ kind: "code", text: body.join("\n") });
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed);
    if (heading) { flush(); blocks.push({ kind: "heading", level: heading[1].length, text: parseInline(heading[2]) }); continue; }
    const image = /^!\[([^\]]*)\]\(([^)\s]+)\)$/.exec(trimmed);
    if (image) { flush(); blocks.push({ kind: "image", alt: image[1], src: image[2] }); continue; }
    if (trimmed.startsWith("|") && i + 1 < lines.length && isDivider(lines[i + 1])) {
      flush();
      const header = cells(trimmed);
      const align = cells(lines[i + 1]).map((c) => (c.startsWith(":") && c.endsWith(":") ? "center" : c.endsWith(":") ? "right" : "left") as "left" | "right" | "center");
      const rows: Inline[][][] = [];
      for (i += 2; i < lines.length && lines[i].trim().startsWith("|"); i++) rows.push(cells(lines[i]).map(parseInline));
      i--;
      blocks.push({ kind: "table", header: header.map(parseInline), align, rows });
      continue;
    }
    if (/^[-*]\s+/.test(trimmed)) {
      flush();
      const items: Inline[][] = [];
      for (; i < lines.length && /^\s*[-*]\s+/.test(lines[i]); i++) {
        let item = lines[i].trim().replace(/^[-*]\s+/, "");
        // A continuation line, indented under the bullet, belongs to it.
        while (i + 1 < lines.length && /^\s{2,}\S/.test(lines[i + 1]) && !/^\s*[-*]\s+/.test(lines[i + 1])) item += ` ${lines[++i].trim()}`;
        items.push(parseInline(item));
      }
      i--;
      blocks.push({ kind: "list", items });
      continue;
    }
    paragraph.push(trimmed);
  }
  flush();
  return blocks;
}

/** Only links that cannot run script: web addresses, in-page anchors and relative paths. */
export const safeHref = (href: string): string | null =>
  /^(https?:\/\/|#|\.{0,2}\/|[\w-]+(\/[\w.-]+)*(\.\w+)?(#.*)?$)/i.test(href) && !/^\s*(javascript|data|vbscript):/i.test(href) ? href : null;
