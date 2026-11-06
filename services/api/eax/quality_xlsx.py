"""Data quality as an Excel workbook (build phase 12, D239): every metric, with the drill-downs as Excel groups.

model_xlsx sheets:
  Summary      the score, its parts and the counts
  By type      completeness and problems per entity type; each type opens (Excel's + on the left) to its entities, and each
               entity to its findings: the drill-down, grouped (outline levels 1 and 2)
  By owner     the same, grouped by the Owner attribute
  Rules        the failing rules; each opens to the entities failing it
  Findings     every finding in one flat table with filters (type, owner, kind, rule, severity, responsible)
  Entities     every entity with its completeness, problems, seal and who is responsible, with filters
  Trend        the kept measurements
A drill-down (drill, value) keeps only that drill-down's entities everywhere. Names link back to EA Explorer.
estate_xlsx: the estate's score and weekly trend, and every model (each opens to its types when it was measured).
"""

from __future__ import annotations

import io
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

HEAD = PatternFill("solid", fgColor="E9ECEF")
GROUP = PatternFill("solid", fgColor="F3F6FA")
BOLD = Font(bold=True)
LINK = Font(color="1D5FD1", underline="single")
TONE = {"good": PatternFill("solid", fgColor="D3F9D8"), "fair": PatternFill("solid", fgColor="FFF3BF"),
        "poor": PatternFill("solid", fgColor="FFE3E3")}


def _tone(v) -> PatternFill:
    """The fill of a percentage by the thresholds in force (D244)."""
    from .quality_pdf import BANDS
    if v is None:
        return PatternFill()
    b = BANDS.get()
    return TONE["good" if float(v) >= b["green"] else "fair" if float(v) >= b["amber"] else "poor"]


def _sheet(wb: Workbook, title: str, header: list[str], widths: list[int]) -> Worksheet:
    ws = wb.create_sheet(title)
    ws.append(header)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
        ws.cell(1, i).font, ws.cell(1, i).fill = BOLD, HEAD
    ws.freeze_panes = "A2"
    ws.sheet_properties.outlinePr.summaryBelow = False      # the + sits on the group's own row
    return ws


def _link(cell, url: str) -> None:
    if url:
        cell.hyperlink, cell.font = url, LINK


def _row(ws: Worksheet, values: list, level: int = 0, hidden: bool = False, fill: PatternFill | None = None, bold=False) -> int:
    ws.append(values)
    r = ws.max_row
    if level:
        ws.row_dimensions[r].outlineLevel = level
        ws.row_dimensions[r].hidden = hidden
    if fill or bold:
        for c in ws[r]:
            if fill:
                c.fill = fill
            if bold:
                c.font = BOLD
    return r


def _pct(v):
    return None if v is None else round(float(v), 1) / 100


def _pctfmt(ws: Worksheet, col: int) -> None:
    for (c,) in ws.iter_rows(min_row=2, min_col=col, max_col=col):
        c.number_format = "0%"


def model_xlsx(d: dict, base: str, drill: str = "", value: str = "", username: str = "") -> bytes:
    """d: eax.quality.dashboard() of a model; base: EA Explorer's address for the links (https://host/)."""
    from .quality_pdf import BANDS, _drilled
    BANDS.set(d.get("bands") or d["summary"].get("bands") or {"green": 80, "amber": 60})
    mid = d["model"]["id"]
    ent_url = lambda g: f"{base.rstrip('/')}/#/metamodel/{mid}/entity/{g}"   # noqa: E731
    title, ents = _drilled(d, drill, value, (username or "").lower()) if drill else ("Every entity", d["entities"])
    keep = {e["entity"] for e in ents}
    finds = [f for f in d["findings"] if f["entity"] in keep]
    by_ent = defaultdict(list)
    for f in finds:
        by_ent[f["entity"]].append(f)
    s = d["summary"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 34, 60
    rows = [("Model", d["model"]["name"]), ("Showing", title if drill else "The whole model"),
            ("Measured (UTC)", str(d.get("measured_at", ""))[:16].replace("T", " ")), ("Quality score", s["score"]),
            ("Completeness", _pct(s["completeness"])), ("Entities failing no rule", _pct(s["passing"])),
            ("Entities not stale", _pct(s["fresh"])), ("Entities", s["entities"]), ("Incomplete", s["incomplete"]),
            ("Failing a rule", s["failing"]), ("Failing an error rule", s["errors"]), ("Stale", s["stale"]),
            ("Stale after (days)", s["stale_days"]), ("Orphans", s["orphans"]), ("Seals valid", s["seals"]["valid"]),
            ("Seals broken", s["seals"]["broken"]), ("Seals expired", s["seals"]["expired"]), ("Quality rules", s["rules"]),
            ("How the score is made", "Half completeness, almost a third the entities failing no rule, a fifth the entities "
                                      "that are not stale"),
            ("How to drill down", "On By type, By owner and Rules, the + on the left opens a row to its entities, and each "
                                  "entity to its findings; Data > Ungroup removes the groups")]
    for k, v in rows:
        ws.append([k, v])
        ws.cell(ws.max_row, 1).font = BOLD
        if isinstance(v, float) and v <= 1 and k not in ("Quality score",):
            ws.cell(ws.max_row, 2).number_format = "0%"
    ws.cell(4, 2).fill = _tone(s["score"])

    def grouped(name: str, key):
        sh = _sheet(wb, name, [name.replace("By ", "").capitalize(), "Entities", "Completeness", "Incomplete", "Failing",
                               "Errors", "Stale", "Orphans", "Entity", "ID", "Responsible", "Finding"],
                    [34, 10, 13, 11, 9, 8, 8, 9, 34, 12, 22, 70])
        groups = defaultdict(list)
        for e in ents:
            groups[key(e)].append(e)
        order = sorted(groups.items(), key=lambda kv: sum(e["completeness"] for e in kv[1]) / len(kv[1]))
        for g, es in order:
            comp = sum(e["completeness"] for e in es) / len(es)
            r = _row(sh, [g, len(es), _pct(comp), sum(1 for e in es if e["completeness"] < 100), sum(1 for e in es if e["failing"]),
                          sum(1 for e in es if e["errors"]), sum(1 for e in es if e["stale"]), sum(1 for e in es if e["orphan"])],
                     fill=GROUP, bold=True)
            sh.cell(r, 3).fill = _tone(comp)
            for e in sorted(es, key=lambda e: (e["completeness"], -e["failing"])):
                r = _row(sh, [None, None, _pct(e["completeness"]), None, e["failing"] or None, e["errors"] or None,
                              "stale" if e["stale"] else None, "orphan" if e["orphan"] else None, e["name"], e["display_id"],
                              ", ".join(e["responsible"])], level=1, hidden=True)
                _link(sh.cell(r, 9), ent_url(e["entity"]))
                for f in by_ent.get(e["entity"], []):
                    _row(sh, [None] * 11 + [f"{f['kind']}{' ' + f['rule'] if f.get('rule') else ''}: {f['message']}"],
                         level=2, hidden=True)
        _pctfmt(sh, 3)
        sh.auto_filter.ref = None
    grouped("By type", lambda e: e["type_name"])
    grouped("By owner", lambda e: e["owner"] or "(no owner)")

    rs = _sheet(wb, "Rules", ["Rule", "Name", "Severity", "Entities", "Entity", "ID", "Responsible", "Why"],
                [10, 44, 10, 10, 34, 12, 22, 70])
    per_rule = defaultdict(list)
    for f in finds:
        if f["kind"] == "rule":
            per_rule[(f["rule"], f.get("rule_name", ""), f.get("severity", ""))].append(f)
    for (code, name, sev), fs in sorted(per_rule.items(), key=lambda kv: (kv[0][2] != "error", -len(kv[1]))):
        _row(rs, [code, name, sev, len({f["entity"] for f in fs})], fill=GROUP, bold=True)
        for f in fs:
            r = _row(rs, [None, None, None, None, f["name"], f["display_id"], ", ".join(f["responsible"]), f["message"]],
                     level=1, hidden=True)
            _link(rs.cell(r, 5), ent_url(f["entity"]))
    if not per_rule:
        rs.append(["No entity fails a rule."])

    fsheet = _sheet(wb, "Findings", ["Entity", "ID", "Type", "Owner", "Responsible", "Kind", "Rule", "Severity", "What"],
                    [34, 12, 24, 24, 22, 14, 10, 10, 70])
    for f in finds:
        r = _row(fsheet, [f["name"], f["display_id"], f["type_name"], f["owner"] or "(no owner)", ", ".join(f["responsible"]),
                          f["kind"], f.get("rule") or "", f.get("severity") or "", f["message"]])
        _link(fsheet.cell(r, 1), ent_url(f["entity"]))
    fsheet.auto_filter.ref = f"A1:I{max(1, fsheet.max_row)}"

    es = _sheet(wb, "Entities", ["Entity", "ID", "Type", "Owner", "Responsible", "Completeness", "Missing", "Failing", "Errors",
                                 "Stale", "Orphan", "Seal", "Last change"],
                [34, 12, 24, 24, 22, 13, 50, 9, 8, 8, 8, 10, 18])
    for e in sorted(ents, key=lambda e: (e["completeness"], -e["failing"])):
        r = _row(es, [e["name"], e["display_id"], e["type_name"], e["owner"] or "(no owner)", ", ".join(e["responsible"]),
                      _pct(e["completeness"]), ", ".join(m.split(":", 1)[1] for m in e["missing"]), e["failing"], e["errors"],
                      "yes" if e["stale"] else "", "yes" if e["orphan"] else "", "" if e["seal"] == "none" else e["seal"],
                      str(e["last_change"])[:16].replace("T", " ")])
        _link(es.cell(r, 1), ent_url(e["entity"]))
        es.cell(r, 6).fill = _tone(e["completeness"])
    _pctfmt(es, 6)
    es.auto_filter.ref = f"A1:M{max(1, es.max_row)}"

    ts = _sheet(wb, "Trend", ["Measured", "Score", "Completeness", "Stale", "Failing", "How"], [20, 10, 13, 9, 9, 12])
    for t in d.get("trend") or []:
        ts.append([str(t["at"])[:16].replace("T", " "), float(t["score"]), _pct(t["completeness"]), t.get("stale"),
                   t.get("failing"), t.get("trigger")])
    _pctfmt(ts, 3)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def estate_xlsx(data: dict, base: str) -> bytes:
    """data: eax.quality.installation(); every model opens (+) to its latest measurement's entity types."""
    from .quality_pdf import BANDS
    BANDS.set(data.get("bands") or {"green": 80, "amber": 60})          # the estate: the installation's colours (D244)
    e = data.get("estate") or {}
    wb = Workbook()
    ws = wb.active
    ws.title = "Estate"
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 30, 40
    for k, v in (("Estate score", e.get("score")), ("A month before", e.get("month_ago")), ("Completeness", _pct(e.get("completeness"))),
                 ("Models measured", f"{e.get('measured', 0)} of {e.get('models', 0)}"), ("Entities", e.get("entities")),
                 ("Incomplete", e.get("incomplete")), ("Failing a rule", e.get("failing")), ("Failing an error rule", e.get("errors")),
                 ("Stale", e.get("stale")), ("Orphans", e.get("orphans")),
                 ("How it is made", "Each model's latest measurement, weighing as many entities as it has")):
        ws.append([k, v])
        ws.cell(ws.max_row, 1).font = BOLD
    ws.cell(3, 2).number_format = "0%"
    ms = _sheet(wb, "Models", ["Model", "Entities", "Score", "A month before", "Completeness", "Incomplete", "Failing", "Stale",
                               "Orphans", "Measured"], [40, 10, 9, 15, 13, 11, 9, 8, 9, 18])
    for m in data["models"]:
        sm = m.get("summary") or {}
        r = _row(ms, [m["name"], m["entities"], None if m["score"] is None else float(m["score"]),
                      None if m["month_ago"] is None else float(m["month_ago"]), _pct(m["completeness"]), sm.get("incomplete"),
                      sm.get("failing"), sm.get("stale"), sm.get("orphans"), str(m["measured_at"] or "not yet")[:16].replace("T", " ")],
                 bold=True, fill=GROUP)
        _link(ms.cell(r, 1), f"{base.rstrip('/')}/#/metamodel/{m['id']}/quality")
        if m["score"] is not None:
            ms.cell(r, 3).fill = _tone(m["score"])
        for t in (m.get("by_type") or []):
            _row(ms, [f"   {t['name']}", t["entities"], None, None, _pct(t["completeness"]), t["incomplete"], t["failing"],
                      t["stale"], t["orphans"]], level=1, hidden=True)
    _pctfmt(ms, 5)
    ts = _sheet(wb, "Trend", ["Week ending", "Estate score", "Models measured"], [20, 13, 16])
    for t in e.get("trend") or []:
        ts.append([str(t["at"])[:10], t["score"], t["models"]])
    for c in ws["B"]:
        c.alignment = Alignment(horizontal="left")
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
