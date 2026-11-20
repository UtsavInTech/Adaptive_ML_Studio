"""Builds the project report as a Word file in the university's report format, and an HTML preview
that follows the same page rules (used only to check layout and to estimate page numbers).

    backend/.venv/bin/python docs/report/build/build.py [--pages pages.json]

The Word file reuses the style, numbering, footer and theme parts of the format file the university
report template came from, so fonts, heading sizes, page borders and page numbering match.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import zipfile
import zlib
from pathlib import Path

from PIL import Image

import content as C
from refs import REFS

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
TEMPLATE = HERE / "template"          # parts copied from the format file (styles, numbering, footers, theme)
OUT_DOCX = HERE.parent / "Adaptive_ML_Studio_Project_Report.docx"
OUT_HTML = HERE / "preview.html"

W_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
EMU = 914400


# ------------------------------------------------------------------ numbering of figures, tables, references
class Doc:
    def __init__(self):
        self.fig_no, self.tab_no, self.cites = {}, {}, {}
        self.figs, self.tabs = [], []          # (number, caption)
        self.chapters = []                     # (n, title, [h2 titles])
        self.pages = {}

    def number(self):
        f = t = 0
        for n, title, blocks in C.CHAPTERS:
            h2s = []
            for b in blocks:
                if b[0] == "h2":
                    h2s.append(b[1])
                elif b[0] == "fig":
                    f += 1
                    self.fig_no[b[1]] = f
                    self.figs.append((f, b[4]))
                elif b[0] == "table":
                    t += 1
                    self.tab_no[b[1]] = t
                    self.tabs.append((t, b[2]))
            self.chapters.append((n, title, h2s))
        # citations, in order of first appearance
        for text in self.all_text():
            for m in re.finditer(r"\[\[([a-z0-9, ]+)\]\]", text):
                for key in [k.strip() for k in m.group(1).split(",")]:
                    if key not in self.cites:
                        self.cites[key] = len(self.cites) + 1
        unknown = [k for k in self.cites if k not in REFS]
        assert not unknown, f"unknown reference keys: {unknown}"

    def all_text(self):
        for n, title, blocks in C.CHAPTERS:
            for b in blocks:
                if b[0] in ("p", "h2", "h3"):
                    yield b[1]
                elif b[0] == "pl":
                    yield b[1]; yield b[2]
                elif b[0] in ("bul", "num"):
                    for it in b[1]:
                        yield it if isinstance(it, str) else " ".join(it)
                elif b[0] == "table":
                    rows = resolve_rows(b[4])
                    yield b[2]
                    for r in rows:
                        for cell in r:
                            yield cell
                elif b[0] == "fig":
                    yield b[4]

    def text(self, s: str) -> str:
        def cite(m):
            return ", ".join(f"[{self.cites[k.strip()]}]" for k in m.group(1).split(","))
        s = re.sub(r"\[\[([a-z0-9, ]+)\]\]", cite, s)
        s = re.sub(r"<<tab:(\w+)>>", lambda m: f"Table {self.tab_no[m.group(1)]}", s)
        s = re.sub(r"<<fig:(\w+)>>", lambda m: f"Figure {self.fig_no[m.group(1)]}", s)
        return s


def resolve_rows(rows):
    if rows == "WEEK":
        return C.whole_week_rows()
    if rows == "VS":
        return C.rules_vs_effort_rows()
    return rows


# ------------------------------------------------------------------ inline markup -> runs
TOKEN = re.compile(r"(\*\*.+?\*\*|\*.+?\*|_\{[^}]*\})")


def parse_inline(s: str):
    """-> list of (text, bold, italic, sub)"""
    out = []
    for part in TOKEN.split(s):
        if not part:
            continue
        if part.startswith("**"):
            out.append((part[2:-2], True, False, False))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append((part[1:-1], False, True, False))
        elif part.startswith("_{"):
            out.append((part[2:-1], False, False, True))
        else:
            out.append((part, False, False, False))
    return out


# ------------------------------------------------------------------ DOCX xml helpers
def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def rpr(bold=False, italic=False, size=None, sub=False, font=None):
    x = ""
    if font:
        x += f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>'
    if bold:
        x += "<w:b/><w:bCs/>"
    if italic:
        x += "<w:i/><w:iCs/>"
    if size:
        x += f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    if sub:
        x += '<w:vertAlign w:val="subscript"/>'
    return f"<w:rPr>{x}</w:rPr>" if x else ""


def run(text, **kw):
    if text == "":
        return ""
    return f'<w:r>{rpr(**kw)}<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'


def runs(s, size=None, bold=False, italic=False):
    out = ""
    for text, b, i, sub in parse_inline(s):
        out += run(text, bold=bold or b, italic=italic or i, size=size, sub=sub)
    return out


def ppr(style=None, keep_next=False, page_before=False, num=None, tabs=None, before=None, after=None, line=None,
        line_rule="auto", left=None, right=None, first=None, hanging=None, jc=None, sect=None, rpr_x=""):
    x = ""
    if style:
        x += f'<w:pStyle w:val="{style}"/>'
    if keep_next:
        x += "<w:keepNext/>"
    if page_before:
        x += "<w:pageBreakBefore/>"
    if num:
        x += f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr>'
    if tabs:
        x += "<w:tabs>" + "".join(f'<w:tab w:val="{k}" w:pos="{p}"/>' for k, p in tabs) + "</w:tabs>"
    sp = ""
    if before is not None:
        sp += f' w:before="{before}"'
    if after is not None:
        sp += f' w:after="{after}"'
    if line is not None:
        sp += f' w:line="{line}" w:lineRule="{line_rule}"'
    if sp:
        x += f"<w:spacing{sp}/>"
    ind = ""
    for k, v in (("left", left), ("right", right), ("firstLine", first), ("hanging", hanging)):
        if v is not None:
            ind += f' w:{k}="{v}"'
    if ind:
        x += f"<w:ind{ind}/>"
    if jc:
        x += f'<w:jc w:val="{jc}"/>'
    if rpr_x:
        x += rpr_x
    if sect:
        x += sect
    return f"<w:pPr>{x}</w:pPr>" if x else ""


def para(inner="", **kw):
    return f"<w:p>{ppr(**kw)}{inner}</w:p>"


PAGE_BREAK = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


class Ids:
    bookmark = 100
    drawing = 1
    images: list[tuple[str, str]] = []   # (rId, filename)


def image_run(file: str, width_in: float):
    path = ASSETS / file
    with Image.open(path) as im:
        w, h = im.size
    cx = int(width_in * EMU)
    cy = int(cx * h / w)
    rid = f"rIdImg{len(Ids.images) + 1}"
    Ids.images.append((rid, file))
    did = Ids.drawing
    Ids.drawing += 1
    return (f'<w:r><w:rPr><w:noProof/></w:rPr><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:docPr id="{did}" name="Picture {did}" descr="{esc(file)}"/>'
            f'<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{did}" name="{esc(file)}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
            f'</wp:inline></w:drawing></w:r>'), (cx / EMU, cy / EMU)


def bookmarked(inner: str, name: str) -> str:
    Ids.bookmark += 1
    i = Ids.bookmark
    return f'<w:bookmarkStart w:id="{i}" w:name="{name}"/>{inner}<w:bookmarkEnd w:id="{i}"/>'


def pageref(name: str, cached: str, size=None, bold=False) -> str:
    rp = rpr(bold=bold, size=size)
    return (f'<w:r>{rp}<w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r>{rp}<w:instrText xml:space="preserve"> PAGEREF {name} \\h </w:instrText></w:r>'
            f'<w:r>{rp}<w:fldChar w:fldCharType="separate"/></w:r>'
            f'<w:r>{rp}<w:t>{esc(cached)}</w:t></w:r>'
            f'<w:r>{rp}<w:fldChar w:fldCharType="end"/></w:r>')


BORDERS_PG = ('<w:pgBorders w:offsetFrom="page">' + "".join(
    f'<w:{s} w:val="double" w:sz="4" w:space="24" w:color="auto"/>' for s in ("top", "left", "bottom", "right")) + "</w:pgBorders>")


def sectpr(footer_rid, fmt=None, start=None):
    pg = ""
    if fmt or start is not None:
        pg = "<w:pgNumType" + (f' w:fmt="{fmt}"' if fmt else "") + (f' w:start="{start}"' if start is not None else "") + "/>"
    return (f'<w:sectPr><w:footerReference w:type="default" r:id="{footer_rid}"/>'
            f'<w:pgSz w:w="11906" w:h="16838"/>'
            f'<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
            f'{BORDERS_PG}{pg}<w:cols w:space="720"/><w:docGrid w:linePitch="360"/></w:sectPr>')


# ---- tables
def tc(text_xml, width, borders="all", margins=(70, 110, 70, 110), valign="center", bold_first=False):
    b = ""
    if borders == "all":
        b = "<w:tcBorders>" + "".join(f'<w:{s} w:val="single" w:sz="6" w:space="0" w:color="000000"/>' for s in ("top", "left", "bottom", "right")) + "</w:tcBorders>"
    mar = (f'<w:tcMar><w:top w:w="{margins[0]}" w:type="dxa"/><w:left w:w="{margins[1]}" w:type="dxa"/>'
           f'<w:bottom w:w="{margins[2]}" w:type="dxa"/><w:right w:w="{margins[3]}" w:type="dxa"/></w:tcMar>')
    return (f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{b}{mar}<w:vAlign w:val="{valign}"/></w:tcPr>{text_xml}</w:tc>')


def table_xml(doc: Doc, header, rows, widths, size=22, align=None, first_bold=False, keep=False):
    total = sum(widths)
    x = (f'<w:tbl><w:tblPr><w:tblW w:w="{total}" w:type="dxa"/><w:jc w:val="center"/>'
         '<w:tblBorders>' + "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="auto"/>' for s in ("top", "left", "bottom", "right", "insideH", "insideV")) +
         '</w:tblBorders><w:tblLayout w:type="fixed"/><w:tblCellMar><w:left w:w="10" w:type="dxa"/><w:right w:w="10" w:type="dxa"/></w:tblCellMar>'
         '<w:tblLook w:val="0000" w:firstRow="0" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" w:noHBand="0" w:noVBand="0"/></w:tblPr>')
    x += "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>"
    align = align or "l" * len(widths)

    def jcv(ch):
        return {"l": None, "r": "right", "c": "center"}[ch]

    x += '<w:tr><w:trPr><w:cantSplit/><w:tblHeader/><w:jc w:val="center"/></w:trPr>'
    for h, w in zip(header, widths):
        x += tc(para(runs(doc.text(h), size=size, bold=True), keep_next=True, line=252, jc=jcv("l")), w)
    x += "</w:tr>"
    for ri, r in enumerate(rows):
        x += '<w:tr><w:trPr><w:cantSplit/><w:jc w:val="center"/></w:trPr>'
        for ci, (cell, w) in enumerate(zip(r, widths)):
            x += tc(para(runs(doc.text(cell), size=size, bold=(first_bold and ci == 0)), line=252, jc=jcv(align[ci]),
                         keep_next=(keep and ri < len(rows) - 1)), w)
        x += "</w:tr>"
    return x + "</w:tbl>"


def list_table(entries, widths=(1800, 6800), size=None):
    """The plain two-column list used for the lists of figures and tables (outer lines and one divider)."""
    total = sum(widths)
    x = (f'<w:tbl><w:tblPr><w:tblW w:w="{total}" w:type="dxa"/><w:jc w:val="center"/><w:tblLayout w:type="fixed"/>'
         '<w:tblCellMar><w:left w:w="10" w:type="dxa"/><w:right w:w="10" w:type="dxa"/></w:tblCellMar>'
         '<w:tblLook w:val="0000" w:firstRow="0" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" w:noHBand="0" w:noVBand="0"/></w:tblPr>')
    x += "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>"
    n = len(entries)
    line = lambda side, on: (f'<w:{side} w:val="single" w:sz="6" w:space="0" w:color="000000"/>' if on
                             else f'<w:{side} w:val="none" w:sz="0" w:space="0" w:color="FFFFFF"/>')
    for i, (a, b) in enumerate(entries):
        x += '<w:tr><w:trPr><w:cantSplit/><w:jc w:val="center"/></w:trPr>'
        for ci, (t, w) in enumerate(((a, widths[0]), (b, widths[1]))):
            bd = ("<w:tcBorders>" + line("top", i == 0) + line("left", ci == 0) + line("bottom", i == n - 1) + line("right", True) + "</w:tcBorders>")
            mar = '<w:tcMar><w:top w:w="50" w:type="dxa"/><w:left w:w="140" w:type="dxa"/><w:bottom w:w="50" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tcMar>'
            x += (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{bd}{mar}</w:tcPr>{para(run(t, size=size))}</w:tc>')
        x += "</w:tr>"
    return x + "</w:tbl>"


def abbreviations_table(entries):
    widths = (2400, 5600)
    x = (f'<w:tbl><w:tblPr><w:tblW w:w="{sum(widths)}" w:type="dxa"/><w:jc w:val="center"/>'
         '<w:tblBorders>' + "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="auto"/>' for s in ("top", "left", "bottom", "right", "insideH", "insideV")) +
         '</w:tblBorders><w:tblLayout w:type="fixed"/><w:tblCellMar><w:left w:w="10" w:type="dxa"/><w:right w:w="10" w:type="dxa"/></w:tblCellMar>'
         '<w:tblLook w:val="0000" w:firstRow="0" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" w:noHBand="0" w:noVBand="0"/></w:tblPr>')
    x += "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>"
    for a, b in entries:
        x += '<w:tr><w:trPr><w:jc w:val="center"/></w:trPr>'
        x += tc(para(run(a, bold=True), line=252), widths[0]) + tc(para(run(b), line=252), widths[1])
        x += "</w:tr>"
    return x + "</w:tbl>"


# ------------------------------------------------------------------ the body, as docx xml and as html
class Builder:
    def __init__(self, doc: Doc):
        self.doc = doc
        self.d: list[str] = []      # docx
        self.h: list[str] = []      # html
        self.bm: dict[str, str] = {}  # bookmark name -> label, in order
        self.toc_targets: list[tuple[str, str, int]] = []  # (bookmark, label, level)

    def add(self, dx, hx):
        self.d.append(dx)
        self.h.append(hx)

    # --- helpers to emit both
    def front_heading(self, text, first=False):
        self.add(para(run(text, bold=True, size=32), before=400, after=400 if text != "ACKNOWLEDGEMENT" else 300, line=288, jc="center"),
                 f'<h1 class="front">{html.escape(text)}</h1>')

    # --- chapter pieces
    def chapter_divider(self, n, title, first):
        """Chapter heading: 'CHAPTER n' and the title, starting a new page (no separate divider page)."""
        name = f"_TocCh{n}"
        self.toc_targets.append((name, f"CHAPTER {n}: {title}", 1))
        self.add(para(bookmarked(run(f"CHAPTER {n}"), name), style="Heading1", jc="center", page_before=not first),
                 f'<h1 class="chap" id="{name}">CHAPTER {n}</h1>')
        self.add(para(run(title, bold=True, size=32), after=360, jc="center"), f'<div class="chaptitle">{html.escape(title)}</div>')

    def block(self, b):
        doc = self.doc
        kind = b[0]
        if kind == "h2":
            name = f"_Toc{zlib.crc32(b[1].encode()) & 0xffffffff:08x}"
            self.toc_targets.append((name, b[1], 2))
            self.add(para(bookmarked(run(b[1]), name), style="Heading2", keep_next=True, before=280, after=160),
                     f'<h2 id="{name}">{html.escape(b[1])}</h2>')
        elif kind == "h3":
            self.add(para(run(b[1]), style="Heading3", keep_next=True, before=200, after=120), f"<h3>{html.escape(b[1])}</h3>")
        elif kind == "p":
            t = doc.text(b[1])
            self.add(para(runs(t), after=140, line=288, jc="both"), f"<p>{inline_html(t)}</p>")
        elif kind == "pl":
            lead, t = doc.text(b[1]), doc.text(b[2])
            self.add(para(run(lead + " ", bold=True) + runs(t), after=140, line=288, jc="both"),
                     f"<p><b>{html.escape(lead)}</b> {inline_html(t)}</p>")
        elif kind in ("bul", "num"):
            numid = 3 if kind == "bul" else 2
            d = h = ""
            tag = "ul" if kind == "bul" else "ol"
            for it in b[1]:
                if isinstance(it, str):
                    inner = runs(doc.text(it))
                    hh = inline_html(doc.text(it))
                else:
                    inner = run(doc.text(it[0]) + " ", bold=True) + runs(doc.text(it[1]))
                    hh = f"<b>{html.escape(doc.text(it[0]))}</b> {inline_html(doc.text(it[1]))}"
                d += para(inner, style="ListParagraph", num=numid, after=80, line=276, jc="both")
                h += f"<li>{hh}</li>"
            self.add(d, f'<{tag} class="lst">{h}</{tag}>')
        elif kind == "table":
            _, key, cap, header, rows, widths, opts = b
            rows = resolve_rows(rows)
            n = doc.tab_no[key]
            size = opts.get("size", 22)
            align = opts.get("align")
            caption = f"Table {n}: {doc.text(cap)}"
            self.add(para(run(caption, size=22), keep_next=True, before=120, after=100, jc="center"),
                     f'<div class="cap tcap">{html.escape(caption)}</div>')
            self.add(table_xml(doc, header, rows, widths, size=size, align=align, first_bold=opts.get("first_bold", False), keep=opts.get("keep", False)),
                     table_html(doc, header, rows, widths, size, align, opts.get("keep", False)))
            self.add(para("", after=0, line=240, rpr_x='<w:rPr><w:sz w:val="12"/><w:szCs w:val="12"/></w:rPr>'), '<div class="after-table"></div>')
        elif kind == "fig":
            _, key, file, width, cap = b
            n = doc.fig_no[key]
            run_xml, (w_in, h_in) = image_run(file, width)
            caption = f"Figure {n}: {doc.text(cap)}"
            self.add(para(run_xml, keep_next=True, before=120, after=40, jc="center"),
                     f'<figure><img src="assets/{file}" style="width:{w_in:.3f}in"><figcaption>{html.escape(caption)}</figcaption></figure>')
            # caption paragraph: html carries it inside <figure>, so only docx adds it here
            self.d.append(para(run(caption, size=22), before=40, after=200, jc="center"))
            self.h.append("")
        elif kind == "eq":
            _, text, num = b
            parts = parse_inline(text)
            inner = "".join(run(t, italic=True, sub=sub) for t, bd, it, sub in parts) + run(f"      ({num})", italic=True)
            self.add(para(inner, before=120, after=160, jc="center"),
                     f'<p class="eq"><i>{"".join(("<sub>" + html.escape(t) + "</sub>") if sub else html.escape(t) for t, bd, it, sub in parts)}&emsp;&emsp;({num})</i></p>')
        else:
            raise ValueError(kind)

    # --- front matter and the rest
    def build(self, pages: dict):
        doc, C_ = self.doc, C
        meta = C_.META
        students = meta["students"]
        # ===== cover (section 1) =====
        d = ""
        d += para(run(meta["title_main"], bold=True, size=48), after=120, line=288, jc="center")
        d += para(run(meta["title_sub"], bold=True, size=32), after=460, line=288, jc="center")
        d += para(run("A project report submitted", bold=True, italic=True, size=26), after=60, line=288, jc="center")
        d += para(run("in partial fulfilment of the requirements for the degree of Bachelor of Technology in Computer Science and Engineering",
                      bold=True, italic=True, size=26), after=420, line=288, left=400, right=400, jc="center")
        d += para(run("by", bold=True, size=26), after=240, line=288, jc="center")
        for i, (nm, rid) in enumerate(students):
            d += para(run(f"{nm} ({rid})", size=26), after=60 if i < len(students) - 1 else 360, line=288, jc="center")
        logo_run, _ = image_run("logo_sharda.png", 3.0)
        d += para(logo_run, after=360, line=288, jc="center")
        d += para(run("Supervised by:", bold=True, size=26), after=140, line=288, jc="center")
        d += para(run(f"{meta['guide']},", size=26), line=288, jc="center")
        d += para(run(meta["guide_title"], size=26), after=360, line=288, jc="center")
        d += para(run(meta["month"], size=26), after=360, line=288, jc="center")
        d += para(run("DEPARTMENT OF COMPUTER SCIENCE & ENGINEERING", size=26), after=100, line=288, jc="center")
        d += para(run("SHARDA SCHOOL OF ENGINEERING AND TECHNOLOGY", size=26), after=100, line=288, jc="center")
        d += para(run("SHARDA UNIVERSITY, GREATER NOIDA", size=26), line=288, jc="center", sect=sectpr("rIdFooter1", fmt="lowerRoman", start=1))
        cover_html = (f'<section class="cover"><h1 class="ctitle">{html.escape(meta["title_main"])}</h1>'
                      f'<div class="csub">{html.escape(meta["title_sub"])}</div>'
                      f'<div class="ci b">A project report submitted</div>'
                      f'<div class="ci b" style="margin:0 .28in 30pt">in partial fulfilment of the requirements for the degree of Bachelor of Technology in Computer Science and Engineering</div>'
                      f'<div class="cb">by</div>'
                      + "".join(f'<div class="cn">{html.escape(n)} ({r})</div>' for n, r in students)
                      + '<img class="logo" src="assets/logo_sharda.png">'
                      f'<div class="cb">Supervised by:</div><div class="cn">{html.escape(meta["guide"])},</div>'
                      f'<div class="cn" style="margin-bottom:20pt">{html.escape(meta["guide_title"])}</div>'
                      f'<div class="cn" style="margin-bottom:20pt">{meta["month"]}</div>'
                      '<div class="cn" style="margin-bottom:6pt">DEPARTMENT OF COMPUTER SCIENCE &amp; ENGINEERING</div>'
                      '<div class="cn" style="margin-bottom:6pt">SHARDA SCHOOL OF ENGINEERING AND TECHNOLOGY</div>'
                      '<div class="cn">SHARDA UNIVERSITY, GREATER NOIDA</div></section>')
        self.add(d, cover_html)
        self.h.append('<!--FRONT-->')

        # ===== front matter (section 2) =====
        title = f"{meta['full_title']}"
        names = ", ".join(f"{n} ({r})" for n, r in students[:-1]) + f" and {students[-1][0]} ({students[-1][1]})"
        self.front_heading("CERTIFICATE")
        self.add(para(runs(f"This is to certify that the report entitled “{title}” submitted by “{names}” to Sharda University, towards "
                           "the fulfilment of requirements of the degree of “Bachelor of Technology” is a record of bonafide final year Project "
                           "work carried out by them in the “Department of Computer Science & Engineering, Sharda School of Engineering and "
                           "Technology, Sharda University”. The results/findings contained in this Project have not been submitted in part or full "
                           "to any other University/Institute for any other Degree/Diploma."), after=700, line=360, jc="both"),
                 f'<p class="cert">This is to certify that the report entitled “{html.escape(title)}” submitted by “{html.escape(names)}” to Sharda University, towards the fulfilment of requirements of the degree of “Bachelor of Technology” is a record of bonafide final year Project work carried out by them in the “Department of Computer Science &amp; Engineering, Sharda School of Engineering and Technology, Sharda University”. The results/findings contained in this Project have not been submitted in part or full to any other University/Institute for any other Degree/Diploma.</p>')
        sig = [("Signature of the Guide", True, 40, 5760), (f"Name: {meta['guide']}", True, 40, None), (f"Designation: {meta['guide_title']}, CSE", True, 600, None)]
        d = ""
        h = '<div class="sig r">'
        d += para(run("Signature of the Guide", bold=True), after=40, line=288, left=5760, jc="right")
        d += para(run(f"Name: {meta['guide']}", bold=True), after=40, line=288, jc="right")
        d += para(run(f"Designation: {meta['guide_title']}, CSE", bold=True), after=600, line=288, left=5760, jc="right")
        h += f"<b>Signature of the Guide</b><br><b>Name: {html.escape(meta['guide'])}</b><br><b>Designation: {meta['guide_title']}, CSE</b></div>"
        for t, last in (("Signature of Head of Department", False),):
            d += para(run(t, bold=True), after=40, line=288, left=5040)
        d += para(run(f"Name: {meta['hod']}", bold=True), after=40, line=288, left=5040)
        d += para(run("Place: Sharda University", bold=True), after=40, line=288, left=5040)
        d += para(run("Date:", bold=True), after=600, line=288, left=5040)
        d += para(run("Signature of External Examiner", bold=True), after=40, line=288, left=5040)
        d += para(run("Date:", bold=True), line=288, left=5040)
        h += (f'<div class="sig"><b>Signature of Head of Department</b><br><b>Name: {html.escape(meta["hod"])}</b><br><b>Place: Sharda University</b><br><br><b>Date:</b></div>'
              '<div class="sig" style="margin-top:34pt"><b>Signature of External Examiner</b><br><br><b>Date:</b></div>')
        self.add(d, h)

        self.add(PAGE_BREAK, '<div class="pb"></div>')
        self.front_heading("ACKNOWLEDGEMENT")
        self.add(para(runs(C_.ACK), after=600, line=360, jc="both"), f'<p class="cert">{html.escape(C_.ACK)}</p>')
        d = para(run("Name and signature of Students:"), after=120, line=288)
        h = '<p class="nm">Name and signature of Students:</p>'
        for i, (n, r) in enumerate(students):
            d += para(run(f"{n} ({r})", bold=True), after=60 if i < len(students) - 1 else 0, line=288)
            h += f'<p class="nm b">{html.escape(n)} ({r})</p>'
        self.add(d, h)

        self.add(PAGE_BREAK, '<div class="pb"></div>')
        self.front_heading("ABSTRACT")
        for i, a in enumerate(C_.ABSTRACT):
            self.add(para(runs(a), after=140, line=360, first=500, jc="both"), f'<p class="abs">{html.escape(a)}</p>')

        # ----- contents
        self.add(PAGE_BREAK, '<div class="pb"></div>')
        d = para(run("CONTENTS", bold=True, size=30), before=200, after=120)
        h = '<h1 class="toc">CONTENTS</h1>'
        front = [("TITLE", "i"), ("CERTIFICATE", "ii"), ("ACKNOWLEDGEMENT", "iii"), ("ABSTRACT", "iv"), ("TABLE OF CONTENT", "v"),
                 ("LIST OF FIGURES", "vi"), ("LIST OF TABLES", "vii"), ("LIST OF ABBREVIATION", "viii")]
        for t, pn in front:
            d += para(run(t, bold=True, size=23) + '<w:r><w:rPr><w:b/><w:bCs/><w:sz w:val="23"/><w:szCs w:val="23"/></w:rPr><w:tab/></w:r>' + run(pn, bold=True, size=23),
                      tabs=[("right", 8900)], after=50, line=252, left=120)
            h += f'<div class="te l1"><span>{t}</span><span>{pn}</span></div>'
        self.toc_insert_at = len(self.d)
        self.d.append(d)
        self.h.append(h)
        self.toc_placeholder_index = len(self.d)
        self.d.append("@@TOC@@")
        self.h.append("@@TOCH@@")

        # ----- lists
        self.add(PAGE_BREAK, '<div class="pb"></div>')
        self.front_heading("LIST OF FIGURES")
        figs = [(f"Figure {n}:", doc.text(c)) for n, c in doc.figs]
        self.add(list_table(figs), '<table class="lt">' + "".join(f"<tr><td>{a}</td><td>{html.escape(b)}</td></tr>" for a, b in figs) + "</table>")
        self.add(PAGE_BREAK, '<div class="pb"></div>')
        self.front_heading("LIST OF TABLES")
        tabs = [(f"Table {n}:", doc.text(c)) for n, c in doc.tabs]
        self.add(list_table(tabs), '<table class="lt">' + "".join(f"<tr><td>{a}</td><td>{html.escape(b)}</td></tr>" for a, b in tabs) + "</table>")
        self.add(PAGE_BREAK, '<div class="pb"></div>')
        self.front_heading("LIST OF ABBREVIATION")
        self.add(abbreviations_table(C_.ABBREVIATIONS),
                 '<table class="ab">' + "".join(f"<tr><td><b>{html.escape(a)}</b></td><td>{html.escape(b)}</td></tr>" for a, b in C_.ABBREVIATIONS) + "</table>")
        # end of section 2
        self.add(para("", sect=sectpr("rIdFooter2", fmt="lowerRoman")), '<!--BODY-->')

        # ===== chapters (section 3) =====
        for idx, (n, title_, blocks) in enumerate(C_.CHAPTERS):
            self.chapter_divider(n, title_, first=(idx == 0))
            for b in blocks:
                self.block(b)

        # chapter 6: references
        self.chapter_divider(6, "REFERENCES", first=False)
        ordered = sorted(doc.cites.items(), key=lambda kv: kv[1])
        for key, num in ordered:
            t = f"[{num}] {REFS[key]}"
            self.add(para(run(t), after=160, line=264, jc="both"), f'<p class="ref">{html.escape(t)}</p>')

        # annexures
        self.annexures()

    def annexures(self):
        def head(text, name):
            self.toc_targets.append((name, text, 1))
            return bookmarked(run(text, bold=True, size=32), name)

        # Annexure I
        self.add(para(head("ANNEXURE-I", "_TocAnnex1"), style="Heading1", jc="center", page_before=True, after=240),
                 '<h1 class="annex" id="_TocAnnex1" style="break-before:page">ANNEXURE-I</h1>')
        self.add(para(run("Meeting details –"), style="Heading2", keep_next=True, before=280, after=160), "<h2>Meeting details –</h2>")
        for i in range(4):
            lbl = f"Eval {i}" + (": (to be pasted before eval 3)" if i == 3 else "")
            d = para(run("❖", font="Segoe UI Symbol") + run(lbl), style="Heading2", keep_next=True, before=280, after=160, left=360)
            note = ("Screenshot of the evaluation meeting with Dr. Neha Kumari, to be pasted here."
                    if i < 3 else "Screenshot of the evaluation meeting, to be pasted before Eval 3.")
            d += para(run(note, italic=True), after=240, left=360)
            self.add(d, f'<h2 class="ev">❖ {lbl}</h2><p class="evnote">{note}</p>')
        # Annexure II
        self.add(para(head("ANNEXURE-II", "_TocAnnex2"), style="Heading1", jc="center", page_before=True, after=200),
                 '<h1 class="annex" id="_TocAnnex2" style="break-before:page">ANNEXURE-II</h1>')
        sub = ("Paper 159, “Adaptive Machine Learning Pipelines for Evolving Data Streams”, was submitted to the 9th International "
               "Conference on Pattern Analysis, Understanding and Learning (PAUL 2026), track PAUL2026, by Utsav Kumar, Simran Shikha, "
               "Aastha Bansal and Neha Kumari.")
        self.add(para(run("Submission:", bold=True) + run(" " + sub), after=140, line=264, jc="both"),
                 f'<p class="a2"><b>Submission:</b> {html.escape(sub)}</p>')
        acc = ("The camera-ready summary (left) shows that the final files (paper, source, copyright form and registration proof) were "
               "uploaded on 19 October 2026 and that every agreement was accepted.")
        reg = ("The registration fee of ₹8,004.72 was paid to Poornima University on 19 October 2026 at 09:50 PM (right).")
        self.add(para(run("Acceptance and registration:", bold=True) + run(" " + acc + " " + reg), after=120, line=264, jc="both"),
                 f'<p class="a2"><b>Acceptance and registration:</b> {html.escape(acc + " " + reg)}</p>')
        img1, (w1, h1) = image_run("annex_camera_ready.jpg", 2.35)
        img2, (w2, h2) = image_run("annex_receipt.jpg", 2.35)
        cell = lambda im: (f'<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/><w:vAlign w:val="top"/></w:tcPr>{para(im, jc="center", after=0)}</w:tc>')
        tbl = ('<w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/><w:jc w:val="center"/><w:tblLayout w:type="fixed"/>'
               '<w:tblLook w:val="0000" w:firstRow="0" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" w:noHBand="0" w:noVBand="0"/></w:tblPr>'
               '<w:tblGrid><w:gridCol w:w="4500"/><w:gridCol w:w="4500"/></w:tblGrid><w:tr><w:trPr><w:cantSplit/></w:trPr>'
               + cell(img1) + cell(img2) + "</w:tr></w:tbl>")
        self.add(tbl, '<div class="pair"><img src="assets/annex_camera_ready.jpg"><img src="assets/annex_receipt.jpg"></div>')
        self.add(para("", after=0, line=240), "")
        self.add(para(run("Left: camera-ready summary, Paper 159. Right: registration fee payment receipt.", size=22), before=60, after=0, jc="center"),
                 '<div class="cap">Left: camera-ready summary, Paper 159. Right: registration fee payment receipt.</div>')


def inline_html(s: str) -> str:
    out = ""
    for text, b, i, sub in parse_inline(s):
        t = html.escape(text)
        if sub:
            t = f"<sub>{t}</sub>"
        if b:
            t = f"<b>{t}</b>"
        if i:
            t = f"<i>{t}</i>"
        out += t
    return out


def table_html(doc, header, rows, widths, size, align, keep=False):
    total = sum(widths)
    pt = size / 2
    align = align or "l" * len(widths)
    cols = "".join(f'<col style="width:{w / total * 100:.2f}%">' for w in widths)
    th = "".join(f"<th>{inline_html(doc.text(h))}</th>" for h in header)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(f'<td class="{"r" if a == "r" else ""}">{inline_html(doc.text(c))}</td>' for c, a in zip(r, align)) + "</tr>"
    return (f'<table class="dt{" keep" if keep else ""}" style="font-size:{pt}pt;line-height:{pt * 1.15 * 1.05:.2f}pt;width:{total / 20}pt"><colgroup>{cols}</colgroup>'
            f"<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>")


# ------------------------------------------------------------------ contents
def toc_xml(builder: Builder, pages: dict) -> tuple[str, str]:
    d = ""
    h = ""
    for name, label, level in builder.toc_targets:
        cached = str(pages.get(name, 0))
        if level == 1:
            d += para(bookmark_free_run(label, 23, True) + '<w:r><w:rPr><w:b/><w:bCs/><w:sz w:val="23"/><w:szCs w:val="23"/></w:rPr><w:tab/></w:r>' + pageref(name, cached, size=23, bold=True),
                      tabs=[("right", 8900)], after=50, line=252, left=120)
            h += f'<div class="te l1"><span>{html.escape(label)}</span><span>{cached}</span></div>'
        else:
            d += para(bookmark_free_run(label, 21, False) + '<w:r><w:rPr><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr><w:tab/></w:r>' + pageref(name, cached, size=21),
                      tabs=[("right", 8900)], after=20, line=252, left=360)
            h += f'<div class="te l2"><span>{html.escape(label)}</span><span>{cached}</span></div>'
    return d, h


def bookmark_free_run(text, size, bold):
    return run(text, bold=bold, size=size)


# ------------------------------------------------------------------ packaging
CSS = """
@page { size: A4; margin: 72pt 72pt 72pt 72pt; }
@page cover { margin: 72pt; }
@page front { margin: 72pt; @bottom-left { content: counter(page, lower-roman); font: 11pt "Times New Roman"; vertical-align: top; padding-top: 22pt; } }
@page body { margin: 72pt; @bottom-left { content: counter(page); font: 11pt "Times New Roman"; vertical-align: top; padding-top: 22pt; } }
.s-cover { page: cover; } .s-front { page: front; } .s-body { page: body; }
html { font-family: "Times New Roman", Times, serif; font-size: 12pt; }
body { margin: 0; }
.pgborder { position: fixed; top: -48pt; left: -48pt; right: -48pt; bottom: -48pt; border: 3pt double #000; pointer-events: none; }
p { margin: 0 0 7pt; line-height: 16.56pt; text-align: justify; orphans: 2; widows: 2; }
h1, h2, h3 { margin: 0; font-weight: bold; }
h1.front { font-size: 16pt; text-align: center; margin: 20pt 0 20pt; line-height: 19.8pt; break-after: avoid; }
h1.toc { font-size: 15pt; margin: 10pt 0 6pt; line-height: 17pt; }
h1.chap { font-size: 16pt; text-align: center; line-height: 18.4pt; break-before: page; }
.chaptitle { font-size: 16pt; font-weight: bold; text-align: center; margin-bottom: 18pt; line-height: 18.4pt; }
h1.annex { font-size: 16pt; text-align: center; margin-bottom: 12pt; line-height: 18.4pt; }
h2 { font-size: 14pt; line-height: 16.1pt; margin: 14pt 0 8pt; break-after: avoid; }
h3 { font-size: 12pt; line-height: 13.8pt; margin: 10pt 0 6pt; break-after: avoid; }
.divider { break-before: page; padding-top: 270pt; }
.divider.first { break-before: auto; }
.dtext { font-size: 14pt; font-weight: bold; text-align: center; line-height: 16.1pt; }
.cover { text-align: center; page: cover; }
.cover .ctitle { font-size: 24pt; margin: 0 0 6pt; line-height: 27.6pt; }
.cover .csub { font-size: 16pt; font-weight: bold; margin: 0 0 23pt; line-height: 18.4pt; }
.cover .b { font-weight: bold; font-style: italic; font-size: 13pt; line-height: 17.9pt; margin-bottom: 3pt; }
.cover .cb { font-weight: bold; font-size: 13pt; line-height: 17.9pt; margin-bottom: 7pt; }
.cover .cn { font-size: 13pt; line-height: 17.9pt; margin-bottom: 3pt; }
.cover .logo { width: 3.0in; margin: 14pt 0 16pt; }
.cert { line-height: 24.84pt; margin-bottom: 35pt; }
.abs { line-height: 24.84pt; text-indent: 25pt; margin-bottom: 7pt; }
.nm { margin: 0 0 3pt; line-height: 16.56pt; text-align: left; }
.nm.b { font-weight: bold; }
.sig { margin-left: 252pt; font-size: 12pt; line-height: 16.56pt; margin-bottom: 30pt; }
.sig.r { text-align: right; margin-left: 0; padding-right: 0; }
ul.lst, ol.lst { margin: 0 0 7pt 0; padding-left: 36pt; }
.lst li { line-height: 15.87pt; margin-bottom: 4pt; text-align: justify; }
.cap { text-align: center; font-size: 11pt; line-height: 12.65pt; }
.tcap { margin: 6pt 0 5pt; break-after: avoid; }
figure { margin: 6pt 0 10pt; text-align: center; break-inside: avoid; }
figure img { display: block; margin: 0 auto 3pt; }
figcaption { font-size: 11pt; line-height: 12.65pt; text-align: center; }
table { border-collapse: collapse; margin: 0 auto; }
table.dt { table-layout: fixed; break-inside: auto; }
table.dt.keep { break-inside: avoid; }
table.dt th, table.dt td { border: 0.75pt solid #000; padding: 3.5pt 5.5pt; text-align: left; vertical-align: middle; }
table.dt th { font-weight: bold; }
table.dt td.r { text-align: right; }
table.dt tr { break-inside: avoid; }
table.dt thead { display: table-header-group; }
.after-table { height: 6pt; }
table.lt { width: 430pt; border-left: 0.75pt solid #000; border-right: 0.75pt solid #000; border-top: 0.75pt solid #000; border-bottom: 0.75pt solid #000; }
table.lt td { padding: 2.5pt 4pt 2.5pt 7pt; line-height: 16.56pt; }
table.lt td:first-child { width: 90pt; }
table.ab { width: 400pt; }
table.ab td { border: 0.75pt solid #000; padding: 3.5pt 5.5pt; line-height: 13.9pt; vertical-align: middle; }
table.ab td:first-child { width: 120pt; }
.te { display: flex; justify-content: space-between; }
.te.l1 { font-weight: bold; font-size: 11.5pt; line-height: 14.5pt; margin: 0 0 2.5pt 6pt; }
.te.l2 { font-size: 10.5pt; line-height: 13.2pt; margin: 0 0 1pt 18pt; }
p.ref { line-height: 15.2pt; margin-bottom: 8pt; }
p.eq { text-align: center; margin: 6pt 0 8pt; }
h2.ev { margin-left: 18pt; }
.evnote { margin-left: 18pt; font-style: italic; }
p.a2 { line-height: 15.2pt; margin-bottom: 6pt; }
.pair { display: flex; justify-content: center; gap: 24pt; }
.pair img { width: 2.35in; }
.pb { break-after: page; height: 0; }
"""


def write_html(builder: Builder, toc_h: str):
    parts = []
    for p_ in builder.h:
        if p_ == "@@TOCH@@":
            p_ = toc_h
        parts.append(p_)
    body = "\n".join(parts)
    # split into cover / front / body sections for page naming
    front_i = body.index("<!--FRONT-->")
    body_i = body.index("<!--BODY-->")
    cover, front, main = body[:front_i], body[front_i:body_i], body[body_i:]
    head = f"<!doctype html><html><head><meta charset=\"utf-8\"><title>Report preview</title><style>{CSS}</style></head><body>"
    html_front = head + f'<div class="s-cover">{cover}</div><div class="s-front">{front}</div></body></html>'
    html_body = head + f'<div class="s-body">{main}</div></body></html>'
    OUT_HTML.with_name("preview_front.html").write_text(html_front, encoding="utf8")
    OUT_HTML.with_name("preview_body.html").write_text(html_body, encoding="utf8")
    return
    OUT_HTML.write_text(html_doc, encoding="utf8")


def write_docx(builder: Builder, toc_d: str):
    body = "".join(toc_d if x == "@@TOC@@" else x for x in builder.d)
    final = sectpr("rIdFooter3", start=1)
    doc_xml = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W_NS}><w:body>{body}{final}</w:body></w:document>'
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    base = [("rIdStyles", "styles", "styles.xml"), ("rIdSettings", "settings", "settings.xml"), ("rIdNumbering", "numbering", "numbering.xml"),
            ("rIdFontTable", "fontTable", "fontTable.xml"), ("rIdWebSettings", "webSettings", "webSettings.xml"),
            ("rIdTheme", "theme", "theme/theme1.xml"), ("rIdFootnotes", "footnotes", "footnotes.xml"), ("rIdEndnotes", "endnotes", "endnotes.xml"),
            ("rIdFooter1", "footer", "footer1.xml"), ("rIdFooter2", "footer", "footer2.xml"), ("rIdFooter3", "footer", "footer3.xml")]
    for rid, typ, target in base:
        rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{typ}" Target="{target}"/>')
    seen = {}
    for rid, f in Ids.images:
        seen.setdefault(f, f"media/{f}")
        rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{f}"/>')
    rels.append("</Relationships>")
    ctypes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="jpeg" ContentType="image/jpeg"/><Default Extension="jpg" ContentType="image/jpeg"/><Default Extension="png" ContentType="image/png"/>'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
              '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
              '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
              '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
              '<Override PartName="/word/webSettings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.webSettings+xml"/>'
              '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>'
              '<Override PartName="/word/endnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml"/>'
              + "".join(f'<Override PartName="/word/footer{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>' for i in (1, 2, 3)) +
              '<Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/>'
              '<Override PartName="/word/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
              '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
              '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                 '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>')
    meta = C.META
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{esc(meta["full_title"])}</dc:title><dc:creator>{esc(", ".join(n for n, _ in meta["students"]))}</dc:creator>'
            '<dcterms:created xsi:type="dcterms:W3CDTF">2026-11-20T00:00:00Z</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">2026-11-20T00:00:00Z</dcterms:modified></cp:coreProperties>')
    app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
           '<Application>Microsoft Office Word</Application><AppVersion>16.0000</AppVersion></Properties>')
    OUT_DOCX.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT_DOCX, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/document.xml", doc_xml)
        z.writestr("word/_rels/document.xml.rels", "".join(rels))
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
        for name in ("styles.xml", "settings.xml", "numbering.xml", "fontTable.xml", "webSettings.xml", "footnotes.xml", "endnotes.xml",
                     "footer1.xml", "footer2.xml", "footer3.xml"):
            z.write(TEMPLATE / name, f"word/{name}")
        z.write(TEMPLATE / "theme1.xml", "word/theme/theme1.xml")
        for f in seen:
            z.write(ASSETS / f, f"word/media/{f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=Path, default=None, help="JSON {bookmark: page} from the preview, used for the contents")
    args = ap.parse_args()
    pages = json.loads(args.pages.read_text()) if args.pages and args.pages.exists() else {}
    doc = Doc()
    doc.number()
    b = Builder(doc)
    b.build(pages)
    toc_d, toc_h = toc_xml(b, pages)
    write_html(b, toc_h)
    write_docx(b, toc_d)
    json.dump([[n, l, lv] for n, l, lv in b.toc_targets], open(HERE / "toc_targets.json", "w"), ensure_ascii=False)
    print("figures:", len(doc.figs), "tables:", len(doc.tabs), "references:", len(doc.cites))
    print("wrote", OUT_DOCX.relative_to(HERE.parents[2]), "and", OUT_HTML.name)


if __name__ == "__main__":
    main()
