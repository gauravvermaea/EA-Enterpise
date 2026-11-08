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


@blp.route("/schema")
class SqlSchema(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The tables of a schema with their columns and the joins between them, for the SQL window's database diagram:
        ?schema=core (models: the repository) or proj (architecture projects) (owner, 8 Nov 2026)"""
        from flask import request
        from sqlalchemy import text

        from ..db import get_projects_engine
        schema = request.args.get("schema") or "core"
        if schema not in ("core", "proj"):
            abort(400, message="The schema is core (models) or proj (projects).")
        eng = get_projects_engine() if schema == "proj" else get_engine()
        with eng.connect() as conn:
            cols = conn.execute(text("""SELECT c.table_name AS t, c.column_name AS c, c.data_type AS type, c.is_nullable = 'YES' AS nullable
                                          FROM information_schema.columns c JOIN information_schema.tables t
                                            ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE'
                                         WHERE c.table_schema = :s ORDER BY c.table_name, c.ordinal_position"""), {"s": schema}).mappings().all()
            pks = conn.execute(text("""SELECT tc.table_name AS t, kcu.column_name AS c FROM information_schema.table_constraints tc
                                         JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
                                          AND kcu.table_schema = tc.table_schema
                                        WHERE tc.table_schema = :s AND tc.constraint_type = 'PRIMARY KEY'"""), {"s": schema}).mappings().all()
            fks = conn.execute(text("""SELECT cl.relname AS t, a.attname AS c, rn.nspname AS to_schema, rt.relname AS to_t, ra.attname AS to_c
                                         FROM pg_constraint k JOIN pg_class cl ON cl.oid = k.conrelid JOIN pg_namespace n ON n.oid = cl.relnamespace
                                         JOIN pg_class rt ON rt.oid = k.confrelid JOIN pg_namespace rn ON rn.oid = rt.relnamespace
                                         JOIN LATERAL unnest(k.conkey, k.confkey) AS u(a1, a2) ON true
                                         JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = u.a1
                                         JOIN pg_attribute ra ON ra.attrelid = k.confrelid AND ra.attnum = u.a2
                                        WHERE k.contype = 'f' AND n.nspname = :s"""), {"s": schema}).mappings().all()
        pk = {(r["t"], r["c"]) for r in pks}
        fk = {(r["t"], r["c"]): f"{'' if r['to_schema'] == schema else r['to_schema'] + '.'}{r['to_t']}.{r['to_c']}" for r in fks}
        tables: dict[str, list] = {}
        for r in cols:
            tables.setdefault(r["t"], []).append({"name": r["c"], "type": r["type"], "nullable": r["nullable"],
                                                  "pk": (r["t"], r["c"]) in pk, "fk": fk.get((r["t"], r["c"]))})
        return {"schema": schema, "tables": [{"name": t, "columns": c} for t, c in tables.items()],
                "joins": [{"from": r["t"], "column": r["c"], "to": r["to_t"], "to_column": r["to_c"],
                           "outside": r["to_schema"] != schema} for r in fks]}
