"""Background jobs (Procrastinate, queue held in PostgreSQL, schema "jobs").

The job runner runs in the same container as the API (see entrypoint.sh):
    procrastinate --app=eax.jobs.app worker
"""

from __future__ import annotations

import logging

from procrastinate import App, PsycopgConnector
from sqlalchemy import text

from . import audit
from .config import get_settings
from .db import get_engine

log = logging.getLogger(__name__)

_settings = get_settings()

# kwargs must be a mapping: Procrastinate's LISTEN/NOTIFY listener opens its own connection with
# **kwargs, and fails with "argument after ** must be a mapping, not NoneType" when none are given.
app = App(
    connector=PsycopgConnector(
        conninfo=_settings.libpq_conninfo,
        kwargs={"options": "-c search_path=jobs,public"},
    )
)


@app.task(name="eax.record_heartbeat", queue="default", pass_context=True)
def record_heartbeat(context, note: str, requested_by: str) -> None:
    """Sample job for phase 0: records a heartbeat row and an audit event."""
    job_id = context.job.id if context and context.job else None
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO core.heartbeat_logs (source, note, requested_by, job_id) "
                "VALUES ('job', :note, :by, :job_id)"
            ),
            {"note": note, "by": requested_by, "job_id": job_id},
        )
        audit.record(
            conn,
            actor=requested_by,
            action="job.completed",
            object_type="job",
            object_id=str(job_id),
            details={"task": "eax.record_heartbeat", "note": note},
            source="job",
        )
    log.info("heartbeat job %s done", job_id)


@app.task(name="eax.copy_model", queue="default", pass_context=True)
def copy_model(context, source: str, target: str, actor: str, roles: list[str], publish: bool = False) -> None:
    """Phase 4: fills a new model from another (metamodel and content), as the person who asked: the
    database checks their rights as it would in the screens. With publish, a Library Admin's promotion is
    locked into the library once copied. A failure is written on the model (copy_state failed)."""
    from . import model_ops, permissions

    token = permissions.current.set(permissions.Principal(actor, tuple(roles or ())))
    try:
        try:
            with get_engine().begin() as conn:
                counts = model_ops.run_copy(conn, source, target, actor, publish=publish)
                audit.record(conn, actor=actor, action="model.copied", object_type="model", object_id=target,
                             details={"source": source, "counts": counts, "published": publish}, source="job")
            log.info("copy %s -> %s done: %s", source, target, counts)
        except Exception as exc:  # recorded on the model so the screens can say why
            with get_engine().begin() as conn:
                model_ops.copy_failed(conn, target, str(exc)[:400])
            log.exception("copy %s -> %s failed", source, target)
            raise
    finally:
        permissions.current.reset(token)


@app.task(name="eax.run_task", queue="default")
def run_task(task_id: str, actor: str, roles: list[str]) -> None:
    """Long work in the background (D192): tagging a model, ... (eax/tasks.py)."""
    from . import tasks
    tasks.run(task_id, actor, roles)


@app.task(name="eax.admin_sign_in_check", queue="default", pass_context=True)
def admin_sign_in_check(context, username: str) -> None:
    """D215: when an IT or Super Admin signs in, check the installation and notify them of anything that needs attention."""
    from . import admin_check
    nid = admin_check.run(username)
    log.info("sign-in check for %s: %s", username, f"notification {nid}" if nid else "all well")


@app.periodic(cron="* * * * *")
@app.task(name="eax.record_terminal_ends", queue="default", queueing_lock="record_terminal_ends")
def record_terminal_ends(timestamp: int) -> None:
    """D214: interactive terminal sessions that ended go into the audit trail, every minute."""
    from .api.admin import record_terminal_ends as record
    n = record()
    if n:
        log.info("terminal sessions recorded: %s", n)


@app.periodic(cron="* * * * *")
@app.task(name="eax.deliver_webhooks", queue="default", queueing_lock="deliver_webhooks")
def deliver_webhooks(timestamp: int) -> None:
    """Phase 8.1: sends the webhook deliveries that are due (D209), every minute."""
    from . import webhooks
    with get_engine().begin() as conn:
        out = webhooks.deliver_due(conn)
    if any(out.values()):
        log.info("webhooks: %s", out)


# ---------------------------------------------------------------- backups (phase 8.4, D216, D222)
@app.periodic(cron="* * * * *")
@app.task(name="eax.announce_restores", queue="default", queueing_lock="announce_restores")
def announce_restores(timestamp: int) -> None:
    """Every minute: a restore that ended (or one running that was not announced) is told to everyone (D229); after a
    full restore this is how the restored database hears of it. A model lock left by a restore that stopped is lifted."""
    from . import backups, restore_notice
    with get_engine().begin() as conn:
        n = restore_notice.catch_up(conn, backups.list_records())
        lifted = backups.lift_stale_restore_locks(conn)     # D236: a restore that stopped leaves no lock behind
    if lifted:
        log.info("restore locks lifted: %s", lifted)
    if n:
        log.info("restores announced: %s", n)


@app.periodic(cron="* * * * *")
@app.task(name="eax.backup_scheduler", queue="default", queueing_lock="backup_scheduler")
def backup_scheduler(timestamp: int) -> None:
    """Every minute: the backups due on their schedules (core.backup_schedules, set on Administration > Backups) start.
    Infrastructure: in the operations helper; application: here, as the system. The oldest beyond 'keep' go after each."""
    from . import __version__, services
    from . import backup_schedule as bs
    from . import backups as bk
    from . import permissions as perms
    from .api.admin import _ops_raw
    with get_engine().begin() as conn:
        due = bs.due(conn)
    for s in due:
        status = "started"
        try:
            if not services.enabled("backups"):
                status = "skipped: Backups are switched off"
            elif s["kind"] == "infrastructure":
                _ops_raw("POST", "/backups/backup", {"tag": s["tag"], "by": "system", "kind": "scheduled", "version": __version__,
                                                     "keep": s["keep"]}, timeout=30)
            else:
                with get_engine().begin() as conn:
                    status, _ = bk.application_backup(conn, perms.Principal("system", (perms.SUPER_ADMIN,)), s["tag"], keep_n=s["keep"])
        except Exception as exc:  # noqa: BLE001 - busy, or the helper is down: the sign-in check reports an old backup
            status = f"failed: {exc}"
            log.warning("scheduled %s backup: %s", s["kind"], exc)
        with get_engine().begin() as conn:
            bs.set_status(conn, s["kind"], status)
            audit.record(conn, actor="system", action="backup.scheduled", object_type="backup", object_id=s["kind"],
                         details={"tag": s["tag"], "status": status[:300]})


@app.periodic(cron="* * * * *")
@app.task(name="eax.record_backup_events", queue="default", queueing_lock="record_backup_events")
def record_backup_events(timestamp: int) -> None:
    """Every minute: backups, restores and clean-ups done by the operations helper go into the audit trail."""
    from .api.admin import _ops_raw
    try:
        events = _ops_raw("GET", "/backups/events", timeout=20).get("events", [])
    except Exception:  # noqa: BLE001 - the helper is down: next minute
        return
    if not events:
        return
    action = {"backup": "backup.scheduled", "restore": "backup.restore.done", "cleanup": "backup.cleanup", "delete": "backup.delete"}
    with get_engine().begin() as conn:
        for e in events:
            act = action.get(e.get("kind"), "backup.scheduled")
            if e.get("kind") == "backup" and e.get("reason") != "scheduled":
                act = "backup.infrastructure"
            audit.record(conn, actor=e.get("by") or "system", action=act, object_type="backup",
                         object_id=str(e.get("name") or e.get("kind")), details={k: v for k, v in e.items() if k != "log"})
