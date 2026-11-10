"""EA capability maturity (owner, 9 Nov 2026, phase 40, D377, D381, D450 to D453): how mature the organisation's
architecture practice is, by questions and evidence.

- An assessment is a survey (eax/surveys.py) of kind 'maturity', sent to the people chosen. Its starting questions
  follow the shape of the US Department of Commerce Architecture Capability Maturity Model (ACMM) version 1.2: six
  levels (0 None to 5 Measured) and nine architecture elements; one question per element ("which description fits
  best today?") with a description for each level, and a comment. The descriptions are EA Explorer's own wording (no
  text is taken from any guide), and the questions can be changed in the survey designer while the assessment is a draft.
- Scored by the ACMM's two methods: per element the mean level of the answers, and overall the mean weighted by each
  element's weight; and for each element the share of answers at or above each level.
- Beside the answers: evidence EA Explorer measures itself (models in use, data quality, governance log use, projects
  following the ADM, sign-offs, people taking part), live while the assessment is open and kept when it closes.
- Each element has a target (default 3) and a gap; closed assessments make the trend.
- Who: Super Admins (permission maturity.manage) start and run assessments and see results; the people asked answer.
Every rule is here, in Python (D248).
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from . import permissions as perms
from . import surveys as sv
from .metamodel_edit import EditError

LEVELS = [(0, "None"), (1, "Initial"), (2, "Under development"), (3, "Defined"), (4, "Managed"), (5, "Measured")]
LEVEL_NAMES = dict(LEVELS)

# (key, name, what it covers, levels 0 to 5: (description, examples)): our own wording (D450, D455, D456)
ELEMENTS: list[tuple[str, str, str, list[tuple[str, list[str]]]]] = [
    ("architecture_process", "Architecture process", "How architecture work is planned, done and repeated", [
        ("There is no architecture process at all.",
         ["Nobody can say how architecture work is meant to be done", "Projects start without any architecture step"]),
        ("Architecture work happens case by case, depending on who is involved; nothing is written down.",
         ["Each architect works their own way", "Principles exist only in people's heads"]),
        ("A way of working is being written; some projects follow parts of it.",
         ["A draft method sits in a shared folder", "Two or three projects tried the new steps"]),
        ("A written process is agreed and most architecture work follows it.",
         ["Projects follow the ADM steps in EA Explorer", "Every deliverable comes from an agreed template"]),
        ("The process is followed everywhere, measured, and adjusted when the measures say so.",
         ["Step completion is reported every month", "The process changed after a review of late deliverables"]),
        ("The process is improved all the time from measures and lessons, and others copy it.",
         ["Lessons learned feed a change to the method each quarter", "Other units ask to use the method"]),
    ]),
    ("architecture_development", "Architecture development", "How the baseline, target and roadmaps are produced and kept", [
        ("No architecture descriptions exist.",
         ["No inventory of applications or capabilities", "Diagrams are drawn for one meeting and thrown away"]),
        ("Few architecture descriptions exist; those that do are personal and out of date.",
         ["Spreadsheets on personal drives", "The last landscape picture is two years old"]),
        ("Baseline and target descriptions are being built for some areas, in a shared place.",
         ["The application inventory is half loaded into the repository", "A target exists for one domain"]),
        ("Baseline, target and roadmaps exist for most areas, to an agreed standard, in the repository.",
         ["One metamodel used by every architect", "Roadmaps link work packages to gaps"]),
        ("They are kept current as part of normal change; quality is checked and reported.",
         ["Repository updated within a week of every change", "Data quality scores reviewed monthly"]),
        ("Their quality and use are measured, and the gaps found are closed quickly.",
         ["Quality above 90% on every measured model", "Stale entries are fixed within a sprint"]),
    ]),
    ("business_linkage", "Business linkage", "How closely architecture follows the business strategy and needs", [
        ("Architecture has no link to the business strategy.",
         ["Architects have not seen the strategy", "IT plans are written without business input"]),
        ("Architecture and business plans are made separately.",
         ["Business goals are mentioned in slides but not traced", "Capabilities are not described"]),
        ("Some architecture work is traced to business drivers and goals.",
         ["A capability map exists but is not used for planning", "A few projects state the outcome they serve"]),
        ("Architecture is traced to business strategy, capabilities and outcomes in most work.",
         ["Every project links to goals and outcomes", "Capability heat maps steer the roadmap"]),
        ("Business and architecture plans are made together and reviewed together.",
         ["Business owners sit in roadmap reviews", "Value streams drive investment discussions"]),
        ("The business uses architecture to decide; the value delivered is measured.",
         ["Business cases quote the architecture", "Outcomes are measured against the plan after delivery"]),
    ]),
    ("senior_management", "Senior management involvement", "How far senior leaders support and use architecture", [
        ("Senior leaders are not involved at all.",
         ["No sponsor for architecture", "Architecture never appears on a leadership agenda"]),
        ("Senior leaders know little about architecture work.",
         ["Architecture reports go no higher than IT managers", "Leaders ask what architects do"]),
        ("Some senior leaders sponsor architecture work.",
         ["One executive sponsors the practice", "Leaders attend some architecture reviews"]),
        ("Senior leaders sign off the architecture and its principles.",
         ["Principles signed off by the executive committee", "Target architectures approved by leaders"]),
        ("Senior leaders steer architecture through a board and use it in their decisions.",
         ["An architecture board chaired by an executive", "Funding decisions refer to the roadmap"]),
        ("Senior leaders champion architecture and hold people to it.",
         ["Leaders ask for the architecture view before deciding", "Departures from principles need executive approval"]),
    ]),
    ("operating_unit", "Operating unit participation", "How far business and IT units take part", [
        ("Units do not take part at all.",
         ["Units do not know the practice exists", "Nobody outside the architects reviews anything"]),
        ("Units take no real part; architecture is an IT matter.",
         ["Business units are informed after decisions", "Only IT staff use the repository"]),
        ("A few units take part in some architecture work.",
         ["One business unit keeps its own capabilities current", "Units join workshops when invited"]),
        ("Most units take part and agree the architecture that affects them.",
         ["Units review their part of the target", "Stakeholders accept key question answers"]),
        ("Units take part as normal practice and own parts of the architecture.",
         ["Data owners in each unit keep their entities current", "Units raise change requests themselves"]),
        ("Units bring architecture into their own planning without being asked.",
         ["Unit plans reference the roadmap", "Units propose improvements to the target"]),
    ]),
    ("communication", "Architecture communication", "How architecture is shared and understood", [
        ("Architecture is not communicated at all.",
         ["Nothing is published", "People cannot find any architecture material"]),
        ("Architecture material is hard to find and seldom shared.",
         ["Documents are emailed on request", "Diagrams live in personal folders"]),
        ("Architecture material is shared now and then, mostly within IT.",
         ["An intranet page that is rarely updated", "Occasional presentations to IT teams"]),
        ("Architecture is published in one place and explained to those it affects.",
         ["Everyone reads the repository and its views", "Briefings held when the target changes"]),
        ("Communication is planned, kept current and checked for understanding.",
         ["A communication plan per audience", "Surveys ask whether people understand the target"]),
        ("Feedback on communication is measured and used to improve it.",
         ["Understanding scores rise year on year", "Views are redesigned after feedback"]),
    ]),
    ("it_security", "IT security", "How security is built into the architecture", [
        ("Security is not considered in architecture at all.",
         ["No security requirements in designs", "Security learns of changes after go-live"]),
        ("Security is added late, project by project.",
         ["Security reviews happen just before go-live", "Each project picks its own controls"]),
        ("Security requirements are starting to be considered in architecture work.",
         ["A security checklist used by some architects", "A draft security reference architecture"]),
        ("Security architecture and its standards are part of the architecture.",
         ["Security standards in the standards library", "Data classified in the repository"]),
        ("Security is checked in every architecture review and its risks are managed.",
         ["Compliance assessments include security", "Security risks tracked in the governance log"]),
        ("Security outcomes are measured and fed back into the architecture.",
         ["Incidents traced back to design weaknesses", "Security standards updated from measured results"]),
    ]),
    ("governance", "Architecture governance", "How architecture decisions are made, recorded and followed", [
        ("There is no governance of architecture.",
         ["No architecture decisions are recorded", "Nobody checks designs against anything"]),
        ("There is no real governance; decisions are made and forgotten.",
         ["Decisions live in meeting minutes only", "The same question is decided twice"]),
        ("A board or decision log is being set up; some decisions are recorded.",
         ["A decision log started for one project", "The board met twice this year"]),
        ("Decisions, compliance reviews and dispensations are recorded and followed.",
         ["Every project keeps a decision log", "Dispensations need board approval"]),
        ("Governance is applied to all change; compliance is measured and reported.",
         ["Compliance results reported to the board monthly", "Every change passes an architecture review"]),
        ("Governance is reviewed and improved from its measures.",
         ["Review turnaround time is measured and falling", "Governance rules changed after a yearly review"]),
    ]),
    ("investment", "IT investment and acquisition strategy", "How architecture shapes spending and buying", [
        ("Investment and buying ignore architecture entirely.",
         ["Software is bought by whoever has budget", "Nobody asks architects about purchases"]),
        ("Investments are decided without reference to the architecture.",
         ["Business cases do not mention the target", "Duplicate tools bought by different units"]),
        ("Some investments are checked against the architecture.",
         ["Large purchases get an architecture review", "A list of preferred products exists"]),
        ("Investment and buying decisions follow the architecture and its standards.",
         ["Procurement checks the standards library", "Business cases state which gaps they close"]),
        ("Every investment is assessed against the architecture and the roadmap.",
         ["Investment committee uses the roadmap", "Spend is tracked per capability"]),
        ("Investment results are measured against the architecture and drive the next plans.",
         ["Benefits are checked against the target after delivery", "Next year's budget follows measured gaps"]),
    ]),
]
ELEMENT_NAMES = {k: n for k, n, *_ in ELEMENTS}
DEFAULT_TARGET = 3


def may_manage(user) -> bool:
    return perms.allowed(set(getattr(user, "roles", ()) or ()), "maturity.manage")


def _need(user) -> None:
    if not may_manage(user):
        raise EditError("Maturity assessments are run by Super Admins.", 403)


def default_spec() -> dict:
    """The starting questions: one section per element, its level and a comment."""
    sections = []
    for key, name, about, levels in ELEMENTS:
        opts = [{"value": str(i), "label": f"{i} {LEVEL_NAMES[i]}", "description": d, "examples": ex, "score": i}
                for i, (d, ex) in enumerate(levels)]
        sections.append({"key": key, "title": name, "text": about, "questions": [
            {"key": f"{key}_level", "kind": "single", "text": f"Which description fits {name.lower()} best today?",
             "required": True, "element": key, "options": opts},
            {"key": f"{key}_comment", "kind": "long_text", "text": "Comment: why this level, or what is missing", "element": key},
            {"key": f"{key}_evidence", "kind": "links", "text": "Evidence: links to what shows it", "element": key},
        ]})
    return sv.clean_spec({"sections": sections})


def clean_settings(d: dict) -> dict:
    """Targets (0 to 5) and weights (0 to 10) per element; kept evidence and scores pass through."""
    out = {k: v for k, v in (d or {}).items() if k in ("evidence", "evidence_at", "scores", "opened_evidence")}
    t, w = (d or {}).get("targets") or {}, (d or {}).get("weights") or {}
    out["targets"], out["weights"] = {}, {}
    for key, *_ in ELEMENTS:
        try:
            out["targets"][key] = min(max(float(t.get(key, DEFAULT_TARGET)), 0), 5)
            out["weights"][key] = min(max(float(w.get(key, 1)), 0), 10)
        except (TypeError, ValueError) as exc:
            raise EditError("Targets and weights are numbers.") from exc
    return out


# ---------------------------------------------------------------- evidence measured by EA Explorer
def evidence(conn) -> list[dict]:
    """What EA Explorer measures itself, each with the elements it speaks to. A part that cannot be read is left out."""
    items: list[dict] = []
    from .quality import _bypass
    _bypass(conn, True)            # counts across the organisation, whoever runs it (no rows are shown)

    def one(sql: str, **p) -> dict:
        with conn.begin_nested():          # a part that fails (an older installation) never spoils the rest
            return dict(conn.execute(text(sql), p).mappings().first() or {})

    try:
        r = one("""SELECT count(*) AS models,
                          count(*) FILTER (WHERE EXISTS (SELECT 1 FROM core.commits c WHERE c.model_id = m.id
                                                           AND c.committed_at > now() - interval '90 days')) AS active
                     FROM core.models m WHERE NOT m.is_deleted AND m.kind_code NOT IN ('template', 'reference')""")
        items.append({"key": "models_in_use", "name": "Models in use", "value": f"{r['active']} of {r['models']}",
                      "note": "models with a commit in the last 90 days, of all the organisation's own models",
                      "share": round(100 * r["active"] / r["models"]) if r["models"] else 0,
                      "elements": ["architecture_development", "architecture_process"]})
    except Exception:  # noqa: BLE001
        pass
    try:
        r = one("""SELECT round(avg(score), 1) AS score, count(*) AS n FROM (
                       SELECT DISTINCT ON (model_id) model_id, score FROM core.quality_runs ORDER BY model_id, run_at DESC) q""")
        if r.get("n"):
            items.append({"key": "data_quality", "name": "Data quality", "value": f"{r['score']}%",
                          "note": f"the mean of the latest quality score of {r['n']} measured models",
                          "share": float(r["score"] or 0), "elements": ["architecture_development", "governance"]})
    except Exception:  # noqa: BLE001
        pass
    try:
        people = one("SELECT count(DISTINCT username) AS n FROM core.model_users").get("n", 0)
    except Exception:  # noqa: BLE001
        people = 0
    _bypass(conn, False)
    try:
        from .db import get_engine, get_projects_engine
        peng = get_projects_engine()
        with (contextlib.nullcontext(conn) if peng is get_engine() else peng.connect()) as pconn:
            def pone(sql: str) -> dict:
                with pconn.begin_nested():
                    return dict(pconn.execute(text(sql)).mappings().first() or {})
            g = pone("""SELECT count(*) AS records, count(DISTINCT project_id) AS projects FROM proj.gov_records
                         WHERE created_at > now() - interval '180 days'""")
            p = pone("""SELECT count(*) FILTER (WHERE status = 'active') AS active,
                               count(*) FILTER (WHERE status = 'active' AND EXISTS (SELECT 1 FROM proj.steps s WHERE s.project_id = p.id
                                                AND s.done_at > now() - interval '180 days')) AS moving
                          FROM proj.projects p""")
            so = pone("SELECT count(*) AS n FROM proj.signoff_requests WHERE closed_at > now() - interval '365 days'")
            members = pone("SELECT count(DISTINCT lower(username)) AS n FROM proj.members").get("n", 0)
        items.append({"key": "governance_log", "name": "Governance log use", "value": f"{g['records']} records",
                      "note": f"decisions, compliance reviews and other governance records in the last 180 days, in {g['projects']} projects",
                      "elements": ["governance", "investment"]})
        items.append({"key": "projects_adm", "name": "Projects following the ADM", "value": f"{p['moving']} of {p['active']}",
                      "note": "active projects that finished an ADM step in the last 180 days",
                      "share": round(100 * p["moving"] / p["active"]) if p["active"] else 0,
                      "elements": ["architecture_process", "business_linkage"]})
        items.append({"key": "signoffs", "name": "Sign-offs", "value": f"{so['n']} decided",
                      "note": "deliverable sign-offs decided in the last 365 days",
                      "elements": ["senior_management", "business_linkage"]})
        people = max(people, members)
    except Exception:  # noqa: BLE001 - projects switched off or not reachable
        pass
    items.append({"key": "people", "name": "People taking part", "value": f"{people} people",
                  "note": "people with a role on a model or a project", "elements": ["operating_unit", "communication"]})
    return items


def on_open(conn, s: dict) -> None:
    m = clean_settings(s["maturity"] or {})
    m["opened_evidence"] = evidence(conn)
    conn.execute(text("UPDATE core.surveys SET maturity = CAST(:m AS jsonb) WHERE guid = :g"), {"m": json.dumps(m), "g": s["guid"]})


def on_close(conn, s: dict) -> None:
    """Kept when it closes: the evidence then, and the scores, so the trend compares like with like."""
    m = clean_settings(s["maturity"] or {})
    m["evidence"] = evidence(conn)
    m["evidence_at"] = datetime.now(UTC).isoformat()
    m["scores"] = scores({**s, "maturity": m}, sv._responses(conn, s))
    conn.execute(text("UPDATE core.surveys SET maturity = CAST(:m AS jsonb) WHERE guid = :g"), {"m": json.dumps(m), "g": s["guid"]})


# ---------------------------------------------------------------- scores
def scores(s: dict, responses: list[dict]) -> dict:
    """Per element: the answers' mean level, target, gap, weight, spread over the levels and the share at or above each
    level (the ACMM's second method); overall: the mean weighted by the elements' weights (its first method)."""
    m = clean_settings(s.get("maturity") or {})
    by_el: dict[str, dict[str, float]] = {}
    for q in sv.questions(s.get("spec") or {}):
        if q.get("element") and q["kind"] == "single":
            by_el.setdefault(q["element"], {}).update({o["value"]: o["score"] for o in q.get("options", []) if "score" in o})
    qkeys = {q["key"]: q["element"] for q in sv.questions(s.get("spec") or {}) if q.get("element") and q["kind"] == "single"}
    rows, wsum, wtot = [], 0.0, 0.0
    for key, name, about, _d in ELEMENTS:
        levels = []
        for r in responses:
            for qk, el in qkeys.items():
                v = (r.get("answers") or {}).get(qk)
                if el == key and v in by_el.get(key, {}):
                    levels.append(by_el[key][v])
        mean = round(sum(levels) / len(levels), 2) if levels else None
        target, weight = m["targets"][key], m["weights"][key]
        row = {"element": key, "name": name, "about": about, "answers": len(levels), "mean": mean,
               "level": LEVEL_NAMES[int(mean)] if mean is not None else "", "target": target, "weight": weight,
               "gap": round(max(target - mean, 0), 2) if mean is not None else None,
               "spread": {str(i): sum(1 for x in levels if int(x) == i) for i, _n in LEVELS},
               "at_or_above": {str(i): round(100 * sum(1 for x in levels if x >= i) / len(levels)) if levels else 0
                               for i in range(1, 6)}}
        if mean is not None and weight:
            wsum += mean * weight
            wtot += weight
        rows.append(row)
    overall = round(wsum / wtot, 2) if wtot else None
    return {"elements": rows, "overall": overall, "overall_level": LEVEL_NAMES[int(overall)] if overall is not None else "",
            "responses": len(responses), "levels": [{"level": i, "name": n} for i, n in LEVELS]}


# ---------------------------------------------------------------- screens
def overview(conn, user) -> dict:
    """Every assessment, the trend over closed ones, and the evidence now."""
    _need(user)
    rows = [dict(r) for r in conn.execute(text("""SELECT * FROM core.surveys WHERE kind = 'maturity' AND NOT is_deleted
                                                   ORDER BY COALESCE(closed_at, opened_at, created_at) DESC""")).mappings()]
    out, trend = [], []
    for s in rows:
        item = sv._out(conn, s, user)
        sc = (s["maturity"] or {}).get("scores") if s["status"] == "closed" else None
        if sc is None and s["status"] != "draft":
            sc = scores(s, sv._responses(conn, s))
        item["overall"] = sc["overall"] if sc else None
        out.append(item)
        if s["status"] == "closed" and sc:
            trend.append({"id": str(s["guid"]), "title": s["title"], "closed_at": s["closed_at"], "overall": sc["overall"],
                          "elements": {e["element"]: e["mean"] for e in sc["elements"]}})
    trend.sort(key=lambda t: t["closed_at"])
    return {"assessments": out, "trend": trend, "evidence": evidence(conn), "may_manage": True,
            "elements": [{"key": k, "name": n, "about": a} for k, n, a, _d in ELEMENTS],
            "levels": [{"level": i, "name": n} for i, n in LEVELS]}


def create(conn, user, d: dict) -> dict:
    """A new assessment: a draft survey with the starting questions, targets and weights (and sent at once if asked)."""
    _need(user)
    when = datetime.now(UTC)
    body = {"title": (d.get("title") or f"EA capability maturity {when:%B %Y}"), "description": d.get("description") or (
                "How mature is our architecture practice? For each of nine areas, choose the description that fits best "
                "today and say what shows it. It takes about fifteen minutes."),
            "spec": d.get("spec") or default_spec(), "recipients": d.get("recipients") or [],
            "anonymous": bool(d.get("anonymous")), "closes_at": d.get("closes_at"),
            "remind_every_days": d.get("remind_every_days"),
            "maturity": clean_settings({"targets": d.get("targets") or {}, "weights": d.get("weights") or {}})}
    out = sv.create(conn, user, body, kind="maturity")
    if d.get("send"):
        out = sv.send(conn, user, out["id"])
    return out


def result(conn, user, guid: Any) -> dict:
    _need(user)
    out = sv.results(conn, user, guid)
    if out["kind"] != "maturity":
        raise EditError("Not a maturity assessment.", 404)
    s = sv._survey(conn, guid)
    m = s["maturity"] or {}
    out["evidence"] = m.get("evidence") if s["status"] == "closed" and m.get("evidence") else evidence(conn)
    out["evidence_at"] = m.get("evidence_at") if s["status"] == "closed" else None
    out["respondents"] = respondents(s, sv._responses(conn, s))
    out["previous"] = None
    prev = conn.execute(text("""SELECT guid, title, maturity FROM core.surveys WHERE kind = 'maturity' AND status = 'closed'
                                   AND NOT is_deleted AND guid <> :g AND closed_at < COALESCE(:c, now())
                                 ORDER BY closed_at DESC LIMIT 1"""), {"g": s["guid"], "c": s["closed_at"]}).mappings().first()
    if prev and (prev["maturity"] or {}).get("scores"):
        ps = prev["maturity"]["scores"]
        out["previous"] = {"id": str(prev["guid"]), "title": prev["title"], "overall": ps["overall"],
                           "elements": {e["element"]: e["mean"] for e in ps["elements"]}}
    return out


def respondents(s: dict, responses: list[dict]) -> list[dict]:
    """Per person (D456): each element's value, comment and evidence; "Respondent n" in an anonymous assessment."""
    qs = [q for q in sv.questions(s.get("spec") or {}) if q.get("element")]
    out = []
    for i, r in enumerate(responses, 1):
        a = r.get("answers") or {}
        els: dict[str, dict] = {}
        for q in qs:
            v = a.get(q["key"])
            if v in (None, "", []):
                continue
            part = "level" if q["kind"] == "single" else "evidence" if q["kind"] == "links" else "comment"
            if part == "level":
                o = next((o for o in q.get("options", []) if o["value"] == v), None)
                v = {"value": v, "score": (o or {}).get("score"), "label": (o or {}).get("label", v)}
            els.setdefault(q["element"], {})[part] = v
        out.append({"who": r.get("respondent") or f"Respondent {i}", "submitted_at": r.get("submitted_at"), "elements": els})
    return out


def xlsx_sheet(wb, sc: dict, bold, spec: dict | None = None) -> None:
    """The scores sheet of an assessment's workbook, and its levels with their examples (as the questions were sent)."""
    if spec:
        lv = wb.create_sheet("Levels and examples", 1)
        lv.append(["Element", "Level", "Description", "Examples"])
        for c in lv[1]:
            c.font = bold
        for q in sv.questions(spec):
            if q.get("element") and q["kind"] == "single":
                for o in q.get("options", []):
                    lv.append([q["section_title"], o["label"], o.get("description", ""), "\n".join(o.get("examples", []))])
        for col, w in zip("ABCD", (34, 22, 70, 70), strict=False):
            lv.column_dimensions[col].width = w
    ws = wb.create_sheet("Maturity scores", 1)
    ws.append(["Element", "Answers", "Mean level", "Level", "Target", "Gap", "Weight"] + [f"% at or above {i}" for i in range(1, 6)])
    for c in ws[1]:
        c.font = bold
    for e in sc["elements"]:
        ws.append([e["name"], e["answers"], e["mean"], e["level"], e["target"], e["gap"], e["weight"]]
                  + [e["at_or_above"][str(i)] for i in range(1, 6)])
    ws.append([])
    ws.append(["Overall (weighted mean)", sc["responses"], sc["overall"], sc["overall_level"]])
    ws.cell(ws.max_row, 1).font = bold
    ws.column_dimensions["A"].width = 38
