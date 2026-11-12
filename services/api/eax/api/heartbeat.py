"""Heartbeat: is the API up, can it reach the database, how is the job queue doing."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint
from sqlalchemy import text

from .. import __version__, audit, health, maintenance
from ..auth import require_auth
from ..config import get_settings
from ..db import get_engine
from ..versioning import database_version, version_warning
from .schemas import Heartbeat, HeartbeatRecordIn, HeartbeatRecordOut, ServicesHealth

blp = Blueprint(
    "heartbeat", __name__, url_prefix="/api/v1/heartbeat",
    description="Heartbeat of the API, the database and the job queue",
)


def check_database() -> tuple[dict, dict]:
    db = {"reachable": False, "latency_ms": None, "schema_version": None, "version": None, "error": None}
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
            db["version"] = database_version(conn)
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

        Always answers 200 while the API runs. "status" is "degraded" when the database cannot be
        reached, and "warning" when the API version (version.toml) and the database version
        (core.schema_versions) differ.
        """
        settings = get_settings()
        db, jobs = check_database()
        warning = version_warning(db["version"]) if db["reachable"] else None
        return {
            "status": "degraded" if not db["reachable"] else "warning" if warning else "ok",
            "service": "eaexplorer-api",
            "version": __version__,
            "versions_match": (db["version"] == __version__) if db["reachable"] else None,
            "warning": warning,
            "deployment": settings.deployment,
            "time": datetime.now(UTC),
            "database": db,
            "jobs": jobs,
            "maintenance": maintenance.state(),
            "test_in_progress": _test_in_progress() if db["reachable"] else None,   # R2.51 (D609)
        }

    @blp.arguments(HeartbeatRecordIn)
    @blp.response(201, HeartbeatRecordOut)
    @blp.doc(security=[{"bearerAuth": []}])
    @require_auth()
    def post(self, data):
        """Record a heartbeat now (signed in)

        Writes a row to core.heartbeat_logs, which the sample Superset dashboard shows.
        """
        user = g.user
        with get_engine().begin() as conn:
            row = conn.execute(
                text(
                    "INSERT INTO core.heartbeat_logs (source, note, requested_by) "
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


@blp.route("/services")
class ServicesView(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.response(200, ServicesHealth)
    @require_auth()
    def get(self):
        """Health of every service (signed in)

        Checks, at the same time and from inside the stack: the API, the database, the job runner,
        Keycloak, the web screens, the proxy, Superset, Mayan EDMS and its queue (Valkey), draw.io,
        the MCP server and the age of the newest backup. Each service is up, warning, down or off;
        the overall status is ok, degraded, or down when the database is down. Always answers 200.
        """
        return health.check_all()


def _test_in_progress():
    """The self-test in progress, for the screens' sign-in screen and banner (R2.51, D609)."""
    from .. import test_lock
    from ..db import get_engine
    try:
        with get_engine().connect() as conn:
            return test_lock.active(conn)
    except Exception:  # noqa: BLE001 - no test tables yet
        return None
