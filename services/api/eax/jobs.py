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
