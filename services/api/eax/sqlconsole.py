"""The SQL window: run queries against the installation's own PostgreSQL with a database login.

Used by POST /api/v1/sql/query and the web screen #/sql. Rules:
  * Turned on with EAX_SQL_CONSOLE_ENABLED (default: on for laptops, off for servers).
  * The caller must be signed in with the system-admin role AND give a PostgreSQL user and password;
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


def run(database: str, username: str, password: str, sql: str) -> dict:
    """Runs the text (one or more statements) and returns every result set."""
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
        conn.rollback()   # read-only: nothing a run does is kept
    return {"results": results, "notices": notices, "committed": False,
            "duration_ms": round((time.perf_counter() - started) * 1000)}


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
