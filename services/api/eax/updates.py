"""Updates in the API (phase 36, D417, D512): the operations helper's record of updates copied into the database, the
banner before a scheduled update, the What's new note after one, and the administrators told when an update fails,
finishes or the installed version is out of support (8.5, D515).

The update itself runs in the updater container (eaxcli/updater.py), started by the operations helper
(services/ops/updates.py); this module only reads and relays. The host's record (work/updates/history.json) comes
first: operations.update_history is its copy (D248: rows only).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from . import databases, notify

LINK = "#/admin/updates"
STATUSES = ("running", "failed", "ok", "rolling-back", "rolled-back", "not-started", "scheduled", "cancelled")


def _ts(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def _row(h: dict) -> dict:
    frm = h.get("from") if isinstance(h.get("from"), dict) else {}
    st = h.get("status") if h.get("status") in STATUSES else "failed"
    return {"id": str(h.get("id") or "")[:60], "kind": h.get("kind") if h.get("kind") in ("update", "rollback") else "update",
            "status": st, "channel": h.get("channel") if h.get("channel") in ("prod", "rc", "latest") else "prod",
            "from_version": str(frm.get("version") or ""), "from_commit": str(frm.get("commit") or ""),
            "to_version": str(h.get("to") or ""), "failed_version": str(h.get("failed_version") or ""),
            "by_user": str(h.get("by") or ""), "started_at": _ts(h.get("started")), "finished_at": _ts(h.get("finished")),
            "backup": str(h.get("backup") or ""), "error": str(h.get("error") or "")[:4000],
            "notes": str(h.get("notes") or "")[:20000], "steps": json.dumps(h.get("steps") or [])}


def sync(conn, ops_status: dict) -> int:
    """Copies the host's history and the update running into operations.update_history (by id). Returns rows written."""
    rows = list(ops_status.get("history") or [])
    if ops_status.get("current"):
        rows.append(ops_status["current"])
    n = 0
    for h in rows:
        r = _row(h)
        if not r["id"]:
            continue
        databases.on("operations", conn).execute(text("""
            INSERT INTO operations.update_history (id, kind, status, channel, from_version, from_commit, to_version, failed_version,
                                             by_user, started_at, finished_at, backup, error, notes, steps)
            VALUES (:id, :kind, :status, :channel, :from_version, :from_commit, :to_version, :failed_version, :by_user,
                    :started_at, :finished_at, :backup, :error, :notes, CAST(:steps AS jsonb))
            ON CONFLICT (id) DO UPDATE SET kind = EXCLUDED.kind, status = EXCLUDED.status, channel = EXCLUDED.channel,
                from_version = EXCLUDED.from_version, from_commit = EXCLUDED.from_commit, to_version = EXCLUDED.to_version,
                failed_version = EXCLUDED.failed_version, by_user = EXCLUDED.by_user, started_at = EXCLUDED.started_at,
                finished_at = EXCLUDED.finished_at, backup = EXCLUDED.backup, error = EXCLUDED.error, notes = EXCLUDED.notes,
                steps = EXCLUDED.steps, recorded_at = now()
            WHERE (operations.update_history.status, operations.update_history.finished_at) IS DISTINCT FROM (EXCLUDED.status, EXCLUDED.finished_at)"""), r)
        n += 1
    return n


def history(conn, limit: int = 100) -> list[dict]:
    out = databases.on("operations", conn).execute(text("""SELECT id, kind, status, channel, from_version, from_commit, to_version, failed_version, by_user,
                                      started_at, finished_at, backup, error, notes, steps, sample
                                 FROM operations.update_history ORDER BY started_at DESC NULLS LAST, recorded_at DESC LIMIT :n"""),
                       {"n": limit}).mappings().all()
    return [dict(r) for r in out]


def _admins(conn) -> list[str]:
    return [r[0] for r in conn.execute(text("""SELECT lower(username) FROM core.known_users
                                                 WHERE 'super-admin' = ANY (roles) OR 'it-admin' = ANY (roles)"""))]


def tell(conn) -> int:
    """Each update that failed, finished or was rolled back is told once to the Super Admins and IT Admins (D515)."""
    told = 0
    for r in databases.on("operations", conn).execute(text("""SELECT id, status, to_version, from_version, failed_version, error, by_user, sample
                                    FROM operations.update_history WHERE status IN ('failed', 'ok', 'rolled-back', 'not-started')
                                     AND notified IS DISTINCT FROM status AND NOT sample""")).mappings().all():
        title, needs = {
            "failed": (f"The update to {r['to_version']} failed: choose Retry or Roll back", True),
            "ok": (f"EA Explorer was updated to {r['to_version']}", False),
            "rolled-back": (f"EA Explorer was rolled back to {r['from_version']} ({r['failed_version']} failed)", False),
            "not-started": (f"The update to {r['to_version']} did not start", True),
        }[r["status"]]
        notify.create(conn, kind=f"update.{r['status']}", category="system", title=title, body=r["error"] or "",
                      link=LINK, actor=r["by_user"] or "system", recipients=_admins(conn), needs_action=needs,
                      include_actor=True)
        databases.on("operations", conn).execute(text("UPDATE operations.update_history SET notified = status WHERE id = :i"), {"i": r["id"]})
        told += 1
    return told


def tell_support(conn, installed: str, releases: list[str]) -> bool:
    """The installed version out of support (the policy in eaxcli/releases.py and docs/release-process.md): the
    administrators are told once per version."""
    from .releases_policy import supported
    ok, why = supported(installed, releases)
    if ok:
        return False
    kind = f"update.unsupported.{installed}"
    from . import personal as P
    try:
        if P.one(conn, "SELECT 1 AS x FROM personal.notifications WHERE kind = :k LIMIT 1", k=kind):
            return False
    except P.Unavailable:
        return False
    notify.create(conn, kind=kind, category="system", title=f"EA Explorer {installed} is out of support", body=why,
                  link=LINK, actor="system", recipients=_admins(conn), needs_action=True, include_actor=True)
    return True


def notice(conn, ops_status: dict | None) -> dict:
    """For everyone signed in: a scheduled update (the banner beforehand) and the latest update's What's new note."""
    sched = (ops_status or {}).get("scheduled") or None
    if sched:
        sched = {"at": sched.get("at"), "to": sched.get("to"), "channel": sched.get("channel")}
    last = databases.on("operations", conn).execute(text("""SELECT id, to_version, finished_at, notes FROM operations.update_history
                                 WHERE kind = 'update' AND status = 'ok' AND finished_at > now() - interval '14 days'
                                 ORDER BY finished_at DESC LIMIT 1""")).mappings().first()
    running = (ops_status or {}).get("current") or None
    return {"scheduled": sched,
            "running": {"to": running.get("to"), "status": running.get("status")} if running else None,
            "whats_new": dict(last) if last else None}


def sample(conn) -> list[str]:
    """Laptop sample data (AGENTS.md): an update that succeeded, one that failed and was rolled back, one that did not
    start, and one scheduled; marked sample, never told to anyone."""
    if databases.on("operations", conn).execute(text("SELECT 1 FROM operations.update_history WHERE sample LIMIT 1")).first():
        return []
    now = datetime.now(UTC)
    rows = [
        ("sample-20261001-ok", "ok", "prod", "0.16.0", "0.17.0", "", now - timedelta(days=40), 38,
         "20261001T200000Z-before-update-to-0.17.0", "", "Batch 1: merge into the parent, dedupe, KPI trends, OData, "
         "machine access, operations, surveys and maturity.", [{"ref": "v0.17.0", "status": "ok", "version": "0.17.0"}]),
        ("sample-20261020-rolled", "rolled-back", "rc", "0.17.0", "0.18.0-rc.1", "0.18.0-rc.1", now - timedelta(days=21), 52,
         "20261020T190000Z-before-update-to-0.18.0-rc.1", "Step 1 (v0.18.0-rc.1) failed: EA Explorer did not come up at "
         "version 0.18.0-rc.1 within 20 minutes. Rolled back by user_it_admin.", "",
         [{"ref": "v0.18.0-rc.1", "status": "failed", "version": "0.18.0-rc.1"}]),
        ("sample-20261102-notstarted", "not-started", "prod", "0.17.0", "0.18.0", "", now - timedelta(days=8), 1, "",
         "Not started, nothing changed: the backup container is not running (switch Backups on in System admin > Services).",
         "", [{"ref": "v0.18.0", "status": "waiting"}]),
        ("sample-20261108-scheduled", "scheduled", "prod", "0.18.0", "0.19.0", "", now + timedelta(days=2), 0, "", "", "",
         [{"ref": "v0.19.0", "status": "waiting"}]),
    ]
    out = []
    for rid, st, ch, frm, to, failed, started, mins, backup, err, notes, steps in rows:
        databases.on("operations", conn).execute(text("""
            INSERT INTO operations.update_history (id, kind, status, channel, from_version, to_version, failed_version, by_user,
                                             started_at, finished_at, backup, error, notes, steps, sample, notified)
            VALUES (:id, 'update', :st, :ch, :frm, :to, :failed, :by, :s, :f, :b, :e, :n, CAST(:steps AS jsonb), true, :st)
            ON CONFLICT (id) DO NOTHING"""),
            {"id": rid, "st": st, "ch": ch, "frm": frm, "to": to, "failed": failed,
             "by": "user_it_admin" if st != "ok" else "user_super_admin", "s": started,
             "f": started + timedelta(minutes=mins) if st not in ("scheduled",) else None, "b": backup, "e": err, "n": notes,
             "steps": json.dumps(steps)})
        out.append(f"sample update history: {rid} ({st})")
    return out
