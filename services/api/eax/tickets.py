"""Requests between people (phase 8.1, WF-016, D209): like a ticket. Anyone sends another user (or themselves: a note) a subject and a body
(no attachments, no links to models or items); it goes open -> in progress -> done or declined (done and declined
need a note); both can comment; the sender is told at each step and the receiver of each comment. Private to the two:
every read and write checks the person is the sender or the receiver. Not passed on to someone else.
"""

from __future__ import annotations

from sqlalchemy import text

from . import notify
from .notify import _one, _rows

STATUSES = ("open", "in_progress", "done", "declined")
LABEL = {"open": "Open", "in_progress": "In progress", "done": "Done", "declined": "Declined"}


class RequestError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _known_user(conn, username: str) -> bool:
    """Someone EA Explorer knows: a role on a model, or seen signing in (the reports' list of people)."""
    u = username.lower()
    return bool(_one(conn, "SELECT 1 AS x FROM core.model_users WHERE username = :u LIMIT 1", u=u)
                or _one(conn, "SELECT 1 AS x FROM audit.events WHERE lower(actor) = :u LIMIT 1", u=u))


def people(conn, q: str = "", limit: int = 30) -> list[dict]:
    """People a request can be sent to: everyone with a role on a model or who has used EA Explorer."""
    return _rows(conn, """
        SELECT username FROM (
            SELECT DISTINCT username FROM core.model_users
            UNION SELECT DISTINCT lower(actor) FROM audit.events WHERE actor NOT LIKE '%:%' AND actor <> ''
        ) p WHERE username ILIKE :q AND username NOT IN ('system', 'break-glass') ORDER BY username LIMIT :l""",
                 q=f"%{q}%", l=limit)


def _out(r: dict, me: str) -> dict:
    return {"id": str(r["guid"]), "number": r["number"], "subject": r["subject"], "body": r["body"], "sender": r["sender"],
            "receiver": r["receiver"], "status": r["status"], "status_label": LABEL[r["status"]], "close_note": r["close_note"],
            "via": r["via"], "created_at": r["created_at"], "updated_at": r["updated_at"], "closed_at": r["closed_at"],
            "mine_to_act": r["receiver"] == me and r["status"] in ("open", "in_progress"),
            "comments": r.get("comments", None)}


def _get(conn, guid, me: str) -> dict:
    ref = str(guid)
    where = "number = :g" if ref.isdigit() else "guid = CAST(:g AS uuid)"
    r = _one(conn, f"SELECT * FROM core.requests WHERE {where}", g=int(ref) if ref.isdigit() else ref)
    if not r or me not in (r["sender"], r["receiver"]):
        raise RequestError("No such request for you.", 404)
    return r


def _notify(conn, r: dict, to: str, actor: str, title: str, body: str = "", needs_action: bool = False) -> None:
    notify.create(conn, kind="request." + ("new" if needs_action else "update"), category="request", title=title,
                  body=body, actor=actor, recipients=[to], needs_action=needs_action,
                  link=f"#/notifications/requests/{r['number']}", ref_kind="request", ref_id=r["id"])


def send(conn, me: str, receiver: str, subject: str, body: str, via: str = "screen") -> dict:
    me, receiver = me.lower(), (receiver or "").strip().lower()
    if not receiver:
        raise RequestError("Choose who the request is for.")
    if receiver != me and not _known_user(conn, receiver):   # to oneself: a note (owner, 6 Nov 2026)
        raise RequestError(f"{receiver} is not someone EA Explorer knows (no role on a model and never signed in).", 404)
    subject, body = (subject or "").strip(), (body or "").strip()
    if not subject:
        raise RequestError("Give the request a subject.")
    if len(subject) > 200:
        raise RequestError("Keep the subject under 200 characters.")
    r = _one(conn, """INSERT INTO core.requests (subject, body, sender, receiver, via) VALUES (:s, :b, :f, :t, :v) RETURNING *""",
             s=subject, b=body[:20000], f=me, t=receiver, v=via if via in ("screen", "api", "mcp") else "api")
    if receiver != me:   # a note to oneself needs no notification
        _notify(conn, r, receiver, me, f"Request #{r['number']} from {me}: {subject}", body[:500], needs_action=True)
    return _out(r, me)


def listing(conn, me: str, box: str = "received", status: str = "active", q: str = "") -> dict:
    """box: received, sent; status: active (open and in progress), closed (done and declined), all, or one status."""
    me = me.lower()
    where = ["receiver = :me" if box == "received" else "sender = :me"]
    if status == "active":
        where.append("status IN ('open', 'in_progress')")
    elif status == "closed":
        where.append("status IN ('done', 'declined')")
    elif status in STATUSES:
        where.append("status = :st")
    if q:
        where.append("(subject ILIKE :q OR body ILIKE :q OR CAST(number AS text) = :n)")
    rows = _rows(conn, f"""SELECT r.*, (SELECT count(*) FROM core.request_comments c WHERE c.request_id = r.id) AS comment_count
                            FROM core.requests r WHERE {' AND '.join(where)} ORDER BY updated_at DESC LIMIT 300""",
                 me=me, st=status, q=f"%{q}%", n=q.strip())
    counts = _one(conn, """SELECT count(*) FILTER (WHERE receiver = :me AND status IN ('open', 'in_progress')) AS received_active,
                                  count(*) FILTER (WHERE sender = :me AND status IN ('open', 'in_progress')) AS sent_active
                             FROM core.requests WHERE :me IN (sender, receiver)""", me=me)
    return {"items": [{**_out(r, me), "comment_count": r["comment_count"]} for r in rows], "counts": counts}


def get(conn, me: str, guid) -> dict:
    r = _get(conn, guid, me.lower())
    comments = _rows(conn, "SELECT author, body, status, created_at FROM core.request_comments WHERE request_id = :r ORDER BY id",
                     r=r["id"])
    return _out({**r, "comments": comments}, me.lower())


def comment(conn, me: str, guid, body: str) -> dict:
    me = me.lower()
    r = _get(conn, guid, me)
    body = (body or "").strip()
    if not body:
        raise RequestError("Write the comment first.")
    conn.execute(text("INSERT INTO core.request_comments (request_id, author, body) VALUES (:r, :a, :b)"),
                 {"r": r["id"], "a": me, "b": body[:20000]})
    conn.execute(text("UPDATE core.requests SET updated_at = now() WHERE id = :r"), {"r": r["id"]})
    other = r["receiver"] if me == r["sender"] else r["sender"]
    if other != me:
        _notify(conn, r, other, me, f"{me} commented on request #{r['number']}: {r['subject']}", body[:500])
    return get(conn, me, r["guid"])


def set_status(conn, me: str, guid, status: str, note: str = "") -> dict:
    """The receiver moves it along: in progress, done or declined (with a note); the sender may reopen a closed one."""
    me = me.lower()
    r = _get(conn, guid, me)
    if status not in STATUSES:
        raise RequestError(f"Status is one of {', '.join(STATUSES)}.")
    if status == r["status"]:
        raise RequestError(f"It is already {LABEL[status].lower()}.")
    note = (note or "").strip()
    if status == "open":
        if r["status"] not in ("done", "declined"):
            raise RequestError("Only a closed request is opened again.")
    elif me != r["receiver"]:
        raise RequestError("Only the person it was sent to moves it along.", 403)
    if status in ("done", "declined") and not note:
        raise RequestError(f"Say why it is {LABEL[status].lower()}: a note is needed.")
    closed = status in ("done", "declined")
    conn.execute(text("""UPDATE core.requests SET status = :s, close_note = CASE WHEN :c THEN :n ELSE '' END,
                                closed_at = CASE WHEN :c THEN now() END, updated_at = now() WHERE id = :r"""),
                 {"s": status, "c": closed, "n": note[:20000], "r": r["id"]})
    trail = note or {"in_progress": "Started", "open": "Opened again"}.get(status, LABEL[status])
    conn.execute(text("INSERT INTO core.request_comments (request_id, author, body, status) VALUES (:r, :a, :b, :s)"),
                 {"r": r["id"], "a": me, "b": trail, "s": status})
    if closed:
        notify.resolve_ref(conn, "request", r["id"], me, f"{LABEL[status]}: {note}")
    other = r["receiver"] if me == r["sender"] else r["sender"]
    if other != me:
        _notify(conn, r, other, me, f"Request #{r['number']} is {LABEL[status].lower()}: {r['subject']}", note[:500],
                needs_action=status == "open")   # opened again: back with the receiver to act on
    return get(conn, me, r["guid"])
