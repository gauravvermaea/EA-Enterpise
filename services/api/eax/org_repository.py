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


# ---------------------------------------------------------------- the Architecture Board (D324): members only
def board(conn, user) -> dict:
    rows = _rows(conn, "SELECT username, role, added_by, added_at FROM proj.board_members ORDER BY username")
    for r in rows:
        r["added_at"] = r["added_at"].isoformat() if hasattr(r["added_at"], "isoformat") else r["added_at"]
    return {"members": rows, "may_change": pj._super(user)}


def board_set(conn, user, username: str, role: str = "", remove: bool = False) -> dict:
    from sqlalchemy import text
    if not pj._super(user):
        raise EditError("The Architecture Board's members are named by Super Admins.", 403)
    u = (username or "").strip().lower()
    if not u:
        raise EditError("Choose the person.")
    if remove:
        conn.execute(text("DELETE FROM proj.board_members WHERE username = :u"), {"u": u})
        return {"message": f"{u} is no longer on the Architecture Board."}
    conn.execute(text("""INSERT INTO proj.board_members (username, role, added_by) VALUES (:u, :r, :b)
                         ON CONFLICT (username) DO UPDATE SET role = EXCLUDED.role"""), {"u": u, "r": " ".join((role or "").split())[:120], "b": user.username})
    return {"message": f"{u} is on the Architecture Board{' as ' + role if role else ''}."}


# ---------------------------------------------------------------- performance measurement (D324): one tab each
def _ts(v):
    from datetime import UTC, datetime
    if isinstance(v, str):
        v = datetime.fromisoformat(v)
    return v if v.tzinfo else v.replace(tzinfo=UTC)


def _days(a, b) -> float:
    return round((_ts(b) - _ts(a)).total_seconds() / 86400, 1)


def measures(conn, user, what: str) -> dict:
    """completion, governance, turnaround or coverage, across the projects the person may see (admins: all)."""
    from datetime import UTC, date, datetime
    ps = _visible(conn, user)
    ids = [p["id"] for p in ps]
    if not ids:
        return {"what": what, "rows": [], "projects": 0}
    if what == "completion":
        pk = {r["g"]: r["id"] for r in _rows(conn, "SELECT id, guid::text AS g FROM proj.projects WHERE guid = ANY (CAST(:i AS uuid[]))", i=ids)}
        comp = pj.completion(conn, list(pk.values()))
        rows = []
        for p in ps:
            c = comp.get(pk.get(p["id"])) or {}
            rows.append({"project_id": p["id"], "project": p["name"],
                         **{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in c.items()}})
        return {"what": what, "rows": sorted(rows, key=lambda r: -(r.get("percent") or 0)), "projects": len(ps)}
    if what == "governance":
        today = date.today()
        rows = _rows(conn, """SELECT p.guid::text AS project_id, p.name AS project,
                                     count(*) FILTER (WHERE g.approval = 'Waiting for approval') AS waiting,
                                     min(a.raised_at) FILTER (WHERE a.state = 'open') AS oldest_wait,
                                     count(*) FILTER (WHERE g.approval = 'Draft') AS drafts,
                                     count(*) FILTER (WHERE g.kind = 'Dispensation' AND g.expires_on IS NOT NULL AND g.expires_on < CAST(:t AS date)
                                                        AND g.status NOT IN ('Expired', 'Withdrawn', 'Refused')) AS overdue,
                                     count(*) FILTER (WHERE g.kind = 'Dispensation' AND g.expires_on BETWEEN CAST(:t AS date) AND CAST(:t AS date) + 30) AS expiring,
                                     count(*) FILTER (WHERE g.kind = 'Compliance assessment' AND g.status = 'Not compliant') AS not_compliant,
                                     count(g.id) AS records
                                FROM proj.projects p LEFT JOIN proj.gov_records g ON g.project_id = p.id
                                LEFT JOIN proj.gov_approvals a ON a.record_id = g.id AND a.state = 'open'
                               WHERE p.guid = ANY (CAST(:i AS uuid[])) GROUP BY p.id ORDER BY p.name""", i=ids, t=today)
        now = datetime.now(UTC)
        for r in rows:
            w = r.pop("oldest_wait", None)
            r["oldest_days"] = _days(w, now) if w else None
        return {"what": what, "rows": rows, "projects": len(ps)}
    if what == "turnaround":
        now = datetime.now(UTC)
        reqs = _rows(conn, """SELECT p.guid::text AS project_id, p.name AS project, 'document' AS kind, r.raised_at, r.closed_at, r.state, r.signers
                                FROM proj.signoff_requests r JOIN proj.documents d ON d.id = r.document_id JOIN proj.projects p ON p.id = d.project_id
                               WHERE p.guid = ANY (CAST(:i AS uuid[])) AND r.state <> 'withdrawn'
                              UNION ALL
                              SELECT p.guid::text, p.name, 'governance record', a.raised_at, a.closed_at, a.state, a.signers
                                FROM proj.gov_approvals a JOIN proj.gov_records g ON g.id = a.record_id JOIN proj.projects p ON p.id = g.project_id
                               WHERE p.guid = ANY (CAST(:i AS uuid[])) AND a.state <> 'withdrawn'""", i=ids)
        byp: dict[str, dict] = {}
        for r in reqs:
            x = byp.setdefault(r["project_id"], {"project_id": r["project_id"], "project": r["project"], "closed": 0, "open": 0, "_days": [], "oldest_open": 0})
            if r["closed_at"]:
                x["closed"] += 1
                x["_days"].append(_days(r["raised_at"], r["closed_at"]))
            else:
                x["open"] += 1
                x["oldest_open"] = max(x["oldest_open"], _days(r["raised_at"], now))
        rows = []
        for x in byp.values():
            d = x.pop("_days")
            rows.append({**x, "average_days": round(sum(d) / len(d), 1) if d else None})
        people = _rows(conn, """SELECT x.signer, count(*) AS decided, avg(EXTRACT(EPOCH FROM (x.at - r.raised_at)) / 86400) AS avg_days
                                  FROM (SELECT signer, at, request_id AS rid, 'd' AS k FROM proj.signoff_decisions
                                        UNION ALL SELECT signer, at, approval_id, 'g' FROM proj.gov_decisions) x
                                  JOIN LATERAL (SELECT raised_at FROM proj.signoff_requests WHERE x.k = 'd' AND id = x.rid
                                                UNION ALL SELECT raised_at FROM proj.gov_approvals WHERE x.k = 'g' AND id = x.rid) r ON true
                                 GROUP BY x.signer ORDER BY avg_days DESC NULLS LAST""")
        for pr in people:
            pr["avg_days"] = round(float(pr["avg_days"]), 1) if pr["avg_days"] is not None else None
        return {"what": what, "rows": sorted(rows, key=lambda r: r["project"]), "people": people, "projects": len(ps)}
    if what == "coverage":
        from . import content_framework as cf
        rows = []
        total = len(cf.LABEL)
        for p in ps:
            try:
                ov = cf.overview(conn, p["id"], _Viewer(user))
            except EditError:
                continue
            filled = [a for a in ov["areas"] if a["types"] or a["doc_types"] or a["documents"]]
            with_docs = [a for a in ov["areas"] if a["documents"]]
            rows.append({"project_id": p["id"], "project": p["name"], "areas": total, "filled": len(filled), "with_documents": len(with_docs),
                         "percent": round(100 * len(filled) / total), "empty": [a["label"] for a in ov["areas"] if a not in filled][:40]})
        return {"what": what, "rows": sorted(rows, key=lambda r: -r["percent"]), "projects": len(ps)}
    raise EditError("Completion, governance, turnaround or coverage.", 404)


class _Viewer:
    """Reads a project as the person, or (an admin seeing every project) as a Super Admin would."""
    def __init__(self, user):
        self._u = user
        self.username = user.username
        self.roles = list(user.roles) + (["super-admin"] if may_see_all_users(user) else [])


# ---------------------------------------------------------------- the reference library's four parts (D324)
REF_PARTS = {"foundation": "Foundation architectures", "common": "Common systems architectures", "industry": "Industry architectures",
             "own": "Organisation's own architectures"}
SEEDED = ("eax_migrator", "system", "seed", "postgres")


def reference_part(conn, user, part: str) -> dict:
    """One part of the reference library: the model library's models of that kind and the reference library's folder.
    Foundation: root metamodels; Common systems: reference models with no industry; Industry: reference models of an
    industry; the Organisation's own: reference models the organisation made."""
    name = REF_PARTS.get(part)
    if not name:
        raise EditError("Foundation, common, industry or own.", 404)
    models = _rows(pj.core(conn), """SELECT guid::text AS id, name, kind_code AS kind, coalesce(industry, '') AS industry, created_by, description
                                       FROM core.models WHERE kind_code IN ('template', 'reference') AND NOT is_deleted
                                        AND coalesce(library_state, 'published') <> 'withdrawn' ORDER BY name""")
    pick = {"foundation": lambda m: m["kind"] == "template",
            "common": lambda m: m["kind"] == "reference" and not m["industry"] and m["created_by"] in SEEDED,
            "industry": lambda m: m["kind"] == "reference" and bool(m["industry"]) and m["created_by"] in SEEDED,
            "own": lambda m: m["kind"] == "reference" and m["created_by"] not in SEEDED}[part]
    from . import reference_library as rl
    try:
        docs = rl.browse(conn, user, name, deep=True)
    except EditError:
        docs = {"entries": [], "folders": []}
    return {"part": part, "name": name, "models": [m for m in models if pick(m)], "folder": name, "documents": docs}
