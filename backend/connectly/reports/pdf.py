"""PDF rendering of saved reports (ReportLab; the logo is drawn from the official SVG)."""

from __future__ import annotations

import io
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from svglib.svglib import svg2rlg

MAROON = colors.HexColor("#6B1420")
GOLD = colors.HexColor("#D9A441")
GOLD_INK = colors.HexColor("#7F5A12")
INK = colors.HexColor("#1F1517")
MUTED = colors.HexColor("#6A5D5F")
LINE = colors.HexColor("#E9E1DB")
PAPER = colors.HexColor("#FAF7F3")
LOGO = Path(__file__).parent / "assets" / "connectly-logo-horizontal.svg"

KIND_LABEL = {
    "fact": "Fact",
    "derived": "Derived",
    "recommendation": "Recommendation",
    "gap": "Data gap",
}
KIND_COLOUR = {
    "fact": "#1D6B45",
    "derived": "#7F5A12",
    "recommendation": "#6B1420",
    "gap": "#6A5D5F",
}

S = {
    "title": ParagraphStyle(
        "title", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK, spaceAfter=4
    ),
    "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=10, leading=14, textColor=MUTED),
    "h2": ParagraphStyle(
        "h2",
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=MAROON,
        spaceBefore=12,
        spaceAfter=5,
    ),
    "h3": ParagraphStyle(
        "h3",
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=14,
        textColor=INK,
        spaceBefore=6,
        spaceAfter=2,
    ),
    "body": ParagraphStyle(
        "body", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK, alignment=TA_LEFT
    ),
    "small": ParagraphStyle(
        "small", fontName="Helvetica", fontSize=8, leading=10.5, textColor=MUTED
    ),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK),
    "cellb": ParagraphStyle(
        "cellb", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=INK
    ),
}


@lru_cache
def _logo():
    return svg2rlg(str(LOGO))


def p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(escape(str(text)), S[style])


def item(
    kind: str, text: str, cites: list[str] | None = None, evidence: list[str] | None = None
) -> Paragraph:
    tag = f'<font color="{KIND_COLOUR.get(kind, "#6A5D5F")}"><b>{KIND_LABEL.get(kind, kind)}</b></font>'
    extra = ""
    if cites:
        extra += f' <font color="#6B1420" size="7.5">[{", ".join(cites)}]</font>'
    if evidence:
        extra += f'<br/><font color="#6A5D5F" size="7.5">{escape(" · ".join(evidence))}</font>'
    return Paragraph(f"{tag}&nbsp;&nbsp;{escape(text)}{extra}", S["body"])


def table(rows: list[list], widths: list[float], header: bool = True) -> Table:
    data = [
        [
            c
            if not isinstance(c, str)
            else Paragraph(escape(c), S["cellb" if header and i == 0 else "cell"])
            for c in r
        ]
        for i, r in enumerate(rows)
    ]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), PAPER), ("LINEBELOW", (0, 0), (-1, 0), 0.8, GOLD)]
    t.setStyle(TableStyle(style))
    return t


def _decorate(title: str, generated: str):
    def draw(canvas, doc):
        canvas.saveState()
        w, h = A4
        logo = _logo()
        scale = (7 * mm) / logo.height
        canvas.translate(18 * mm, h - 15 * mm)
        canvas.scale(scale, scale)
        renderPDF.draw(logo, canvas, 0, 0)
        canvas.restoreState()
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MAROON)
        canvas.drawRightString(w - 18 * mm, h - 12.5 * mm, "Intelligence report")
        canvas.setStrokeColor(GOLD)
        canvas.setLineWidth(0.8)
        canvas.line(18 * mm, h - 18 * mm, w - 18 * mm, h - 18 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(
            18 * mm, 10 * mm, f"Connectly Intelligence · {title[:90]} · generated {generated}"
        )
        canvas.drawRightString(w - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw


NOTE = (
    "Every value in this report is read from the Connectly Intelligence database with its source, "
    "value type and verification status. Missing data is reported as a gap and never estimated. "
    "Scores are relative to the comparison group shown and change as data is added."
)


def render(report: dict) -> bytes:
    created = report["created_at"]
    generated = (
        created.strftime("%d %b %Y %H:%M UTC") if isinstance(created, datetime) else str(created)
    )
    body = [
        Spacer(1, 4 * mm),
        p(report["title"], "title"),
        p(
            f"{KIND_TITLE[report['kind']]} · saved {generated}"
            + (f" by {report['created_by']}" if report.get("created_by") else ""),
            "sub",
        ),
        Spacer(1, 3 * mm),
        p(NOTE, "small"),
        Spacer(1, 2 * mm),
    ]
    body += RENDERERS[report["kind"]](report["result"])
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=24 * mm,
        bottomMargin=18 * mm,
        title=report["title"],
        author="Connectly Intelligence",
        subject=KIND_TITLE[report["kind"]],
        creator="Connectly Intelligence",
    )
    deco = _decorate(report["title"], generated)
    doc.build(body, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()


# ------------------------------------------------------------------ per report kind

WIDTH = A4[0] - 36 * mm
SECTION_TITLES = {
    "profile": "Community profile",
    "infrastructure": "Available infrastructure",
    "gaps": "Identified service gaps",
    "beneficiaries": "Potential beneficiary groups",
    "barriers": "Technology adoption barriers",
    "solutions": "Relevant available solutions",
    "opportunities": "Implementation opportunities",
    "limitations": "Data limitations",
    "confidence": "Confidence",
    "sources": "Supporting sources",
    "related": "Related to the question",
}


def _brief(r: dict) -> list:
    out = [p(f"{r['sector_name']}: {r['area']['place']}", "h2")]
    if r.get("question"):
        out.append(p(f"Question: {r['question']}", "sub"))
    n = r.get("narrative") or {}
    if n.get("status") == "accepted":
        out += [
            p(
                "Summary (AI-generated, checked against the cited evidence; model: "
                + str(n.get("model"))
                + ")",
                "h3",
            ),
            p(n["text"]),
        ]
    for s in r["sections"]:
        out.append(p(SECTION_TITLES.get(s["key"], s["key"]), "h3"))
        out += [item(st["kind"], st["text"], st["cites"]) for st in s["statements"]]
    out.append(p("Evidence", "h2"))
    rows = [["Id", "Evidence", "Type", "Source"]] + [
        [
            e["id"],
            e["text"],
            " / ".join(x for x in (e.get("value_type"), e.get("verification")) if x) or "—",
            e["source"],
        ]
        for e in r["evidence"]
    ]
    out.append(table(rows, [12 * mm, WIDTH * 0.52, 26 * mm, WIDTH * 0.48 - 38 * mm]))
    return out


def _needs(r: dict) -> list:
    lvl = {"state": "States", "lga": "LGAs", "ward": "Wards"}[r["level"]]
    out = [p(f"{r['sector_name']}: {lvl} in {r['scope']['name']}", "h2")]
    if r.get("message"):
        out.append(item("gap", r["message"]))
    if r["status"] != "no_model":
        out.append(
            p(
                f"{r.get('areas_scored', 0)} of {r.get('areas_in_scope', 0)} areas have enough data for a score.",
                "body",
            )
        )
        out.append(p("Evidence used", "h3"))
        out.append(
            table(
                [["Indicator", "Weight", "Areas with value", "Status"]]
                + [
                    [
                        i["name"],
                        f"{round(i['weight'] * 100)}%",
                        str(i["areas_with_value"]),
                        "used" if i["used"] else (i["reason"] or "not used"),
                    ]
                    for i in r["indicators"]
                ],
                [WIDTH * 0.4, 16 * mm, 24 * mm, WIDTH * 0.6 - 40 * mm],
            )
        )
    scored = [a for a in r["areas"] if a["score"] is not None]
    if scored:
        out.append(p("Ranking", "h3"))
        out.append(
            table(
                [["#", "Area", "Gap score", "Confidence", "Population (modelled)"]]
                + [
                    [
                        str(a["rank"]),
                        a["name"],
                        f"{a['score']:.0f}",
                        a["confidence_label"],
                        f"{a['population']:,.0f}" if a["population"] else "—",
                    ]
                    for a in scored
                ],
                [10 * mm, WIDTH * 0.4, 22 * mm, 26 * mm, WIDTH * 0.6 - 58 * mm],
            )
        )
        out.append(p("Evidence for the ten least-served areas", "h3"))
        for a in scored[:10]:
            out.append(
                KeepTogether(
                    [p(f"{a['rank']}. {a['name']}", "cellb")]
                    + [item("derived", c["statement"]) for c in a["components"]]
                )
            )
    return out


def _matching(r: dict) -> list:
    out = [
        p(f"{r['sector_name']} in {r['area']['name']}", "h2"),
        p(
            "Needs matched on: "
            + (", ".join(n["name"] for n in r["target_needs"]) or "none")
            + {
                "selected": " (chosen by the user)",
                "gap_evidence": " (from the area's gap evidence)",
            }.get(r["needs_basis"], ""),
            "body",
        ),
    ]
    out += [item("derived", g) for g in r.get("gap_evidence", [])]
    if r.get("message"):
        out.append(item("gap", r["message"]))
    for m in r["results"]:
        s = m["solution"]
        block = [
            p(
                f"{m['rank']}. {s['name']} ({s['organisation_name']}): score {m['score']:.0f}, {m['confidence_label']} confidence, "
                f"{m['criteria_known']} of 8 criteria judged",
                "h3",
            ),
            p(s["summary"], "small"),
        ]
        block.append(
            table(
                [["Criterion", "Score", "Reason"]]
                + [
                    [
                        c["label"],
                        "unknown" if c["score"] is None else f"{round(c['score'] * 100)}",
                        c["reason"],
                    ]
                    for c in m["criteria"]
                ],
                [WIDTH * 0.3, 16 * mm, WIDTH * 0.7 - 16 * mm],
            )
        )
        out.append(KeepTogether(block))
    if r.get("excluded"):
        out.append(p("Not recommended", "h3"))
        out += [
            p(f"{e['name']} ({e['organisation_name']}): {e['reason']}", "small")
            for e in r["excluded"]
        ]
    return out


def _market(r: dict) -> list:
    out = [
        p(f"{r['objective']}: {r['product']['name']} ({r['sector_name']})", "h2"),
        p(
            "Requirements from "
            + r["product"]["source"]
            + ". Opportunity = gap 40%, local fit 25%, reach 20%, fewer competitors 15%, "
            "over the parts with data; areas without evidence of need are not scored.",
            "small",
        ),
    ]
    out.append(
        table(
            [["#", "Area", "Opportunity", "Gap", "Fit", "Reach", "Competitors"]]
            + [
                [str(c["rank"]), c["name"], "—" if c["score"] is None else f"{c['score']:.0f}"]
                + [
                    "—" if c["components"][k] is None else f"{round(c['components'][k] * 100)}"
                    for k in ("gap", "fit", "reach")
                ]
                + [str(len(c["competitors"]))]
                for c in r["candidates"][:15]
            ],
            [10 * mm, WIDTH * 0.34, 22 * mm, 16 * mm, 16 * mm, 16 * mm, WIDTH * 0.66 - 90 * mm],
        )
    )
    for s in r["sections"]:
        out.append(p(s["title"], "h3"))
        out += [item(i["kind"], i["text"], evidence=i["evidence"]) for i in s["items"]]
    return out


RENDERERS = {"brief": _brief, "needs": _needs, "matching": _matching, "market_entry": _market}
KIND_TITLE = {
    "brief": "Intelligence brief",
    "needs": "Needs assessment",
    "matching": "Technology matching",
    "market_entry": "Market entry analysis",
}
