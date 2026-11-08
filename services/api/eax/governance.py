"""A project's governance log and its architecture charter (owner, 8 Nov 2026, phase 13.1, D306, D307).

Governance log: records of kinds, each kind a tab of its own: Decisions, Dispensations, Compliance assessments, Risks,
Issues, and any kind a project makes up (with its own statuses). A record has a reference (DEC-001), a title, a date,
an owner, a status, rich-text detail, an end or review date, what it relates to, and (a dispensation) the principle or
standard it is about. Everyone on the project reads it; contributors write it.

Architecture charter: a structured page of rich-text sections (purpose, scope, authority, governance and the board,
principles and standards applied, roles, method, compliance and review), taken from the project's base when the
project is made. A Project Admin or Lead Architect changes and approves it; a change after approval makes it a draft.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError
from .project_work import clean_html

_rows, _one = pj._rows, pj._one

# name -> (prefix, statuses); the first status is a new record's
KINDS: dict[str, tuple[str, list[str]]] = {
    "Decision": ("DEC", ["Proposed", "Accepted", "Superseded", "Rejected"]),
    "Dispensation": ("DSP", ["Requested", "Granted", "Refused", "Expired", "Withdrawn"]),
    "Compliance assessment": ("CMP", ["Planned", "In progress", "Compliant", "Compliant with conditions", "Not compliant"]),
    "Risk": ("RSK", ["Open", "Mitigated", "Accepted", "Closed"]),
    "Issue": ("ISS", ["Open", "In progress", "Resolved", "Closed"]),
}


def _may(conn, p: dict, user, what: str = "contribute") -> bool:
    try:
        pj._need(conn, p, user, what)
        return True
    except EditError:
        return False


def kinds(conn, p: dict) -> list[dict]:
    out = [{"name": k, "prefix": v[0], "statuses": v[1], "own": False} for k, v in KINDS.items()]
    for r in _rows(conn, "SELECT name, prefix, statuses FROM proj.gov_kinds WHERE project_id = :p ORDER BY sort_order, name", p=p["id"]):
        out.append({"name": r["name"], "prefix": r["prefix"], "statuses": list(r["statuses"] or []) or ["Open", "Closed"], "own": True})
    return out


def listing(conn, project: Any, user) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    rows = _rows(conn, """SELECT g.guid::text AS id, g.kind, g.ref, g.title, g.html, g.status, g.owner, g.raised_on, g.expires_on,
                                 g.principle::text AS principle, g.standard::text AS standard, g.related, g.created_by,
                                 coalesce(g.modified_by, g.created_by) AS modified_by, coalesce(g.modified_at, g.created_at) AS modified_at,
                                 pr.name AS principle_name, st.name AS standard_name
                            FROM proj.gov_records g
                            LEFT JOIN proj.principles pr ON pr.guid = g.principle AND pr.project_id = g.project_id
                            LEFT JOIN proj.standards st ON st.guid = g.standard AND st.project_id = g.project_id
                           WHERE g.project_id = :p ORDER BY g.raised_on DESC, g.id DESC""", p=p["id"])
    for r in rows:
        for k in ("raised_on", "expires_on"):
            r[k] = str(r[k])[:10] if r[k] else ""
        r["overdue"] = bool(r["expires_on"] and r["expires_on"] < date.today().isoformat())
    return {"records": rows, "kinds": kinds(conn, p), "may_edit": _may(conn, p, user),
            "principles": _rows(conn, "SELECT guid::text AS id, name, area FROM proj.principles WHERE project_id = :p ORDER BY area, name", p=p["id"]),
            "standards": _rows(conn, "SELECT guid::text AS id, name, area FROM proj.standards WHERE project_id = :p ORDER BY area, name", p=p["id"])}


def _date(v: Any, what: str) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError as exc:
        raise EditError(f"{what} is a date (YYYY-MM-DD).") from exc


def _vals(conn, p: dict, d: dict) -> dict:
    ks = {k["name"]: k for k in kinds(conn, p)}
    kind = (d.get("kind") or "").strip()
    if kind not in ks:
        raise EditError(f"The kind is one of: {', '.join(ks)}.")
    title = " ".join((d.get("title") or "").split())
    if not title:
        raise EditError("Give the record a title.")
    status = (d.get("status") or ks[kind]["statuses"][0]).strip()
    if status not in ks[kind]["statuses"]:
        raise EditError(f"A {kind.lower()}'s status is one of: {', '.join(ks[kind]['statuses'])}.")
    pr = d.get("principle") or None
    st = d.get("standard") or None
    if pr and not _one(conn, "SELECT 1 AS x FROM proj.principles WHERE project_id = :p AND guid = CAST(:g AS uuid)", p=p["id"], g=pr):
        raise EditError("No such principle in this project.")
    if st and not _one(conn, "SELECT 1 AS x FROM proj.standards WHERE project_id = :p AND guid = CAST(:g AS uuid)", p=p["id"], g=st):
        raise EditError("No such standard in this project.")
    return {"kind": kind, "title": title[:300], "html": clean_html(d.get("html")), "status": status,
            "owner": (d.get("owner") or "").strip()[:120], "raised_on": _date(d.get("raised_on"), "The date") or date.today(),
            "expires_on": _date(d.get("expires_on"), "The end or review date"), "principle": pr, "standard": st,
            "related": (d.get("related") or "").strip()[:1000], "prefix": ks[kind]["prefix"]}


def add(conn, project: Any, user, d: dict) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    v = _vals(conn, p, d)
    n = (_one(conn, "SELECT count(*) AS n FROM proj.gov_records WHERE project_id = :p AND kind = :k", p=p["id"], k=v["kind"]) or {"n": 0})["n"]
    ref = f"{v['prefix'] or 'REC'}-{int(n) + 1:03d}"
    g = conn.execute(text("""INSERT INTO proj.gov_records (project_id, kind, ref, title, html, status, owner, raised_on, expires_on,
                                                           principle, standard, related, created_by)
                             VALUES (:p, :kind, :ref, :title, :html, :status, :owner, :raised_on, :expires_on,
                                     CAST(:principle AS uuid), CAST(:standard AS uuid), :related, :u) RETURNING guid::text"""),
                     {**v, "p": p["id"], "ref": ref, "u": user.username}).scalar()
    return {"id": g, "ref": ref, "message": f"{ref} {v['title']} logged."}


def _row(conn, p: dict, rid: str) -> dict:
    r = _one(conn, "SELECT * FROM proj.gov_records WHERE project_id = :p AND guid = CAST(:g AS uuid)", p=p["id"], g=rid)
    if not r:
        raise EditError("No such record in the governance log.", 404)
    return r


def update(conn, project: Any, user, rid: str, d: dict) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    r = _row(conn, p, rid)
    base = {k: r[k] for k in ("kind", "title", "html", "status", "owner", "raised_on", "expires_on", "related")}
    base["principle"] = str(r["principle"]) if r["principle"] else None
    base["standard"] = str(r["standard"]) if r["standard"] else None
    v = _vals(conn, p, {**base, **d, "kind": r["kind"]})          # a record keeps its kind
    conn.execute(text("""UPDATE proj.gov_records SET title = :title, html = :html, status = :status, owner = :owner, raised_on = :raised_on,
                                expires_on = :expires_on, principle = CAST(:principle AS uuid), standard = CAST(:standard AS uuid),
                                related = :related, modified_by = :u, modified_at = now() WHERE id = :i"""),
                 {**v, "u": user.username, "i": r["id"]})
    return {"id": rid, "message": f"{r['ref']} saved."}


def delete(conn, project: Any, user, rid: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "admin")
    r = _row(conn, p, rid)
    conn.execute(text("DELETE FROM proj.gov_records WHERE id = :i"), {"i": r["id"]})
    return {"message": f"{r['ref']} taken out of the governance log."}


def add_kind(conn, project: Any, user, d: dict) -> dict:
    """A kind of record of the project's own (its own tab), with its statuses."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    name = " ".join((d.get("name") or "").split())[:60]
    if not name:
        raise EditError("Give the kind a name.")
    if name.lower() in {k["name"].lower() for k in kinds(conn, p)}:
        raise EditError(f"{name} is a kind already.")
    statuses = [" ".join(str(s).split())[:40] for s in (d.get("statuses") or []) if str(s).strip()][:12] or ["Open", "Closed"]
    prefix = ("".join(ch for ch in (d.get("prefix") or name).upper() if ch.isalnum())[:4]) or "REC"
    n = conn.execute(text("SELECT coalesce(max(sort_order), 0) + 1 FROM proj.gov_kinds WHERE project_id = :p"), {"p": p["id"]}).scalar()
    conn.execute(text("""INSERT INTO proj.gov_kinds (project_id, name, prefix, statuses, sort_order, added_by)
                         VALUES (:p, :n, :x, CAST(:s AS text[]), :o, :u)"""), {"p": p["id"], "n": name, "x": prefix, "s": statuses, "o": n, "u": user.username})
    return {"message": f"A new kind of record: {name} ({prefix}; {', '.join(statuses)})."}


def delete_kind(conn, project: Any, user, name: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    if name in KINDS:
        raise EditError(f"{name} is a standard kind: it stays.", 409)
    used = (_one(conn, "SELECT count(*) AS n FROM proj.gov_records WHERE project_id = :p AND kind = :k", p=p["id"], k=name) or {"n": 0})["n"]
    if used:
        raise EditError(f"{used} record(s) are of kind {name}: remove them first.", 409)
    conn.execute(text("DELETE FROM proj.gov_kinds WHERE project_id = :p AND name = :n"), {"p": p["id"], "n": name})
    return {"message": f"Kind {name} removed."}


# ---------------------------------------------------------------- the architecture charter
def _sections() -> list[dict]:
    from . import project_bases as pb
    return pb.seed()["charter"]


def charter(conn, project: Any, user) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    r = _one(conn, "SELECT * FROM proj.charters WHERE project_id = :p", p=p["id"])
    got = (r or {}).get("sections") or {}
    if not r and p.get("base_id"):           # none yet (a project made before 13.1): its base's charter to start from
        b = _one(conn, "SELECT sections FROM proj.charters WHERE project_id = :b", b=p["base_id"])
        got = (b or {}).get("sections") or {}
    if isinstance(got, str):
        got = json.loads(got)
    return {"sections": [{"key": s["key"], "title": s["title"], "html": got.get(s["key"], "")} for s in _sections()],
            "state": (r or {}).get("state") or "Draft", "approved_by": (r or {}).get("approved_by"), "approved_at": (r or {}).get("approved_at"),
            "modified_by": (r or {}).get("modified_by"), "modified_at": (r or {}).get("modified_at"), "may_edit": _may(conn, p, user, "admin")}


def charter_from_wizard(conn, p: dict, user, sections: dict | None) -> None:
    """The charter as written in the project wizard (owner, 8 Nov 2026): the sections changed there, over the base's
    charter the project took when it was made (a draft until approved). Rights were checked by the wizard's create."""
    if not sections:
        return
    keys = {s["key"] for s in _sections()}
    r = _one(conn, "SELECT sections FROM proj.charters WHERE project_id = :p", p=p["id"])
    got = (r or {}).get("sections") or {}
    if isinstance(got, str):
        got = json.loads(got)
    for k, v in sections.items():
        if k in keys:
            got[k] = clean_html(v)
    conn.execute(text("""INSERT INTO proj.charters (project_id, sections, state, modified_by, modified_at)
                         VALUES (:p, CAST(:s AS jsonb), 'Draft', :u, now())
                         ON CONFLICT (project_id) DO UPDATE SET sections = EXCLUDED.sections, state = 'Draft', approved_by = NULL,
                             approved_at = NULL, modified_by = EXCLUDED.modified_by, modified_at = now()"""),
                 {"p": p["id"], "s": json.dumps(got), "u": user.username})


def save_charter(conn, project: Any, user, d: dict) -> dict:
    """Sections changed ({sections: {key: html}}) and/or approve ({approve: true}). A change after approval: draft again."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "admin")
    keys = {s["key"] for s in _sections()}
    r = _one(conn, "SELECT * FROM proj.charters WHERE project_id = :p", p=p["id"])
    got = (r or {}).get("sections") or {}
    if not r and p.get("base_id"):
        b = _one(conn, "SELECT sections FROM proj.charters WHERE project_id = :b", b=p["base_id"])
        got = (b or {}).get("sections") or {}
    if isinstance(got, str):
        got = json.loads(got)
    changed = False
    for k, v in (d.get("sections") or {}).items():
        if k in keys:
            new = clean_html(v)
            changed = changed or new != got.get(k, "")
            got[k] = new
    approve = bool(d.get("approve"))
    state = "Approved" if approve else ("Draft" if changed else ((r or {}).get("state") or "Draft"))
    conn.execute(text("""INSERT INTO proj.charters (project_id, sections, state, approved_by, approved_at, modified_by, modified_at)
                         VALUES (:p, CAST(:s AS jsonb), :st, :ab, CASE WHEN :ap THEN now() END, :u, now())
                         ON CONFLICT (project_id) DO UPDATE SET sections = EXCLUDED.sections, state = EXCLUDED.state,
                             approved_by = CASE WHEN :ap THEN EXCLUDED.approved_by WHEN EXCLUDED.state = 'Draft' THEN NULL
                                                ELSE proj.charters.approved_by END,
                             approved_at = CASE WHEN :ap THEN now() WHEN EXCLUDED.state = 'Draft' THEN NULL ELSE proj.charters.approved_at END,
                             modified_by = EXCLUDED.modified_by, modified_at = now()"""),
                 {"p": p["id"], "s": json.dumps(got), "st": state, "ab": user.username if approve else None, "ap": approve, "u": user.username})
    if approve:
        return {"message": "The architecture charter is approved."}
    return {"message": "Charter saved" + (" (it is a draft again: approve it once more)." if changed and (r or {}).get("state") == "Approved" else ".")}
