"""The organisation's Architecture Repository (owner, 8 Nov 2026, D318): read-only views across projects that the
repository map's parts lead to. Each person sees the projects they have a role on (a Super Admin: all); records are
changed only inside their project. Admins (Super Admins and User Admins) see every project, and the organisation
structure lists every user.

* governance(kind): every visible project's governance records of one kind (decisions, compliance assessments,
  capability assessments), each with its project.
* people(): everyone on the visible projects' Organisation tabs, with their role and skills (organisation structure
  and the skills repository).
* model_levels(): the landscape level of each model, taken from the depth of the project it is in (Strategic,
  Segment, Capability), with its role there (current, target, transition...); a model in several projects shows under
  each.
* org_base(): the Organisation base project, which the method, the charter and the content framework links open.
"""
from __future__ import annotations

from . import projects as pj
from .metamodel_edit import EditError

GOV_KINDS = {"decisions": "Decision", "compliance": "Compliance assessment", "capability": "Capability assessment"}
LEVELS = ("strategic", "segment", "capability")


def _rows(conn, sql: str, **p) -> list[dict]:
    return pj._rows(conn, sql, **p)


def _visible(conn, user) -> list[dict]:
    """The projects (not the bases) this person has a role on; admins (Super Admins and User Admins): every one
    (owner, 8 Nov 2026: at organisation level admins see everything)."""
    if may_see_all_users(user):
        return _rows(conn, "SELECT guid::text AS id, name FROM proj.projects WHERE base_kind = '' ORDER BY name")
    return [{"id": p["id"], "name": p["name"]} for p in pj.listing(conn, user)]


def _ids(conn, user) -> tuple[list[str], dict[str, str]]:
    ps = _visible(conn, user)
    return [p["id"] for p in ps], {p["id"]: p["name"] for p in ps}


def org_base(conn) -> dict | None:
    r = pj._one(conn, "SELECT guid::text AS id, name FROM proj.projects WHERE base_kind = 'org' ORDER BY id LIMIT 1")
    return dict(r) if r else None


def governance(conn, user, kind: str) -> dict:
    name = GOV_KINDS.get(kind)
    if not name:
        raise EditError("Decisions, compliance assessments or capability assessments.", 404)
    ids, _names = _ids(conn, user)
    rows = []
    if ids:
        rows = _rows(conn, """SELECT g.guid::text AS id, g.ref, g.title, g.status, g.owner, g.raised_on, g.expires_on, g.approval, g.approved_by,
                                     coalesce(g.modified_at, g.created_at) AS modified_at, p.guid::text AS project_id, p.name AS project
                                FROM proj.gov_records g JOIN proj.projects p ON p.id = g.project_id
                               WHERE g.kind = :k AND p.guid = ANY (CAST(:ids AS uuid[]))
                               ORDER BY g.raised_on DESC, p.name, g.ref""", k=name, ids=ids)
    for r in rows:
        for k in ("raised_on", "expires_on"):
            r[k] = str(r[k])[:10] if r[k] else ""
        r["modified_at"] = r["modified_at"].isoformat() if hasattr(r["modified_at"], "isoformat") else r["modified_at"]
    return {"kind": name, "records": rows, "projects": len(ids), "all": may_see_all_users(user)}


def people(conn, user) -> dict:
    ids, _names = _ids(conn, user)
    rows = []
    if ids:
        rows = _rows(conn, """SELECT o.guid::text AS id, o.name, o.role, o.username, o.skills, p.guid::text AS project_id, p.name AS project
                                FROM proj.org_people o JOIN proj.projects p ON p.id = o.project_id
                               WHERE p.guid = ANY (CAST(:ids AS uuid[])) ORDER BY lower(o.name), p.name""", ids=ids)
    for r in rows:
        r["skills"] = list(r["skills"] or [])
    out = {"people": rows, "skills": sorted({k for r in rows for k in r["skills"]}, key=str.lower), "projects": len(ids),
           "all_users": may_see_all_users(user)}
    if out["all_users"]:     # admins see every user (owner, 8 Nov 2026): the projects each is a member of, with the role
        out["members"] = _rows(conn, """SELECT lower(m.username) AS username, m.role, p.guid::text AS project_id, p.name AS project
                                          FROM proj.members m JOIN proj.projects p ON p.id = m.project_id
                                         WHERE p.base_kind = '' ORDER BY p.name""")
    return out


def may_see_all_users(user) -> bool:
    """Super Admins and User Admins: on the organisation's map, the organisation structure is every user."""
    from . import permissions as perms
    return pj._super(user) or perms.allowed(user.roles, "users.read")


def model_levels(conn, user) -> dict:
    ids, _names = _ids(conn, user)
    rows = []
    if ids:
        rows = _rows(conn, """SELECT pm.model_guid::text AS model_id, pm.role, p.guid::text AS project_id, p.name AS project,
                                     lower(coalesce(p.scope_depth, '')) AS level
                                FROM proj.project_models pm JOIN proj.projects p ON p.id = pm.project_id
                               WHERE p.guid = ANY (CAST(:ids AS uuid[])) ORDER BY p.name""", ids=ids)
    return {"levels": list(LEVELS), "models": rows}


def summary(conn, user) -> dict:
    """The Organisation base and its charter's state: the organisation-wide charter (D319), set up by a Super Admin
    before the first project (Project admin › Wizards) or later."""
    b = org_base(conn)
    ch = pj._one(conn, """SELECT c.state, c.approved_by, c.approved_at FROM proj.charters c JOIN proj.projects p ON p.id = c.project_id
                           WHERE p.guid = CAST(:g AS uuid)""", g=b["id"]) if b else None
    if ch and ch.get("approved_at") is not None:
        ch = {**ch, "approved_at": ch["approved_at"].isoformat()}
    return {"org_base": b, "charter": dict(ch) if ch else None, "may_change": pj._super(user)}
