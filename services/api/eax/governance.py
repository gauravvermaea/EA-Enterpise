"""A project's governance log and its architecture charter (owner, 8 Nov 2026, phase 13.1, D306, D307).

Governance log: records of kinds, each kind a tab of its own: Decisions, Dispensations, Compliance assessments, Risks,
Issues, and any kind a project makes up (with its own statuses). A record has a reference (DEC-001), a title, a date,
an owner, a status, rich-text detail, an end or review date, what it relates to, and (a dispensation) the principle or
standard it is about. Everyone on the project reads it; contributors write it.

Approval (owner, 8 Nov 2026, D321): every record has an approval state beside its own status: Draft, Waiting for
approval, Approved, Rejected. Sent for approval to the project's sign-off people (every phase's, once each): approved
when the project's quorum approves, any rejection rejects it (a rejection needs a reason). Or approved directly by
anyone who contributes, with evidence (a file, kept in Sign-off evidence) or a reason. A change to an approved or
waiting record makes it a draft again (an open request is withdrawn); its history keeps every step and the record as it
was each time.

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
    # the EA capability's own maturity and capability assessments, read across projects on the repository map (D318)
    "Capability assessment": ("CAP", ["Planned", "In progress", "Done"]),
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
                                 g.approval, g.approved_by, g.approved_at, g.approval_note, g.evidence_name,
                                 g.principle::text AS principle, g.standard::text AS standard, g.related, g.created_by,
                                 coalesce(g.modified_by, g.created_by) AS modified_by, coalesce(g.modified_at, g.created_at) AS modified_at,
                                 pr.name AS principle_name, st.name AS standard_name
                            FROM proj.gov_records g
                            LEFT JOIN proj.principles pr ON pr.guid = g.principle AND pr.project_id = g.project_id
                            LEFT JOIN proj.standards st ON st.guid = g.standard AND st.project_id = g.project_id
                           WHERE g.project_id = :p ORDER BY g.raised_on DESC, g.id DESC""", p=p["id"])
    reqs = _open_requests(conn, p)
    me = user.username.lower()
    for r in rows:
        for k in ("raised_on", "expires_on"):
            r[k] = str(r[k])[:10] if r[k] else ""
        r["overdue"] = bool(r["expires_on"] and r["expires_on"] < date.today().isoformat())
        r["approved_at"] = r["approved_at"].isoformat() if hasattr(r.get("approved_at"), "isoformat") else r.get("approved_at")
        q = reqs.get(r["id"])
        if q:
            done = {x["signer"].lower(): x for x in q["decisions"]}
            q["waiting_for"] = [s for s in q["signers"] if s.lower() not in done]
            q["mine"] = me in [s.lower() for s in q["signers"]] and me not in done
        r["request"] = q
    return {"records": rows, "kinds": kinds(conn, p), "may_edit": _may(conn, p, user), "signers": _signers(conn, p),
            "quorum": pj_work().quorum_of(p, len(_signers(conn, p))) if _signers(conn, p) else 0,
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
    _history(conn, _row(conn, p, g), user, "logged")
    return {"id": g, "ref": ref, "message": f"{ref} {v['title']} logged, a draft: send it for approval, or approve it with evidence."}


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
    again = ""
    if r["approval"] in ("Approved", "Waiting for approval", "Rejected"):
        _withdraw(conn, r, user, "the record changed")
        conn.execute(text("""UPDATE proj.gov_records SET approval = 'Draft', approved_by = NULL, approved_at = NULL, approval_note = '',
                                    evidence_name = NULL, evidence_mayan_id = NULL WHERE id = :i"""), {"i": r["id"]})
        again = f" It was {r['approval'].lower()}: it is a draft again (the earlier version is kept in its history)."
    _history(conn, r, user, "changed", "", snapshot=True)
    return {"id": rid, "message": f"{r['ref']} saved.{again}"}


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


# ---------------------------------------------------------------- approval (owner, 8 Nov 2026, D321)
APPROVAL = ("Draft", "Waiting for approval", "Approved", "Rejected")


def pj_work():
    from . import project_work as pw
    return pw


def _signers(conn, p: dict) -> list[str]:
    """The project's sign-off people: every phase's and the whole project's, once each."""
    return [r["u"] for r in _rows(conn, "SELECT DISTINCT lower(username) AS u FROM proj.signoff WHERE project_id = :p ORDER BY 1", p=p["id"])]


def _snap(r: dict) -> dict:
    keep = ("kind", "ref", "title", "html", "status", "owner", "raised_on", "expires_on", "related", "approval", "approved_by",
            "approved_at", "approval_note", "evidence_name")
    return {k: (str(r[k]) if r.get(k) is not None and not isinstance(r[k], (str, int)) else r.get(k)) for k in keep}


def _history(conn, r: dict, user, action: str, note: str = "", snapshot: bool = False) -> None:
    conn.execute(text("""INSERT INTO proj.gov_history (record_id, by_user, action, note, snapshot)
                         VALUES (:r, :u, :a, :n, CAST(:s AS jsonb))"""),
                 {"r": r["id"], "u": user.username, "a": action, "n": note or "", "s": json.dumps(_snap(r)) if snapshot else None})


def _open_requests(conn, p: dict) -> dict:
    """guid of a record -> its open request: signers, quorum, note, who raised it, decisions so far."""
    out = {}
    for a in _rows(conn, """SELECT a.id AS _id, a.guid::text AS id, g.guid::text AS rec, a.signers, a.quorum, a.note, a.raised_by, a.raised_at
                              FROM proj.gov_approvals a JOIN proj.gov_records g ON g.id = a.record_id
                             WHERE g.project_id = :p AND a.state = 'open'""", p=p["id"]):
        a["raised_at"] = a["raised_at"].isoformat() if hasattr(a["raised_at"], "isoformat") else a["raised_at"]
        a["signers"] = list(a["signers"])
        a["decisions"] = [{**x, "at": x["at"].isoformat() if hasattr(x["at"], "isoformat") else x["at"]} for x in
                          _rows(conn, "SELECT signer, decision, comment, at FROM proj.gov_decisions WHERE approval_id = :a ORDER BY at", a=a.pop("_id"))]
        out[a.pop("rec")] = a
    return out


def _withdraw(conn, r: dict, user, why: str) -> None:
    a = _one(conn, "UPDATE proj.gov_approvals SET state = 'withdrawn', closed_at = now() WHERE record_id = :r AND state = 'open' RETURNING id",
             r=r["id"])
    if a:
        _history(conn, r, user, "approval request withdrawn", why)


def send_for_approval(conn, project: Any, user, rid: str, note: str = "") -> dict:
    """Asks the project's sign-off people to approve the record; each is told in the application."""
    from . import notify
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    r = _row(conn, p, rid)
    conn.execute(text("SELECT 1 FROM proj.gov_records WHERE id = :i FOR UPDATE"), {"i": r["id"]})
    if r["approval"] == "Approved":
        raise EditError(f"{r['ref']} is approved already: change it first to ask again.", 409)
    if _one(conn, "SELECT 1 AS x FROM proj.gov_approvals WHERE record_id = :r AND state = 'open'", r=r["id"]):
        raise EditError(f"{r['ref']} is already waiting for approval.", 409)
    signers = _signers(conn, p)
    if not signers:
        raise EditError("Nobody signs off in this project yet: set who signs off (Edit › People and sign-off), or approve it with evidence.", 409)
    q = pj_work().quorum_of(p, len(signers))
    conn.execute(text("""INSERT INTO proj.gov_approvals (record_id, signers, quorum, note, raised_by)
                         VALUES (:r, CAST(:s AS text[]), :q, :n, :u)"""), {"r": r["id"], "s": signers, "q": q, "n": (note or "").strip(), "u": user.username})
    conn.execute(text("UPDATE proj.gov_records SET approval = 'Waiting for approval' WHERE id = :i"), {"i": r["id"]})
    _history(conn, r, user, "sent for approval", note, snapshot=True)
    notify.create(pj.core(conn), kind="project.governance_approval", category="request", actor=user.username,
                  title=f"Approve {r['ref']} {r['title']}",
                  body=f"Project {p['name']}: {user.username} asks you to approve or reject this {r['kind'].lower()}.{(' ' + note) if note else ''}",
                  link=f"#/projects/{p['guid']}/governance?kind={r['kind']}", recipients=signers, include_actor=True)
    return {"message": f"Asked {', '.join(signers)} to approve {r['ref']}: approved when {q} of {len(signers)} approve; any rejection rejects it."}


def decide(conn, project: Any, user, rid: str, decision: str, comment: str = "") -> dict:
    """A sign-off person approves or rejects (a rejection needs a reason)."""
    from . import notify
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    if p.get("status") in pj_work().FROZEN:
        raise EditError(f"{p['name']} is {p['status']}: it is read only.", 409)
    r = _row(conn, p, rid)
    a = _one(conn, "SELECT * FROM proj.gov_approvals WHERE record_id = :r AND state = 'open' FOR UPDATE", r=r["id"])
    if not a:
        raise EditError(f"{r['ref']} is not waiting for approval.", 409)
    me = user.username.lower()
    if me not in [s.lower() for s in a["signers"]]:
        raise EditError("You are not one of its sign-off people.", 403)
    if decision not in ("approved", "rejected"):
        raise EditError("Approve or reject.")
    if decision == "rejected" and not (comment or "").strip():
        raise EditError("Say why it is rejected.")
    if _one(conn, "SELECT 1 AS x FROM proj.gov_decisions WHERE approval_id = :a AND lower(signer) = :u", a=a["id"], u=me):
        raise EditError("You have decided already.", 409)
    conn.execute(text("INSERT INTO proj.gov_decisions (approval_id, signer, decision, comment) VALUES (:a, :s, :d, :c)"),
                 {"a": a["id"], "s": me, "d": decision, "c": (comment or "").strip()})
    _history(conn, r, user, decision, comment)
    decs = [x["decision"] for x in _rows(conn, "SELECT decision FROM proj.gov_decisions WHERE approval_id = :a", a=a["id"])]
    state = pj_work().settle_state(decs, a["quorum"])
    if state == "open":
        return {"message": f"{'Approved' if decision == 'approved' else 'Rejected'}: {decs.count('approved')} of the {a['quorum']} approvals needed."}
    conn.execute(text("UPDATE proj.gov_approvals SET state = :s, closed_at = now() WHERE id = :a"), {"s": state, "a": a["id"]})
    word = "Approved" if state == "approved" else "Rejected"
    conn.execute(text("""UPDATE proj.gov_records SET approval = :w, approved_by = CASE WHEN :w = 'Approved' THEN :by ELSE NULL END,
                                approved_at = CASE WHEN :w = 'Approved' THEN now() ELSE NULL END, approval_note = :n WHERE id = :i"""),
                 {"w": word, "by": ", ".join(x["signer"] for x in _rows(conn, "SELECT signer FROM proj.gov_decisions WHERE approval_id = :a AND decision = 'approved'", a=a["id"])),
                  "n": (comment or "").strip(), "i": r["id"]})
    _history(conn, {**r, "approval": word}, user, f"approval {state}", "", snapshot=True)
    notify.create(pj.core(conn), kind=f"project.governance_{state}", category="request", actor=user.username,
                  title=f"{r['ref']} {r['title']} is {state}", body=f"Project {p['name']}: the approval you asked for is {state}.",
                  link=f"#/projects/{p['guid']}/governance?kind={r['kind']}", recipients=[a["raised_by"]], include_actor=True)
    return {"message": f"{r['ref']} is {state}."}


def approve_with_evidence(conn, project: Any, user, rid: str, reason: str = "", evidence_name: str = "", evidence: bytes = b"") -> dict:
    """Anyone who contributes marks the record approved, with evidence (a file: minutes, an email) or a reason; an open
    request for approval is withdrawn."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    r = _row(conn, p, rid)
    reason = (reason or "").strip()
    if not reason and not evidence:
        raise EditError("Give the reason it is approved, or attach the evidence (minutes, an email, a signed page).")
    if r["approval"] == "Approved":
        raise EditError(f"{r['ref']} is approved already.", 409)
    _withdraw(conn, r, user, "approved with evidence")
    mid = None
    if evidence:
        stored = pj_work()._store(conn, p, user, pj_work().EVIDENCE, f"{r['ref']} - {evidence_name or 'evidence'}", evidence,
                                  origin="evidence", kind="Artifact")
        mid = stored["mayan_id"]
    conn.execute(text("""UPDATE proj.gov_records SET approval = 'Approved', approved_by = :u, approved_at = now(), approval_note = :n,
                                evidence_name = :e, evidence_mayan_id = :m WHERE id = :i"""),
                 {"u": user.username, "n": reason, "e": evidence_name or None if evidence else None, "m": mid, "i": r["id"]})
    _history(conn, {**r, "approval": "Approved"}, user, "approved with evidence", reason + (f" (file: {evidence_name})" if evidence else ""), snapshot=True)
    return {"message": f"{r['ref']} approved{' with ' + evidence_name if evidence else ''}."}


def history(conn, project: Any, user, rid: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    r = _row(conn, p, rid)
    rows = _rows(conn, "SELECT at, by_user, action, note, snapshot FROM proj.gov_history WHERE record_id = :r ORDER BY at DESC, id DESC", r=r["id"])
    for x in rows:
        x["at"] = x["at"].isoformat() if hasattr(x["at"], "isoformat") else x["at"]
        if isinstance(x["snapshot"], str):
            x["snapshot"] = json.loads(x["snapshot"])
    return {"ref": r["ref"], "title": r["title"], "history": rows}
