"""Heartbeat: is the API up, can it reach the database, how is the job queue doing."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint
from sqlalchemy import text

from .. import __version__, audit
from ..auth import require_auth
from ..config import get_settings
from ..db import get_engine
from .schemas import Heartbeat, HeartbeatRecordIn, HeartbeatRecordOut

blp = Blueprint(
    "heartbeat", __name__, url_prefix="/api/v1/heartbeat",
    description="Heartbeat of the API, the database and the job queue",
)


def check_database() -> tuple[dict, dict]:
    db = {"reachable": False, "latency_ms": None, "schema_version": None, "error": None}
    jobs = {"waiting": None, "failed": None}
    started = time.perf_counter()
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            db["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
            db["reachable"] = True
            db["schema_version"] = conn.execute(
                text("SELECT version_num FROM public.alembic_version LIMIT 1")
            ).scalar()
            if conn.execute(text("SELECT to_regclass('jobs.procrastinate_jobs')")).scalar():
                row = conn.execute(
                    text(
                        "SELECT count(*) FILTER (WHERE status = 'todo'), "
                        "count(*) FILTER (WHERE status = 'failed') FROM jobs.procrastinate_jobs"
                    )
                ).one()
                jobs = {"waiting": row[0], "failed": row[1]}
    except Exception as exc:  # noqa: BLE001 - report any failure as "degraded"
        db["error"] = exc.__class__.__name__
    return db, jobs


@blp.route("")
class HeartbeatView(MethodView):
    @blp.response(200, Heartbeat)
    def get(self):
        """Heartbeat (public)

        Always answers 200 while the API runs; "status" is "degraded" when the database
        cannot be reached.
        """
        settings = get_settings()
        db, jobs = check_database()
        return {
            "status": "ok" if db["reachable"] else "degraded",
            "service": "eaexplorer-api",
            "version": __version__ if settings.version == "dev" else settings.version,
            "deployment": settings.deployment,
            "time": datetime.now(timezone.utc),
            "database": db,
            "jobs": jobs,
        }

    @blp.arguments(HeartbeatRecordIn)
    @blp.response(201, HeartbeatRecordOut)
    @blp.doc(security=[{"bearerAuth": []}])
    @require_auth()
    def post(self, data):
        """Record a heartbeat now (signed in)

        Writes a row to core.heartbeat_log, which the sample Superset dashboard shows.
        """
        user = g.user
        with get_engine().begin() as conn:
            row = conn.execute(
                text(
                    "INSERT INTO core.heartbeat_log (source, note, requested_by) "
                    "VALUES ('api', :note, :by) RETURNING id, at, source, note, requested_by"
                ),
                {"note": data["note"], "by": user.username},
            ).mappings().one()
            audit.record(
                conn, actor=user.username, action="heartbeat.recorded",
                object_type="heartbeat", object_id=str(row["id"]),
                details={"note": data["note"]}, request_id=g.request_id,
            )
        return dict(row)
