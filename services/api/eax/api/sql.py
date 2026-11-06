"""The SQL window: POST /api/v1/sql/query runs SQL with a PostgreSQL login (see eax/sqlconsole.py)."""

from __future__ import annotations

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import audit, sqlconsole
from ..auth import require_auth
from ..db import get_engine
from .models import Free
from .schemas import SqlQueryIn, SqlQueryOut

blp = Blueprint(
    "sql", __name__, url_prefix="/api/v1/sql",
    description="SQL window: run queries with a database login (laptops; Super Admin and IT Admin only)",
)


def _audit(query: dict, outcome: str, **extra) -> None:
    try:
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="sql.query", object_type="database",
                         object_id=query.get("database") or "eaexplorer", source="api",
                         request_id=getattr(g, "request_id", None),
                         details={"db_user": query["username"],
                                  "outcome": outcome, "sql": query["sql"][:2000], **extra})
    except Exception:  # the audit must never hide the query's own result
        pass


@blp.route("/query")
class SqlQuery(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.arguments(SqlQueryIn)
    @blp.response(200, SqlQueryOut)
    @require_auth("system.operate")
    def post(self, query):
        """Run SQL with a database login

        One or more statements; every result set comes back (at most 1,000 rows each, 30-second
        limit). Rolled back at the end unless keep is true: then committed, and what the database login may do decides
        what is written (owner, 6 Nov 2026, replacing D52). Every run is in the audit trail, with whether it was kept.
        """
        if not sqlconsole.enabled():
            abort(404, message="The SQL window is turned off on this installation (EAX_SQL_CONSOLE_ENABLED=false).")
        try:
            result = sqlconsole.run(query.get("database") or "", query["username"], query["password"],
                                    query["sql"], bool(query.get("keep")))
        except sqlconsole.SqlConsoleError as exc:
            _audit(query, "error", error=str(exc)[:500])
            abort(exc.status, message=str(exc), errors=exc.details)
        _audit(query, "kept" if result["committed"] else "ok", results=len(result["results"]),
               duration_ms=result["duration_ms"], kept=result["committed"])
        return result


@blp.route("/databases")
class SqlDatabases(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The databases on this installation's server (EA Explorer's own first)"""
        if not sqlconsole.enabled():
            abort(404, message="The SQL window is turned off on this installation (EAX_SQL_CONSOLE_ENABLED=false).")
        return {"databases": sqlconsole.databases()}
