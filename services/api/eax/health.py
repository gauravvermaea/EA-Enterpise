"""Health of every service in the stack, checked from the api container.

Each check is small and safe (a request a browser or the product itself would make), runs with a
short timeout, and all run at the same time, so the whole check takes about as long as the slowest
service. A check never raises: it reports a status for its service.

  up        working
  warning   working, but something needs attention (old backup, jobs waiting long, failed jobs)
  down      not answering or answering with an error
  off       turned off in the config file (MCP, SQL window)

Overall: "ok" when nothing is down or in warning, "degraded" otherwise, "down" when the database
is down (nothing works without it).
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from . import __version__
from .config import get_settings
from .db import get_engine
from .versioning import database_version, version_warning

TIMEOUT = 3.0
JOB_WAIT_WARNING_MINUTES = 5
BACKUP_DIR = Path(os.environ.get("EAX_BACKUP_MOUNT", "/data/backups"))


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip().strip("'\"")


def _result(name: str, kind: str, status: str, detail: str, started: float, target: str = "") -> dict:
    return {"name": name, "kind": kind, "status": status, "detail": detail, "target": target,
            "response_ms": round((time.perf_counter() - started) * 1000)}


def _http(name: str, kind: str, host: str, port: int, path: str, ok=lambda s, b: s < 400,
          method: str = "GET", describe=None) -> dict:
    """One HTTP request inside the Docker network (redirects are not followed)."""
    started = time.perf_counter()
    target = f"http://{host}:{port}{path}"
    try:
        conn = http.client.HTTPConnection(host, port, timeout=TIMEOUT)
        conn.request(method, path, headers={"User-Agent": "eaexplorer-health", "Host": host})
        resp = conn.getresponse()
        body = resp.read(65536)
        conn.close()
        if ok(resp.status, body):
            detail = describe(resp.status, body) if describe else f"HTTP {resp.status}"
            return _result(name, kind, "up", detail, started, target)
        return _result(name, kind, "down", f"answered HTTP {resp.status}", started, target)
    except (OSError, http.client.HTTPException) as exc:
        return _result(name, kind, "down", f"not reachable: {exc.__class__.__name__}: {exc}"[:200], started, target)


# ---------------------------------------------------------------- the checks
def check_database() -> dict:
    started = time.perf_counter()
    s = get_settings()
    target = f"postgresql://{s.db_host}:{s.db_port}/{s.db_name}"
    try:
        with get_engine().connect() as conn:
            row = conn.execute(text("""
                SELECT current_setting('server_version'),
                       (SELECT version_num FROM public.alembic_version LIMIT 1),
                       pg_size_pretty(pg_database_size(current_database())),
                       (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database())""")).one()
            db_version = database_version(conn)
        warning = version_warning(db_version)
        detail = (f"version {db_version}, PostgreSQL {row[0]}, migration {row[1]}, {row[2]}, "
                  f"{row[3]} connections")
        if warning:
            return _result("Database", "PostgreSQL", "warning", f"{warning} ({detail})", started, target)
        return _result("Database", "PostgreSQL", "up", detail, started, target)
    except Exception as exc:  # noqa: BLE001
        return _result("Database", "PostgreSQL", "down", f"{exc.__class__.__name__}: {str(exc)[:160]}", started, target)


def check_jobs() -> dict:
    """The job queue lives in the database; a job waiting long means the job runner is not working."""
    started = time.perf_counter()
    name, kind = "Job runner", "Procrastinate"
    try:
        with get_engine().connect() as conn:
            if not conn.execute(text("SELECT to_regclass('jobs.procrastinate_jobs')")).scalar():
                return _result(name, kind, "down", "job tables missing", started)
            waiting, doing, failed = conn.execute(text("""
                SELECT count(*) FILTER (WHERE status = 'todo'), count(*) FILTER (WHERE status = 'doing'),
                       count(*) FILTER (WHERE status = 'failed') FROM jobs.procrastinate_jobs""")).one()
    except Exception as exc:  # noqa: BLE001
        return _result(name, kind, "down", f"{exc.__class__.__name__}: {str(exc)[:160]}", started)
    detail = f"{waiting} waiting, {doing} running, {failed} failed"
    stuck = 0
    if waiting:
        try:  # when each waiting job was queued (its 'deferred' event)
            with get_engine().connect() as conn:
                stuck = conn.execute(text(f"""
                    SELECT count(*) FROM jobs.procrastinate_jobs j
                     WHERE j.status = 'todo'
                       AND coalesce(j.scheduled_at, (SELECT min(e.at) FROM jobs.procrastinate_events e
                                                      WHERE e.job_id = j.id AND e.type = 'deferred'))
                           < now() - interval '{JOB_WAIT_WARNING_MINUTES} minutes'""")).scalar()
        except Exception:  # noqa: BLE001 - older queue layout: report the counts only
            stuck = 0
    if stuck:
        return _result(name, kind, "warning",
                       f"{detail}; {stuck} waiting over {JOB_WAIT_WARNING_MINUTES} minutes: is the job runner running?", started)
    return _result(name, kind, "warning" if failed else "up", detail, started)


def check_keycloak() -> dict:
    realm = get_settings().realm
    return _http("Sign-in", "Keycloak", "keycloak", 8080, f"/auth/realms/{realm}/.well-known/openid-configuration",
                 ok=lambda s, b: s == 200 and b"issuer" in b,
                 describe=lambda s, b: f"realm '{realm}' answering")


def check_reports() -> dict:
    return _http("Reports", "Apache Superset", "reports", 8088, "/health",
                 ok=lambda s, b: s == 200, describe=lambda s, b: b.decode(errors="replace").strip()[:40] or "OK")


def check_dms() -> dict:
    # Mayan answers its login page (or a redirect to it) when it is up
    return _http("Documents", "Mayan EDMS", "dms", 8000, "/", ok=lambda s, b: s < 500)


def check_dms_broker() -> dict:
    """Mayan's task queue and locks (Valkey): AUTH and PING over the Redis protocol."""
    started = time.perf_counter()
    target = "valkey://dms-broker:6379"
    password = _env("EAX_DMS_BROKER_PASSWORD")
    try:
        with socket.create_connection(("dms-broker", 6379), timeout=TIMEOUT) as sock:
            def command(*parts: str) -> bytes:
                payload = f"*{len(parts)}\r\n" + "".join(f"${len(p.encode())}\r\n{p}\r\n" for p in parts)
                sock.sendall(payload.encode())
                return sock.recv(256)
            if password:
                reply = command("AUTH", password)
                if not reply.startswith(b"+OK"):
                    return _result("Document queue", "Valkey", "down", "password refused", started, target)
            reply = command("PING")
        if reply.startswith(b"+PONG"):
            return _result("Document queue", "Valkey", "up", "PONG", started, target)
        return _result("Document queue", "Valkey", "down", f"unexpected answer {reply[:40]!r}", started, target)
    except OSError as exc:
        return _result("Document queue", "Valkey", "down", f"not reachable: {exc}"[:200], started, target)


def check_drawio() -> dict:
    return _http("Diagrams", "draw.io", "drawio", 8080, "/")


def check_web() -> dict:
    return _http("Web screens", "nginx (ours)", "web", 8080, "/")


def check_proxy() -> dict:
    # the proxy answers plain http with a redirect to https
    return _http("Entry point", "nginx proxy", "proxy", 80, "/", ok=lambda s, b: s < 500)


def check_mcp() -> dict:
    if _env("EAX_MCP_ENABLED", "false").lower() != "true":
        started = time.perf_counter()
        return _result("MCP server", "MCP (ours)", "off", "EAX_MCP_ENABLED is false", started)
    # without a token it must refuse with 401: that proves it is up and guarded
    return _http("MCP server", "MCP (ours)", "127.0.0.1", 8001, "/mcp", method="POST",
                 ok=lambda s, b: s == 401, describe=lambda s, b: "answering, sign-in required")


def check_backup() -> dict:
    """Age of the newest backup (the backups folder is mounted read-only into the api container)."""
    started = time.perf_counter()
    max_hours = float(_env("EAX_BACKUP_MAX_AGE_HOURS", "36") or 36)
    if not BACKUP_DIR.is_dir():
        return _result("Backup", "Backup (ours)", "warning", "backups folder not mounted in the api container", started)
    newest = None
    for manifest in BACKUP_DIR.glob("*/manifest.json"):
        try:
            created = manifest.stat().st_mtime
        except OSError:
            continue
        newest = max(newest or created, created)
    if newest is None:
        return _result("Backup", "Backup (ours)", "warning", "no backup yet (run: eax backup)", started, str(BACKUP_DIR))
    hours = (time.time() - newest) / 3600
    when = datetime.fromtimestamp(newest, UTC).strftime("%Y-%m-%d %H:%M UTC")
    status = "up" if hours <= max_hours else "warning"
    return _result("Backup", "Backup (ours)", status, f"newest {when} ({hours:.0f} h ago; limit {max_hours:.0f} h)",
                   started, str(BACKUP_DIR))


def check_api() -> dict:
    started = time.perf_counter()
    return _result("API", "Flask (ours)", "up", f"version {__version__}, {get_settings().deployment}", started)


def check_break_glass() -> dict:
    """D80: a used break-glass password is an alert until it is changed."""
    started = time.perf_counter()
    name, kind = "Break-glass account", "Emergency sign-in (ours)"
    try:
        from .api.break_glass import status
        with get_engine().connect() as conn:
            st = status(conn)
    except Exception as exc:  # noqa: BLE001
        return _result(name, kind, "warning", f"could not read: {exc.__class__.__name__}", started)
    if not st["enabled"]:
        return _result(name, kind, "off", "not set up (EAX_BREAK_GLASS_PASSWORD is empty)", started)
    if st["change_password"]:
        return _result(name, kind, "warning", f"used on {st['last_used_at']:%Y-%m-%d %H:%M} UTC: change "
                       "EAX_BREAK_GLASS_PASSWORD and restart (see the audit log for what was done)", started)
    last = f"; last used {st['last_used_at']:%Y-%m-%d}" if st["last_used_at"] else "; never used"
    return _result(name, kind, "up", "sealed" + last, started)


CHECKS = [check_api, check_database, check_jobs, check_keycloak, check_web, check_proxy, check_reports,
          check_dms, check_dms_broker, check_drawio, check_mcp, check_backup, check_break_glass]


def check_all() -> dict:
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(CHECKS)) as pool:
        services = list(pool.map(lambda f: f(), CHECKS))
    statuses = {s["status"] for s in services}
    database_down = next(s for s in services if s["name"] == "Database")["status"] == "down"
    overall = "down" if database_down else "degraded" if statuses & {"down", "warning"} else "ok"
    return {
        "status": overall,
        "time": datetime.now(UTC),
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "counts": {k: sum(1 for s in services if s["status"] == k) for k in ("up", "warning", "down", "off")},
        "services": services,
    }


def to_json(result: dict) -> str:  # for the command line: python -m eax.health
    return json.dumps(result, default=str, indent=2)


if __name__ == "__main__":
    print(to_json(check_all()))
