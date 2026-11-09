"""Key questions (owner, 9 Nov 2026): every piece of a project's work answers a stakeholder's question.

    a key question     the question, who asks it, and the answer we expect or how we will answer it
    its viewpoints     the viewpoints that answer it: many to many (a question may need several viewpoints; a viewpoint
                       may answer several questions). A library viewpoint mapped to a question is chosen for the project
    a placeholder      stands in where no viewpoint fits: a text (a name and what it will show), or an empty file of a
                       type (docx, pptx, xlsx, pdf, drawio, md, txt) put in the project's files to fill in later.
                       Placeholders stay in the project (PH-01 ...): never in the organisation's viewpoints

    its status         open, then answered (a contributor writes the answer), then accepted by the stakeholder: in the
                       application by a project member with the Stakeholder role, or recorded by a contributor (who,
                       when, a note, optional evidence file) when it was given outside. A rejection sends it back to
                       open; changing an accepted question or its answer takes the acceptance away. Every step is kept
                       (question_events)

Set in the project wizard (the Key questions step, then the Viewpoints step maps them), and on the project's Key
questions tab by anyone who contributes. Rules are here, never in the database (D248).
"""

from __future__ import annotations

import re
from html import escape
from typing import Any

from sqlalchemy import text

from . import blank_files
from . import project_work as pw
from . import projects as pj
from .metamodel_edit import EditError

_rows, _one = pj._rows, pj._one
STATUSES = ("open", "answered", "accepted")


# ---------------------------------------------------------------- reading
def listing(conn, p: dict) -> dict:
    qs = _rows(conn, """SELECT q.id, q.guid::text AS id_guid, q.sort_order, q.question, q.asked_by, q.approach, q.created_by, q.created_at,
                               q.changed_by, q.changed_at, q.status, q.answer, q.answered_by, q.answered_at, q.accepted_by,
                               q.accepted_at, q.accept_note, q.accept_recorded_by, d.guid::text AS evidence, d.file_name AS evidence_name
                          FROM proj.key_questions q LEFT JOIN proj.documents d ON d.id = q.evidence_document_id
                         WHERE q.project_id = :p ORDER BY q.sort_order, q.id""", p=p["id"])
    events: dict[int, list[dict]] = {}
    for r in _rows(conn, """SELECT e.question_id, e.action, e.status, e.username, e.at, e.note FROM proj.question_events e
                             JOIN proj.key_questions q ON q.id = e.question_id WHERE q.project_id = :p ORDER BY e.at, e.id""", p=p["id"]):
        events.setdefault(r.pop("question_id"), []).append(r)
    links: dict[int, list[dict]] = {}
    for r in _rows(conn, """SELECT l.question_id, l.url, l.label, d.guid::text AS document, d.file_name, d.title, d.folder, d.state
                              FROM proj.question_links l JOIN proj.key_questions q ON q.id = l.question_id
                              LEFT JOIN proj.documents d ON d.id = l.document_id
                             WHERE q.project_id = :p ORDER BY l.sort_order, l.id""", p=p["id"]):
        links.setdefault(r.pop("question_id"), []).append(r)
    maps: dict[int, list[str]] = {}
    for r in _rows(conn, """SELECT qv.question_id, qv.viewpoint FROM proj.question_viewpoints qv
                             JOIN proj.key_questions q ON q.id = qv.question_id WHERE q.project_id = :p ORDER BY qv.viewpoint""", p=p["id"]):
        maps.setdefault(r["question_id"], []).append(r["viewpoint"])
    phs = _rows(conn, """SELECT ph.guid::text AS id, ph.code, ph.name, ph.description, ph.kind, ph.file_type, ph.created_by, ph.created_at,
                                d.guid::text AS document, d.file_name, d.folder
                           FROM proj.placeholder_viewpoints ph LEFT JOIN proj.documents d ON d.id = ph.document_id
                          WHERE ph.project_id = :p ORDER BY ph.code""", p=p["id"])
    questions = [{"id": q["id_guid"], "seq": q["sort_order"], "question": q["question"], "asked_by": q["asked_by"], "approach": q["approach"],
                  "viewpoints": maps.get(q["id"], []), "created_by": q["created_by"], "created_at": q["created_at"],
                  "changed_by": q["changed_by"], "changed_at": q["changed_at"],
                  **{k: q[k] for k in ("status", "answer", "answered_by", "answered_at", "accepted_by", "accepted_at", "accept_note",
                                       "accept_recorded_by", "evidence", "evidence_name")},
                  "links": links.get(q["id"], []), "history": events.get(q["id"], [])} for q in qs]
    for ph in phs:
        ph["answers"] = [q["id"] for q in questions if ph["code"] in q["viewpoints"]]
    counts = {k: sum(1 for q in questions if q["status"] == k) for k in STATUSES}
    return {"questions": questions, "placeholders": phs, "file_types": blank_files.TYPES, "counts": counts}


def read(conn, project: Any, user) -> dict:
    return listing(conn, _project(conn, project, user, "read"))


def _project(conn, project: Any, user, what: str = "contribute") -> dict:
    p = pj.project_row(conn, project)
    pw.need(conn, p, user, what)
    return p


def _question(conn, p: dict, qid: str) -> dict:
    q = _one(conn, "SELECT * FROM proj.key_questions WHERE project_id = :p AND guid::text = :g", p=p["id"], g=str(qid))
    if not q:
        raise EditError("No such key question in this project.", 404)
    return q


def _clean(s: Any, n: int = 4000) -> str:
    return (str(s or "")).strip()[:n]


def _rich(s: Any) -> str:
    """The answer is rich text (owner, 9 Nov 2026): cleaned as every rich text is (only plain formatting survives); a
    plain text answer (MCP, the seed) becomes one paragraph."""
    s = str(s or "").strip()
    if s and not s.startswith("<"):
        s = "".join(f"<p>{escape(x)}</p>" for x in s.split("\n\n") if x.strip())
    return pw.clean_html(s)[:40000]


def _plain(html: str) -> str:
    return re.sub(r"<[^>]+>|&nbsp;", " ", html or "").strip()


# ---------------------------------------------------------------- the viewpoints a question maps to
def _known(conn, p: dict) -> tuple[set[str], set[str]]:
    """The codes the project has (its viewpoints and placeholders) and the organisation's library codes."""
    have = {r["v"] for r in _rows(conn, "SELECT viewpoint AS v FROM proj.project_viewpoints WHERE project_id = :p", p=p["id"])}
    have |= {r["code"] for r in _rows(conn, "SELECT code FROM proj.placeholder_viewpoints WHERE project_id = :p", p=p["id"])}
    lib = {r["code"] for r in _rows(pj.core(conn), "SELECT code FROM core.viewpoints")}
    return have, lib


def set_viewpoints(conn, p: dict, question_id: int, codes: list[str]) -> list[str]:
    """The viewpoints that answer a question, as they should be. A viewpoint of the organisation's library not yet the
    project's is chosen for it; a code that is neither the project's nor the library's is refused."""
    have, lib = _known(conn, p)
    codes = list(dict.fromkeys(c for c in (str(x).strip() for x in codes or []) if c))
    unknown = [c for c in codes if c not in have and c not in lib]
    if unknown:
        raise EditError(f"No such viewpoint: {', '.join(unknown)}.")
    for c in codes:
        if c not in have and not c.startswith("PH-"):
            conn.execute(text("INSERT INTO proj.project_viewpoints (project_id, viewpoint) VALUES (:p, :v) ON CONFLICT DO NOTHING"),
                         {"p": p["id"], "v": c})
    conn.execute(text("DELETE FROM proj.question_viewpoints WHERE question_id = :q AND NOT (viewpoint = ANY (CAST(:c AS text[])))"),
                 {"q": question_id, "c": codes})
    for c in codes:
        conn.execute(text("INSERT INTO proj.question_viewpoints (question_id, viewpoint) VALUES (:q, :v) ON CONFLICT DO NOTHING"),
                     {"q": question_id, "v": c})
    return codes


def tidy(conn, p: dict) -> None:
    """Mappings to a viewpoint the project no longer has (taken out in the wizard) go."""
    have, _lib = _known(conn, p)
    conn.execute(text("""DELETE FROM proj.question_viewpoints qv USING proj.key_questions q
                          WHERE q.id = qv.question_id AND q.project_id = :p AND NOT (qv.viewpoint = ANY (CAST(:h AS text[])))"""),
                 {"p": p["id"], "h": sorted(have)})


# ---------------------------------------------------------------- questions
def _insert_question(conn, p: dict, user, data: dict, seq: int | None = None) -> dict:
    q = _clean(data.get("question"), 1000)
    if not q:
        raise EditError("Write the question.")
    if seq is None:
        seq = (_one(conn, "SELECT coalesce(max(sort_order), 0) + 1 AS n FROM proj.key_questions WHERE project_id = :p", p=p["id"]) or {"n": 1})["n"]
    row = _one(conn, """INSERT INTO proj.key_questions (project_id, sort_order, question, asked_by, approach, created_by)
                        VALUES (:p, :s, :q, :a, :ap, :u) RETURNING id, guid::text AS guid""",
               p=p["id"], s=seq, q=q, a=_clean(data.get("asked_by"), 500), ap=_clean(data.get("approach")), u=user.username)
    _event(conn, row["id"], user, "asked", "open", _clean(data.get("asked_by"), 500) and f"asked by {_clean(data.get('asked_by'), 500)}")
    return row


def add_question(conn, project: Any, user, data: dict) -> dict:
    p = _project(conn, project, user)
    row = _insert_question(conn, p, user, data)
    set_viewpoints(conn, p, row["id"], data.get("viewpoints") or [])
    return {"id": row["guid"], "message": "Key question added."}


def change_question(conn, project: Any, user, qid: str, data: dict) -> dict:
    p = _project(conn, project, user)
    q = _question(conn, p, qid)
    new = {k: data[k] if k in data else q[k] for k in ("question", "asked_by", "approach", "answer")}
    new["answer"] = _rich(new["answer"])
    if not _clean(new["question"]):
        raise EditError("Write the question.")
    if q["status"] != "open" and not _plain(new["answer"]):
        raise EditError("An answered question keeps its answer: reopen it to take the answer away.")
    conn.execute(text("""UPDATE proj.key_questions SET question = :q, asked_by = :a, approach = :ap, answer = :an, changed_by = :u,
                                changed_at = now() WHERE id = :i"""),
                 {"q": _clean(new["question"], 1000), "a": _clean(new["asked_by"], 500), "ap": _clean(new["approach"]),
                  "an": new["answer"], "u": user.username, "i": q["id"]})
    msg = "Key question saved."
    if any(_clean(new[k]) != _clean(q[k]) for k in ("question", "asked_by", "approach", "answer")):
        msg += _changed(conn, q, user, _clean(new["question"]) != _clean(q["question"]) or _clean(new["answer"]) != _clean(q["answer"]))
    if "viewpoints" in data:
        set_viewpoints(conn, p, q["id"], data.get("viewpoints") or [])
    if "documents" in data or "links" in data:
        set_links(conn, p, q["id"], user, data.get("documents"), data.get("links"))
    return {"id": qid, "message": msg}


def set_links(conn, p: dict, question_id: int, user, documents: list | None, links: list | None) -> None:
    """What the answer points to, as it should be: documents of the project (by id) and links ({url, label})."""
    docs = []
    for g in documents or []:
        r = _one(conn, "SELECT id FROM proj.documents WHERE project_id = :p AND guid::text = :g", p=p["id"], g=str(g))
        if not r:
            raise EditError("A document the answer points to is not in this project.")
        docs.append(r["id"])
    urls = []
    for x in links or []:
        u = _clean(x.get("url") if isinstance(x, dict) else x, 2000)
        if not u:
            continue
        if not re.match(r"^(https?://|#/)", u):
            raise EditError(f"A link starts with https:// (or #/ for a page of EA Explorer): {u}")
        urls.append((u, _clean(x.get("label") if isinstance(x, dict) else "", 300)))
    conn.execute(text("DELETE FROM proj.question_links WHERE question_id = :q"), {"q": question_id})
    for n, d in enumerate(dict.fromkeys(docs)):
        conn.execute(text("INSERT INTO proj.question_links (question_id, document_id, sort_order, added_by) VALUES (:q, :d, :s, :u)"),
                     {"q": question_id, "d": d, "s": n, "u": user.username})
    for n, (u, label) in enumerate(urls, start=len(docs)):
        conn.execute(text("INSERT INTO proj.question_links (question_id, url, label, sort_order, added_by) VALUES (:q, :l, :b, :s, :u)"),
                     {"q": question_id, "l": u, "b": label, "s": n, "u": user.username})


def _changed(conn, q: dict, user, matters: bool) -> str:
    """A change is kept; a change to the question or the answer of an accepted one takes the acceptance away."""
    if matters and q["status"] == "accepted":
        conn.execute(text("""UPDATE proj.key_questions SET status = 'answered', accepted_by = '', accepted_at = NULL, accept_note = '',
                                    accept_recorded_by = '', evidence_document_id = NULL WHERE id = :i"""), {"i": q["id"]})
        _event(conn, q["id"], user, "changed", "answered", f"changed after {q['accepted_by']} accepted it: to be accepted again")
        return f" It was accepted by {q['accepted_by']}: it needs accepting again."
    _event(conn, q["id"], user, "changed", q["status"])
    return ""


# ---------------------------------------------------------------- answering and acceptance
def _event(conn, qid: int, user, action: str, status: str, note: str = "") -> None:
    conn.execute(text("INSERT INTO proj.question_events (question_id, action, status, username, note) VALUES (:q, :a, :s, :u, :n)"),
                 {"q": qid, "a": action, "s": status, "u": getattr(user, "username", str(user)), "n": _clean(note, 2000)})


def _stakeholders(conn, p: dict) -> list[str]:
    return [r["username"] for r in _rows(conn, "SELECT username FROM proj.members WHERE project_id = :p AND role = 'stakeholder'", p=p["id"])]


def _tell(conn, p: dict, user, kind: str, title: str, body: str, to: list[str]) -> None:
    from . import notify
    to = sorted({u for u in to if u and u.lower() != user.username.lower()})
    if to:
        notify.create(pj.core(conn), kind=f"project.question_{kind}", category="request", actor=user.username, title=title, body=body,
                      link=f"#/projects/{p['guid']}/questions", recipients=to)


def _qn(conn, p: dict, q: dict) -> str:
    n = (_one(conn, """SELECT count(*) AS n FROM proj.key_questions WHERE project_id = :p AND (sort_order, id) <= (:s, :i)""",
              p=p["id"], s=q["sort_order"], i=q["id"]) or {"n": 0})["n"]
    return f"Q{n}"


def answer(conn, project: Any, user, qid: str, data: dict) -> dict:
    """A contributor writes the answer (again): the question is answered, to be accepted by the stakeholder."""
    p = _project(conn, project, user)
    q = _question(conn, p, qid)
    a = _rich(data.get("answer"))
    if not _plain(a):
        raise EditError("Write the answer: a summary of it, pointing to the artifacts that hold it.")
    if "documents" in data or "links" in data:
        set_links(conn, p, q["id"], user, data.get("documents"), data.get("links"))
    if "viewpoints" in data:
        set_viewpoints(conn, p, q["id"], data.get("viewpoints") or [])
    points = (_one(conn, """SELECT (SELECT count(*) FROM proj.question_links WHERE question_id = :q)
                                   + (SELECT count(*) FROM proj.question_viewpoints WHERE question_id = :q) AS n""", q=q["id"]) or {"n": 0})["n"]
    if not points:
        raise EditError("Point the answer to what holds it: a document of the project, a link, or a viewpoint.")
    if q["status"] == "accepted" and a == q["answer"]:
        return {"id": qid, "message": "Already accepted with that answer."}
    conn.execute(text("""UPDATE proj.key_questions SET status = 'answered', answer = :a, answered_by = :u, answered_at = now(),
                                accepted_by = '', accepted_at = NULL, accept_note = '', accept_recorded_by = '', evidence_document_id = NULL
                          WHERE id = :i"""), {"a": a, "u": user.username, "i": q["id"]})
    again = q["status"] == "accepted"
    _event(conn, q["id"], user, "answered", "answered", ("answer changed after acceptance; " if again else "") + _clean(data.get("note"), 1000))
    qn = _qn(conn, p, q)
    _tell(conn, p, user, "answered", f"{qn} answered: please accept it", f"Project {p['name']}: {user.username} answered “{q['question']}”.",
          _stakeholders(conn, p))
    return {"id": qid, "message": f"{qn} answered: waiting for the stakeholder to accept it."}


def _decide(conn, p: dict, q: dict, user, decision: str, by: str, note: str, recorded_by: str, at: str | None, evidence: int | None) -> str:
    if q["status"] != "answered":
        raise EditError("Only an answered question is accepted or rejected." if q["status"] == "open" else "It is accepted already.", 409)
    qn = _qn(conn, p, q)
    if decision == "accepted":
        conn.execute(text("""UPDATE proj.key_questions SET status = 'accepted', accepted_by = :b, accepted_at = coalesce(CAST(:t AS timestamptz), now()),
                                    accept_note = :n, accept_recorded_by = :r, evidence_document_id = :e WHERE id = :i"""),
                     {"b": by, "t": at or None, "n": note, "r": recorded_by, "e": evidence, "i": q["id"]})
        _event(conn, q["id"], user, "accepted", "accepted", (f"recorded for {by}: " if recorded_by else "") + note)
        msg = f"{qn} accepted by {by}."
    elif decision == "rejected":
        if not note:
            raise EditError("Say why the answer is not accepted: it goes back to open with the reason.")
        conn.execute(text("UPDATE proj.key_questions SET status = 'open' WHERE id = :i"), {"i": q["id"]})
        _event(conn, q["id"], user, "rejected", "open", (f"recorded for {by}: " if recorded_by else "") + note)
        msg = f"{qn} not accepted by {by}: it is open again."
    else:
        raise EditError("The stakeholder accepts or rejects.")
    _tell(conn, p, user, decision, f"{qn} {decision} by {by}", f"Project {p['name']}: “{q['question']}”. {note}".strip(),
          [q["answered_by"]])
    return msg


def decide(conn, project: Any, user, qid: str, decision: str, note: str = "") -> dict:
    """The stakeholder, signed in, accepts or rejects the answer (a project member with the Stakeholder role)."""
    p = pj.project_row(conn, project)
    pw.need(conn, p, user, "read")
    if p.get("status") in pw.FROZEN:
        raise EditError(f"{p['name']} is {p['status']}: it is read only.", 409)
    if "stakeholder" not in pj.my_roles(conn, p, user):
        raise EditError("Accepting an answer in the application is for the project's stakeholders: a contributor records an "
                        "acceptance given outside instead.", 403)
    q = _question(conn, p, qid)
    return {"id": qid, "message": _decide(conn, p, q, user, decision, user.username, _clean(note, 2000), "", None, None)}


def record(conn, project: Any, user, qid: str, data: dict, file_name: str = "", content: bytes = b"") -> dict:
    """A contributor records the stakeholder's decision given outside the application: who, when, a note and optional
    evidence (kept in 00_Project/Sign-off evidence)."""
    p = _project(conn, project, user)
    q = _question(conn, p, qid)
    by = _clean(data.get("by") or data.get("accepted_by"), 200)
    if not by:
        raise EditError("Say which stakeholder decided.")
    on = _clean(data.get("on"), 10)
    if on and not re.match(r"^\d{4}-\d{2}-\d{2}$", on):
        raise EditError("The date is YYYY-MM-DD.")
    evidence = None
    if content:
        doc = pw._store(conn, p, user, pw.EVIDENCE, file_name or "evidence", content, origin="evidence", kind="Artifact")
        evidence = (_one(conn, "SELECT id FROM proj.documents WHERE guid::text = :g", g=doc["id"]) or {}).get("id")
    msg = _decide(conn, p, q, user, data.get("decision") or "accepted", by, _clean(data.get("note"), 2000), user.username, on or None, evidence)
    return {"id": qid, "message": msg + (" Evidence kept." if evidence else "")}


def reopen(conn, project: Any, user, qid: str, note: str = "") -> dict:
    """A contributor opens an answered or accepted question again (its answer is kept, to be changed)."""
    p = _project(conn, project, user)
    q = _question(conn, p, qid)
    if q["status"] == "open":
        return {"id": qid, "message": "It is open already."}
    if not _clean(note):
        raise EditError("Say why it is opened again.")
    conn.execute(text("""UPDATE proj.key_questions SET status = 'open', accepted_by = '', accepted_at = NULL, accept_note = '',
                                accept_recorded_by = '', evidence_document_id = NULL WHERE id = :i"""), {"i": q["id"]})
    _event(conn, q["id"], user, "reopened", "open", note)
    return {"id": qid, "message": f"{_qn(conn, p, q)} is open again."}


def delete_question(conn, project: Any, user, qid: str) -> dict:
    p = _project(conn, project, user)
    q = _question(conn, p, qid)
    conn.execute(text("DELETE FROM proj.key_questions WHERE id = :i"), {"i": q["id"]})
    return {"id": qid, "message": "Key question removed (its viewpoints stay in the project)."}


# ---------------------------------------------------------------- placeholder viewpoints
def _next_code(conn, p: dict) -> str:
    used = [r["code"] for r in _rows(conn, "SELECT code FROM proj.placeholder_viewpoints WHERE project_id = :p", p=p["id"])]
    n = max([int(m.group(1)) for c in used if (m := re.match(r"^PH-(\d+)$", c))] or [0]) + 1
    return f"PH-{n:02d}"


def _insert_placeholder(conn, p: dict, user, data: dict) -> dict:
    name = _clean(data.get("name"), 200)
    if not name:
        raise EditError("Name the placeholder viewpoint.")
    kind = data.get("kind") or "text"
    if kind not in ("text", "file"):
        raise EditError("A placeholder viewpoint is a text or a file.")
    ft = (data.get("file_type") or "").lower().lstrip(".") if kind == "file" else ""
    if kind == "file" and ft not in blank_files.TYPES:
        raise EditError(f"Choose the kind of file: {', '.join(blank_files.TYPES)}.")
    code = _next_code(conn, p)
    conn.execute(text("""INSERT INTO proj.placeholder_viewpoints (project_id, code, name, description, kind, file_type, created_by)
                         VALUES (:p, :c, :n, :d, :k, :f, :u)"""),
                 {"p": p["id"], "c": code, "n": name, "d": _clean(data.get("description")), "k": kind, "f": ft, "u": user.username})
    return {"code": code, "name": name, "kind": kind}


def add_placeholder(conn, project: Any, user, data: dict) -> dict:
    """A placeholder viewpoint; a file one gets its empty file in the project's files (make_files, after the commit)."""
    p = _project(conn, project, user)
    ph = _insert_placeholder(conn, p, user, data)
    for qid in data.get("questions") or []:
        q = _question(conn, p, qid)
        conn.execute(text("INSERT INTO proj.question_viewpoints (question_id, viewpoint) VALUES (:q, :v) ON CONFLICT DO NOTHING"),
                     {"q": q["id"], "v": ph["code"]})
    return {**ph, "message": f"Placeholder viewpoint {ph['code']} {ph['name']} added."}


def _placeholder(conn, p: dict, code: str) -> dict:
    ph = _one(conn, "SELECT * FROM proj.placeholder_viewpoints WHERE project_id = :p AND code = :c", p=p["id"], c=code)
    if not ph:
        raise EditError("No such placeholder viewpoint in this project.", 404)
    return ph


def change_placeholder(conn, project: Any, user, code: str, data: dict) -> dict:
    p = _project(conn, project, user)
    ph = _placeholder(conn, p, code)
    name = _clean(data.get("name", ph["name"]), 200)
    if not name:
        raise EditError("Name the placeholder viewpoint.")
    conn.execute(text("UPDATE proj.placeholder_viewpoints SET name = :n, description = :d WHERE id = :i"),
                 {"n": name, "d": _clean(data.get("description", ph["description"])), "i": ph["id"]})
    return {"code": code, "message": f"{code} saved."}


def delete_placeholder(conn, project: Any, user, code: str) -> dict:
    p = _project(conn, project, user)
    ph = _placeholder(conn, p, code)
    _drop_placeholder(conn, p, ph)
    return {"code": code, "message": f"{code} {ph['name']} removed" + (" (its file stays in the project's files)." if ph["document_id"] else ".")}


def _drop_placeholder(conn, p: dict, ph: dict) -> None:
    conn.execute(text("""DELETE FROM proj.question_viewpoints qv USING proj.key_questions q
                          WHERE q.id = qv.question_id AND q.project_id = :p AND qv.viewpoint = :c"""), {"p": p["id"], "c": ph["code"]})
    conn.execute(text("DELETE FROM proj.placeholder_viewpoints WHERE id = :i"), {"i": ph["id"]})


def waiting_files(conn, p: dict) -> int:
    return (_one(conn, """SELECT count(*) AS n FROM proj.placeholder_viewpoints WHERE project_id = :p AND kind = 'file'
                           AND document_id IS NULL""", p=p["id"]) or {"n": 0})["n"]


def make_files(conn, project: Any, user) -> dict:
    """The empty file of each file placeholder that has none yet, put in the project's files (00_Project/Project files).
    One that cannot be stored now (Documents not up) is left to try again."""
    p = _project(conn, project, user)
    made, left = [], []
    for ph in _rows(conn, """SELECT * FROM proj.placeholder_viewpoints WHERE project_id = :p AND kind = 'file' AND document_id IS NULL
                              ORDER BY code""", p=p["id"]):
        name = blank_files.file_name(f"{ph['code']} {ph['name']}", ph["file_type"])
        try:
            doc = pw._store(conn, pj.project_row(conn, p["guid"]), user, pw.PROJECT_FILES, name,
                            blank_files.make(ph["file_type"], ph["name"]), origin="placeholder", kind="Artifact")
        except Exception as exc:  # noqa: BLE001 - Documents down or busy: the rest is tried, this one later
            left.append(f"{ph['code']} ({exc})")
            continue
        conn.execute(text("""UPDATE proj.placeholder_viewpoints SET document_id = (SELECT id FROM proj.documents WHERE guid::text = :g)
                              WHERE id = :i"""), {"g": doc["id"], "i": ph["id"]})
        made.append(name)
    msg = f"Made {len(made)} empty file{'s' if len(made) != 1 else ''} in the project's files." if made else "No file to make."
    if left:
        msg += f" Not made yet: {', '.join(left)}. Try again in a minute."
    return {"made": made, "left": left, "message": msg}


# ---------------------------------------------------------------- the wizard
def from_wizard(conn, p: dict, user, d: dict, own_codes: dict[str, str], editing: bool) -> None:
    """The Key questions and Viewpoints steps, as they should be. d:
        key_questions        [{id (existing), question, asked_by, approach, viewpoints: [code | "own:<key>" | "ph:<key>"]}]
        key_questions_seen   (editing) the ids the wizard showed: one shown and gone is removed; others added meanwhile stay
        placeholder_viewpoints  [{code (existing) | key (new), name, description, kind, file_type}]
        removed_placeholders [codes]
    own_codes: the key of each viewpoint made in this save (own_viewpoints) -> its PV- code."""
    if "key_questions" not in d and "placeholder_viewpoints" not in d:
        return
    ph_codes: dict[str, str] = {}
    gone = set(d.get("removed_placeholders") or []) if editing else set()
    for ph in d.get("placeholder_viewpoints") or []:
        if ph.get("code"):
            if editing and ph["code"] not in gone:
                row = _one(conn, "SELECT * FROM proj.placeholder_viewpoints WHERE project_id = :p AND code = :c", p=p["id"], c=ph["code"])
                if row and _clean(ph.get("name"), 200):
                    conn.execute(text("UPDATE proj.placeholder_viewpoints SET name = :n, description = :d WHERE id = :i"),
                                 {"n": _clean(ph.get("name"), 200), "d": _clean(ph.get("description")), "i": row["id"]})
                continue
            if not editing:         # a derived project: its parent's placeholders come as new ones
                ph = {k: v for k, v in ph.items() if k != "code"} | {"key": ph.get("key") or ph["code"]}
            else:
                continue
        if not _clean(ph.get("name")):
            continue
        made = _insert_placeholder(conn, p, user, ph)
        ph_codes[str(ph.get("key") or made["code"])] = made["code"]
    for code in gone:
        row = _one(conn, "SELECT * FROM proj.placeholder_viewpoints WHERE project_id = :p AND code = :c", p=p["id"], c=code)
        if row:
            _drop_placeholder(conn, p, row)

    def resolve(ref: str) -> str | None:
        if ref.startswith("own:"):
            return own_codes.get(ref[4:])
        if ref.startswith("ph:"):
            return ph_codes.get(ref[3:])
        if ref.startswith("PH-") and not editing:     # a derived project: the parent's placeholder, made again here
            return ph_codes.get(ref)
        return ref

    have, lib = _known(conn, p)                       # a viewpoint taken out in the same save no longer answers anything
    wanted = [q for q in d.get("key_questions") or [] if _clean(q.get("question"))]
    if editing:
        keep = {str(q["id"]) for q in wanted if q.get("id")}
        seen = [str(x) for x in d.get("key_questions_seen") or []]
        for g in seen:
            if g not in keep:
                conn.execute(text("DELETE FROM proj.key_questions WHERE project_id = :p AND guid::text = :g"), {"p": p["id"], "g": g})
    for n, q in enumerate(wanted, start=1):
        codes = [c for c in (resolve(str(r)) for r in q.get("viewpoints") or []) if c and (c in have or c in lib)]
        if editing and q.get("id"):
            row = _one(conn, "SELECT * FROM proj.key_questions WHERE project_id = :p AND guid::text = :g", p=p["id"], g=str(q["id"]))
            if row:
                if any(_clean(q.get(k)) != _clean(row[k]) for k in ("question", "asked_by", "approach")):
                    _changed(conn, row, user, _clean(q["question"]) != _clean(row["question"]))
                conn.execute(text("""UPDATE proj.key_questions SET sort_order = :s, question = :q, asked_by = :a, approach = :ap,
                                            changed_by = :u, changed_at = now() WHERE id = :i"""),
                             {"s": n, "q": _clean(q["question"], 1000), "a": _clean(q.get("asked_by"), 500), "ap": _clean(q.get("approach")),
                              "u": user.username, "i": row["id"]})
                set_viewpoints(conn, p, row["id"], codes)
                continue
        row = _insert_question(conn, p, user, q, seq=n)
        set_viewpoints(conn, p, row["id"], codes)
    tidy(conn, p)
