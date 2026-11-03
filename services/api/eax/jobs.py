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
                "INSERT INTO core.heartbeat_log (source, note, requested_by, job_id) "
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
