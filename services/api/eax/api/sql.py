"""The SQL window: POST /api/v1/sql/query runs SQL with a PostgreSQL login (see eax/sqlconsole.py)."""

from __future__ import annotations

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import audit, sqlconsole
from ..auth import require_auth
from ..db import get_engine
from .schemas import SqlQueryIn, SqlQueryOut

blp = Blueprint(
    "sql", __name__, url_prefix="/api/v1/sql",
    description="SQL window: run queries with a database login (laptops; system-admin only)",
)


def _audit(query: dict, outcome: str, **extra) -> None:
    try:
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="sql.query", object_type="database",
                         object_id=query.get("database") or "eaexplorer", source="api",
                         request_id=getattr(g, "request_id", None),
                         details={"db_user": query["username"], "allow_changes": query["allow_changes"],
                                  "outcome": outcome, "sql": query["sql"][:2000], **extra})
    except Exception:  # the audit must never hide the query's own result
        pass


@blp.route("/query")
class SqlQuery(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.arguments(SqlQueryIn)
    @blp.response(200, SqlQueryOut)
    @require_auth("system-admin")
    def post(self, query):
        """Run SQL with a database login

        One or more statements; every result set comes back (at most 1,000 rows each, 30-second
        limit). Rolled back at the end unless `allow_changes` is true. Temporary tables last for this run only.
        """
        if not sqlconsole.enabled():
            abort(404, message="The SQL window is turned off on this installation (EAX_SQL_CONSOLE_ENABLED=false).")
        try:
            result = sqlconsole.run(query.get("database") or "", query["username"], query["password"],
                                    query["sql"], allow_changes=query["allow_changes"])
        except sqlconsole.SqlConsoleError as exc:
            _audit(query, "error", error=str(exc)[:500])
            abort(exc.status, message=str(exc), errors=exc.details)
        _audit(query, "ok", results=len(result["results"]), duration_ms=result["duration_ms"])
        return result
