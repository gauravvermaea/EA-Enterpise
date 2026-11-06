"""Restore notifications (phase 8.4, D229): everyone hears when a restore starts and when it ends.

* Started: an infrastructure restore asks the API (POST /api/v1/internal/restore-started, with the operations token)
  before anything is stopped; the notification goes to everyone's bell and its webhooks are sent at once, because a
  full restore replaces the database (and with it the bell and the queued deliveries) a moment later. A model restore
  says so itself.
* Ended (finished, failed or interrupted): for an infrastructure restore the job runner looks every minute at the
  restore records (work/backups/restores) and announces the newest ended one if the database does not have its
  notification yet; after a full restore that database is the restored one, so the announcement is made in it, with
  when it started and by whom. A model restore announces its end itself.
Everyone is every person EA Explorer has seen sign in (core.known_users). Each restore is announced once per database:
the link (#/admin/restores/<id>) identifies it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from . import notify

log = logging.getLogger(__name__)

START = "system.restore.start"
END = "system.restore.end"
WHAT = {"full": "everything", "app": "the application config", "app+data": "the application and its data",
        "db": "the databases", "files": "the files", "new": "as a new model", "over": "over the model",
        "all": "every model, each over itself"}
RECENT = timedelta(days=2)     # older ended restores are not announced again after an older database is restored


def link(rid: str) -> str:
    return f"#/admin/restores/{rid}"


def everyone(conn) -> list[str]:
    return [r["u"] for r in notify._rows(conn, "SELECT DISTINCT lower(username) AS u FROM core.known_users")]


def announced(conn, kind: str, rid: str) -> bool:
    return bool(conn.execute(text("SELECT 1 FROM core.notifications WHERE kind = :k AND link = :l LIMIT 1"),
                             {"k": kind, "l": link(rid)}).scalar())


def _label(rec: dict) -> str:
    return "the installation" if rec.get("kind") == "infrastructure" else "a model"


def started(conn, rec: dict, send_now: bool = False) -> int | None:
    """'A backup is being restored' for everyone (once). send_now: the webhooks are sent in this call."""
    if not rec.get("id") or announced(conn, START, rec["id"]):
        return None
    infra = rec.get("kind") == "infrastructure"
    title = (f"Restore started: {rec.get('backup')} ({WHAT.get(rec.get('what'), rec.get('what'))})" if infra else
             f"A model is being restored: {rec.get('backup')} ({WHAT.get(rec.get('what'), rec.get('what'))})")
    body = (f"{rec.get('by') or 'Someone'} started restoring {_label(rec)} from the backup {rec.get('backup')} at "
            f"{rec.get('started')}. " +
            ("EA Explorer is locked for everyone until it has finished (every screen shows the lock page); changes made "
             "since the backup will be lost, and everyone signs in again afterwards." if infra else
             "The model may change under you while it runs."))
    nid = notify.create(conn, kind=START, category="system", title=title, body=body, link=link(rec["id"]),
                        actor=rec.get("by") or "system", recipients=everyone(conn), include_actor=True)
    if nid and send_now:
        from . import webhooks
        try:
            webhooks.deliver_due(conn, notification_id=nid)
        except Exception as exc:  # noqa: BLE001 - the restore goes on; a delivery left pending is retried
            log.warning("restore webhooks not sent at once: %s", exc)
    return nid


def ended(conn, rec: dict) -> int | None:
    """'The restore finished / failed' for everyone (once)."""
    if not rec.get("id") or rec.get("status") == "running" or announced(conn, END, rec["id"]):
        return None
    ok = rec.get("status") == "ok"
    word = {"ok": "finished", "failed": "FAILED", "interrupted": "was INTERRUPTED"}.get(rec.get("status"), rec.get("status"))
    title = f"Restore {word}: {rec.get('backup')} ({WHAT.get(rec.get('what'), rec.get('what'))})"
    if ok and rec.get("kind") == "infrastructure":
        tail = (f"The data is now as it was in the backup {rec.get('backup')}; anything changed after that backup was made "
                "is gone. Sign in again to carry on.")
    elif ok:
        tail = "The model is back as it was in the backup."
    else:
        tail = (f"Nothing was changed: {_label(rec)} is as it was before the restore. Error: {rec.get('error') or '?'}"
                if rec.get("status") == "failed" else (rec.get("error") or ""))
    body = (f"Restore of {_label(rec)} from {rec.get('backup')}, started by {rec.get('by') or '?'} at {rec.get('started')}, "
            f"{word} at {rec.get('finished') or '?'}. {tail}"
            + (f" The state before it is kept as the pinned backup {rec['before']}." if rec.get("before") else ""))
    return notify.create(conn, kind=END, category="system", title=title, body=body, link=link(rec["id"]),
                         actor=rec.get("by") or "system", recipients=everyone(conn), include_actor=True,
                         needs_action=not ok)


def _when(s: str | None) -> datetime | None:
    try:
        return datetime.strptime(s or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def catch_up(conn, records: list[dict], now: datetime | None = None) -> int:
    """Every minute: the newest ended infrastructure restore is announced if this database has not heard of it (after a
    full restore the database is the restored one); a running one that was not announced at its start is announced."""
    now = now or datetime.now(UTC)
    infra = [r for r in records if r.get("kind") == "infrastructure"]     # newest first
    n = 0
    running = next((r for r in infra if r.get("status") == "running"), None)
    if running and started(conn, running):
        n += 1
    last = next((r for r in infra if r.get("status") != "running"), None)
    if last and (_when(last.get("finished")) or now) > now - RECENT and ended(conn, last):
        n += 1
    return n
