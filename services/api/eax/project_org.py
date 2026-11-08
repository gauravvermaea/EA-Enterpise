"""A project's organisation (owner, 8 Nov 2026, D302): who works on the project and their role on it.

Flat, like a matrix organisation: no reporting lines. Each person is typed in (client staff, vendors, consultants)
and may be linked to an EA Explorer user. Everyone on the project sees it; contributors change it. The project's
members (people with a role on it in EA Explorer) can be added in one go.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError

_rows, _one = pj._rows, pj._one

ROLES = ("Sponsor", "Project Manager", "Lead Architect", "Enterprise Architect", "Business Architect", "Data Architect",
         "Application Architect", "Technology Architect", "Security Architect", "Solution Architect", "Business Analyst",
         "Subject Matter Expert", "Reviewer", "Architecture Board member")
MEMBER_ROLE = {"project-admin": "Project Admin", "lead-architect": "Lead Architect", "architect": "Architect",
               "model-admin": "Model Admin", "model-sub-admin": "Model Sub Admin", "stakeholder": "Stakeholder"}


def _may(conn, p: dict, user) -> bool:
    try:
        pj._need(conn, p, user, "contribute")
        return True
    except EditError:
        return False


def listing(conn, project: Any, user) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    rows = _rows(conn, """SELECT o.guid::text AS id, o.name, o.role, o.username, o.skills, s.guid::text AS stakeholder, o.modified_by,
                                 coalesce(o.modified_at, o.created_at) AS modified_at
                            FROM proj.org_people o LEFT JOIN proj.stakeholders s ON s.id = o.stakeholder_id
                           WHERE o.project_id = :p ORDER BY o.sort_order, o.id""", p=p["id"])
    sh = _rows(conn, """SELECT s.guid::text AS id, s.name, s.role_title FROM proj.stakeholders s
                         WHERE s.project_id = :p AND NOT EXISTS (SELECT 1 FROM proj.org_people o WHERE o.stakeholder_id = s.id)
                         ORDER BY s.sort_order, s.id""", p=p["id"])
    members = _rows(conn, "SELECT lower(username) AS username, role FROM proj.members WHERE project_id = :p ORDER BY username", p=p["id"])
    listed = {r["username"] for r in rows if r["username"]}
    return {"people": rows, "roles": list(ROLES), "members": sorted({m["username"] for m in members}),
            "not_listed": sorted({m["username"] for m in members} - listed), "stakeholders_not_listed": sh,
            "skills": sorted({k for r in _rows(conn, "SELECT DISTINCT unnest(skills) AS k FROM proj.org_people") for k in [r["k"]] if k},
                             key=str.lower),
            "may_edit": _may(conn, p, user)}


def _clean(conn, p: dict, d: dict) -> dict:
    name = " ".join((d.get("name") or "").split())[:200]
    if not name:
        raise EditError("Give the person's name.")
    username = (d.get("username") or "").strip().lower()[:120]
    skills = d.get("skills") or []
    if isinstance(skills, str):
        skills = skills.split(",")
    skills = list(dict.fromkeys(" ".join(str(k).split())[:60] for k in skills if str(k).strip()))[:30]    # skills as tags (D302)
    return {"name": name, "role": " ".join((d.get("role") or "").split())[:120], "username": username, "skills": skills}


def add(conn, project: Any, user, d: dict) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    v = _clean(conn, p, d)
    n = conn.execute(text("SELECT coalesce(max(sort_order), 0) + 1 FROM proj.org_people WHERE project_id = :p"), {"p": p["id"]}).scalar()
    g = conn.execute(text("""INSERT INTO proj.org_people (project_id, name, role, username, skills, sort_order, created_by, stakeholder_id)
                             VALUES (:p, :name, :role, :username, CAST(:skills AS text[]), :o, :u, :s) RETURNING guid::text"""),
                     {**v, "p": p["id"], "o": n, "u": user.username, "s": d.get("_stakeholder_id")}).scalar()
    return {"id": g, "message": f"{v['name']} added{(' as ' + v['role']) if v['role'] else ''}."}


def _row(conn, p: dict, pid: str) -> dict:
    r = _one(conn, "SELECT * FROM proj.org_people WHERE project_id = :p AND guid = CAST(:g AS uuid)", p=p["id"], g=pid)
    if not r:
        raise EditError("No such person in the project's organisation.", 404)
    return r


def update(conn, project: Any, user, pid: str, d: dict) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    r = _row(conn, p, pid)
    v = _clean(conn, p, {**{k: r[k] for k in ("name", "role", "username", "skills")}, **d})
    conn.execute(text("""UPDATE proj.org_people SET name = :name, role = :role, username = :username, skills = CAST(:skills AS text[]),
                                modified_by = :u,
                                modified_at = now() WHERE id = :i"""), {**v, "u": user.username, "i": r["id"]})
    return {"id": pid, "message": f"{v['name']} saved."}


def delete(conn, project: Any, user, pid: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    r = _row(conn, p, pid)
    conn.execute(text("DELETE FROM proj.org_people WHERE id = :i"), {"i": r["id"]})
    return {"message": f"{r['name']} taken out of the project's organisation."}


def add_members(conn, project: Any, user) -> dict:
    """The project's members not listed yet, each with their role on the project in EA Explorer."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    listed = {r["u"] for r in _rows(conn, "SELECT lower(username) AS u FROM proj.org_people WHERE project_id = :p AND username <> ''", p=p["id"])}
    roles: dict[str, list[str]] = {}
    for m in _rows(conn, "SELECT lower(username) AS u, role FROM proj.members WHERE project_id = :p ORDER BY username", p=p["id"]):
        roles.setdefault(m["u"], []).append(MEMBER_ROLE.get(m["role"], m["role"]))
    added = 0
    for u, rs in roles.items():
        if u in listed:
            continue
        add(conn, project, user, {"name": u, "role": ", ".join(rs), "username": u})
        added += 1
    return {"message": f"{added} member{'s' if added != 1 else ''} of the project added." if added else "Every member is listed already."}


def reorder(conn, project: Any, user, order: list[str]) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    for n, g in enumerate(order or []):
        conn.execute(text("UPDATE proj.org_people SET sort_order = :n WHERE project_id = :p AND guid = CAST(:g AS uuid)"),
                     {"n": n, "p": p["id"], "g": g})
    return {"message": "Order saved."}


def add_stakeholders(conn, project: Any, user, ids: list[str] | None = None) -> dict:
    """Stakeholders of the matrix into the organisation (all those not listed yet, or the ones given), with their role."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    rows = _rows(conn, """SELECT s.id, s.guid::text AS g, s.name, s.role_title, s.organisation FROM proj.stakeholders s
                           WHERE s.project_id = :p AND NOT EXISTS (SELECT 1 FROM proj.org_people o WHERE o.stakeholder_id = s.id)
                           ORDER BY s.sort_order, s.id""", p=p["id"])
    if ids:
        rows = [r for r in rows if r["g"] in set(ids)]
    for r in rows:
        role = r["role_title"] or "Stakeholder"
        add(conn, project, user, {"name": r["name"], "role": role, "_stakeholder_id": r["id"]})
    n = len(rows)
    return {"message": f"{n} stakeholder{'s' if n != 1 else ''} added to the organisation." if n else "Every stakeholder is listed already."}
