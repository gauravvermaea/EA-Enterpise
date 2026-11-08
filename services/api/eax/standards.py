"""A project's standards (owner, 8 Nov 2026, phase 13.1, D305): like its principles, by area.

Areas: Business, Data, Application, Technology, Security, and any of one's own (AI, say). Each standard has a name,
a description (rich text), a status (Trial, Active, Deprecated, Obsolete) and its source. Standards from the project's
base are mandatory: not changed or removed in the project (a dispensation goes in the governance log). In the
Organisation base, Super Admins keep them; every standard added there binds the projects below it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError
from .project_work import clean_html

_rows, _one = pj._rows, pj._one

AREAS = ("Business", "Data", "Application", "Technology", "Security")
STATUSES = ("Trial", "Active", "Deprecated", "Obsolete")


def _may(conn, p: dict, user) -> bool:
    try:
        pj._need(conn, p, user, "contribute")
        return True
    except EditError:
        return False


def listing(conn, project: Any, user) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    rows = _rows(conn, """SELECT guid::text AS id, area, name, description, status, source, mandatory, origin_guid IS NOT NULL AS from_base,
                                 created_by, coalesce(modified_by, created_by) AS modified_by, coalesce(modified_at, created_at) AS modified_at
                            FROM proj.standards WHERE project_id = :p ORDER BY area, sort_order, name""", p=p["id"])
    areas = list(AREAS) + sorted({r["area"] for r in rows if r["area"] and r["area"] not in AREAS})
    return {"standards": rows, "areas": areas, "statuses": list(STATUSES), "may_edit": _may(conn, p, user),
            "locked_from_base": not p.get("base_kind")}


def _vals(d: dict) -> dict:
    name = " ".join((d.get("name") or "").split())
    if not name:
        raise EditError("Give the standard a name.")
    status = (d.get("status") or "Active").strip()
    if status not in STATUSES:
        raise EditError(f"The status is one of: {', '.join(STATUSES)}.")
    return {"name": name[:200], "area": " ".join((d.get("area") or "").split())[:60], "description": clean_html(d.get("description")),
            "status": status, "source": (d.get("source") or "").strip()[:200]}


def add(conn, project: Any, user, d: dict) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    v = _vals(d)
    g = conn.execute(text("""INSERT INTO proj.standards (project_id, area, name, description, status, source, mandatory, sort_order, created_by)
                             VALUES (:p, :area, :name, :description, :status, :source, :m,
                                     (SELECT coalesce(max(sort_order), 0) + 1 FROM proj.standards WHERE project_id = :p), :u)
                             RETURNING guid::text"""), {**v, "p": p["id"], "m": bool(p.get("base_kind")), "u": user.username}).scalar()
    return {"id": g, "message": f"Standard {v['name']} added{(' under ' + v['area']) if v['area'] else ''}."}


def _row(conn, p: dict, sid: str) -> dict:
    r = _one(conn, "SELECT * FROM proj.standards WHERE project_id = :p AND guid = CAST(:g AS uuid)", p=p["id"], g=sid)
    if not r:
        raise EditError("No such standard in this project.", 404)
    if r["mandatory"] and r["origin_guid"] and not p.get("base_kind"):
        raise EditError(f"{r['name']} comes from the project's base and is mandatory: it is not changed or removed here "
                        "(ask for a dispensation in the governance log).", 409)
    return r


def update(conn, project: Any, user, sid: str, d: dict) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    r = _row(conn, p, sid)
    v = _vals({**{k: r[k] for k in ("name", "area", "description", "status", "source")}, **d})
    conn.execute(text("""UPDATE proj.standards SET name = :name, area = :area, description = :description, status = :status, source = :source,
                                modified_by = :u, modified_at = now() WHERE id = :i"""), {**v, "u": user.username, "i": r["id"]})
    return {"id": sid, "message": f"Standard {v['name']} saved."}


def delete(conn, project: Any, user, sid: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    r = _row(conn, p, sid)
    conn.execute(text("DELETE FROM proj.standards WHERE id = :i"), {"i": r["id"]})
    return {"message": f"Standard {r['name']} taken out."}
