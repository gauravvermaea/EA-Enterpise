"""Background jobs: start the sample job and follow its progress."""

from __future__ import annotations

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy import text

from .. import audit
from ..auth import require_auth
from ..db import get_engine
from .schemas import JobOut, JobRequestIn

blp = Blueprint("jobs", __name__, url_prefix="/api/v1/jobs", description="Background jobs")


@blp.route("/heartbeat")
class HeartbeatJob(MethodView):
    @blp.arguments(JobRequestIn)
    @blp.response(202, JobOut)
    @blp.doc(security=[{"bearerAuth": []}])
    @require_auth()
    def post(self, data):
        """Start the sample background job (signed in)

        The job runner in the api container picks it up, writes a heartbeat row and an
        audit event.
        """
        from ..jobs import app as jobs_app, record_heartbeat

        with jobs_app.open():
            job_id = record_heartbeat.defer(note=data["note"], requested_by=g.user.username)
        with get_engine().begin() as conn:
            audit.record(
                conn, actor=g.user.username, action="job.requested", object_type="job",
                object_id=str(job_id), details={"task": "eax.record_heartbeat"},
                request_id=g.request_id,
            )
        return {"job_id": job_id, "status": "todo", "task": "eax.record_heartbeat"}


@blp.route("/<int:job_id>")
class JobStatus(MethodView):
    @blp.response(200, JobOut)
    @blp.doc(security=[{"bearerAuth": []}])
    @require_auth()
    def get(self, job_id: int):
        """Status of a job: todo, doing, succeeded, failed or cancelled"""
        with get_engine().connect() as conn:
            row = conn.execute(
                text("SELECT id, status, task_name FROM jobs.procrastinate_jobs WHERE id = :id"),
                {"id": job_id},
            ).one_or_none()
        if row is None:
            abort(404, message="No such job.")
        return {"job_id": row.id, "status": str(row.status), "task": row.task_name}
