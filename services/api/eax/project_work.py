"""Setting up and running an architecture project (build phase 13.0.1, D274 to D279).

Beside eax/projects.py (the wizard's first pass, the repository and the documents), this holds:

    scope_fields(d)                    scope (breadth, depth, time, domains), sponsor and asks, notes (rich text, cleaned)
    goals / write_goals                the project's goals and outcomes: Goal and Outcome entities in its home model (D274)
    viewpoint_status / add_viewpoint   its viewpoints: ready in a model's metamodel, or to build; its own (PV-...)
    update(conn, user, project, d)     the edit workflow: the wizard again on a live project (D275)
    project files                      contracts and the like, kept with the project (00_Project/Project files)
    sign-off                           raise, decide (in the application, or self), record with evidence (D276)
    finish                             freeze, or merge into another project (documents copied, models kept or merged
                                       into their parent model), done in the background (D277)

Rules are here, never in the database (D248).
"""

from __future__ import annotations

import json
import mimetypes
import re
from datetime import date
from html.parser import HTMLParser
from typing import Any

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError

DEPTHS = {"strategic": "Strategic", "segment": "Segment", "capability": "Capability"}
DOMAINS = ("business", "data", "application", "technology")
PROJECT_FILES = "00_Project/Project files"
EVIDENCE = "00_Project/Sign-off evidence"
FROZEN = ("finishing", "frozen", "merged", "closed")
GOAL, OUTCOME = "Goal", "Outcome"

_rows, _one = pj._rows, pj._one


# ---------------------------------------------------------------- rich text, cleaned before it is stored
class _Clean(HTMLParser):
    TAGS = {"p", "br", "b", "strong", "i", "em", "u", "s", "h3", "h4", "ul", "ol", "li", "a", "blockquote", "code", "pre",
            "table", "thead", "tbody", "tr", "th", "td", "hr", "div", "span"}
    VOID = {"br", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "iframe", "object", "embed"):
            self.skip += 1
            return
        if self.skip or tag not in self.TAGS:
            return
        extra = ""
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if re.match(r"^(https?:|mailto:|#)", href.strip(), re.I):
                extra = f' href="{_esc(href.strip())}" rel="noreferrer" target="_blank"'
        self.out.append(f"<{tag}{extra}>")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "iframe", "object", "embed"):
            self.skip = max(0, self.skip - 1)
            return
        if not self.skip and tag in self.TAGS and tag not in self.VOID:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(_esc(data))


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def clean_html(html: str | None) -> str:
    """Only plain formatting survives (no scripts, styles, events or images); links only to web pages and mail."""
    c = _Clean()
    c.feed(html or "")
    c.close()
    return "".join(c.out)[:200_000]


# ---------------------------------------------------------------- scope, sponsor, notes (D274)
def _date(v: Any, what: str) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError as exc:
        raise EditError(f"The {what} is not a date (YYYY-MM-DD).") from exc


def scope_fields(d: dict) -> dict:
    s = d.get("scope") or {}
    depth = (s.get("depth") or "").strip().lower()
    if depth and depth not in DEPTHS:
        raise EditError("The level of detail is strategic, segment or capability.")
    domains = [x for x in (s.get("domains") or []) if x in DOMAINS]
    start, end = _date(s.get("start"), "start date"), _date(s.get("end"), "end date")
    if start and end and end < start:
        raise EditError("The project ends before it starts: check the dates in Scope.")
    sp = d.get("sponsor") or {}
    asks = [{"ask": (a.get("ask") or "").strip(), "by": (a.get("by") or "").strip()[:10], "measure": (a.get("measure") or "").strip()}
            for a in (sp.get("asks") or []) if (a.get("ask") or "").strip()]
    return {"scope_breadth": (s.get("breadth") or "").strip(), "scope_depth": depth, "scope_domains": domains,
            "scope_start": start, "scope_end": end, "scope_horizon": (s.get("horizon") or "").strip(),
            "scope_notes": (s.get("notes") or "").strip(), "sponsor_name": (sp.get("name") or "").strip(),
            "sponsor_role": (sp.get("role") or "").strip(), "sponsor_contact": (sp.get("contact") or "").strip(),
            "sponsor_asks": json.dumps(asks), "notes_html": clean_html(d.get("notes_html")),
            "sponsor_notes_html": clean_html(sp.get("notes_html")), "goals_notes_html": clean_html(d.get("goals_notes_html"))}


def save_fields(conn, project_id: int, f: dict) -> None:
    conn.execute(text("""UPDATE proj.projects SET scope_breadth = :scope_breadth, scope_depth = :scope_depth,
                                scope_domains = CAST(:scope_domains AS text[]), scope_start = :scope_start, scope_end = :scope_end,
                                scope_horizon = :scope_horizon, scope_notes = :scope_notes, sponsor_name = :sponsor_name,
                                sponsor_role = :sponsor_role, sponsor_contact = :sponsor_contact,
                                sponsor_asks = CAST(:sponsor_asks AS jsonb), notes_html = :notes_html,
                                sponsor_notes_html = :sponsor_notes_html, goals_notes_html = :goals_notes_html, modified_at = now()
                          WHERE id = :p"""), {**f, "p": project_id})


def fields_out(p: dict) -> dict:
    asks = p.get("sponsor_asks")
    asks = asks if isinstance(asks, list) else json.loads(asks or "[]")
    return {"scope": {"breadth": p["scope_breadth"], "depth": p["scope_depth"], "domains": list(p["scope_domains"] or []),
                      "start": str(p["scope_start"])[:10] if p.get("scope_start") else "",
                      "end": str(p["scope_end"])[:10] if p.get("scope_end") else "", "horizon": p["scope_horizon"],
                      "notes": p["scope_notes"]},
            "sponsor": {"name": p["sponsor_name"], "role": p["sponsor_role"], "contact": p["sponsor_contact"], "asks": asks,
                        "notes_html": p.get("sponsor_notes_html") or ""},
            "notes_html": p["notes_html"], "goals_notes_html": p.get("goals_notes_html") or "", "home_model": str(p["home_model"]) if p.get("home_model") else None,
            "finished_at": p.get("finished_at"), "finished_by": p.get("finished_by"), "finish_note": p.get("finish_note") or ""}


# ---------------------------------------------------------------- goals and outcomes: entities in the home model (D274)
def _tag(p: dict) -> str:
    return f"project:{p['guid']}"


def goals(conn, p: dict) -> list[dict]:
    """The project's goals, each with its outcomes (Outcome realises Goal), read from its home model."""
    if not p.get("home_model"):
        return []
    rows = _rows(pj.core(conn), """SELECT e.guid::text AS id, e.name, e.description, et.name AS type FROM core.entities e
                                     JOIN core.entity_types et ON et.id = e.entity_type_id
                                     JOIN core.models m ON m.id = e.model_id
                                    WHERE m.guid = CAST(:m AS uuid) AND NOT e.is_deleted AND :t = ANY (e.tags)
                                      AND et.name IN ('Goal', 'Outcome') ORDER BY e.name""", m=str(p["home_model"]), t=_tag(p))
    links = _rows(pj.core(conn), """SELECT s.guid::text AS outcome, t.guid::text AS goal FROM core.relationships r
                                      JOIN core.entities s ON s.id = r.source_entity_id JOIN core.entities t ON t.id = r.target_entity_id
                                     WHERE NOT r.is_deleted AND s.guid::text = ANY (CAST(:ids AS text[]))""",
                  ids=[r["id"] for r in rows if r["type"] == OUTCOME])
    of = {link["outcome"]: link["goal"] for link in links}
    out = [{"id": g["id"], "name": g["name"], "description": g["description"], "outcomes": []} for g in rows if g["type"] == GOAL]
    by = {g["id"]: g for g in out}
    loose = {"id": None, "name": "Outcomes not linked to a goal", "description": "", "outcomes": []}
    for o in (r for r in rows if r["type"] == OUTCOME):
        desc, measure, target = _split_outcome(o["description"])
        by.get(of.get(o["id"]), loose)["outcomes"].append({"id": o["id"], "name": o["name"], "description": desc,
                                                          "measure": measure, "target_date": target})
    return out + ([loose] if loose["outcomes"] else [])


def _outcome_text(o: dict) -> str:
    parts = [(o.get("description") or "").strip()]
    if (o.get("measure") or "").strip():
        parts.append(f"Measure: {o['measure'].strip()}")
    if (o.get("target_date") or "").strip():
        parts.append(f"Target date: {o['target_date'].strip()[:10]}")
    return "\n".join(x for x in parts if x)


def _split_outcome(desc: str) -> tuple[str, str, str]:
    measure = target = ""
    keep = []
    for line in (desc or "").splitlines():
        if line.startswith("Measure: "):
            measure = line[9:]
        elif line.startswith("Target date: "):
            target = line[13:]
        else:
            keep.append(line)
    return "\n".join(keep).strip(), measure, target


def write_goals(conn, p: dict, user, wanted: list[dict] | None) -> str:
    """Makes the home model's Goal and Outcome entities match the list (new ones made, changed ones saved, removed ones
    deleted). When the model's metamodel has no Goal or Outcome yet (its copy is still running), the list waits on the
    project (pending_goals) and is written when the copy is done."""
    from . import content
    from . import repository as repo
    wanted = [g for g in (wanted or []) if (g.get("name") or "").strip() or g.get("outcomes")]
    if not p.get("home_model"):
        if wanted:
            raise EditError("Choose the model the goals and outcomes go into (Models: the project's model).")
        return ""
    c = pj.core(conn)
    model = str(p["home_model"])
    m = repo.get_model(c, model)
    try:
        repo._find_type(c, m["_id"], GOAL)
        repo._find_type(c, m["_id"], OUTCOME)
    except repo.NotFound:
        if m.get("copy_state") not in (None, "", "done"):
            conn.execute(text("UPDATE proj.projects SET pending_goals = CAST(:g AS jsonb) WHERE id = :p"),
                         {"g": json.dumps(wanted), "p": p["id"]})
            return f"The goals are written into {m['name']} when its metamodel copy is done."
        raise EditError(f"{m['name']}'s metamodel has no Goal and Outcome types (ArchiMate 4 motivation): choose a model whose "
                        "metamodel has them for the goals.", 409) from None
    have = {g["id"]: g for g in goals(conn, p) if g["id"]}
    have_out = {o["id"]: o for g in goals(conn, p) for o in g["outcomes"]}
    keep: set[str] = set()
    made = changed = 0
    tag = _tag(p)
    for g in wanted:
        name = (g.get("name") or "").strip() or "Goal"
        if g.get("id") in have:
            gid = g["id"]
            if have[gid]["name"] != name or (have[gid]["description"] or "") != (g.get("description") or "").strip():
                content.update_entity(c, model, gid, {"name": name, "description": g.get("description") or ""}, user.username)
                changed += 1
        else:
            gid = content.create_entity(c, model, {"entity_type": GOAL, "name": name, "description": g.get("description") or "",
                                                   "tags": [tag]}, user.username, light=True)["id"]
            made += 1
        keep.add(str(gid))
        for o in g.get("outcomes") or []:
            oname = (o.get("name") or "").strip()
            if not oname:
                continue
            desc = _outcome_text(o)
            if o.get("id") in have_out:
                oid = o["id"]
                cur = have_out[oid]
                if cur["name"] != oname or _outcome_text(cur) != desc:
                    content.update_entity(c, model, oid, {"name": oname, "description": desc}, user.username)
                    changed += 1
            else:
                oid = content.create_entity(c, model, {"entity_type": OUTCOME, "name": oname, "description": desc, "tags": [tag]},
                                            user.username, light=True)["id"]
                made += 1
                try:
                    content.add_relationship(c, model, {"source": oid, "target": gid, "relationship_type": "Realization",
                                                        "allow_outside": True}, user.username)
                except Exception:  # noqa: BLE001 - a metamodel without Realization: the outcome stays, unlinked
                    pj.log.info("outcome %s not linked to goal %s", oid, gid)
            keep.add(str(oid))
    gone = [x for x in list(have) + list(have_out) if x not in keep]
    for x in [x for x in gone if x in have_out] + [x for x in gone if x in have]:     # outcomes first, then goals
        content.delete_entity(c, model, x)
    conn.execute(text("UPDATE proj.projects SET pending_goals = '[]' WHERE id = :p"), {"p": p["id"]})
    return f"Goals and outcomes in {m['name']}: {made} new, {changed} changed, {len(gone)} removed."


def check_goal_model(conn, d: dict) -> None:
    """Fails at once (before anything is made) when goals are given but the project's model, or the model it is made
    from, has no Goal and Outcome types."""
    from . import repository as repo
    goals_given = [g for g in (d.get("goals") or []) if (g.get("name") or "").strip()]
    if not goals_given:
        return
    home = next((m for m in d.get("models") or [] if m.get("home")), None)
    if home is None:
        home = next((m for m in d.get("models") or [] if m.get("how") in ("derived", "created")), None)
    if home is None:
        raise EditError("Goals and outcomes live in the project's model: choose or create one first (Models), and mark it as the project's model.")
    ref = home.get("model") or home.get("from") or home.get("id")
    if not ref:
        return
    c = pj.core(conn)
    m = repo.get_model(c, ref)
    try:
        repo._find_type(c, m["_id"], GOAL)
        repo._find_type(c, m["_id"], OUTCOME)
    except repo.NotFound:
        raise EditError(f"{m['name']}'s metamodel has no Goal and Outcome types (ArchiMate 4 motivation), so the project's goals "
                        "cannot go into a model made from it: choose a model with an ArchiMate 4 metamodel.", 409) from None


def write_pending_goals(conn, project: Any, user) -> str:
    p = pj.project_row(conn, project)
    pending = p.get("pending_goals")
    pending = pending if isinstance(pending, list) else json.loads(pending or "[]")
    return write_goals(conn, p, user, pending) if pending else ""


# ---------------------------------------------------------------- viewpoints (D278)
def model_types(conn, p: dict) -> list[str]:
    guids = [r["g"] for r in _rows(conn, "SELECT model_guid::text AS g FROM proj.project_models WHERE project_id = :p", p=p["id"])]
    if not guids:
        return []
    return [r["name"] for r in _rows(pj.core(conn), """SELECT DISTINCT et.name FROM core.entity_types et JOIN core.models m ON m.id = et.model_id
                                                         WHERE m.guid::text = ANY (CAST(:g AS text[])) AND NOT et.is_deleted
                                                         ORDER BY et.name""", g=guids)]


def viewpoint_status(conn, p: dict) -> list[dict]:
    """Each viewpoint of the project: ready (every element type it shows is in one of the project's models'
    metamodels: open it in that model) or to build (the types still missing)."""
    rows = _rows(conn, "SELECT viewpoint AS code, own, phase FROM proj.project_viewpoints WHERE project_id = :p ORDER BY viewpoint", p=p["id"])
    if not rows:
        return []
    vps = {v["code"]: v for v in _rows(pj.core(conn), """SELECT code, name, purpose, concerns, stakeholders, element_types, category
                                                           FROM core.viewpoints WHERE code = ANY (CAST(:c AS text[]))""",
                                         c=[r["code"] for r in rows])}
    # the project's model first, then the ones it works on, the ones it only refers to last (a tie goes to the first)
    models = _rows(conn, """SELECT model_guid::text AS g FROM proj.project_models WHERE project_id = :p
                             ORDER BY (model_guid::text = :h) DESC NULLS LAST, (how = 'referred'), added_at""", p=p["id"], h=str(p["home_model"]) if p.get("home_model") else None)
    types_by_model: dict[str, set[str]] = {}
    for r in _rows(pj.core(conn), """SELECT m.guid::text AS g, m.name AS model, lower(et.name) AS t, lower(et.code) AS c
                                       FROM core.entity_types et JOIN core.models m ON m.id = et.model_id
                                      WHERE m.guid::text = ANY (CAST(:g AS text[])) AND NOT et.is_deleted""", g=[x["g"] for x in models]):
        types_by_model.setdefault(r["g"], set()).update({r["t"], r["c"]})
    names = {r["g"]: r["n"] for r in _rows(pj.core(conn), "SELECT guid::text AS g, name AS n FROM core.models WHERE guid::text = ANY (CAST(:g AS text[]))",
                                         g=[x["g"] for x in models])}
    out = []
    for r in rows:
        v = vps.get(r["code"])
        if not v:
            continue
        want = [t for t in v["element_types"] or []]
        best, missing = None, want
        per_model = []          # every project model: what of the viewpoint it can show (owner, 7 Nov 2026: choose the model)
        for g in [x["g"] for x in models]:
            miss = [t for t in want if t.lower() not in types_by_model.get(g, set())]
            per_model.append({"model": g, "name": names.get(g), "missing": miss})
            if best is None or len(miss) < len(missing):
                best, missing = g, miss
        out.append({"code": v["code"], "name": v["name"], "purpose": v["purpose"], "concerns": v["concerns"],
                    "stakeholders": v["stakeholders"], "element_types": want, "own": r["own"],
                    "state": "ready" if best and not missing else "to build", "missing": missing,
                    "model": best, "model_name": names.get(best), "models": per_model,
                    "phase": r.get("phase") or VIEWPOINT_PHASE.get(v["code"]) or VIEWPOINT_PHASE_BY_CATEGORY.get(v["category"] or "", "")})
    return out


# the ADM phase a viewpoint is shown with (owner, 7 Nov 2026: viewpoints by phase); a project can move one to another phase
VIEWPOINT_PHASE = {
    "VP-14": "A", "VP-15": "A", "VP-17": "A", "VP-18": "A", "VP-19": "A", "VP-20": "A", "VP-21": "A", "VP-22": "A",
    "VP-01": "B", "VP-05": "B", "VP-07": "B", "VP-10": "B", "VP-12": "B",
    "VP-02": "C", "VP-03": "C", "VP-08": "C", "VP-11": "C",
    "VP-04": "D", "VP-06": "D", "VP-09": "D", "VP-13": "D",
    "VP-23": "F", "VP-24": "F", "VP-25": "E", "VP-26": "E",
    "VP-16": "RM",
}
VIEWPOINT_PHASE_BY_CATEGORY = {"Motivation": "A", "Strategy": "A", "Implementation and migration": "E"}


def set_viewpoint_phase(conn, project: Any, user, code: str, phase: str) -> dict:
    """The phase a project shows a viewpoint with (anyone who contributes)."""
    p = pj.project_row(conn, project)
    need(conn, p, user, "contribute")
    if phase and not _rows(conn, "SELECT 1 AS x FROM proj.lib_phases WHERE code = :c", c=phase):
        raise EditError("No such phase.")
    r = _rows(conn, """UPDATE proj.project_viewpoints SET phase = :ph WHERE project_id = :p AND viewpoint = :v RETURNING viewpoint""",
              ph=phase or None, p=p["id"], v=code)
    if not r:
        raise EditError("The project does not use that viewpoint.", 404)
    return {"code": code, "phase": phase, "message": f"{code} is shown with phase {phase}." if phase else f"{code}: back to its usual phase."}


def add_viewpoint(conn, project: Any, user, data: dict) -> dict:
    """A viewpoint made for the project (a contributor): stored with the organisation's viewpoints (code PV-<n>) and
    chosen for the project. Element types not in its models' metamodels make it a viewpoint to build."""
    from . import viewpoints as vp
    p = pj.project_row(conn, project)
    need(conn, p, user, "contribute")
    used = [r["code"] for r in _rows(pj.core(conn), "SELECT code FROM core.viewpoints WHERE code LIKE 'PV-%'")]
    n = max([int(m.group(1)) for c in used if (m := re.match(r"^PV-(\d+)$", c))] or [0]) + 1
    v = vp.save_viewpoint(pj.core(conn), {"code": f"PV-{n:02d}", "name": data.get("name"), "category": "Project",
                                          "purpose": data.get("purpose") or f"Made for the architecture project {p['name']}.",
                                          "concerns": data.get("concerns"), "stakeholders": data.get("stakeholders"),
                                          "element_types": data.get("element_types") or [],
                                          "relationship_types": data.get("relationship_types") or [],
                                          "heat_attribute": "Lifecycle", "audiences": []}, user.username)
    conn.execute(text("""INSERT INTO proj.project_viewpoints (project_id, viewpoint, own, phase) VALUES (:p, :v, true, :ph)
                         ON CONFLICT DO NOTHING"""), {"p": p["id"], "v": v["code"], "ph": data.get("phase") or None})
    return {"code": v["code"], "message": f"Viewpoint {v['code']} {v['name']} made for {p['name']}."}


# ---------------------------------------------------------------- who may do what, frozen projects read only
def need(conn, p: dict, user, what: str) -> set[str]:
    roles = pj._need(conn, p, user, what)
    if what != "read" and p.get("status") in FROZEN:
        raise EditError(f"{p['name']} is {p['status']}: it is read only.", 409)
    return roles


# ---------------------------------------------------------------- the edit workflow (D275)
def update(conn, user, project: Any, d: dict) -> dict:
    """The wizard on a live project (Project Admin, Lead Architect): what it sends is the project as it should be.
    Returns {project, copies, note}: copies are new model content copies (done by the caller in the background)."""
    p = pj.project_row(conn, project)
    need(conn, p, user, "admin")
    name = (d.get("name") or p["name"]).strip()
    if name.lower() != p["name"].lower() and _one(conn, "SELECT 1 AS x FROM proj.projects WHERE lower(name) = lower(:n)", n=name):
        raise EditError(f"A project called {name} exists already.", 409)
    if not (d.get("purpose") or p["purpose"]).strip():
        raise EditError("Choose the purpose.")
    conn.execute(text("UPDATE proj.projects SET name = :n, purpose = :pu, description = :de WHERE id = :p"),
                 {"n": name, "pu": (d.get("purpose") or p["purpose"]).strip(), "de": (d.get("description") or "").strip(), "p": p["id"]})
    save_fields(conn, p["id"], scope_fields(d))
    if "signoff_quorum" in d:
        pj.set_quorum(conn, p, d.get("signoff_quorum"))
    # models: new ones as in the wizard, removed ones unlinked (the model itself stays)
    linked = {r["g"]: r["how"] for r in _rows(conn, "SELECT model_guid::text AS g, how FROM proj.project_models WHERE project_id = :p", p=p["id"])}
    keep, copies, made, home = set(), [], [], None
    for m in d.get("models") or []:
        if m.get("id") and m["id"] in linked:
            keep.add(m["id"])
            if m.get("home"):
                home = m["id"]
            if "role" in m:
                from .project_templates import ROLES
                if m["role"] and m["role"] not in ROLES:
                    raise EditError(f"Unknown model role {m['role']}.")
                conn.execute(text("UPDATE proj.project_models SET role = :r, role_seq = :q WHERE project_id = :p AND model_guid = CAST(:m AS uuid)"),
                             {"r": m["role"] or None, "q": m.get("seq"), "p": p["id"], "m": m["id"]})
            if m.get("how") in ("added", "referred") and linked[m["id"]] in ("added", "referred") and m["how"] != linked[m["id"]]:
                conn.execute(text("UPDATE proj.project_models SET how = :h WHERE project_id = :p AND model_guid = CAST(:m AS uuid)"),
                             {"h": m["how"], "p": p["id"], "m": m["id"]})
            continue
        mm, cp = pj.link_model(conn, p, user, m)
        keep.add(str(mm["id"]))
        if m.get("home"):
            home = str(mm["id"])
        if cp:
            copies.append(cp)
        if m.get("how") in ("derived", "created"):
            made.append(mm)
    for g in set(linked) - keep:
        conn.execute(text("DELETE FROM proj.project_models WHERE project_id = :p AND model_guid = CAST(:m AS uuid)"), {"p": p["id"], "m": g})
    members = {(r["username"], r["role"]) for r in _rows(conn, "SELECT username, role FROM proj.members WHERE project_id = :p", p=p["id"])}
    pj.model_roles(conn, made, members, user)
    if home is None and p.get("home_model") and str(p["home_model"]) in keep:
        home = str(p["home_model"])
    conn.execute(text("UPDATE proj.projects SET home_model = CAST(:h AS uuid) WHERE id = :p"), {"h": home, "p": p["id"]})
    p = pj.project_row(conn, p["guid"])
    # viewpoints
    own = {r["viewpoint"] for r in _rows(conn, "SELECT viewpoint FROM proj.project_viewpoints WHERE project_id = :p AND own", p=p["id"])}
    wanted = set(d.get("viewpoints") or []) | (own - set(d.get("removed_viewpoints") or []))
    conn.execute(text("DELETE FROM proj.project_viewpoints WHERE project_id = :p AND NOT (viewpoint = ANY (CAST(:v AS text[])))"),
                 {"p": p["id"], "v": sorted(wanted)})
    for v in wanted - own:
        conn.execute(text("INSERT INTO proj.project_viewpoints (project_id, viewpoint) VALUES (:p, :v) ON CONFLICT DO NOTHING"),
                     {"p": p["id"], "v": v})
    # principles: the library ones chosen; own ones added; removed ones (by id) go (inherited ones stay)
    libs_wanted = {int(x) for x in d.get("principles") or [] if str(x).isdigit()}
    have = {r["library_id"] for r in _rows(conn, "SELECT library_id FROM proj.principles WHERE project_id = :p AND library_id IS NOT NULL AND inherited_from IS NULL", p=p["id"])}
    conn.execute(text("""DELETE FROM proj.principles WHERE project_id = :p AND inherited_from IS NULL AND
                         ((library_id IS NOT NULL AND NOT (library_id = ANY (CAST(:l AS bigint[])))) OR id = ANY (CAST(:r AS bigint[])))"""),
                 {"p": p["id"], "l": sorted(libs_wanted), "r": [int(x) for x in d.get("removed_principles") or []]})
    pj._principles(conn, p, user, {"principles": [{"library_id": x} for x in libs_wanted - have] +
                                   [x for x in d.get("own_principles") or [] if not x.get("id")]}, None)
    # steps
    removed = {int(k): (v or "").strip() for k, v in (d.get("removed") or {}).items()}
    if any(not v for v in removed.values()):
        raise EditError("Say why each removed step is removed: it stays in the project, crossed out, with the reason.")
    conn.execute(text("""UPDATE proj.steps SET removed = (library_id = ANY (CAST(:ids AS bigint[]))),
                                removed_reason = coalesce(CAST(:why AS jsonb) ->> library_id::text, '')
                          WHERE project_id = :p AND cycle = :c AND library_id IS NOT NULL"""),
                 {"p": p["id"], "c": p["cycle"], "ids": list(removed), "why": json.dumps({str(k): v for k, v in removed.items()})})
    own_ids = [int(s["id"]) for s in d.get("own_steps") or [] if s.get("id")]
    # the project's own steps the wizard showed and that were removed in it go (their sub steps with them); steps added
    # meanwhile (on the Steps tab, or by an assistant) stay; sub steps themselves are not in the list
    seen = d.get("own_steps_seen")
    gone = [int(x) for x in seen if int(x) not in own_ids] if seen is not None else None
    conn.execute(text(f"""DELETE FROM proj.steps WHERE project_id = :p AND cycle = :c AND library_id IS NULL AND parent_step_id IS NULL
                           AND {"id = ANY (CAST(:g AS bigint[]))" if gone is not None else "NOT (id = ANY (CAST(:k AS bigint[])))"}"""),
                 {"p": p["id"], "c": p["cycle"], "k": own_ids, "g": gone or []})
    for s in d.get("own_steps") or []:
        if s.get("id"):
            conn.execute(text("UPDATE proj.steps SET name = :n WHERE id = :i AND project_id = :p"),
                         {"n": (s.get("name") or "").strip() or "Step", "i": int(s["id"]), "p": p["id"]})
    pj._steps_own(conn, p, [s for s in d.get("own_steps") or [] if not s.get("id")])
    # deliverables and artifacts
    picks = {k: bool(v) for k, v in (d.get("picks") or {}).items()}
    for lib_id, on in picks.items():
        conn.execute(text("UPDATE proj.items SET chosen = :c WHERE project_id = :p AND cycle = :cy AND library_id = :l"),
                     {"c": on, "p": p["id"], "cy": p["cycle"], "l": lib_id})
    for lib_id, kind in (d.get("kinds") or {}).items():
        if kind in ("Deliverable", "Artifact"):
            conn.execute(text("UPDATE proj.items SET kind = :k WHERE project_id = :p AND cycle = :cy AND library_id = :l"),
                         {"k": kind, "p": p["id"], "cy": p["cycle"], "l": lib_id})
    pj.item_templates(conn, p, d)
    for it in d.get("own_items") or []:
        if it.get("id"):
            kind = it.get("kind") if it.get("kind") in ("Deliverable", "Artifact") else "Deliverable"
            fx = pj.own_item_fields(it)
            conn.execute(text("""UPDATE proj.items SET name = :n, kind = :k, chosen = :c, placeholder = :ph, note = :no,
                                        templates = CAST(:tp AS bigint[]), content_area = :ca
                                  WHERE project_id = :p AND guid = CAST(:i AS uuid) AND library_id IS NULL"""),
                         {"n": (it.get("name") or "").strip() or "Item", "k": kind, "c": not it.get("removed"),
                          "ph": fx["placeholder"], "no": fx["note"], "tp": fx["templates"], "ca": fx["content_area"],
                          "p": p["id"], "i": it["id"]})
    pj._items_own(conn, p, [x for x in d.get("own_items") or [] if not x.get("id")])
    if d.get("charter"):          # the wizard's Charter step: the sections changed there (a draft again until approved)
        from . import governance as gov
        gov.save_charter(conn, p["guid"], user, {"sections": d["charter"]})
    # template libraries: new ones added at the end, dropped ones unlinked (documents copied from them stay)
    if d.get("libraries") is not None:
        libs = pj._chosen_libraries(conn, user, d["libraries"])
        conn.execute(text("DELETE FROM proj.project_libraries WHERE project_id = :p"), {"p": p["id"]})
        for n, lib in enumerate(libs):
            conn.execute(text("INSERT INTO proj.project_libraries (project_id, library_id, sort_order) VALUES (:p, :l, :s)"),
                         {"p": p["id"], "l": lib["id"], "s": n})
    if d.get("members") is not None:
        # the wizard lists the others (it shows the editor as "you"): the editor keeps the Project Admin role they have,
        # and gets it when nobody else is Project Admin (a project keeps one)
        me = user.username.lower()
        was_admin = bool(_one(conn, """SELECT 1 AS x FROM proj.members WHERE project_id = :p AND lower(username) = :u
                                        AND role = 'project-admin'""", p=p["id"], u=me))
        listed = any((m.get("username") or "").strip().lower() == me and m.get("role") == "project-admin" for m in d["members"])
        mem = [{"username": user.username, "role": "project-admin"}] if not listed and (
            was_admin or not any(m.get("role") == "project-admin" for m in d["members"])) else []
        pj.set_people(conn, p["guid"], user, mem + list(d["members"]), d.get("signoff") or {})
    pj.reader_roles(conn, p, user)
    note = write_goals(conn, pj.project_row(conn, p["guid"]), user, d.get("goals")) if "goals" in d else ""
    conn.execute(text("""UPDATE proj.projects SET repo_state = CASE WHEN repo_state = 'building' THEN repo_state ELSE 'pending' END,
                                repo_again = (repo_state = 'building'), repo_tries = 0, modified_at = now() WHERE id = :p"""), {"p": p["id"]})
    return {"project": {"id": str(p["guid"]), "name": name}, "copies": copies, "note": note}


# ---------------------------------------------------------------- the project's own files (contracts and the like)
def _cabinet(conn, p: dict, folder: str) -> int:
    from . import mayan
    if not p.get("mayan_cabinet_id"):     # the repository is still being built: its cabinet is made now (as the build does)
        pc = mayan.cabinet(p["name"], mayan.cabinet("EA Explorer projects"))
        conn.execute(text("UPDATE proj.projects SET mayan_cabinet_id = :c WHERE id = :i"), {"c": pc, "i": p["id"]})
        p = {**p, "mayan_cabinet_id": pc}
    row = _one(conn, "SELECT mayan_cabinet_id FROM proj.folders WHERE project_id = :p AND path = :f", p=p["id"], f=folder)
    if row and row["mayan_cabinet_id"]:
        return row["mayan_cabinet_id"]
    cid = mayan.cabinet_path(folder, p["mayan_cabinet_id"])
    conn.execute(text("""INSERT INTO proj.folders (project_id, path, mayan_cabinet_id) VALUES (:p, :f, :c)
                         ON CONFLICT (project_id, path) DO UPDATE SET mayan_cabinet_id = EXCLUDED.mayan_cabinet_id"""),
                 {"p": p["id"], "f": folder, "c": cid})
    return cid


def _store(conn, p: dict, user, folder: str, file_name: str, content: bytes, item_id: int | None = None,
           origin: str = "upload", kind: str | None = None) -> dict:
    from . import mayan
    if not file_name or not content:
        raise EditError("Choose a file to upload.")
    cid = _cabinet(conn, p, folder)
    doc = mayan.upload(file_name, content, mimetypes.guess_type(file_name)[0] or "application/octet-stream")
    mayan.add_to_cabinet(cid, doc["id"])
    row = _one(conn, """INSERT INTO proj.documents (project_id, item_id, folder, mayan_document_id, file_name, origin, kind,
                                                    created_by, modified_by)
                        VALUES (:p, :i, :f, :m, :n, :o, :k, :u, :u) RETURNING id, guid::text AS guid""",
               p=p["id"], i=item_id, f=folder, m=doc["id"], n=file_name, o=origin, k=kind, u=user.username)
    pj._event(conn, row["id"], user, "uploaded", 1, file_name)
    return {"id": row["guid"], "mayan_id": doc["id"], "message": f"{file_name} is in {folder.split('/')[-1]}."}


def upload_project_file(conn, project: Any, user, file_name: str, content: bytes) -> dict:
    p = pj.project_row(conn, project)
    need(conn, p, user, "contribute")
    return _store(conn, p, user, PROJECT_FILES, file_name, content, origin="project-file", kind="Artifact")


def set_document_kind(conn, project: Any, user, doc: str, kind: str) -> dict:
    """A document is an artifact or a deliverable (a deliverable is signed off, D276); set during setup or later."""
    p = pj.project_row(conn, project)
    need(conn, p, user, "contribute")
    if kind not in ("Deliverable", "Artifact", "None"):
        raise EditError("A document is a Deliverable, an Artifact, or neither (None).")
    d = pj._doc(conn, p, doc)
    conn.execute(text("UPDATE proj.documents SET kind = :k WHERE id = :i"), {"k": kind, "i": d["id"]})
    name = d.get("title") or d["file_name"]
    if kind == "None":         # neither needs no approval: a request open for it ends (review, 8 Nov 2026)
        r = _one(conn, "UPDATE proj.signoff_requests SET state = 'withdrawn', closed_at = now() WHERE document_id = :d AND state = 'open' RETURNING id",
                 d=d["id"])
        if r:
            conn.execute(text("UPDATE proj.documents SET state = 'Draft' WHERE id = :i AND state = 'In review'"), {"i": d["id"]})
            pj._event(conn, d["id"], user, "sign-off withdrawn: it needs no approval now")
    pj._event(conn, d["id"], user, f"marked {kind.lower() if kind != 'None' else 'neither deliverable nor artifact'}", d["versions"])
    what = "neither a deliverable nor an artifact" if kind == "None" else f"a{'' if kind == 'Deliverable' else 'n'} {kind.lower()}"
    return {"id": doc, "kind": kind, "message": f"{name} is now {what}."}


# ---------------------------------------------------------------- sign-off of deliverables (D276)
def _kind_of(conn, d: dict) -> str:
    if d.get("kind"):
        return d["kind"]
    it = _one(conn, "SELECT kind FROM proj.items WHERE id = :i", i=d["item_id"]) if d.get("item_id") else None
    return it["kind"] if it else "Artifact"


def signers_for(conn, p: dict, d: dict) -> list[str]:
    phase = ""
    if d.get("item_id"):
        phase = (_one(conn, "SELECT phase FROM proj.items WHERE id = :i", i=d["item_id"]) or {}).get("phase", "")
    rows = _rows(conn, "SELECT username FROM proj.signoff WHERE project_id = :p AND phase = :ph ORDER BY username", p=p["id"], ph=phase)
    if not rows:
        rows = _rows(conn, "SELECT username FROM proj.signoff WHERE project_id = :p AND phase = '' ORDER BY username", p=p["id"])
    return [r["username"] for r in rows]


def _request(conn, p: dict, request: str) -> dict:
    r = _one(conn, """SELECT r.*, d.guid::text AS doc_guid, d.file_name, d.id AS doc_id FROM proj.signoff_requests r
                        JOIN proj.documents d ON d.id = r.document_id
                       WHERE r.guid = CAST(:r AS uuid) AND d.project_id = :p
                         FOR UPDATE OF r""", r=request, p=p["id"])
    if not r:          # locked: two decisions at the same moment are counted one after the other (review, 7 Nov 2026)
        raise EditError("No such sign-off request in this project.", 404)
    return r


def raise_signoff(conn, project: Any, user, doc: str, note: str = "") -> dict:
    """Asks the signers of the document's phase (or of the whole project) to sign off its current version; each is told
    in the application (email comes in a later phase)."""
    from . import notify
    p = pj.project_row(conn, project)
    need(conn, p, user, "contribute")
    d = pj._doc(conn, p, doc)
    if not d["mayan_document_id"] and not (d.get("link_url") or d.get("link_project")):
        raise EditError(f"{d.get('title') or d['file_name']} has no file yet: add its file before asking for sign-off.", 409)
    if d.get("kind") == "None":
        raise EditError(f"{d.get('title') or d['file_name']} is neither a deliverable nor an artifact: it needs no approval.", 409)
    conn.execute(text("SELECT 1 FROM proj.documents WHERE id = :i FOR UPDATE"), {"i": d["id"]})   # one request at a time
    if d.get("deleted_at") or d.get("archived_at"):
        raise EditError(f"{pj._dname(d)} is {'deleted' if d.get('deleted_at') else 'archived'}: restore it first.", 409)
    if d["checked_out_by"]:
        raise EditError(f"{pj._dname(d)} is checked out by {d['checked_out_by']}: check it in first.", 409)
    if _one(conn, "SELECT 1 AS x FROM proj.signoff_requests WHERE document_id = :d AND state = 'open'", d=d["id"]):
        raise EditError("This document is already waiting for sign-off.", 409)
    signers = signers_for(conn, p, d)
    if not signers:
        raise EditError("Nobody signs off in this project yet: set who signs off (Edit › People and sign-off).", 409)
    q = quorum_of(p, len(signers))
    r = _one(conn, """INSERT INTO proj.signoff_requests (document_id, version, signers, note, raised_by, quorum)
                      VALUES (:d, :v, CAST(:s AS text[]), :n, :u, :q) RETURNING guid::text AS guid""",
             d=d["id"], v=d["versions"], s=signers, n=(note or "").strip(), u=user.username, q=q)
    conn.execute(text("UPDATE proj.documents SET state = 'In review' WHERE id = :i"), {"i": d["id"]})
    pj._event(conn, d["id"], user, "raised for sign-off", d["versions"], note or "")
    notify.create(pj.core(conn), kind="project.signoff_asked", category="request", actor=user.username,
                  title=f"Sign off {d['file_name']} (v{d['versions']})",
                  body=f"Project {p['name']}: {user.username} asks you to approve or reject it.{(' ' + note) if note else ''}",
                  link=f"#/projects/{p['guid']}/signoff", recipients=signers, include_actor=True)
    return {"id": r["guid"], "message": f"Asked {', '.join(signers)} to approve {d['file_name']} v{d['versions']}: approved when {q} of "
            f"{len(signers)} approve; any rejection rejects it."}


def quorum_of(p: dict, people: int) -> int:
    """How many of the sign-off people must approve (D290): the project's quorum, or a majority; never more than there are."""
    q = p.get("signoff_quorum") or (people // 2 + 1)
    return max(1, min(int(q), people))


def settle_state(decisions: list[str], quorum: int) -> str:
    """Any rejection rejects it; approved once the quorum approves; otherwise still open."""
    if "rejected" in decisions:
        return "rejected"
    return "approved" if decisions.count("approved") >= quorum else "open"


def _settle(conn, p: dict, r: dict, user) -> str:
    from . import notify
    dec = {x["signer"]: x["decision"] for x in _rows(conn, "SELECT signer, decision FROM proj.signoff_decisions WHERE request_id = :r", r=r["id"])}
    q = r.get("quorum") or len(r["signers"])          # requests raised before 0.14.6: everyone
    state = settle_state(list(dec.values()), q)
    if state == "open":
        return f"{list(dec.values()).count('approved')} of the {q} approvals needed."
    conn.execute(text("UPDATE proj.signoff_requests SET state = :s, closed_at = now() WHERE id = :r"), {"s": state, "r": r["id"]})
    conn.execute(text("""UPDATE proj.documents SET state = :st, signed_version = CASE WHEN :s = 'approved' THEN :v ELSE signed_version END
                          WHERE id = :d"""), {"st": "Approved" if state == "approved" else "Rejected", "s": state, "v": r["version"], "d": r["doc_id"]})
    pj._event(conn, r["doc_id"], user, f"sign-off {state}", r["version"])
    notify.create(pj.core(conn), kind=f"project.signoff_{state}", category="request", actor=user.username,
                  title=f"{r['file_name']} v{r['version']} is {state}",
                  body=f"Project {p['name']}: the sign-off you asked for is {state}.", link=f"#/projects/{p['guid']}/signoff",
                  recipients=[r["raised_by"]], include_actor=True)
    return f"Sign-off {state}."


def decide_signoff(conn, project: Any, user, request: str, decision: str, comment: str = "") -> dict:
    """A signer approves or rejects, with a comment (needed to reject). The person who raised it, if a signer too,
    approves their own part as self approved."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    if p.get("status") in FROZEN:
        raise EditError(f"{p['name']} is {p['status']}: it is read only.", 409)
    r = _request(conn, p, request)
    if r["state"] != "open":
        raise EditError(f"This sign-off is {r['state']}.", 409)
    me = user.username.lower()
    if me not in [s.lower() for s in r["signers"]]:
        raise EditError("You are not one of its signers.", 403)
    if decision not in ("approved", "rejected"):
        raise EditError("Approve or reject.")
    if decision == "rejected" and not (comment or "").strip():
        raise EditError("Say why it is rejected.")
    if _one(conn, "SELECT 1 AS x FROM proj.signoff_decisions WHERE request_id = :r AND lower(signer) = :u", r=r["id"], u=me):
        raise EditError("You have decided already.", 409)
    how = "self" if me == r["raised_by"].lower() else "in-app"
    conn.execute(text("""INSERT INTO proj.signoff_decisions (request_id, signer, decision, how, comment, recorded_by)
                         VALUES (:r, :s, :d, :h, :c, :s)"""), {"r": r["id"], "s": me, "d": decision, "h": how, "c": (comment or "").strip()})
    return {"id": request, "message": f"{'Approved' if decision == 'approved' else 'Rejected'}{' (self approved)' if how == 'self' else ''}. "
            + _settle(conn, p, r, user)}


def record_signoff(conn, project: Any, user, request: str, signer: str, decision: str, comment: str,
                   evidence_name: str, evidence: bytes) -> dict:
    """Records a signer's decision given outside the application (an email, a signed page): by the person who raised it,
    the Project Admin or the Lead Architect, with the evidence uploaded (kept in 00_Project/Sign-off evidence)."""
    p = pj.project_row(conn, project)
    roles = need(conn, p, user, "contribute")
    r = _request(conn, p, request)
    if r["state"] != "open":
        raise EditError(f"This sign-off is {r['state']}.", 409)
    if user.username.lower() != r["raised_by"].lower() and not roles & (pj.ADMINS | {"super-admin"}):
        raise EditError("Recording a decision needs the person who raised it, the Project Admin or the Lead Architect.", 403)
    who = (signer or "").strip().lower()
    if who not in [s.lower() for s in r["signers"]]:
        raise EditError(f"{signer} is not one of its signers.")
    if decision not in ("approved", "rejected"):
        raise EditError("Approve or reject.")
    if not evidence:
        raise EditError("Upload the evidence: the email or the signed document.")
    if _one(conn, "SELECT 1 AS x FROM proj.signoff_decisions WHERE request_id = :r AND lower(signer) = :u", r=r["id"], u=who):
        raise EditError(f"{signer} has decided already.", 409)
    stored = _store(conn, p, user, EVIDENCE, f"{r['file_name']} v{r['version']} - {who} - {evidence_name}", evidence,
                    origin="evidence", kind="Artifact")
    conn.execute(text("""INSERT INTO proj.signoff_decisions (request_id, signer, decision, how, comment, recorded_by, evidence_name,
                                                              evidence_mayan_id)
                         VALUES (:r, :s, :d, 'recorded', :c, :b, :n, :m)"""),
                 {"r": r["id"], "s": who, "d": decision, "c": (comment or "").strip(), "b": user.username, "n": evidence_name,
                  "m": stored["mayan_id"]})
    return {"id": request, "message": f"{who}'s decision recorded with the evidence. " + _settle(conn, p, r, user)}


def withdraw_request(conn, doc_id: int, user, why: str) -> None:
    """Ends an open request for approval without touching an earlier approval (archive, delete, accept: D290)."""
    r = _one(conn, "UPDATE proj.signoff_requests SET state = 'withdrawn', closed_at = now() WHERE document_id = :d AND state = 'open' RETURNING id",
             d=doc_id)
    if r:
        pj._event(conn, doc_id, user, f"approval request withdrawn: {why}")
        conn.execute(text("UPDATE proj.documents SET state = 'Draft' WHERE id = :d AND state = 'In review'"), {"d": doc_id})


def withdraw_open(conn, doc_id: int, user) -> None:
    """A new version checked in ends an open sign-off of the old one (it is raised again for the new version)."""
    r = _one(conn, "UPDATE proj.signoff_requests SET state = 'withdrawn', closed_at = now() WHERE document_id = :d AND state = 'open' RETURNING id",
             d=doc_id)
    if r:
        pj._event(conn, doc_id, user, "sign-off withdrawn: a new version")
    conn.execute(text("UPDATE proj.documents SET state = 'Draft' WHERE id = :d AND state IN ('In review', 'Approved', 'Rejected')"), {"d": doc_id})


def signoffs(conn, p: dict, user) -> list[dict]:
    rows = _rows(conn, """SELECT r.guid::text AS id, d.guid::text AS document, d.file_name, r.version, r.signers, r.note, r.state, r.quorum,
                                 r.raised_by, r.raised_at, r.closed_at, i.phase, i.name AS item
                            FROM proj.signoff_requests r JOIN proj.documents d ON d.id = r.document_id
                            LEFT JOIN proj.items i ON i.id = d.item_id
                           WHERE d.project_id = :p AND d.deleted_at IS NULL ORDER BY (r.state = 'open') DESC, r.raised_at DESC""", p=p["id"])
    dec = {}
    for x in _rows(conn, """SELECT r.guid::text AS rid, x.signer, x.decision, x.how, x.comment, x.recorded_by, x.evidence_name, x.at
                              FROM proj.signoff_decisions x JOIN proj.signoff_requests r ON r.id = x.request_id
                              JOIN proj.documents d ON d.id = r.document_id WHERE d.project_id = :p ORDER BY x.at""", p=p["id"]):
        dec.setdefault(x["rid"], []).append(x)
    me = user.username.lower()
    for r in rows:
        r["decisions"] = dec.get(r["id"], [])
        done = {x["signer"].lower() for x in r["decisions"]}
        r["mine"] = r["state"] == "open" and me in [s.lower() for s in r["signers"]] and me not in done
        r["waiting_for"] = [s for s in r["signers"] if s.lower() not in done] if r["state"] == "open" else []
    return rows


# ---------------------------------------------------------------- finishing: freeze, or merge into another project (D277)
def finish_check(conn, project: Any, user, d: dict) -> dict:
    """The quick checks, before the background task: an admin, an active project, a target the person contributes to."""
    p = pj.project_row(conn, project)
    need(conn, p, user, "admin")
    mode = d.get("mode")
    if mode not in ("freeze", "merge"):
        raise EditError("Finish by freezing the project, or by merging it into another project.")
    if mode == "merge":
        if not d.get("target"):
            raise EditError("Choose the project it merges into.")
        t = pj.project_row(conn, d["target"])
        if t["id"] == p["id"]:
            raise EditError("A project cannot merge into itself.")
        need(conn, t, user, "contribute")
    for g, how in (d.get("models") or {}).items():
        if how not in ("keep", "merge", "merge-freeze", "freeze"):
            raise EditError("Each model is kept as it is, merged into its parent model, merged and frozen, or frozen.")
        if how in ("merge", "merge-freeze"):
            m = _one(pj.core(conn), "SELECT name, parent_model_id FROM core.models WHERE guid = CAST(:g AS uuid)", g=g)
            if not m:
                raise EditError("A model of the project is gone.", 404)
            if not m["parent_model_id"]:
                raise EditError(f"{m['name']} has no parent model to merge into: keep it as it is.")
    return p


def finish(conn, project: Any, user, d: dict) -> dict:
    """Done in the background (task project.finished): documents copied into the target's repository (same phase and
    item where the target has it, else a folder 'From <project>' in that phase), models merged into their parent
    model where asked, then the project frozen (read only). A failure puts its status back and takes back the copies."""
    from . import mayan
    p = finish_check(conn, project, user, d)
    from .db import get_projects_engine
    with get_projects_engine().begin() as c1:      # seen by everyone at once: nobody changes it while it finishes
        c1.execute(text("UPDATE proj.projects SET status = 'finishing' WHERE id = :p"), {"p": p["id"]})
    uploaded: list[int] = []
    try:
        return _finish(conn, p, user, d, uploaded)
    except Exception:
        with get_projects_engine().begin() as c1:  # back as it was: its status, and no copies left in Documents
            c1.execute(text("UPDATE proj.projects SET status = :s WHERE id = :p"), {"s": p["status"], "p": p["id"]})
        for mid in uploaded:
            try:
                mayan.trash(mid)
            except Exception:  # noqa: BLE001
                pass
        raise


def _finish(conn, p: dict, user, d: dict, uploaded: list[int]) -> dict:
    from . import mayan
    from . import merge as mg
    from . import tasks as tk
    copied = 0
    target = None
    if d["mode"] == "merge":
        target = pj.project_row(conn, d["target"])
        if not target.get("mayan_cabinet_id"):
            raise EditError(f"{target['name']}'s repository is not built yet: try again when it is.", 409)
        docs = _rows(conn, """SELECT d.*, i.library_id, i.phase, i.name AS item_name FROM proj.documents d
                                LEFT JOIN proj.items i ON i.id = d.item_id
                               WHERE d.project_id = :p AND d.mayan_document_id IS NOT NULL
                                 AND d.archived_at IS NULL AND d.deleted_at IS NULL ORDER BY d.id""", p=p["id"])
        phases = {r["code"]: r["workspace"] for r in _rows(conn, "SELECT code, workspace FROM proj.lib_phases")}
        for n, doc in enumerate(docs, 1):
            tk.progress(int(70 * n / max(len(docs), 1)), f"Copying documents: {n} of {len(docs)}")
            content, _ctype, _name = mayan.download(doc["mayan_document_id"])
            it = None
            if doc.get("library_id"):
                it = _one(conn, """SELECT * FROM proj.items WHERE project_id = :t AND cycle = :c AND library_id = :l""",
                          t=target["id"], c=target["cycle"], l=doc["library_id"])
            if it and it.get("mayan_cabinet_id"):
                if not it["chosen"]:
                    conn.execute(text("UPDATE proj.items SET chosen = true WHERE id = :i"), {"i": it["id"]})
                uploaded.append(_store_in(conn, target, user, it, doc, content))
            else:
                ws = phases.get(doc.get("phase") or "", "00_Project")
                uploaded.append(_store(conn, target, user, f"{ws}/From {p['name']}"[:200], doc["file_name"], content, origin="merged",
                                       kind=_kind_of(conn, doc))["mayan_id"])
            copied += 1
        # its links come too (D296): into the same document class there when it has one, else its folder
        for lk in _rows(conn, """SELECT d.*, i.library_id FROM proj.documents d LEFT JOIN proj.items i ON i.id = d.item_id
                                  WHERE d.project_id = :p AND (d.link_url <> '' OR d.link_project IS NOT NULL)
                                    AND d.archived_at IS NULL AND d.deleted_at IS NULL""", p=p["id"]):
            it = _one(conn, "SELECT id, folder FROM proj.items WHERE project_id = :t AND cycle = :c AND library_id = :l",
                      t=target["id"], c=target["cycle"], l=lk["library_id"]) if lk.get("library_id") else None
            conn.execute(text("""INSERT INTO proj.documents (project_id, item_id, folder, file_name, origin, kind, state, link_url, link_project,
                                                             link_document, link_item, description, tags, created_by, modified_by)
                                 VALUES (:t, :i, :f, :n, 'link', :k, :s, :url, :lp, :ld, :li, :de, :tags, :u, :u)"""),
                         {"t": target["id"], "i": it["id"] if it else None, "f": it["folder"] if it else lk["folder"], "n": lk["file_name"],
                          "k": lk["kind"], "s": lk["state"] if lk["state"] in ("Approved", "Draft") else "Draft", "url": lk["link_url"],
                          "lp": lk["link_project"], "ld": lk["link_document"], "li": lk["link_item"], "de": lk["description"],
                          "tags": list(lk["tags"] or []), "u": user.username})
            copied += 1
    merged, frozen, notes = [], [], []
    from . import model_wizards as mw
    for g, how in (d.get("models") or {}).items():
        if how not in ("merge", "merge-freeze", "freeze"):
            continue
        c = pj.core(conn)
        m = _one(c, """SELECT m.name, pm.guid::text AS parent FROM core.models m LEFT JOIN core.models pm ON pm.id = m.parent_model_id
                        WHERE m.guid = CAST(:g AS uuid)""", g=g)
        if how in ("merge", "merge-freeze") and m["parent"]:
            tk.progress(75, f"Merging {m['name']} into its parent model (tagged first)")
            mw.tag_first(c, m["parent"], user, f"merging {m['name']}")   # D283: a wizard tags the model it changes first
            plan = mg.analyse_model(c, m["parent"], g, user, True)
            mg.apply(c, m["parent"], plan["id"], user, None, "theirs", True)
            merged.append(m["name"])
        if how in ("merge-freeze", "freeze"):
            try:
                mw.freeze(c, g, user, f"The project {p['name']} finished")
                frozen.append(m["name"])
            except EditError as exc:     # not its Model Admin, or frozen already: the project still finishes
                notes.append(f"{m['name']} not frozen: {exc}")
    state = "merged" if target else "frozen"
    note = (f"Merged into {target['name']}: {copied} documents copied" if target else "Frozen") + \
           (f"; models merged into their parents: {', '.join(merged)}" if merged else "") + \
           (f"; models frozen: {', '.join(frozen)}" if frozen else "") + (f" ({'; '.join(notes)})" if notes else "") + "."
    conn.execute(text("""UPDATE proj.projects SET status = :s, finished_at = now(), finished_by = :u, finish_note = :n,
                                merged_into = :t WHERE id = :p"""),
                 {"s": state, "u": user.username, "n": (d.get("note") or note)[:2000], "t": target["id"] if target else None, "p": p["id"]})
    from . import notify
    people = [r["username"] for r in _rows(conn, "SELECT DISTINCT username FROM proj.members WHERE project_id = :p", p=p["id"])]
    notify.create(pj.core(conn), kind="project.finished", category="model", actor=user.username, title=f"{p['name']} is {state}",
                  body=note, link=f"#/projects/{p['guid']}", recipients=people)
    return {"project": {"id": str(p["guid"]), "name": p["name"], "status": state}, "copied": copied, "merged_models": merged,
            "note": note}


def _store_in(conn, target: dict, user, it: dict, doc: dict, content: bytes) -> int:
    from . import mayan
    name = doc["file_name"]
    up = mayan.upload(name, content, mimetypes.guess_type(name)[0] or "application/octet-stream")
    mayan.add_to_cabinet(it["mayan_cabinet_id"], up["id"])
    row = _one(conn, """INSERT INTO proj.documents (project_id, item_id, folder, mayan_document_id, file_name, origin, kind, state,
                                                    created_by, modified_by)
                        VALUES (:p, :i, :f, :m, :n, 'merged', :k, :s, :u, :u) RETURNING id""",
               p=target["id"], i=it["id"], f=it["folder"], m=up["id"], n=name, k=doc.get("kind"),
               s=doc["state"] if doc["state"] in ("Approved", "Draft") else "Draft", u=user.username)
    pj._event(conn, row["id"], user, "merged in", 1, f"from {doc.get('item_name') or doc['folder']}")
    return up["id"]


# ---------------------------------------------------------------- a project's own principles, at any time (owner, 8 Nov 2026)
def _principle_vals(d: dict) -> dict:
    name = (d.get("name") or "").strip()
    if not name:
        raise EditError("Give the principle a name.")
    return {"n": name[:200], "a": (d.get("area") or "").strip()[:80], "c": (d.get("code") or "").strip()[:20],
            "s": clean_html(d.get("statement")), "r": clean_html(d.get("rationale")), "i": clean_html(d.get("implications"))}


def add_principle(conn, project: Any, user, d: dict) -> dict:
    """A principle of the project's own, added on its Principles tab by anyone who contributes; the name is plain text,
    the statement, rationale and implications rich text; it goes under an area (Business, Data, Security...)."""
    p = pj.project_row(conn, project)
    need(conn, p, user, "contribute")
    v = _principle_vals(d)
    # in the Organisation base every principle binds the projects below it (phase 13.1, D304)
    r = _one(conn, """INSERT INTO proj.principles (project_id, code, name, statement, rationale, implications, area, created_by, mandatory,
                                                   sort_order)
                      VALUES (:p, :c, :n, :s, :r, :i, :a, :u, :m, (SELECT coalesce(max(sort_order), 0) + 1 FROM proj.principles
                                                                     WHERE project_id = :p)) RETURNING id""",
             **v, p=p["id"], u=user.username, m=bool(p.get("base_kind")))
    return {"id": r["id"], "message": f"Principle {v['n']} added{(' under ' + v['a']) if v['a'] else ''}."}


def _own_principle(conn, p: dict, pid: int) -> dict:
    r = _one(conn, "SELECT * FROM proj.principles WHERE project_id = :p AND id = :i", p=p["id"], i=pid)
    if not r:
        raise EditError("No such principle in this project.", 404)
    if r["inherited_from"]:
        raise EditError("This principle is inherited from the parent project: it is changed there.", 409)
    if r.get("mandatory") and r.get("origin_guid") and not p.get("base_kind"):
        raise EditError(f"{r['name']} comes from the project's base and is mandatory: it is not changed or removed here "
                        "(ask for a dispensation in the governance log).", 409)
    return r


def update_principle(conn, project: Any, user, pid: int, d: dict) -> dict:
    p = pj.project_row(conn, project)
    need(conn, p, user, "contribute")
    r = _own_principle(conn, p, pid)
    if r["library_id"] and any(k in d for k in ("name", "statement", "rationale", "implications")):
        raise EditError("A principle from the library keeps its words; only its area can be changed here.", 409)
    v = _principle_vals({**{k: r[k] for k in ("name", "area", "code", "statement", "rationale", "implications")}, **d})
    conn.execute(text("""UPDATE proj.principles SET code = :c, name = :n, statement = :s, rationale = :r, implications = :i, area = :a
                          WHERE id = :id"""), {**v, "id": r["id"]})
    return {"id": pid, "message": f"Principle {v['n']} saved."}


def delete_principle(conn, project: Any, user, pid: int) -> dict:
    p = pj.project_row(conn, project)
    need(conn, p, user, "contribute")
    r = _own_principle(conn, p, pid)
    conn.execute(text("DELETE FROM proj.principles WHERE id = :i"), {"i": r["id"]})
    return {"message": f"Principle {r['name']} taken out of the project."}


# ---------------------------------------------------------------- sign-off requests in the requests boxes (owner, 8 Nov 2026)
SIGNOFF_STATUS = {"open": ("open", "Waiting for sign-off"), "approved": ("done", "Approved"), "rejected": ("declined", "Rejected"),
                  "withdrawn": ("declined", "Withdrawn")}


def signoff_box(conn, username: str, box: str = "received", status: str = "active", q: str = "") -> list[dict]:
    """A person's sign-off requests, shown with their requests: sent (they raised it) or received (they are a signer and,
    while it is open, have not decided yet). Statuses as the requests' (open; done = approved; declined = rejected)."""
    me = username.lower()
    rows = _rows(conn, """SELECT r.guid::text AS id, r.state, r.version, r.signers, r.raised_by, r.raised_at, r.closed_at, r.note,
                                 d.file_name, p.guid::text AS project, p.name AS project_name,
                                 EXISTS (SELECT 1 FROM proj.signoff_decisions x WHERE x.request_id = r.id AND lower(x.signer) = :me) AS decided
                            FROM proj.signoff_requests r JOIN proj.documents d ON d.id = r.document_id
                            JOIN proj.projects p ON p.id = d.project_id
                           WHERE d.deleted_at IS NULL AND """ + ("lower(r.raised_by) = :me" if box == "sent" else
                                                                ":me = ANY (SELECT lower(s) FROM unnest(r.signers) s)")
                     + " ORDER BY coalesce(r.closed_at, r.raised_at) DESC LIMIT 300", me=me)
    out = []
    for r in rows:
        st, label = SIGNOFF_STATUS.get(r["state"], ("open", r["state"]))
        if box == "received" and st == "open" and r["decided"]:
            st, label = "in_progress", "You decided; waiting for the others"
        if status == "active" and st not in ("open", "in_progress") or status == "closed" and st not in ("done", "declined") \
                or status in ("open", "in_progress", "done", "declined") and st != status:
            continue
        subject = f"Sign off {r['file_name']} v{r['version']} ({r['project_name']})"
        if q and q.lower() not in subject.lower():
            continue
        out.append({"id": r["id"], "kind": "signoff", "number": None, "subject": subject, "sender": r["raised_by"],
                    "receiver": ", ".join(r["signers"] or []), "status": st, "status_label": label,
                    "updated_at": r["closed_at"] or r["raised_at"], "created_at": r["raised_at"], "comment_count": 0,
                    "link": f"#/projects/{r['project']}/signoff?request={r['id']}",
                    "mine_to_act": box == "received" and st == "open"})
    return out
