"""The SQL window: run queries against the installation's own PostgreSQL with a database login.

Used by POST /api/v1/sql/query and the web screen #/admin/sql. Rules:
  * Turned on with EAX_SQL_CONSOLE_ENABLED (default: on for laptops, off for servers).
  * The caller must be signed in with the Super Admin or IT Admin role AND give a PostgreSQL user and password;
    the database's own permissions then decide what that login may see and do.
  * Only the installation's database server (EAX_DB_HOST) is used; any of its databases may be named.
  * Read-only for everyone (D52, phase 3): the run is one transaction that is always rolled back at
    the end (not READ ONLY, because eax.get_entity creates temporary tables), so nothing is kept.
  * One connection per run, so temporary tables (eax.get_entity) live for that run only: put
    SELECT eax.get_entity(...) and the SELECT on its temp table in the same run.
  * 30-second statement timeout and at most 1,000 rows per result; every run is audited.
"""

from __future__ import annotations

import datetime as dt
import decimal
import os
import re
import time
import uuid
from typing import Any

from .config import get_settings

MAX_ROWS = 1000
TIMEOUT_SECONDS = 30
MAX_CELL_CHARS = 10_000


class SqlConsoleError(Exception):
    """A problem to show the user; status is the HTTP status."""

    def __init__(self, message: str, status: int = 400, **details: Any):
        super().__init__(message)
        self.status = status
        self.details = {k: v for k, v in details.items() if v not in (None, "", [])}


def enabled() -> bool:
    default = "true" if get_settings().deployment == "laptop" else "false"
    return os.environ.get("EAX_SQL_CONSOLE_ENABLED", default).strip().lower() in ("1", "true", "yes", "on")


def to_json_value(value: Any) -> Any:
    """A database value as something JSON can carry; long text is cut."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else str(value)
    if isinstance(value, (decimal.Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return "\\x" + raw[:256].hex() + ("..." if len(raw) > 256 else "")
    if isinstance(value, (list, tuple)):
        return [to_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_json_value(v) for k, v in value.items()}
    text = str(value)
    return text if len(text) <= MAX_CELL_CHARS else text[:MAX_CELL_CHARS] + "..."


def run(database: str, username: str, password: str, sql: str, keep: bool = False) -> dict:
    """Runs the text (one or more statements) and returns every result set. keep: commit at the end (writing, owner
    6 Nov 2026, replacing D52); otherwise everything is rolled back."""
    if not username or not password:
        raise SqlConsoleError("Give a database user name and password.")
    if not (sql or "").strip():
        raise SqlConsoleError("Nothing to run.")
    import psycopg  # imported here so the helpers above load without the driver (tests)

    settings = get_settings()
    started = time.perf_counter()
    try:
        conn = psycopg.connect(host=settings.db_host, port=settings.db_port, dbname=database or settings.db_name,
                               user=username, password=password, connect_timeout=5,
                               application_name="eaexplorer-sql-window")
    except psycopg.OperationalError as exc:
        lines = str(exc).strip().splitlines()
        raise SqlConsoleError(f"Could not sign in to the database: {lines[-1] if lines else 'connection failed'}", 401) from exc

    notices: list[str] = []
    with conn:
        conn.add_notice_handler(lambda d: notices.append(f"{d.severity}: {d.message_primary}"))
        results = []
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('statement_timeout', %s, false)", (f"{TIMEOUT_SECONDS}s",))
                # no parameters: sent as written (several statements allowed, % needs no escaping)
                cur.execute(sql, prepare=False)
                while True:
                    results.append(_result_set(cur))
                    if not cur.nextset():
                        break
        except psycopg.Error as exc:
            conn.rollback()
            diag = exc.diag
            message = diag.message_primary or str(exc).strip()
            if diag.sqlstate == "57014":
                message += f" (the time limit is {TIMEOUT_SECONDS} seconds)"
            raise SqlConsoleError(message, 400, sqlstate=diag.sqlstate, detail=diag.message_detail,
                                  hint=diag.message_hint, position=diag.statement_position) from exc
        if keep:
            conn.commit()     # the person chose to keep the changes; the database login's own rights decided what ran
        else:
            conn.rollback()   # a trial run: nothing a run does is kept
    return {"results": results, "notices": notices, "committed": bool(keep),
            "duration_ms": round((time.perf_counter() - started) * 1000)}


# what each database and schema is for (owner, 13 Nov 2026: "In the SQL tab do the same for databases and schemas"); a
# table's line is its comment in the database (migration 0064)
ABOUT_DATABASES = {
    "eaexplorer": "EA Explorer: models, projects, people, settings, history, the self-test and the running of the installation",
    "keycloak": "Keycloak: sign-in, users, roles and sessions",
    "superset": "Reports (Superset): dashboards, charts and their settings",
    "mayan": "Documents (Mayan EDMS): the index of the document files",
    "eaxlibrary": "The reference and enterprise libraries' service",
    "eaxviews": "The drawn views' service (pictures of models)",
    "postgres": "PostgreSQL's own maintenance database (nothing of EA Explorer's)",
}
ABOUT_SCHEMAS = {
    "core": "The architecture: models, metamodels, elements, relationships, attributes, commits, users and roles",
    "proj": "Architecture projects: steps, deliverables, documents, people, governance, the template libraries",
    "history": "Every earlier version of every changed row (append only)",
    "changelog": "The change log: every change with its before and after",
    "audit": "The audit trail: who did what and when",
    "rpt": "Views for Reports and OData: the models as tables, read only",
    "staging": "Changes being prepared before they are applied (imports, bulk edits)",
    "jobs": "The background job runner's queue",
    "eax": "EA Explorer's database functions (the permission checks)",
    "library": "The libraries' own tables",
    "library_models": "The read-only shared models' content (industry and reference models), moved here from core",
    "tests": "The self-test: runs, results, the fixtures each made",
    "operations": "Running the installation: backup schedules, deployments, updates, health, start-up",
    "archive": "Archived and deleted models and projects, each kept as its backup file",
    "personal": "Each person's own: notifications, requests, favourites, saved views, skills, settings, remote instances",
    "files": "Files kept in the database on a platform with no local file system",
    "farm": "The EA Explorer sites everyone sees in the site picker",
    "public": "PostgreSQL's default schema: here only the migration version",
}


def databases() -> list[str]:
    """The databases on the installation's server that can be connected to (the drop-down of the SQL window)."""
    from sqlalchemy import text as _t

    from .db import get_engine
    with get_engine().connect() as conn:
        return [r[0] for r in conn.execute(_t("""SELECT datname FROM pg_database WHERE datallowconn AND NOT datistemplate
                                                   ORDER BY datname = current_database() DESC, datname"""))]


def _result_set(cur) -> dict:
    if cur.description is None:  # INSERT, UPDATE, CREATE ...: no rows, only a status
        return {"columns": [], "rows": [], "row_count": cur.rowcount if cur.rowcount >= 0 else None,
                "truncated": False, "status": cur.statusmessage or ""}
    rows = cur.fetchmany(MAX_ROWS + 1)
    return {
        "columns": [d.name for d in cur.description],
        "rows": [[to_json_value(v) for v in r] for r in rows[:MAX_ROWS]],
        "row_count": min(len(rows), MAX_ROWS),
        "truncated": len(rows) > MAX_ROWS,
        "status": cur.statusmessage or "",
    }


# ---------------------------------------------------------------- the database workspace (R2.57)
# Owner, 13 Nov 2026: "a better SQL interface, we need ours to be more like pgadmin". Everything runs with the person's
# own database login (its rights decide what is seen), in one transaction that is rolled back: browsing, a table's rows,
# a query plan and an export change nothing. Names reach SQL only as quoted identifiers (psycopg.sql), never as text.
EXPORT_ROWS = 100_000
PAGE_ROWS = 200


def _connect(database: str, username: str, password: str):
    if not username or not password:
        raise SqlConsoleError("Give a database user name and password.")
    import psycopg
    settings = get_settings()
    try:
        conn = psycopg.connect(host=settings.db_host, port=settings.db_port, dbname=database or settings.db_name,
                               user=username, password=password, connect_timeout=5,
                               application_name="eaexplorer-sql-window")
    except psycopg.OperationalError as exc:
        lines = str(exc).strip().splitlines()
        raise SqlConsoleError(f"Could not sign in to the database: {lines[-1] if lines else 'connection failed'}", 401) from exc
    conn.execute("SELECT set_config('statement_timeout', %s, false)", (f"{TIMEOUT_SECONDS}s",))
    return conn


def _read(database: str, username: str, password: str, work):
    """work(cursor) in a transaction that is always rolled back; database errors become messages."""
    import psycopg
    conn = _connect(database, username, password)
    try:
        with conn.cursor() as cur:
            return work(cur)
    except psycopg.Error as exc:
        d = exc.diag
        raise SqlConsoleError(d.message_primary or str(exc).strip(), 400, sqlstate=d.sqlstate, detail=d.message_detail,
                              hint=d.message_hint) from exc
    finally:
        conn.rollback()
        conn.close()


def plain(comment: str) -> str:
    """A comment as a line for people: the leading story or decision code left off ("R2.41: archived ..." -> "Archived ...")."""
    text = re.sub(r"^\s*(?:[RD]\d[\d.]*(?:\s*(?:,|and|to)\s*[RD]?\d[\d.]*)*\s*[:,]\s*)", "", (comment or "").strip())
    return text[:1].upper() + text[1:]


def about_schema(name: str, comment: str = "") -> str:
    """A schema's line: ours in plain words, else its comment in the database (another service's schema)."""
    return ABOUT_SCHEMAS.get(name) or plain((comment or "").split(";")[0])


def browse(database: str, username: str, password: str) -> dict:
    """The tree: each schema the login may use, with its tables, views and materialised views (estimated rows, size)."""
    def work(cur):
        cur.execute("""
            SELECT n.nspname, c.relname, c.relkind, GREATEST(c.reltuples, 0)::bigint,
                   CASE WHEN c.relkind IN ('r', 'm', 'p') THEN pg_total_relation_size(c.oid) END,
                   COALESCE(obj_description(c.oid, 'pg_class'),
                            CASE WHEN n.nspname = 'library_models'
                                 THEN obj_description(to_regclass('core.' || quote_ident(c.relname)), 'pg_class') END, ''),
                   COALESCE(obj_description(n.oid, 'pg_namespace'), '')
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind IN ('r', 'v', 'm', 'p', 'f') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
               AND n.nspname NOT LIKE 'pg_toast%%' AND n.nspname NOT LIKE 'pg_temp%%'
               AND has_schema_privilege(n.oid, 'USAGE') AND has_table_privilege(c.oid, 'SELECT')
             ORDER BY 1, 2""")
        kinds = {"r": "table", "p": "table", "v": "view", "m": "materialised view", "f": "foreign table"}
        schemas: dict[str, list] = {}
        notes: dict[str, str] = {}
        for s, t, k, rows, size, about, schema_note in cur.fetchall():
            schemas.setdefault(s, []).append({"name": t, "kind": kinds.get(k, k), "rows": int(rows), "bytes": size,
                                              "about": plain(about)})
            notes[s] = schema_note
        return {"database": database, "about": ABOUT_DATABASES.get(database, ""),
                "schemas": [{"name": s, "objects": o, "about": about_schema(s, notes.get(s, ""))} for s, o in schemas.items()]}
    return _read(database, username, password, work)


def describe(database: str, username: str, password: str, schema: str, table: str) -> dict:
    """A table's structure: columns (type, null, default), indexes, constraints, size and rows."""
    def work(cur):
        cur.execute("SELECT to_regclass(format('%%I.%%I', %s::text, %s::text))::oid", (schema, table))
        oid = (cur.fetchone() or [None])[0]
        if not oid:
            raise SqlConsoleError(f"No table {schema}.{table} (or this login may not see it).", 404)
        cur.execute("""SELECT a.attname, format_type(a.atttypid, a.atttypmod), NOT a.attnotnull,
                              pg_get_expr(d.adbin, d.adrelid), col_description(a.attrelid, a.attnum)
                         FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                        WHERE a.attrelid = %s AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum""", (oid,))
        cols = [{"name": n, "type": t, "nullable": nl, "default": df, "comment": cm} for n, t, nl, df, cm in cur.fetchall()]
        cur.execute("""SELECT i.relname, pg_get_indexdef(i.oid), x.indisprimary, x.indisunique, pg_relation_size(i.oid)
                         FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid WHERE x.indrelid = %s ORDER BY 1""", (oid,))
        idx = [{"name": n, "definition": d, "primary": p, "unique": u, "bytes": b} for n, d, p, u, b in cur.fetchall()]
        cur.execute("""SELECT conname, contype, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = %s
                        ORDER BY contype, conname""", (oid,))
        kind = {"p": "primary key", "u": "unique", "f": "foreign key", "c": "check", "x": "exclusion"}
        cons = [{"name": n, "kind": kind.get(k, k), "definition": d} for n, k, d in cur.fetchall()]
        cur.execute("""SELECT GREATEST(reltuples, 0)::bigint, pg_total_relation_size(oid), obj_description(oid, 'pg_class'),
                              relkind FROM pg_class WHERE oid = %s""", (oid,))
        rows, size, comment, relkind = cur.fetchone()
        view = None
        if relkind in ("v", "m"):
            cur.execute("SELECT pg_get_viewdef(%s, true)", (oid,))
            view = cur.fetchone()[0]
        return {"schema": schema, "table": table, "columns": cols, "indexes": idx, "constraints": cons,
                "rows_estimate": int(rows), "bytes": size, "comment": comment, "view_definition": view}
    return _read(database, username, password, work)


def table_rows(database: str, username: str, password: str, schema: str, table: str, page: int = 0,
               order: str = "", desc: bool = False, column: str = "", contains: str = "") -> dict:
    """A page of a table's rows (PAGE_ROWS), sorted by a column, filtered by a column containing words; the count."""
    from psycopg import sql as q

    def work(cur):
        cur.execute("""SELECT a.attname FROM pg_attribute a WHERE a.attrelid = to_regclass(format('%%I.%%I', %s::text, %s::text))
                         AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum""", (schema, table))
        cols = [r[0] for r in cur.fetchall()]
        if not cols:
            raise SqlConsoleError(f"No table {schema}.{table} (or this login may not see it).", 404)
        where, params = q.SQL(""), []
        if column and contains:
            if column not in cols:
                raise SqlConsoleError(f"{table} has no column {column}.")
            where = q.SQL(" WHERE CAST({} AS text) ILIKE %s").format(q.Identifier(column))
            params.append(f"%{contains}%")
        ordering = q.SQL("")
        if order:
            if order not in cols:
                raise SqlConsoleError(f"{table} has no column {order}.")
            ordering = q.SQL(" ORDER BY {} {} NULLS LAST").format(q.Identifier(order), q.SQL("DESC" if desc else "ASC"))
        rel = q.Identifier(schema, table)
        cur.execute(q.SQL("SELECT count(*) FROM {}{}").format(rel, where), params)
        total = cur.fetchone()[0]
        cur.execute(q.SQL("SELECT * FROM {}{}{} LIMIT %s OFFSET %s").format(rel, where, ordering),
                    [*params, PAGE_ROWS, max(0, int(page)) * PAGE_ROWS])
        return {"columns": [d.name for d in cur.description], "rows": [[to_json_value(v) for v in r] for r in cur.fetchall()],
                "total": total, "page": int(page), "pages": max(1, (total + PAGE_ROWS - 1) // PAGE_ROWS)}
    return _read(database, username, password, work)


def explain(database: str, username: str, password: str, sql: str, analyze: bool = False) -> dict:
    """The plan of one statement (EXPLAIN, FORMAT JSON); with analyze it runs, inside the transaction that is rolled
    back, so its timings and rows are real and nothing is kept."""
    text_ = (sql or "").strip().rstrip(";")
    if not text_:
        raise SqlConsoleError("Nothing to explain.")
    if ";" in text_:
        raise SqlConsoleError("Explain one statement at a time (select it first).")

    def work(cur):
        opts = "ANALYZE, BUFFERS, FORMAT JSON" if analyze else "FORMAT JSON"
        cur.execute(f"EXPLAIN ({opts}) {text_}", prepare=False)
        plan = cur.fetchone()[0]
        return {"plan": plan[0] if isinstance(plan, list) else plan, "analyzed": bool(analyze)}
    return _read(database, username, password, work)


def export(database: str, username: str, password: str, sql: str, fmt: str = "csv") -> tuple[bytes, str, str]:
    """A query's rows as CSV or Excel (at most EXPORT_ROWS), rolled back: (bytes, file name, mime type)."""
    import csv
    import io
    if not (sql or "").strip():
        raise SqlConsoleError("Nothing to export.")

    def work(cur):
        cur.execute(sql, prepare=False)
        while cur.description is None and cur.nextset():
            pass
        if cur.description is None:
            raise SqlConsoleError("The statement returns no rows to export.")
        cols = [d.name for d in cur.description]
        rows = cur.fetchmany(EXPORT_ROWS)
        return cols, rows
    cols, rows = _read(database, username, password, work)
    if fmt == "xlsx":
        from openpyxl import Workbook
        wb = Workbook(write_only=True)
        ws = wb.create_sheet("Result")
        ws.append(cols)
        for r in rows:
            ws.append([v if isinstance(v, (int, float, str, bool)) or v is None else str(to_json_value(v)) for v in r])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), "query.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow(["" if v is None else to_json_value(v) for v in r])
    return buf.getvalue().encode("utf-8-sig"), "query.csv", "text/csv"
