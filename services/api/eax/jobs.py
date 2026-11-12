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
from .db import get_engine, get_projects_engine

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


@app.periodic(cron="17 3 * * *")
@app.task(name="eax.test_results_cleanup", queue="default", queueing_lock="test_results_cleanup")
def test_results_cleanup(timestamp: int) -> None:
    """R2.43: test runs older than the days set on the Self-test page go, once a day (their data, results, reports,
    logs and videos); 0 keeps them."""
    from .api.admin import _ops_raw
    from .db import get_engine
    from .testing import cleanup
    try:
        days = int((_ops_raw("GET", "/tests", timeout=20) or {}).get("keep_days", cleanup.DEFAULT_KEEP_DAYS))
    except Exception:  # noqa: BLE001 - the operations helper is not there: try tomorrow
        return
    if days <= 0:
        return
    with get_engine().connect() as conn:
        ids = [r["id"] for r in cleanup.pick(conn, "", days)]
    if ids:
        out = cleanup.delete(get_engine(), ids, "test results kept " + str(days) + " days",
                             lambda folders: _ops_raw("POST", "/tests/results/delete", {"folders": folders}, timeout=120))
        log.info("test results cleanup: %s", cleanup.message(out))


@app.periodic(cron="*/10 * * * *")
@app.task(name="eax.task_files_cleanup", queue="default", queueing_lock="task_files_cleanup")
def task_files_cleanup(timestamp: int) -> None:
    """D273: a background task's file is kept 24 hours; the uploaded files of finished tasks go at once."""
    from . import tasks
    from .db import get_engine
    with get_engine().begin() as conn:
        n = tasks.cleanup(conn)
    if n:
        log.info("removed %s background task files", n)


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


# ---------------------------------------------------------------- data quality (phase 12, D239)
@app.periodic(cron="* * * * *")
@app.task(name="eax.quality_scheduler", queue="default", queueing_lock="quality_scheduler")
def quality_scheduler(timestamp: int) -> None:
    """Every minute: each model whose quality is due on its schedule (every Sunday at 03:00 by default, D244) is measured, the
    measurement kept, and its responsible people told about new problems (stale entities among them)."""
    from datetime import datetime

    from . import backup_schedule as bs
    from . import quality
    with get_engine().begin() as conn:
        due = quality.due(conn, datetime.now(bs.zone(conn)))
    for m in due:
        try:
            with get_engine().begin() as conn:
                mm = {"_id": m["id"], "id": m["g"], "name": m["name"]}
                quality.run(conn, mm, "system", "scheduled")
                quality.tell_new(conn, mm)
        except Exception as exc:  # noqa: BLE001 - one model never stops the others
            log.warning("quality of %s: %s", m["name"], exc)


@app.task(name="eax.quality_entities", queue="default")
def quality_entities(model: str, entities: list[str]) -> None:
    """After a commit (D245, D248): the entities it touched recalculated and their stored rows written, a few seconds
    later; nothing runs inside the commit itself."""
    from . import quality
    with get_engine().begin() as conn:
        n = quality.refresh_entities(conn, model, entities)
    log.info("quality of %s entities of %s recalculated", n, model)


@app.task(name="eax.quality_measure", queue="default")
def quality_measure(request_id: str) -> None:
    """Measure now, Measure all and Recalculate (D245): one model's quality measured and kept in the background; the
    person who asked is told."""
    from . import quality
    quality.run_request(lambda: get_engine().begin(), request_id)


@app.periodic(cron="*/2 * * * *")
@app.task(name="eax.quality_watch", queue="default", queueing_lock="quality_watch")
def quality_watch(timestamp: int) -> None:
    """Every two minutes: models changed lately are checked and the people responsible told about new problems as they
    happen (D239.3); each problem is told once until it is fixed."""
    from datetime import UTC, datetime, timedelta

    from . import quality
    with get_engine().begin() as conn:
        changed = quality.changed_since(conn, datetime.now(UTC) - timedelta(minutes=3))
    for m in changed:
        try:
            with get_engine().begin() as conn:
                n = quality.tell_new(conn, {"_id": m["id"], "id": m["g"], "name": m["name"]})
            if n:
                log.info("quality: %s people told about %s", n, m["name"])
        except Exception as exc:  # noqa: BLE001
            log.warning("quality watch of %s: %s", m["name"], exc)


@app.periodic(cron="0 * * * *")
@app.task(name="eax.quality_digest", queue="default", queueing_lock="quality_digest")
def quality_digest(timestamp: int) -> None:
    """On Mondays at 07:00 in the installation's time zone: each responsible person's weekly data quality digest."""
    from datetime import datetime

    from . import backup_schedule as bs
    from . import quality
    with get_engine().begin() as conn:
        local = datetime.now(bs.zone(conn))
        if local.weekday() != 0 or local.hour != 7:
            return
        n = quality.weekly_digest(conn)
    log.info("quality digest sent to %s people", n)


# ---------------------------------------------------------------- KPI trends (phase 24, D365, D431)
@app.periodic(cron="7 * * * *")
@app.task(name="eax.kpi_monthly", queue="default", queueing_lock="kpi_monthly")
def kpi_monthly(timestamp: int) -> None:
    """Every hour: each live model with no KPI snapshot for this month yet gets one, dated the 1st of the month; on the 1st
    that is in the first hour, and a month missed while the server was off is taken as soon as it is back."""
    from datetime import datetime

    from . import backup_schedule as bs
    from . import kpis
    with get_engine().begin() as conn:
        today = datetime.now(bs.zone(conn)).date()
    n = kpis.take_monthly(lambda: get_engine().begin(), today)
    if n:
        log.info("monthly KPIs kept for %s models", n)


# ---------------------------------------------------------------- architecture projects (phase 13, D260)

@app.task(name="eax.project_repository", queue="default", queueing_lock="project_repository")
def project_repository(project_id: int) -> None:
    """A project's repository built in Mayan (cabinets for its folders and items, templates copied)."""
    from . import projects
    note = projects.build_repository(lambda: get_projects_engine().begin(), project_id)
    log.info("project %s repository: %s", project_id, note)


@app.task(name="eax.template_library_load", queue="default", queueing_lock="template_library_load")
def template_library_load(library_id: int) -> None:
    """An uploaded template library's files stored in Mayan (D264)."""
    from . import projects
    note = projects.load_library_upload(lambda: get_projects_engine().begin(), library_id)
    log.info("template library %s: %s", library_id, note)


@app.periodic(cron="* * * * *")
@app.task(name="eax.project_repositories", queue="default", queueing_lock="project_repositories")
def project_repositories(timestamp: int) -> None:
    """Every minute: uploaded template libraries still to store, then the repositories still to build (made while
    Documents was starting or off) once Mayan answers; each failure is kept on the project and tried again (up to 30 times)."""
    from . import mayan, projects
    from . import settings as app_settings
    if not app_settings.parts().get("projects", True):     # switched off (D329): its work waits until it is on again
        return
    with get_projects_engine().begin() as conn:
        todo = projects.pending_repositories(conn)
        libraries = projects.pending_library_loads(conn)
        togaf = projects.togaf_files_waiting(conn)
    if not (todo or libraries or togaf) or not mayan.ping():
        return
    if togaf:                        # the TOGAF folder on disk, loaded again after a clean restart (no git, no hand work)
        try:
            log.info("TOGAF templates: %s", projects.auto_load_togaf(lambda: get_projects_engine().begin()))
        except Exception as exc:  # noqa: BLE001 - tried again next minute
            log.warning("TOGAF templates: %s", exc)
    for lid in libraries:            # uploaded template libraries first: projects using them wait for them
        try:
            projects.load_library_upload(lambda: get_projects_engine().begin(), lid)
        except Exception as exc:  # noqa: BLE001 - kept on the library; tried again next minute
            log.warning("template library %s: %s", lid, exc)
    for pid in todo:
        try:
            projects.build_repository(lambda: get_projects_engine().begin(), pid)
        except Exception as exc:  # noqa: BLE001 - kept on the project; tried again next minute
            log.warning("project %s repository: %s", pid, exc)


@app.periodic(cron="*/10 * * * *")
@app.task(name="eax.industry_packs", queue="default", queueing_lock="industry_packs")
def industry_packs(timestamp: int) -> None:
    """Every 10 minutes: when the shipped industry packs are not all in Documents (the start-up step ran before Documents
    answered, some files failed, or a loader was stopped half way), they are loaded, each file on its own (D546, R2.23)."""
    from . import industry_packs as ip
    try:
        with get_engine().connect() as conn:
            state = conn.execute(text("SELECT state FROM core.startup_parts WHERE part = :p"), {"p": ip.PART}).scalar()
            if state in ("up", "skipped") or (state is None and not ip.missing_shipped(conn)):
                return
        log.info("industry packs: %s", ip.load_shipped_each("system:job")["message"])
    except Exception as exc:  # noqa: BLE001 - tried again in 10 minutes
        log.warning("industry packs: %s", exc)


# ---------------------------------------------------------------- surveys (phase 38.1, D448)

@app.periodic(cron="7 * * * *")
@app.task(name="eax.surveys", queue="default", queueing_lock="surveys")
def surveys(timestamp: int) -> None:
    """Every hour: surveys past their closing date close (a maturity assessment keeps its evidence and scores), and
    automatic reminders go to those who have not answered."""
    from . import surveys as sv
    with get_engine().begin() as conn:
        out = sv.housekeeping(conn)
    if out["closed"] or out["reminded"]:
        log.info("surveys: %s closed, %s reminded", out["closed"], out["reminded"])


# ---------------------------------------------------------------- housekeeping (phase 35.1, D371, D444)

@app.periodic(cron="40 2 * * *")
@app.task(name="eax.housekeeping", queue="default", queueing_lock="housekeeping")
def housekeeping(timestamp: int) -> None:
    """Every night: the retention rules applied once a dry run of them is confirmed; until then, a dry run that waits
    for an IT Admin or Super Admin to confirm it (System admin > Operations > Housekeeping)."""
    from . import operations
    with get_engine().begin() as conn:
        out = operations.scheduled(conn)
    if out:
        log.info("housekeeping %s: %s", "dry run" if out["dry_run"] else "run",
                 {k: v["archived"] + v["deleted"] for k, v in out["results"].items()})


# ---------------------------------------------------------------- updates (phase 36, D417, D515)

@app.periodic(cron="*/5 * * * *")
@app.task(name="eax.update_watch", queue="default", queueing_lock="update_watch")
def update_watch(timestamp: int) -> None:
    """Every 5 minutes: the operations helper's record of updates copied into the database, and the Super Admins and
    IT Admins told once when an update fails, finishes or is rolled back. Once a day (at 06:15): whether the installed
    version is still supported (the Prod channel's releases, when a repository link is set)."""
    from . import updates as up
    from .api.admin import _ops_raw
    try:
        st = _ops_raw("GET", "/updates", timeout=15)
    except Exception:  # noqa: BLE001 - the helper is down or being rebuilt: next time
        return
    with get_engine().begin() as conn:
        up.sync(conn, st)
        told = up.tell(conn)
    if told:
        log.info("updates: %s notification(s)", told)
    from datetime import datetime
    t = datetime.now()
    if not (t.hour == 6 and 15 <= t.minute < 20) or not (st.get("settings") or {}).get("git_url"):
        return
    try:
        got = _ops_raw("GET", "/updates/versions?channel=prod", timeout=200)
    except Exception:  # noqa: BLE001
        return
    releases = [v["version"] for v in got.get("versions") or []] + [(st.get("installed") or {}).get("version") or ""]
    with get_engine().begin() as conn:
        up.tell_support(conn, (st.get("installed") or {}).get("version") or "", [r for r in releases if r])

