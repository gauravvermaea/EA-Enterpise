"""Each person's data (R2.53, D632; owner, 12 Nov 2026, 21:43: "move user preferences etc into a separate DB and make it a
separate microservice"; 13 Nov 2026: notifications and requests live here, the front door routes /api/v1/me/... to the
personal data service, and when it is down the rest keeps working while notifications wait and are sent later).

The personal schema (notifications and their recipients, requests and their comments, favourites, saved views, skills,
settings) is reached through its own connection string (EAX_PERSONAL_DB_URL, D630): by default the repository's
database, the same connection and transaction as the rest. No query joins it to the repository's tables: what it refers
to in the repository (a model, a task) is kept by id and looked up there separately.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import databases

log = logging.getLogger(__name__)


class Unavailable(Exception):
    """The personal data service's schema cannot be reached right now."""


def on(conn):
    """Where personal statements run: the repository's connection (conn, or the one beside a projects' connection,
    D266) when its schema is in the repository's database, else its own database."""
    info = getattr(conn, "info", None)
    return databases.on("personal", (info or {}).get("core", conn))


def apart() -> bool:
    return databases.own(databases.BY_KEY["personal"])


def rows(conn, sql: str, **p) -> list[dict]:
    try:
        return [dict(r) for r in on(conn).execute(text(sql), p).mappings()]
    except DBAPIError as exc:
        if apart():
            raise Unavailable(str(exc).splitlines()[0][:200]) from exc
        raise


def one(conn, sql: str, **p) -> dict | None:
    r = rows(conn, sql, **p)
    return r[0] if r else None


def run(conn, sql: str, **p):
    try:
        return on(conn).execute(text(sql), p)
    except DBAPIError as exc:
        if apart():
            raise Unavailable(str(exc).splitlines()[0][:200]) from exc
        raise


# ---------------------------------------------------------------- what personal rows refer to in the repository
def models_by_id(conn, ids) -> dict[int, dict]:
    """{model id: {guid, name}} from the repository, for the model ids personal rows keep."""
    ids = sorted({int(i) for i in ids if i is not None})
    if not ids:
        return {}
    conn = (getattr(conn, "info", None) or {}).get("core", conn)
    return {int(r["id"]): {"guid": r["guid"], "name": r["name"]}
            for r in conn.execute(text("SELECT id, guid, name FROM core.models WHERE id = ANY(:i)"), {"i": ids}).mappings()}


def model_ids_by_guid(conn, guids) -> dict[str, int]:
    gs = [str(g) for g in guids if g]
    if not gs:
        return {}
    return {str(r["guid"]): int(r["id"]) for r in conn.execute(
        text("SELECT id, guid FROM core.models WHERE guid = ANY(CAST(:g AS uuid[]))"), {"g": gs}).mappings()}


def forget_models(conn, model_ids: list[int]) -> None:
    """A model purged from the repository: the personal rows about it go too (no foreign key crosses schemas, D632)."""
    if not model_ids:
        return
    for sql in ("DELETE FROM personal.notifications WHERE model_id = ANY(:i)",
                "DELETE FROM personal.favourites WHERE model_id = ANY(:i)",
                "DELETE FROM personal.saved_views WHERE model_id = ANY(:i)"):
        try:
            run(conn, sql, i=list(model_ids))
        except Unavailable as exc:
            log.warning("personal rows of purged models %s kept: %s", model_ids, exc)
            return


# ---------------------------------------------------------------- notifications, queued while the service is away
def queue(conn, payload: dict, why: str = "") -> None:
    conn.execute(text("INSERT INTO core.personal_outbox (kind, payload, last_error) VALUES ('notification', CAST(:p AS jsonb), :e)"),
                 {"p": json.dumps(payload, default=str), "e": why[:500]})


def write_notification(conn, n: dict, people: list[str]) -> int:
    """The notification and its recipients in the personal schema; its id."""
    nid = run(conn, """
        INSERT INTO personal.notifications (kind, category, needs_action, model_id, title, body, link, ref_kind, ref_id,
                                            actor, to_super_admins)
        VALUES (:k, :c, :na, :m, :t, :b, :l, :rk, :ri, :a, :sa) RETURNING id""",
              k=n["kind"], c=n["category"], na=n["needs_action"], m=n["model_id"], t=n["title"], b=n["body"], l=n["link"],
              rk=n["ref_kind"], ri=n["ref_id"], a=n["actor"], sa=n["to_super_admins"]).scalar_one()
    for p in people:
        run(conn, "INSERT INTO personal.notification_recipients (notification_id, username) VALUES (:n, :u) ON CONFLICT DO NOTHING",
            n=nid, u=p)
    return int(nid)


def flush(conn, limit: int = 200) -> dict[str, Any]:
    """Sends what waited in the outbox (a job every minute, eax.personal_flush): oldest first; stops at the first that
    still cannot be sent."""
    sent = 0
    for r in conn.execute(text("SELECT id, payload FROM core.personal_outbox ORDER BY id LIMIT :l FOR UPDATE SKIP LOCKED"),
                          {"l": limit}).mappings().all():
        p = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
        try:
            write_notification(conn, p["notification"], p.get("people") or [])
        except Unavailable as exc:
            conn.execute(text("UPDATE core.personal_outbox SET tries = tries + 1, last_error = :e WHERE id = :i"),
                         {"i": r["id"], "e": str(exc)[:500]})
            break
        conn.execute(text("DELETE FROM core.personal_outbox WHERE id = :i"), {"i": r["id"]})
        sent += 1
    left = conn.execute(text("SELECT count(*) FROM core.personal_outbox")).scalar() or 0
    return {"sent": sent, "waiting": int(left)}


# ---------------------------------------------------------------- each person's settings
def get_settings(conn, username: str) -> dict[str, Any]:
    return {r["key"]: r["value"] for r in rows(conn, "SELECT key, value FROM personal.settings WHERE username = lower(:u) ORDER BY key",
                                                u=username)}


def put_setting(conn, username: str, key: str, value: Any) -> dict:
    import re
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,79}", key or ""):
        raise ValueError("A setting's key is lower-case letters, digits, dots, dashes or underscores (up to 80).")
    blob = json.dumps(value, default=str)
    if len(blob) > 64_000:
        raise ValueError("A setting is at most 64 KB.")
    run(conn, """INSERT INTO personal.settings (username, key, value) VALUES (lower(:u), :k, CAST(:v AS jsonb))
                 ON CONFLICT (username, key) DO UPDATE SET value = EXCLUDED.value, modified_at = now()""", u=username, k=key, v=blob)
    return {"key": key, "value": value}


def delete_setting(conn, username: str, key: str) -> dict:
    run(conn, "DELETE FROM personal.settings WHERE username = lower(:u) AND key = :k", u=username, k=key)
    return {"deleted": key}
