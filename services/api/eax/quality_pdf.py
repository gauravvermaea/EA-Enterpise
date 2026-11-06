"""Data quality as PDF (build phase 12, D239): every metric of the Quality tab, the installation view and any drill-down
list, as a file to download, print or send. Made with ReportLab (BSD licence), no browser needed.

model_pdf: the score and its parts, the counts, completeness by type and by owner (bars), the failing rules, the trend
and the findings (the first 300, worst first), or only a drill-down's entities (type, owner, rule, kind, mine).
installation_pdf: every model with its latest score, completeness, stale and failing counts, and a month before.
"""

from __future__ import annotations

import contextvars
import io
from datetime import UTC, datetime

from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GOOD, FAIR, POOR, INK, TRACK = (colors.HexColor(x) for x in ("#2f9e44", "#e8a317", "#d9480f", "#343a40", "#e9ecef"))
_ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_ss["Heading1"], fontSize=17, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=_ss["Heading2"], fontSize=12.5, spaceBefore=10, spaceAfter=4)
P = ParagraphStyle("p", parent=_ss["BodyText"], fontSize=9, leading=12)
SMALL = ParagraphStyle("s", parent=P, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#555555"))
CELL = ParagraphStyle("c", parent=P, fontSize=7.5, leading=9)


DEFAULT_BANDS = {"green": 80, "amber": 60}
_BANDS: contextvars.ContextVar[dict | None] = contextvars.ContextVar("quality_bands", default=None)


class _Bands:
    """The colour thresholds in force for this export (D244): the model's, or the installation's for the estate."""

    @staticmethod
    def set(b: dict | None) -> None:
        _BANDS.set(dict(b) if b else None)

    @staticmethod
    def get() -> dict:
        return _BANDS.get() or DEFAULT_BANDS


BANDS = _Bands()


def _tone(v) -> colors.Color:
    """The colour of a percentage by the thresholds in force (D244: the model's, or the installation's for the estate)."""
    if v is None:
        return TRACK
    b = BANDS.get()
    return GOOD if float(v) >= b["green"] else FAIR if float(v) >= b["amber"] else POOR


def _parts_text(s: dict) -> str:
    p = s.get("parts") or {"completeness": 50, "rules": 30, "freshness": 20}
    b = s.get("bands") or BANDS.get()
    return (f"The score is {p['completeness']}% completeness, {p['rules']}% the entities failing no rule and "
            f"{p['freshness']}% the entities that are not stale; green from {b['green']}, amber from {b['amber']}, red below.")


def _pct(v) -> str:
    return "-" if v is None else f"{round(float(v))}%"


def _esc(t) -> str:
    return str(t if t is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _table(rows: list[list], widths: list[float], header: bool = True) -> Table:
    data = [[Paragraph(_esc(c), CELL) if not isinstance(c, (Drawing, Paragraph)) else c for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("FONTSIZE", (0, 0), (-1, -1), 7.5), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("LINEBELOW", (0, 0), (-1, -1), 0.25, TRACK), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f5")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(style))
    return t


def _bar(value, width: float = 60, height: float = 7, maximum: float = 100, count: bool = False) -> Drawing:
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=TRACK, strokeColor=None))
    v = max(0.0, min(float(value or 0), maximum))
    d.add(Rect(0, 0, max(1.0, width * v / (maximum or 1)), height, fillColor=colors.HexColor("#4c6ef5") if count else _tone(v),
               strokeColor=None))
    return d


def _score_box(score) -> Drawing:
    d = Drawing(70, 70)
    d.add(Rect(2, 2, 66, 66, rx=8, ry=8, fillColor=None, strokeColor=_tone(score), strokeWidth=4))
    d.add(String(35, 30, "-" if score is None else str(round(float(score))), fontSize=26, fontName="Helvetica-Bold",
                 textAnchor="middle", fillColor=INK))
    d.add(String(35, 13, "quality score", fontSize=7, textAnchor="middle", fillColor=colors.HexColor("#555555")))
    return d


def _trend(points: list[dict], width: float = 240 * mm, height: float = 40 * mm) -> Drawing | None:
    pts = [p for p in points if p.get("score") is not None]
    if len(pts) < 2:
        return None
    d = Drawing(width, height)
    vals = [float(p["score"]) for p in pts]
    lo, hi = max(0.0, min(vals) - 5), min(100.0, max(vals) + 5)
    x = lambda i: 30 + i * (width - 40) / (len(pts) - 1)   # noqa: E731
    y = lambda v: 14 + (v - lo) * (height - 24) / ((hi - lo) or 1)   # noqa: E731
    for v in (lo, (lo + hi) / 2, hi):
        d.add(Line(28, y(v), width, y(v), strokeColor=TRACK, strokeWidth=0.5))
        d.add(String(0, y(v) - 3, str(round(v)), fontSize=6.5, fillColor=colors.grey))
    d.add(PolyLine([c for i, v in enumerate(vals) for c in (x(i), y(v))], strokeColor=colors.HexColor("#4c6ef5"), strokeWidth=1.5))
    d.add(String(30, 2, str(pts[0]["at"])[:10], fontSize=6.5, fillColor=colors.grey))
    d.add(String(width, 2, str(pts[-1]["at"])[:10], fontSize=6.5, fillColor=colors.grey, textAnchor="end"))
    return d


def _doc(title: str) -> tuple[io.BytesIO, SimpleDocTemplate]:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm,
                            bottomMargin=12 * mm, title=title, author="EA Explorer")
    return buf, doc


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawString(14 * mm, 7 * mm, f"EA Explorer data quality · {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    canvas.drawRightString(landscape(A4)[0] - 14 * mm, 7 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _drilled(d: dict, drill: str, value: str, username: str) -> tuple[str, list[dict]]:
    by = {}
    for f in d["findings"]:
        by.setdefault(f["entity"], []).append(f)
    ents = d["entities"]
    if drill == "type":
        return f"Entity type: {value}", [e for e in ents if e["type_name"] == value]
    if drill == "owner":
        return f"Owner: {value}", [e for e in ents if (e["owner"] or "(no owner)") == value]
    if drill == "rule":
        return f"Failing rule {value}", [e for e in ents if any(f["kind"] == "rule" and f.get("rule") == value for f in by.get(e["entity"], []))]
    if drill == "mine":
        return "Yours to fix", [e for e in ents if username in e["responsible"] and (e["completeness"] < 100 or e["failing"] or e["stale"])]
    if drill == "kind":
        test = {"incomplete": lambda e: e["completeness"] < 100, "failing": lambda e: e["failing"] > 0,
                "errors": lambda e: e["errors"] > 0, "stale": lambda e: e["stale"], "orphan": lambda e: e["orphan"],
                "seal-broken": lambda e: e["seal"] in ("broken", "expired"), "sealed": lambda e: e["seal"] == "valid"}
        return value.replace("-", " ").capitalize(), [e for e in ents if test.get(value, lambda e: True)(e)]
    return "Every entity", list(ents)


def model_pdf(d: dict, drill: str = "", value: str = "", username: str = "") -> bytes:
    """d: eax.quality.dashboard() of a model."""
    s, name = d["summary"], d["model"]["name"]
    BANDS.set(d.get("bands") or s.get("bands") or {"green": 80, "amber": 60})
    buf, doc = _doc(f"Data quality of {name}")
    story = [Paragraph(f"Data quality of {_esc(name)}", H1),
             Paragraph(f"Measured {str(d.get('measured_at', ''))[:16].replace('T', ' ')} UTC · {s['entities']} entities · "
                       f"stale after {s['stale_days']} days · {s['rules']} quality rule{'s' if s['rules'] != 1 else ''}. "
                       + _parts_text(s), SMALL), Spacer(1, 6)]
    if drill:
        title, rows = _drilled(d, drill, value, (username or "").lower())
        by = {}
        for f in d["findings"]:
            by.setdefault(f["entity"], []).append(f)
        story.append(Paragraph(f"{_esc(title)} ({len(rows)} entities)", H2))
        body = [["Entity", "ID", "Type", "Owner", "Responsible", "Complete", "", "Problems", "Seal"]]
        for e in sorted(rows, key=lambda e: (e["completeness"], -e["failing"]))[:2000]:
            probs = "; ".join(f["message"] for f in by.get(e["entity"], [])[:6])
            body.append([e["name"], e["display_id"], e["type_name"], e["owner"], ", ".join(e["responsible"]), _pct(e["completeness"]),
                         _bar(e["completeness"], 40), probs, "" if e["seal"] == "none" else e["seal"]])
        story.append(_table(body, [40 * mm, 18 * mm, 28 * mm, 28 * mm, 30 * mm, 14 * mm, 14 * mm, 84 * mm, 13 * mm]))
        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
        return buf.getvalue()
    tiles = [["Score", "Completeness", "Rules passed", "Fresh", "Incomplete", "Failing (errors)", "Stale", "Orphans",
              "Seals valid / broken / expired"],
             [str(round(float(s["score"]))), _pct(s["completeness"]), _pct(s["passing"]), _pct(s["fresh"]), str(s["incomplete"]),
              f"{s['failing']} ({s['errors']})", str(s["stale"]), str(s["orphans"]),
              f"{s['seals']['valid']} / {s['seals']['broken']} / {s['seals']['expired']}"]]
    head = Table([[_score_box(s["score"]), _table(tiles, [22 * mm] * 8 + [36 * mm])]], colWidths=[26 * mm, 216 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(head)
    trend = _trend(d.get("trend") or [])
    if trend:
        story += [Paragraph("Score over time", H2), trend]

    def groups(title, rows):
        out = [Paragraph(title, H2)]
        body = [["Name", "Entities", "Completeness", "", "Incomplete", "Failing", "Errors", "Stale", "Orphans"]]
        for r in rows:
            body.append([r["name"], r["entities"], _pct(r["completeness"]), _bar(r["completeness"], 70), r["incomplete"],
                         r["failing"], r["errors"], r["stale"], r["orphans"]])
        out.append(_table(body, [60 * mm, 18 * mm, 22 * mm, 28 * mm, 20 * mm, 18 * mm, 16 * mm, 16 * mm, 18 * mm]))
        return out
    story += groups("Completeness by entity type (weakest first)", d["by_type"])
    story += groups("Completeness by owner (weakest first)", d["by_owner"])
    rules = s.get("by_rule") or []
    story.append(Paragraph("Failing rules", H2))
    if rules:
        top = max(r["entities"] for r in rules)
        story.append(_table([["Rule", "Name", "Severity", "Entities", ""]] +
                            [[r["rule"], r["name"], r["severity"], r["entities"], _bar(r["entities"], 90, maximum=top, count=True)]
                             for r in rules], [24 * mm, 110 * mm, 22 * mm, 20 * mm, 40 * mm]))
    else:
        story.append(Paragraph("No entity fails a rule.", P))
    order = {"rule": 0, "seal-broken": 1, "stale": 2, "incomplete": 3, "seal-expired": 4, "orphan": 5}
    fs = sorted(d["findings"], key=lambda f: (order.get(f["kind"], 9), f.get("severity") != "error", f["name"]))
    story.append(Paragraph(f"What to fix ({len(fs)} findings{'; the first 300' if len(fs) > 300 else ''})", H2))
    story.append(_table([["Entity", "ID", "Type", "Kind", "What", "Responsible"]] +
                        [[f["name"], f["display_id"], f["type_name"], f["kind"] + (f" {f['rule']}" if f.get("rule") else ""),
                          f["message"], ", ".join(f["responsible"])] for f in fs[:300]],
                        [48 * mm, 20 * mm, 34 * mm, 26 * mm, 84 * mm, 30 * mm]))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def installation_pdf(data: dict) -> bytes:
    """data: eax.quality.installation(): the estate and every model."""
    models, e = data["models"], data.get("estate") or {}
    BANDS.set(data.get("bands") or {"green": 80, "amber": 60})        # the estate: the installation's colours (D244)
    buf, doc = _doc("Data quality of the estate")
    story = [Paragraph("Data quality of the estate", H1),
             Paragraph(f"The overall quality: each model's latest measurement, weighing as many entities as it has. {e.get('measured', 0)} "
                       f"of {e.get('models', 0)} models measured, {e.get('entities', 0)} entities.", SMALL), Spacer(1, 6)]
    tiles = [["Estate score", "A month before", "Completeness", "Incomplete", "Failing (errors)", "Stale", "Orphans"],
             ["-" if e.get("score") is None else str(round(float(e["score"]))),
              "-" if e.get("month_ago") is None else str(round(float(e["month_ago"]))), _pct(e.get("completeness")),
              str(e.get("incomplete", 0)), f"{e.get('failing', 0)} ({e.get('errors', 0)})", str(e.get("stale", 0)), str(e.get("orphans", 0))]]
    head = Table([[_score_box(e.get("score")), _table(tiles, [30 * mm] * 7)]], colWidths=[26 * mm, 216 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(head)
    trend = _trend(e.get("trend") or [])
    if trend:
        story += [Paragraph("The estate over time (weekly)", H2), trend]
    story.append(Paragraph("Every model (weakest first)", H2))
    body = [["Model", "Entities", "Score", "", "A month before", "Completeness", "Stale", "Failing", "Measured"]]
    for m in models:
        sm = m.get("summary") or {}
        body.append([m["name"], m["entities"], "-" if m["score"] is None else round(float(m["score"])),
                     _bar(m["score"], 70) if m["score"] is not None else "", "-" if m["month_ago"] is None else round(float(m["month_ago"])),
                     _pct(m["completeness"]), sm.get("stale", "-"), sm.get("failing", "-"),
                     str(m["measured_at"] or "not yet")[:16].replace("T", " ")])
    story.append(_table(body, [70 * mm, 18 * mm, 14 * mm, 28 * mm, 24 * mm, 22 * mm, 14 * mm, 16 * mm, 32 * mm]))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
