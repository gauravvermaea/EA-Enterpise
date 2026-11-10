"""Model roles in a project and project templates (build phase 13.0.3, D281, D282).

A model has a role in a project: current state, target state, transition state (numbered), scenario, reference (read
only) or working copy. A project template is a specialised wizard with the decisions already taken: which models, in
which roles and how each starts (an existing one, empty, a copy, a child kept linked), the purpose, scope, phases,
views, whether there are goals and which model they go into, and which wizard steps are left out. 14 are shipped
(eax/seed/project_templates.json, added once); they are data: a Super Admin changes them, adds one, retires one, or
saves a project as a new one. The wizard applies a template's decisions; the person can still change any of them in
the full wizard ("Both", owner, 7 Nov 2026). Gap analyses are made by people on the gap screen, not by the template.

Spec (jsonb):
    purpose, depth, domains[], phases[] (null: all) or items[] (library item ids), removed_steps {id: reason},
    views[], goals (bool), primary (a role or null), skip[] (wizard steps left out), finish (a hint),
    stakeholders[{name, category, power, interest, concerns, role_title}] (suggested, D294),
    slots[{role, label, help, starts[existing|empty|copy|child], default_start, min, many, how}]
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError

ROLES = {"current": "Current state", "target": "Target state", "transition": "Transition state", "scenario": "Scenario",
         "reference": "Reference", "working-copy": "Working copy"}
STARTS = ("existing", "empty", "copy", "child", "library")
STEPS = ("Goals and outcomes", "Sponsor", "Stakeholders", "Notes and files", "Reference", "Template libraries", "Views", "Principles", "Phase by phase")

_rows, _one = pj._rows, pj._one


def _out(r: dict) -> dict:
    spec = r["spec"] if isinstance(r["spec"], dict) else json.loads(r["spec"] or "{}")
    return {"code": r["code"], "name": r["name"], "icon": r["icon"], "description": r["description"], "spec": spec,
            "builtin": r["builtin"], "retired": r["retired"], "modified_by": r["modified_by"], "modified_at": r["modified_at"]}


def listing(conn, all_: bool = False) -> list[dict]:
    return [_out(r) for r in _rows(conn, f"""SELECT * FROM proj.project_templates {'' if all_ else 'WHERE NOT retired'}
                                              ORDER BY sort_order, name""")]


def get(conn, code: str) -> dict:
    r = _one(conn, "SELECT * FROM proj.project_templates WHERE code = :c", c=code)
    if not r:
        raise EditError(f"No project template {code}.", 404)
    return _out(r)


def clean_spec(spec: dict) -> dict:
    """A template's decisions, checked."""
    s = dict(spec or {})
    slots = []
    for x in s.get("slots") or []:
        role = x.get("role")
        if role not in ROLES:
            raise EditError(f"Unknown model role {role}: one of {', '.join(ROLES)}.")
        starts = [v for v in x.get("starts") or [] if v in STARTS] or ["existing"]
        slots.append({"role": role, "label": (x.get("label") or ROLES[role]).strip(), "help": (x.get("help") or "").strip(),
                      "starts": starts, "default_start": x.get("default_start") if x.get("default_start") in starts else starts[0],
                      "min": max(0, int(x.get("min") or 0)), "many": bool(x.get("many")),
                      "how": "referred" if x.get("how") == "referred" or role == "reference" else "added"})
    s["slots"] = slots
    if s.get("primary") and s["primary"] not in ROLES:
        raise EditError(f"The goals go into a model role: one of {', '.join(ROLES)}, or none.")
    s["skip"] = [x for x in s.get("skip") or [] if x in STEPS]
    s["goals"] = bool(s.get("goals", True))
    from . import references as rf
    from . import stakeholders as sh
    s["stakeholders"] = sh.suggestions(s)          # the suggested stakeholders (D294)
    s["reference"] = rf.template_links(s)          # reference links offered to its projects (D296)
    return s


def _need(user) -> None:
    if not pj._super_or_library(user):
        raise EditError("Project templates are kept by Super Admins (and Library Admins).", 403)


def save(conn, user, code: str | None, data: dict) -> dict:
    """Changes a template (code given) or adds one."""
    _need(user)
    name = (data.get("name") or "").strip()
    if not name:
        raise EditError("Give the template a name.")
    spec = clean_spec(data.get("spec") or {})
    if code:
        cur = get(conn, code)
        conn.execute(text("""UPDATE proj.project_templates SET name = :n, icon = :i, description = :d, spec = CAST(:s AS jsonb),
                                    retired = :r, modified_by = :u, modified_at = now() WHERE code = :c"""),
                     {"n": name, "i": data.get("icon", cur["icon"]) or "", "d": data.get("description", cur["description"]) or "",
                      "s": json.dumps(spec), "r": bool(data.get("retired", cur["retired"])), "u": user.username, "c": code})
        return get(conn, code)
    new = re.sub(r"[^a-z0-9]+", "-", (data.get("code") or name).lower()).strip("-")[:60] or "template"
    if _one(conn, "SELECT 1 AS x FROM proj.project_templates WHERE code = :c", c=new):
        raise EditError(f"There is already a project template {new}.", 409)
    conn.execute(text("""INSERT INTO proj.project_templates (code, name, icon, description, spec, created_by, modified_by)
                         VALUES (:c, :n, :i, :d, CAST(:s AS jsonb), :u, :u)"""),
                 {"c": new, "n": name, "i": data.get("icon") or "", "d": data.get("description") or "", "s": json.dumps(spec), "u": user.username})
    return get(conn, new)


def from_project(conn, user, project: Any, data: dict) -> dict:
    """Saves a project's decisions as a new template: its models by role and how each started, purpose, scope, the
    deliverables in use, removed steps, views, goals and the primary model's role (not the models themselves)."""
    _need(user)
    p = pj.project_row(conn, project)
    models = _rows(conn, "SELECT how, role, model_guid::text AS g FROM proj.project_models WHERE project_id = :p ORDER BY role_seq NULLS FIRST",
                   p=p["id"])
    by_role: dict[str, list[dict]] = {}
    for m in models:
        by_role.setdefault(m["role"] or ("reference" if m["how"] == "referred" else "current"), []).append(m)
    start = {"added": "existing", "referred": "existing", "derived": "child", "created": "copy"}
    slots = [{"role": r, "label": ROLES[r], "help": "", "starts": sorted({start[m["how"]] for m in ms}) + (["empty"] if any(m["how"] == "created" for m in ms) else []),
              "default_start": start[ms[0]["how"]], "min": 1 if r != "reference" else 0, "many": len(ms) > 1 or r in ("transition", "scenario", "reference"),
              "how": "referred" if r == "reference" else "added"} for r, ms in by_role.items()]
    primary = next((m["role"] for m in models if p.get("home_model") and m["g"] == str(p["home_model"])), None)
    spec = {"purpose": p["purpose"], "depth": p["scope_depth"], "domains": list(p["scope_domains"] or []), "phases": None,
            "items": [r["library_id"] for r in _rows(conn, """SELECT library_id FROM proj.items WHERE project_id = :p AND cycle = :c
                                                                AND chosen AND library_id IS NOT NULL""", p=p["id"], c=p["cycle"])],
            "removed_steps": {str(r["library_id"]): r["removed_reason"] for r in _rows(conn, """SELECT library_id, removed_reason FROM proj.steps
                                                                WHERE project_id = :p AND removed AND library_id IS NOT NULL""", p=p["id"])},
            "views": [r["view"] for r in _rows(conn, "SELECT view FROM proj.project_views WHERE project_id = :p AND NOT own", p=p["id"])],
            "goals": bool(p.get("home_model")), "primary": primary, "skip": [], "slots": slots,
            "finish": "", "from_project": p["name"],
            "stakeholders": [{k: r[k] for k in ("name", "category", "power", "interest", "concerns", "role_title")}
                             for r in _rows(conn, "SELECT * FROM proj.stakeholders WHERE project_id = :p ORDER BY sort_order, id", p=p["id"])],
            "reference": [{"title": r["file_name"], "url": r["link_url"], "folder": r["folder"].split("/", 1)[1] if "/" in r["folder"] else "",
                           "description": r["description"]}
                          for r in _rows(conn, """SELECT * FROM proj.documents WHERE project_id = :p AND link_url <> '' AND folder LIKE '05_Reference_Library%'
                                                    AND deleted_at IS NULL""", p=p["id"])]}
    return save(conn, user, None, {"name": data.get("name") or f"{p['name']} (template)", "description": data.get("description") or
                                   f"Made from the project {p['name']}.", "icon": data.get("icon") or "📁", "spec": spec, "code": data.get("code")})
