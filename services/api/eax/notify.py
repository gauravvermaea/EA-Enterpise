"""Notifications (phase 8.1, D209): what happened and who must know.

A model's notifications go to everyone with a role on that model, snapshot at the moment they are made. Those that
need action (a metamodel version offered, changes waiting for a committer, a request sent to you) stay open until
someone resolves them with a note, once for everyone who received them; information ones are read or dismissed by
each person. Every notification is also queued for the installation's webhooks (eax/webhooks.py); never email.

Most model notifications come from the audit trail: on_audit() is called by audit.record() for every action, so
whatever the screens, the API or MCP do, the same actions notify.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

CATEGORIES = ("commit", "metamodel", "request", "model", "system", "task")

# audit action -> (kind, category, needs action, title template); {actor} {model} {detail}
FROM_AUDIT: dict[str, tuple[str, str, bool, str]] = {
    "changes.request": ("commit.requested", "commit", True, "{actor} asked for changes to be committed in {model}"),
    "changes.commit": ("commit.committed", "commit", False, "{actor} committed changes in {model}"),
    "changes.reject": ("commit.rejected", "commit", False, "{actor} rejected changes in {model}"),
    "changes.send-back": ("commit.sent_back", "commit", False, "{actor} sent changes back in {model}"),
    "changes.withdraw": ("commit.withdrawn", "commit", False, "{actor} withdrew a commit request in {model}"),
    "commit.roll_back": ("commit.rolled_back", "commit", False, "{actor} rolled back a commit in {model}"),
    "model.lock": ("model.locked", "model", False, "{actor} locked {model}"),
    "model.unlock": ("model.unlocked", "model", False, "{actor} unlocked {model}"),
    "tag.create": ("model.tagged", "model", False, "{actor} tagged {model}{detail}"),
    "load.added": ("model.loaded", "model", False, "{actor} loaded a sheet into {model}{detail}"),
    "merge.apply": ("model.merged", "model", False, "{actor} merged into {model}"),
    "model.copied": ("model.copied", "model", False, "{actor} copied {model}"),
    "model.archived": ("model.archived", "model", False, "{actor} archived {model}"),
    "model.reactivated": ("model.reactivated", "model", False, "{actor} reactivated {model}"),
    "model.published": ("model.published", "model", False, "{actor} published {model}"),
}
# a decision on the commit requests of a model resolves the open "asked for a commit" notifications of that model
RESOLVES_COMMIT_REQUESTS = {"changes.commit": "Committed", "changes.reject": "Rejected", "changes.send-back": "Sent back",
                            "changes.withdraw": "Withdrawn"}
LINKS = {"commit": "#/metamodel/{m}/changes", "model": "#/metamodel/{m}"}


def _rows(conn, sql: str, **p) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), p).mappings()]


def _one(conn, sql: str, **p) -> dict | None:
    r = conn.execute(text(sql), p).mappings().first()
    return dict(r) if r else None


def model_people(conn, model_id: int) -> list[str]:
    """Everyone with a role on the model (D209)."""
    return [r["username"] for r in _rows(conn, "SELECT DISTINCT username FROM core.model_users WHERE model_id = :m ORDER BY 1",
                                         m=model_id)]


def _model(conn, ref) -> dict | None:
    if ref is None or ref == "":
        return None
    if isinstance(ref, int):
        return _one(conn, "SELECT id, guid, name FROM core.models WHERE id = :m", m=ref)
    try:
        return _one(conn, "SELECT id, guid, name FROM core.models WHERE guid = CAST(:g AS uuid)", g=str(ref))
    except Exception:  # noqa: BLE001 - not a guid
        return None


def create(conn, *, kind: str, category: str, title: str, actor: str, body: str = "", link: str = "",
           model_id: int | None = None, recipients: list[str] | None = None, needs_action: bool = False,
           ref_kind: str = "", ref_id: int | None = None, include_actor: bool = False, webhooks: bool = True) -> int | None:
    """Makes one notification and queues it for the webhooks. recipients: usernames (default: everyone on the model);
    the person who made it happen is left out unless include_actor. Returns its id (None when nobody gets it and no
    webhook wants it)."""
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category}")
    people = recipients if recipients is not None else (model_people(conn, model_id) if model_id else [])
    people = sorted({p.lower() for p in people if p and (include_actor or p.lower() != (actor or "").lower())})
    hooks = _rows(conn, "SELECT id FROM core.webhooks WHERE enabled AND (kinds = '{}' OR :c = ANY (kinds))", c=category) if webhooks else []
    if not people and not hooks and not (model_id and recipients is None):
        return None
    to_sa = bool(model_id) and recipients is None    # everyone on the model, Super Admins included (global role)
    nid = conn.execute(text("""
        INSERT INTO core.notifications (kind, category, needs_action, model_id, title, body, link, ref_kind, ref_id, actor,
                                        to_super_admins)
        VALUES (:k, :c, :na, :m, :t, :b, :l, :rk, :ri, :a, :sa) RETURNING id"""),
        {"k": kind, "c": category, "na": needs_action, "m": model_id, "t": title[:300], "b": body[:4000], "l": link,
         "rk": ref_kind, "ri": ref_id, "a": actor or "system", "sa": to_sa}).scalar_one()
    for p in people:
        conn.execute(text("INSERT INTO core.notification_recipients (notification_id, username) VALUES (:n, :u) "
                          "ON CONFLICT DO NOTHING"), {"n": nid, "u": p})
    if hooks:
        from . import webhooks as _hooks
        _hooks.queue(conn, nid)
    return nid


def join_super_admin(conn, username: str) -> int:
    """A Super Admin has a role on every model (a global role, not in core.model_users): the model notifications made
    for everyone on a model become theirs when they look (except their own doings)."""
    return conn.execute(text("""
        INSERT INTO core.notification_recipients (notification_id, username)
        SELECT n.id, lower(:u) FROM core.notifications n
         WHERE n.to_super_admins AND lower(n.actor) <> lower(:u)
           AND n.created_at > now() - interval '180 days'
        ON CONFLICT DO NOTHING"""), {"u": username}).rowcount


def resolve_ref(conn, ref_kind: str, ref_id: int, by: str, note: str) -> int:
    """Resolves the open action notifications about one thing (a request closed, a push decided)."""
    return conn.execute(text("""
        UPDATE core.notifications SET resolved_at = now(), resolved_by = :b, resolution = :n
         WHERE needs_action AND resolved_at IS NULL AND ref_kind = :k AND ref_id = :i"""),
        {"b": by, "n": note[:4000], "k": ref_kind, "i": ref_id}).rowcount


def on_audit(conn, *, actor: str, action: str, object_type: str | None, object_id: str | None, details: dict | None) -> None:
    """Called for every audited action: the ones in FROM_AUDIT notify everyone on the model."""
    if action not in FROM_AUDIT or (object_type or "") != "model":
        return
    m = _model(conn, object_id)
    if not m:
        return
    d = details or {}
    kind, category, needs, title = FROM_AUDIT[action]
    detail = ""
    if action == "tag.create" and d.get("name"):
        detail = f" as '{d['name']}'"
    elif action == "load.added" and d.get("name"):
        detail = f" ({d['name']}, {d.get('changes', 0)} changes)"
    body = str(d.get("note") or d.get("message") or "")
    if action in RESOLVES_COMMIT_REQUESTS:
        conn.execute(text("""
            UPDATE core.notifications SET resolved_at = now(), resolved_by = :b, resolution = :n
             WHERE kind = 'commit.requested' AND model_id = :m AND resolved_at IS NULL"""),
            {"b": actor, "m": m["id"], "n": f"{RESOLVES_COMMIT_REQUESTS[action]} by {actor}" + (f": {body}" if body else "")})
    link = LINKS.get(category, "#/metamodel/{m}").format(m=m["guid"])
    doc_id = None
    if action in ("changes.commit", "merge.apply"):
        from . import change_docs
        doc_id = change_docs.for_commit(conn, m["id"], actor, merged=action == "merge.apply")
        if doc_id:
            link = f"#/change-documents/{doc_id}"
    create(conn, kind=kind, category=category, needs_action=needs, model_id=m["id"], actor=actor,
           title=title.format(actor=actor, model=m["name"], detail=detail), body=body, link=link,
           ref_kind="change_document" if doc_id else "", ref_id=doc_id)


# ---------------------------------------------------------------- reading and acting (the person's own)

def _visible(username: str) -> str:
    return "EXISTS (SELECT 1 FROM core.notification_recipients r WHERE r.notification_id = n.id AND r.username = lower(:u))"


def counts(conn, username: str) -> dict:
    r = _one(conn, """
        SELECT count(*) FILTER (WHERE r.read_at IS NULL AND r.dismissed_at IS NULL AND n.resolved_at IS NULL) AS unread,
               count(*) FILTER (WHERE n.needs_action AND n.resolved_at IS NULL) AS open_actions
          FROM core.notifications n JOIN core.notification_recipients r ON r.notification_id = n.id AND r.username = lower(:u)""",
               u=username)
    req = _one(conn, "SELECT count(*) AS n FROM core.requests WHERE receiver = lower(:u) AND status IN ('open', 'in_progress')",
               u=username)
    return {"unread": r["unread"], "open_actions": r["open_actions"], "open_requests": req["n"]}


def listing(conn, username: str, *, show: str = "open", category: str = "", model: str = "", q: str = "",
            limit: int = 100, offset: int = 0) -> dict:
    """show: open (unresolved actions and undismissed information), actions, resolved, all."""
    where = [_visible(username)]
    p: dict[str, Any] = {"u": username, "lim": min(max(limit, 1), 500), "off": max(offset, 0)}
    if show == "open":
        where.append("""((n.needs_action AND n.resolved_at IS NULL) OR (NOT n.needs_action AND NOT EXISTS (
                          SELECT 1 FROM core.notification_recipients r2 WHERE r2.notification_id = n.id
                             AND r2.username = lower(:u) AND r2.dismissed_at IS NOT NULL)))""")
    elif show == "actions":
        where.append("n.needs_action AND n.resolved_at IS NULL")
    elif show == "resolved":
        where.append("(n.resolved_at IS NOT NULL OR EXISTS (SELECT 1 FROM core.notification_recipients r2 "
                     "WHERE r2.notification_id = n.id AND r2.username = lower(:u) AND r2.dismissed_at IS NOT NULL))")
    if category in CATEGORIES:
        where.append("n.category = :c")
        p["c"] = category
    if model:
        where.append("m.guid = CAST(:m AS uuid)")
        p["m"] = model
    if q:
        where.append("(n.title ILIKE :q OR n.body ILIKE :q)")
        p["q"] = f"%{q}%"
    w = " AND ".join(where)
    rows = _rows(conn, f"""
        SELECT n.guid AS id, n.kind, n.category, n.needs_action, n.title, n.body, n.link, n.actor, n.created_at,
               n.resolved_at, n.resolved_by, n.resolution, m.guid AS model_id, m.name AS model_name,
               r.read_at, r.dismissed_at, tt.guid AS task_id,
               (SELECT f.name FROM core.task_files f WHERE f.task_id = tt.id AND f.role = 'result'
                   AND f.created_at > now() - interval '24 hours' ORDER BY f.id DESC LIMIT 1) AS task_file
          FROM core.notifications n LEFT JOIN core.models m ON m.id = n.model_id
          LEFT JOIN core.tasks tt ON n.ref_kind = 'task' AND tt.id = n.ref_id
          JOIN core.notification_recipients r ON r.notification_id = n.id AND r.username = lower(:u)
         WHERE {w} ORDER BY (n.needs_action AND n.resolved_at IS NULL) DESC, n.id DESC LIMIT :lim OFFSET :off""", **p)
    total = _one(conn, f"""SELECT count(*) AS n FROM core.notifications n LEFT JOIN core.models m ON m.id = n.model_id
                            WHERE {w}""", **p)["n"]
    return {"items": rows, "total": total, "counts": counts(conn, username)}


class NotFound(Exception):
    pass


def _mine(conn, username: str, guid) -> dict:
    n = _one(conn, f"""SELECT n.* FROM core.notifications n WHERE n.guid = CAST(:g AS uuid) AND {_visible(username)}""",
             g=str(guid), u=username)
    if not n:
        raise NotFound("No such notification for you.")
    return n


def mark_read(conn, username: str, guids: list | None = None) -> int:
    """Marks some (or, without guids, all) of the person's notifications read."""
    sql = "UPDATE core.notification_recipients r SET read_at = now() WHERE r.username = lower(:u) AND r.read_at IS NULL"
    p: dict[str, Any] = {"u": username}
    if guids:
        sql += " AND r.notification_id IN (SELECT id FROM core.notifications WHERE guid = ANY (CAST(:g AS uuid[])))"
        p["g"] = [str(x) for x in guids]
    return conn.execute(text(sql), p).rowcount


def dismiss(conn, username: str, guid) -> dict:
    n = _mine(conn, username, guid)
    if n["needs_action"] and n["resolved_at"] is None:
        raise ValueError("This one needs action: resolve it with a note of what you did.")
    conn.execute(text("""UPDATE core.notification_recipients SET dismissed_at = now(), read_at = coalesce(read_at, now())
                          WHERE notification_id = :n AND username = lower(:u)"""), {"n": n["id"], "u": username})
    return {"dismissed": True}


def dismiss_all(conn, username: str, category: str = "") -> dict:
    """Every information notification of mine (of one kind, or all) put away and read at once, so the bell and the lists
    stop showing them (owner, 8 Nov 2026); those needing action stay open until resolved."""
    r = conn.execute(text("""UPDATE core.notification_recipients nr SET dismissed_at = now(), read_at = coalesce(read_at, now())
                               FROM core.notifications n
                              WHERE n.id = nr.notification_id AND nr.username = lower(:u) AND nr.dismissed_at IS NULL
                                AND NOT (n.needs_action AND n.resolved_at IS NULL) AND (:c = '' OR n.category = :c)"""),
                     {"u": username, "c": category or ""})
    return {"dismissed": r.rowcount}


def resolve(conn, username: str, guid, note: str) -> dict:
    n = _mine(conn, username, guid)
    if not n["needs_action"]:
        raise ValueError("Only notifications that need action are resolved; dismiss this one.")
    if n["resolved_at"] is not None:
        raise ValueError(f"Already resolved by {n['resolved_by']}.")
    if not (note or "").strip():
        raise ValueError("Say what you did: resolving needs a note.")
    conn.execute(text("""UPDATE core.notifications SET resolved_at = now(), resolved_by = :b, resolution = :r WHERE id = :n"""),
                 {"b": username, "r": note.strip()[:4000], "n": n["id"]})
    conn.execute(text("UPDATE core.notification_recipients SET read_at = coalesce(read_at, now()) WHERE notification_id = :n"),
                 {"n": n["id"]})
    return {"resolved": True}


def payload(conn, nid: int) -> dict:
    """The plain JSON a webhook receives (D209)."""
    n = _one(conn, """SELECT n.*, m.guid AS model_guid, m.name AS model_name FROM core.notifications n
                       LEFT JOIN core.models m ON m.id = n.model_id WHERE n.id = :n""", n=nid)
    return {"id": str(n["guid"]), "kind": n["kind"], "category": n["category"], "needs_action": n["needs_action"],
            "title": n["title"], "body": n["body"], "link": n["link"], "actor": n["actor"],
            "model": {"id": str(n["model_guid"]), "name": n["model_name"]} if n["model_guid"] else None,
            "created_at": n["created_at"].isoformat() if hasattr(n["created_at"], "isoformat") else n["created_at"]}


def jsonable(v):
    return json.loads(json.dumps(v, default=str))
