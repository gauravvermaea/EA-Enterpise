"""Operations insight and housekeeping (phases 35 and 35.1, D371, D442 to D445), for IT Admins and Super Admins.

  * usage insight: who uses what and how often, which parts, each model's use and size, models unused for 180 days (a
    report only: nobody is told and nothing happens to them), stale uncommitted work and loads never finished. The API
    counts its calls per day, person, part and model (core.usage_daily), in memory and written about once a minute
  * Prometheus metrics: /api/metrics, read with a machine credential that may read Administration (phase 25)
  * retention rules for what grows: keep, archive or delete after N days. The defaults only archive (loads and task
    files after 90 days, notifications after a year, old history versions after three years) and nothing is deleted
    until an admin says so
  * a scheduled housekeeping job (every night): while the rules have no confirmed dry run, it only does a dry run and
    waits; an admin confirms it, and from then on it acts. Changing a rule asks for a new dry run
  * the archive: what housekeeping archived, searchable on request (a file's content downloadable)
  * database health: the largest tables, the slowest queries (when the database records them), when tables were last
    tidied (vacuumed and analysed)
Nothing of this is in the database's logic (D248).
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text

from . import __version__

IDLE_DAYS = 180          # a model unused this long is listed (D371): a report only
STALE_CHANGE_DAYS = 30   # uncommitted changes older than this are stale work
STALE_LOAD_DAYS = 14     # a load still not added after this long
BATCH = 5000             # rows a rule handles in one run, so transactions stay short

# ---------------------------------------------------------------- usage counting
_lock = threading.Lock()
_counts: Counter = Counter()
_last_flush = time.monotonic()
FLUSH_EVERY = 60          # seconds
FLUSH_AT = 500            # calls
_MODEL = re.compile(r"^/api/v1/models/([0-9a-f-]{36})(?:/([a-z-]+))?")
_PROJECT = re.compile(r"^/api/v1/projects/([0-9a-f-]{36})(?:/([a-z-]+))?")


def feature_of(path: str) -> tuple[str, str]:
    """(feature, model guid) of an API address: models/<part>, projects/<part> or the first part of the address."""
    m = _MODEL.match(path)
    if m:
        return f"models/{m.group(2) or 'model'}", m.group(1)
    p = _PROJECT.match(path)
    if p:
        return f"projects/{p.group(2) or 'project'}", ""
    parts = [x for x in path.removeprefix("/api/v1/").split("/") if x]
    if not parts:
        return "api", ""
    if parts[0] in ("admin", "projects", "models") and len(parts) > 1 and not re.match(r"^[0-9a-f-]{36}$", parts[1]):
        return f"{parts[0]}/{parts[1]}", ""
    return parts[0], ""


def count_call(username: str, path: str, machine: bool = False) -> None:
    """One API call by a signed-in person or credential (called after each call; never fails it)."""
    if not username or not path.startswith(("/api/v1/", "/mcp")):
        return
    from .machine_access import area_of
    feature, model = feature_of(path) if path.startswith("/api/v1/") else ("mcp", "")
    key = (date.today().isoformat(), username.lower(), area_of(path) or "other", feature, model, bool(machine))
    with _lock:
        _counts[key] += 1
        due = sum(_counts.values()) >= FLUSH_AT or time.monotonic() - _last_flush >= FLUSH_EVERY
    if due:
        flush()


def flush(conn=None) -> int:
    """Writes the counted calls (adds to what other API servers wrote). Returns how many rows."""
    global _last_flush
    with _lock:
        items = list(_counts.items())
        _counts.clear()
        _last_flush = time.monotonic()
    if not items:
        return 0
    sql = text("""INSERT INTO core.usage_daily (day, username, area, feature, model_guid, machine, calls)
                  VALUES (CAST(:d AS date), :u, :a, :f, :m, :mc, :n)
                  ON CONFLICT (day, username, area, feature, model_guid, machine)
                  DO UPDATE SET calls = core.usage_daily.calls + EXCLUDED.calls""")
    try:
        if conn is None:
            from .db import get_engine
            with get_engine().begin() as c:
                for (d, u, a, f, m, mc), n in items:
                    c.execute(sql, {"d": d, "u": u, "a": a, "f": f, "m": m, "mc": mc, "n": n})
        else:
            for (d, u, a, f, m, mc), n in items:
                conn.execute(sql, {"d": d, "u": u, "a": a, "f": f, "m": m, "mc": mc, "n": n})
    except Exception:  # noqa: BLE001 - counting never breaks a call; the counts are put back for next time
        with _lock:
            for k, n in items:
                _counts[k] += n
        return 0
    return len(items)


# ---------------------------------------------------------------- insight
def _rows(conn, sql: str, **params) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings()]


def _iso(v):
    return v.isoformat() if isinstance(v, (date, datetime)) else v


def _clean(rows: list[dict]) -> list[dict]:
    return [{k: _iso(v) for k, v in r.items()} for r in rows]


def insight(conn, days: int = 30) -> dict:
    """The usage page: people, parts, models (use and size), idle models, stale work, old loads, credentials."""
    days = max(1, min(int(days or 30), 3650))
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    people = _rows(conn, """
        SELECT u.username, sum(u.calls) AS calls, count(DISTINCT u.day) AS days_active, max(u.day) AS last_day,
               bool_or(u.machine) AS uses_machine_access,
               (SELECT k.seen_at FROM core.known_users k WHERE k.username = u.username) AS last_seen,
               (SELECT string_agg(x.area, ', ' ORDER BY x.n DESC) FROM (SELECT area, sum(calls) AS n FROM core.usage_daily v
                  WHERE v.username = u.username AND v.day >= CAST(:s AS date) GROUP BY area ORDER BY n DESC LIMIT 3) x) AS top_areas
          FROM core.usage_daily u WHERE u.day >= CAST(:s AS date)
         GROUP BY u.username ORDER BY calls DESC""", s=since)
    features = _rows(conn, """
        SELECT area, feature, sum(calls) AS calls, count(DISTINCT username) AS people, max(day) AS last_day
          FROM core.usage_daily WHERE day >= CAST(:s AS date)
         GROUP BY area, feature ORDER BY calls DESC LIMIT 200""", s=since)
    areas = _rows(conn, """SELECT area, sum(calls) AS calls, count(DISTINCT username) AS people FROM core.usage_daily
                            WHERE day >= CAST(:s AS date) GROUP BY area ORDER BY calls DESC""", s=since)
    by_day = _rows(conn, """SELECT day, sum(calls) AS calls, count(DISTINCT username) AS people FROM core.usage_daily
                             WHERE day >= CAST(:s AS date) GROUP BY day ORDER BY day""", s=since)
    models = model_use(conn, since)
    # idle: no call about the model for IDLE_DAYS (D371, a report only). A model never used counts only once the usage
    # record itself goes back that far, so a new installation does not list every model on its first day
    idle_cut = (date.today() - timedelta(days=IDLE_DAYS)).isoformat()
    first = _scalar(conn, "SELECT min(day) FROM core.usage_daily")
    known_long = first is not None and _iso(first) <= idle_cut
    idle = [m for m in models if m["kind"] != "template" and not m["archived"]
            and ((m["last_used"] is not None and m["last_used"] < idle_cut) or (m["last_used"] is None and known_long))]
    stale = _rows(conn, """
        SELECT m.guid AS model_guid, m.name AS model, p.author, count(*) AS changes, min(p.created_at) AS oldest
          FROM core.pending_changes p JOIN core.models m ON m.id = p.model_id
         WHERE p.status = 'pending' AND p.created_at < now() - make_interval(days => :d)
         GROUP BY m.guid, m.name, p.author ORDER BY oldest""", d=STALE_CHANGE_DAYS)
    loads = _rows(conn, """
        SELECT l.guid, m.name AS model, m.guid AS model_guid, l.file_name, l.status, l.owner, l.created_at,
               length(l.content) AS bytes
          FROM core.loads l JOIN core.models m ON m.id = l.model_id
         WHERE l.status IN ('uploaded', 'mapping', 'previewed') AND l.created_at < now() - make_interval(days => :d)
         ORDER BY l.created_at""", d=STALE_LOAD_DAYS)
    creds = _rows(conn, """
        SELECT kind, count(*) FILTER (WHERE revoked_at IS NULL AND expires_at > now()) AS live,
               count(*) FILTER (WHERE revoked_at IS NULL AND expires_at > now() AND expires_at < now() + interval '14 days') AS expiring,
               count(*) FILTER (WHERE revoked_at IS NULL AND expires_at > now() AND (last_used_at IS NULL OR last_used_at < now() - interval '90 days')) AS unused
          FROM core.machine_credentials GROUP BY kind ORDER BY kind""")
    return {"days": days, "since": since, "totals": {"calls": sum(int(p["calls"]) for p in people), "people": len(people),
                                                       "models_used": sum(1 for m in models if m["calls"])},
            "people": _clean(people), "areas": _clean(areas), "features": _clean(features), "by_day": _clean(by_day),
            "models": models, "idle_models": idle, "idle_days": IDLE_DAYS, "stale_changes": _clean(stale),
            "stale_change_days": STALE_CHANGE_DAYS, "old_loads": _clean(loads), "stale_load_days": STALE_LOAD_DAYS,
            "credentials": _clean(creds)}


def model_use(conn, since: str) -> list[dict]:
    rows = _rows(conn, """
        SELECT m.guid, m.name, m.kind_code AS kind, m.status_code AS status,
               (m.status_code IN ('archived', 'frozen')) AS archived,
               (SELECT count(*) FROM core.entities e WHERE e.model_id = m.id AND NOT e.is_deleted) AS entities,
               (SELECT count(*) FROM core.relationships r WHERE r.model_id = m.id AND NOT r.is_deleted) AS relationships,
               (SELECT max(e.modified_at) FROM core.entities e WHERE e.model_id = m.id) AS last_changed,
               (SELECT count(*) FROM history.row_versions h WHERE h.model_id = m.id) AS versions,
               coalesce((SELECT sum(u.calls) FROM core.usage_daily u WHERE u.model_guid = m.guid::text AND u.day >= CAST(:s AS date)), 0) AS calls,
               (SELECT count(DISTINCT u.username) FROM core.usage_daily u WHERE u.model_guid = m.guid::text AND u.day >= CAST(:s AS date)) AS people,
               (SELECT max(u.day) FROM core.usage_daily u WHERE u.model_guid = m.guid::text) AS last_used
          FROM core.models m WHERE NOT m.is_deleted ORDER BY m.name""", s=since)
    out = []
    for r in rows:
        r = {k: _iso(v) for k, v in r.items()}
        r["guid"] = str(r["guid"])
        for k in ("entities", "relationships", "versions", "calls", "people"):
            r[k] = int(r[k] or 0)
        out.append(r)
    return out


# ---------------------------------------------------------------- Prometheus metrics
def _line(name: str, value, labels: dict | None = None) -> str:
    lab = ""
    if labels:
        lab = "{" + ",".join(f'{k}="{str(v).replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
                             for k, v in labels.items()) + "}"
    return f"{name}{lab} {value}"


METRICS = [
    ("eax_info", "gauge", "EA Explorer's version (always 1)"),
    ("eax_up", "gauge", "The API answers and reaches its database"),
    ("eax_models", "gauge", "Models, by kind"),
    ("eax_entities", "gauge", "Entities that are not deleted"),
    ("eax_relationships", "gauge", "Relationships that are not deleted"),
    ("eax_people_active", "gauge", "People who used EA Explorer, over the last day and the last 30 days"),
    ("eax_api_calls_today", "gauge", "API calls today, by area (written about once a minute)"),
    ("eax_uncommitted_changes", "gauge", "Uncommitted changes waiting"),
    ("eax_jobs", "gauge", "Background jobs by status"),
    ("eax_backup_last_success_age_seconds", "gauge", "Seconds since the last infrastructure backup that worked"),
    ("eax_machine_credentials", "gauge", "Machine credentials that are live, by kind"),
    ("eax_database_size_bytes", "gauge", "The database's size"),
    ("eax_housekeeping_last_run_age_seconds", "gauge", "Seconds since the last housekeeping run (dry or not)"),
]


def metrics(conn) -> str:
    """The Prometheus text exposition (version 0.0.4)."""
    out: list[str] = []
    for name, kind, help_ in METRICS:
        out.append(f"# HELP {name} {help_}")
        out.append(f"# TYPE {name} {kind}")
        try:
            out += _metric(conn, name)
        except Exception:  # noqa: BLE001 - one metric that cannot be read never hides the others
            pass
    return "\n".join(out) + "\n"


def _scalar(conn, sql: str, **p):
    return conn.execute(text(sql), p).scalar()


def _metric(conn, name: str) -> list[str]:
    if name == "eax_info":
        return [_line(name, 1, {"version": __version__})]
    if name == "eax_up":
        return [_line(name, 1 if _scalar(conn, "SELECT 1") == 1 else 0)]
    if name == "eax_models":
        return [_line(name, r["n"], {"kind": r["kind_code"]}) for r in conn.execute(text(
            "SELECT kind_code, count(*) AS n FROM core.models WHERE NOT is_deleted GROUP BY kind_code ORDER BY 1")).mappings()]
    if name == "eax_entities":
        return [_line(name, _scalar(conn, "SELECT count(*) FROM core.entities WHERE NOT is_deleted"))]
    if name == "eax_relationships":
        return [_line(name, _scalar(conn, "SELECT count(*) FROM core.relationships WHERE NOT is_deleted"))]
    if name == "eax_people_active":
        return [_line(name, _scalar(conn, "SELECT count(*) FROM core.known_users WHERE seen_at > now() - interval '1 day'"), {"period": "1d"}),
                _line(name, _scalar(conn, "SELECT count(*) FROM core.known_users WHERE seen_at > now() - interval '30 days'"), {"period": "30d"})]
    if name == "eax_api_calls_today":
        return [_line(name, r["n"], {"area": r["area"]}) for r in conn.execute(text(
            "SELECT area, sum(calls) AS n FROM core.usage_daily WHERE day = current_date GROUP BY area ORDER BY 1")).mappings()]
    if name == "eax_uncommitted_changes":
        return [_line(name, _scalar(conn, "SELECT count(*) FROM core.pending_changes WHERE status = 'pending'"))]
    if name == "eax_jobs":
        return [_line(name, r["n"], {"status": r["status"]}) for r in conn.execute(text(
            "SELECT status::text AS status, count(*) AS n FROM jobs.procrastinate_jobs GROUP BY 1 ORDER BY 1")).mappings()]
    if name == "eax_backup_last_success_age_seconds":
        v = _scalar(conn, """SELECT extract(epoch FROM now() - max(at)) FROM audit.events
                              WHERE action IN ('backup.infrastructure', 'backup.scheduled')""")
        return [_line(name, int(v))] if v is not None else []
    if name == "eax_machine_credentials":
        return [_line(name, r["n"], {"kind": r["kind"]}) for r in conn.execute(text(
            """SELECT kind, count(*) AS n FROM core.machine_credentials WHERE revoked_at IS NULL AND expires_at > now()
                GROUP BY kind ORDER BY 1""")).mappings()]
    if name == "eax_database_size_bytes":
        return [_line(name, _scalar(conn, "SELECT pg_database_size(current_database())"))]
    if name == "eax_housekeeping_last_run_age_seconds":
        v = _scalar(conn, "SELECT extract(epoch FROM now() - max(started_at)) FROM core.housekeeping_runs")
        return [_line(name, int(v))] if v is not None else []
    return []


# ---------------------------------------------------------------- database health
def db_health(conn) -> dict:
    tables = _rows(conn, """
        SELECT n.nspname AS schema, c.relname AS name, pg_total_relation_size(c.oid) AS bytes,
               pg_relation_size(c.oid) AS table_bytes, greatest(c.reltuples, 0)::bigint AS rows,
               s.last_vacuum, s.last_autovacuum, s.last_analyze, s.last_autoanalyze, s.n_dead_tup AS dead_rows
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
          LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
         WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg_toast%'
         ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 25""")
    for t in tables:
        tidied = [x for x in (t["last_vacuum"], t["last_autovacuum"]) if x]
        analysed = [x for x in (t["last_analyze"], t["last_autoanalyze"]) if x]
        t["last_tidied"] = _iso(max(tidied)) if tidied else None
        t["last_analysed"] = _iso(max(analysed)) if analysed else None
        for k in ("last_vacuum", "last_autovacuum", "last_analyze", "last_autoanalyze"):
            t.pop(k)
    has_statements = bool(_scalar(conn, "SELECT count(*) FROM pg_extension WHERE extname = 'pg_stat_statements'"))
    slow: list[dict] = []
    note = ""
    if has_statements:
        try:
            slow = _clean(_rows(conn, """SELECT left(query, 300) AS query, calls, round(mean_exec_time::numeric, 1) AS mean_ms,
                                               round(max_exec_time::numeric, 1) AS max_ms, round(total_exec_time::numeric) AS total_ms
                                          FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 15"""))
        except Exception as exc:  # noqa: BLE001
            note = f"pg_stat_statements is there but cannot be read: {str(exc)[:120]}"
    else:
        note = ("The database does not record query times (the pg_stat_statements extension is not loaded); shown "
                "instead: the queries running now for longer than a second.")
        slow = _clean(_rows(conn, """SELECT left(query, 300) AS query, state, round(extract(epoch FROM now() - query_start)::numeric, 1) AS running_s
                                      FROM pg_stat_activity WHERE state <> 'idle' AND query_start < now() - interval '1 second'
                                       AND pid <> pg_backend_pid() ORDER BY query_start LIMIT 15"""))
    return {"database": _scalar(conn, "SELECT current_database()"), "size": int(_scalar(conn, "SELECT pg_database_size(current_database())")),
            "tables": _clean(tables), "slow_queries": slow, "slow_note": note, "statements": has_statements,
            "connections": int(_scalar(conn, "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"))}


# ---------------------------------------------------------------- retention rules and housekeeping
# code: (label, what it covers, allowed actions, minimum days)
RULES: dict[str, tuple[str, str, tuple[str, ...], int]] = {
    "loads": ("Loads", "Sheet loads that were added, undone or failed (the uploaded file with them)",
              ("keep", "archive", "delete"), 7),
    "task_files": ("Task files", "Files of background tasks still kept (finished tasks' files go after a day anyway)",
                   ("keep", "archive", "delete"), 1),
    "notifications": ("Notifications", "Notifications that need no action, or were resolved",
                      ("keep", "archive", "delete"), 30),
    "history_versions": ("Old history versions", "Earlier versions of entities, values, relationships, metamodel parts and "
                         "models. Removed, never archived; set by Super Admins only, in years (D445)", ("keep", "delete"), 365),
    "webhook_deliveries": ("Webhook deliveries", "Webhook calls that were sent or failed for good",
                           ("keep", "archive", "delete"), 7),
    "discarded_changes": ("Discarded and rejected changes", "Uncommitted changes that were discarded or rejected",
                          ("keep", "archive", "delete"), 30),
    "usage": ("Usage counts", "The calls counted per day for the usage page", ("keep", "delete"), 90),
    "housekeeping_runs": ("Housekeeping runs", "The record of earlier housekeeping runs", ("keep", "delete"), 90),
}
DEFAULTS = {"loads": ("archive", 90), "task_files": ("archive", 90), "notifications": ("archive", 365),
            "history_versions": ("keep", 1095), "webhook_deliveries": ("keep", 365), "discarded_changes": ("keep", 365),
            "usage": ("keep", 730), "housekeeping_runs": ("keep", 730)}
HISTORY_NOTE = ("Once removed, the model's earlier states before that age can no longer be viewed or compared (history, "
                "as-at views, comparisons with older dates). Always kept: the current version of everything, and every "
                "version a tag, baseline, merge starting point, drawn view evidence or governance record needs (D445).")
HISTORY_BATCH = 50000     # versions removed in one run at most
SUPER_ONLY = {"history_versions"}   # rules only a Super Admin sets (D445)


class NotConfirmed(Exception):
    """A real run asked for without a confirmed dry run of the rules as they are."""


def rules(conn) -> list[dict]:
    have = {r["code"]: r for r in _rows(conn, "SELECT * FROM core.retention_rules")}
    out = []
    for code, (label, covers, actions, min_days) in RULES.items():
        r = have.get(code) or {"action": DEFAULTS[code][0], "after_days": DEFAULTS[code][1], "set_by": "installation", "set_at": None}
        out.append({"code": code, "label": label, "covers": covers, "actions": list(actions), "min_days": min_days,
                    "action": r["action"], "after_days": r["after_days"], "set_by": r["set_by"], "set_at": _iso(r["set_at"]),
                    "default": {"action": DEFAULTS[code][0], "after_days": DEFAULTS[code][1]},
                    "note": HISTORY_NOTE if code == "history_versions" else ""})
    return out


def _rule_snapshot(conn) -> dict:
    return {r["code"]: [r["action"], r["after_days"]] for r in rules(conn)}


def set_rule(conn, actor: str, code: str, action: str, after_days: int, roles=("super-admin",)) -> dict:
    if code not in RULES:
        raise LookupError(f"No retention rule '{code}'.")
    if code in SUPER_ONLY and "super-admin" not in set(roles or ()):
        raise PermissionError(f"{RULES[code][0]}: only a Super Admin sets this rule.")
    _label, _covers, actions, min_days = RULES[code]
    if action not in actions:
        raise ValueError(f"{RULES[code][0]}: {', '.join(actions)}.")
    after_days = int(after_days)
    if not min_days <= after_days <= 36500:
        raise ValueError(f"{RULES[code][0]}: at least {min_days} days"
                         + (" (a year)." if code in SUPER_ONLY else "."))
    conn.execute(text("""INSERT INTO core.retention_rules (code, action, after_days, set_by, set_at) VALUES (:c, :a, :d, :by, now())
                          ON CONFLICT (code) DO UPDATE SET action = EXCLUDED.action, after_days = EXCLUDED.after_days,
                                 set_by = EXCLUDED.set_by, set_at = now()"""),
                 {"c": code, "a": action, "d": after_days, "by": actor})
    from . import audit
    audit.record(conn, actor=actor, action="housekeeping.rule", object_type="retention_rule", object_id=code,
                 details={"name": RULES[code][0], "rule": code, "do": action, "after_days": after_days})
    return next(r for r in rules(conn) if r["code"] == code)


def state(conn) -> dict:
    """Whether housekeeping may act: a dry run of the rules as they are now, confirmed."""
    snap = _rule_snapshot(conn)
    last = _rows(conn, "SELECT * FROM core.housekeeping_runs ORDER BY id DESC LIMIT 1")
    confirmed = _rows(conn, """SELECT * FROM core.housekeeping_runs WHERE dry_run AND confirmed_at IS NOT NULL
                                ORDER BY confirmed_at DESC LIMIT 1""")
    ok = bool(confirmed) and confirmed[0]["rules"] == snap
    waiting = _rows(conn, """SELECT * FROM core.housekeeping_runs WHERE dry_run AND confirmed_at IS NULL AND status = 'done'
                              ORDER BY id DESC LIMIT 1""")
    waiting = [w for w in waiting if w["rules"] == snap] if not ok else []
    acting = [r for r in snap.values() if r[0] != "keep"]
    return {"confirmed": ok, "confirmed_run": _run_shape(confirmed[0]) if confirmed else None,
            "awaiting_confirmation": _run_shape(waiting[0]) if waiting else None,
            "last_run": _run_shape(last[0]) if last else None, "rules_act": bool(acting),
            "schedule": "every night at 02:40 (the server's time)"}


def _run_shape(r: dict) -> dict:
    return {"id": r["id"], "guid": str(r["guid"]), "dry_run": r["dry_run"], "started_by": r["started_by"],
            "started_at": _iso(r["started_at"]), "finished_at": _iso(r["finished_at"]), "status": r["status"],
            "message": r["message"], "rules": r["rules"], "results": r["results"],
            "confirmed_at": _iso(r["confirmed_at"]), "confirmed_by": r["confirmed_by"]}


def runs(conn, limit: int = 30) -> list[dict]:
    return [_run_shape(r) for r in _rows(conn, "SELECT * FROM core.housekeeping_runs ORDER BY id DESC LIMIT :n", n=limit)]


def confirm(conn, actor: str, run_id) -> dict:
    run = _rows(conn, "SELECT * FROM core.housekeeping_runs WHERE id::text = :i OR guid::text = :i", i=str(run_id))
    if not run:
        raise LookupError("No such run.")
    run = run[0]
    if not run["dry_run"] or run["status"] != "done":
        raise ValueError("Only a finished dry run is confirmed.")
    if run["rules"] != _rule_snapshot(conn):
        raise ValueError("The rules changed since this dry run: do a new dry run first.")
    conn.execute(text("UPDATE core.housekeeping_runs SET confirmed_at = now(), confirmed_by = :a WHERE id = :i"),
                 {"a": actor, "i": run["id"]})
    from . import audit
    audit.record(conn, actor=actor, action="housekeeping.confirm", object_type="housekeeping_run", object_id=str(run["guid"]),
                 details={"name": f"dry run of {str(_iso(run['started_at']))[:16].replace('T', ' ')}"})
    return state(conn)


# Each rule: how to find what is due (a SELECT of id, created_at, model_id, summary and the row as JSON) and where it lives
_FIND: dict[str, tuple[str, str]] = {
    "loads": ("core.loads", """SELECT l.id, l.created_at, l.model_id, l.file_name || ' (' || l.status || ')' AS summary,
                                     to_jsonb(l) - 'content' AS data, l.content AS content
                                FROM core.loads l WHERE l.status IN ('added', 'undone', 'failed') AND l.created_at < :cut
                               ORDER BY l.id LIMIT :n"""),
    "task_files": ("core.task_files", """SELECT f.id, f.created_at, NULL::bigint AS model_id, f.name AS summary,
                                             to_jsonb(f) - 'content' AS data, f.content AS content
                                        FROM core.task_files f WHERE f.created_at < :cut ORDER BY f.id LIMIT :n"""),
    "notifications": ("core.notifications", """SELECT n.id, n.created_at, n.model_id, n.title AS summary,
                         to_jsonb(n) || jsonb_build_object('recipients', (SELECT coalesce(jsonb_agg(to_jsonb(r)), '[]')
                                 FROM core.notification_recipients r WHERE r.notification_id = n.id)) AS data, NULL::bytea AS content
                         FROM core.notifications n WHERE n.created_at < :cut AND (NOT n.needs_action OR n.resolved_at IS NOT NULL)
                        ORDER BY n.id LIMIT :n"""),
    "webhook_deliveries": ("core.webhook_deliveries", """SELECT d.id, d.created_at, NULL::bigint AS model_id,
                         'webhook ' || d.webhook_id || ': ' || d.status AS summary, to_jsonb(d) AS data, NULL::bytea AS content
                         FROM core.webhook_deliveries d WHERE d.status IN ('sent', 'failed') AND d.created_at < :cut
                        ORDER BY d.id LIMIT :n"""),
    "discarded_changes": ("core.pending_changes", """SELECT p.id, p.created_at, p.model_id, p.op || ' ' || p.label || ' (' || p.status || ')' AS summary,
                         to_jsonb(p) AS data, NULL::bytea AS content
                         FROM core.pending_changes p WHERE p.status IN ('discarded', 'rejected') AND p.created_at < :cut
                        ORDER BY p.id LIMIT :n"""),
}
_COUNT: dict[str, str] = {
    "usage": "SELECT count(*) FROM core.usage_daily WHERE day < CAST(:cut AS date)",
    "housekeeping_runs": "SELECT count(*) FROM core.housekeeping_runs WHERE started_at < :cut AND confirmed_at IS NULL",
}


def run(conn, actor: str, dry_run: bool) -> dict:
    """One housekeeping run over every rule. A real run needs a confirmed dry run of the rules as they are."""
    if not dry_run and not state(conn)["confirmed"]:
        raise NotConfirmed("Housekeeping acts only after a dry run of these rules is confirmed.")
    snap = _rule_snapshot(conn)
    rid = conn.execute(text("""INSERT INTO core.housekeeping_runs (dry_run, started_by, rules) VALUES (:d, :a, CAST(:r AS jsonb))
                               RETURNING id"""), {"d": dry_run, "a": actor, "r": json.dumps(snap)}).scalar()
    results: dict[str, dict] = {}
    now = datetime.now(UTC)
    for code, (action, days) in snap.items():
        cut = now - timedelta(days=days)
        res = {"action": action, "after_days": days, "found": 0, "archived": 0, "deleted": 0, "note": ""}
        if code in _FIND:
            table, sql = _FIND[code]
            rows = _rows(conn, sql, cut=cut, n=BATCH)
            res["found"] = len(rows)
            if len(rows) == BATCH:
                res["note"] = f"More than {BATCH}: the rest goes on the next run."
            if not dry_run and action != "keep" and rows:
                ids = [r["id"] for r in rows]
                if action == "archive":
                    for r in rows:
                        conn.execute(text("""INSERT INTO core.archived_items (rule, source_table, source_id, model_id, summary, data,
                                                     content, created_at, run_id)
                                             VALUES (:rule, :t, :i, :m, :s, CAST(:d AS jsonb), :c, :ca, :run)
                                             ON CONFLICT (source_table, source_id) DO NOTHING"""),
                                     {"rule": code, "t": table, "i": r["id"], "m": r["model_id"], "s": (r["summary"] or "")[:300],
                                      "d": json.dumps(r["data"], default=str) if not isinstance(r["data"], str) else r["data"],
                                      "c": r["content"], "ca": r["created_at"], "run": rid})
                    res["archived"] = len(ids)
                else:
                    res["deleted"] = len(ids)
                conn.execute(text(f"DELETE FROM {table} WHERE id = ANY(:ids)"), {"ids": ids})
        elif code == "history_versions":
            res.update(history_due(conn, cut, action, dry_run, actor))
        else:
            res["found"] = int(_scalar(conn, _COUNT[code], cut=cut if code != "usage" else cut.date().isoformat()) or 0)
            if not dry_run and action == "delete" and res["found"]:
                if code == "usage":
                    conn.execute(text("DELETE FROM core.usage_daily WHERE day < CAST(:cut AS date)"), {"cut": cut.date().isoformat()})
                else:
                    conn.execute(text("""DELETE FROM core.housekeeping_runs WHERE started_at < :cut AND confirmed_at IS NULL
                                          AND id <> :run"""), {"cut": cut, "run": rid})
                res["deleted"] = res["found"]
        results[code] = res
    conn.execute(text("""UPDATE core.housekeeping_runs SET finished_at = now(), status = 'done', results = CAST(:r AS jsonb)
                          WHERE id = :i"""), {"r": json.dumps(results), "i": rid})
    from . import audit
    audit.record(conn, actor=actor, action="housekeeping.dry_run" if dry_run else "housekeeping.run",
                 object_type="housekeeping_run", object_id=str(rid),
                 details={"name": "housekeeping " + ("dry run" if dry_run else "run"),
                          "archived": sum(r["archived"] for r in results.values()),
                          "deleted": sum(r["deleted"] for r in results.values())})
    return _run_shape(_rows(conn, "SELECT * FROM core.housekeeping_runs WHERE id = :i", i=rid)[0])


# ---------------------------------------------------------------- old history versions (D445)
# Due: a version older than the age that is not the current one of its row, whose row nobody pins (a governance
# record's principle or standard), and that was not the current version at any pinned moment of its model (a tag of any
# kind, so baselines and a child's merge starting point too, and drawn view evidence added to a project).
_DUE = """
    WITH pin(model_id, at) AS (SELECT * FROM unnest(CAST(:pm AS bigint[]), CAST(:pt AS timestamptz[]))),
    v AS (SELECT h.id, h.model_id, h.row_guid, h.changed_at,
                 lead(h.changed_at) OVER (PARTITION BY h.table_name, h.row_id ORDER BY h.row_version, h.id) AS next_at
            FROM history.row_versions h
           WHERE (h.table_name, h.row_id) IN (SELECT table_name, row_id FROM history.row_versions WHERE changed_at < :cut))
    SELECT v.id, v.model_id FROM v
     WHERE v.next_at IS NOT NULL AND v.changed_at < :cut
       AND NOT (v.row_guid = ANY (CAST(:keep AS uuid[])))
       AND NOT EXISTS (SELECT 1 FROM pin WHERE pin.model_id = v.model_id AND pin.at >= v.changed_at AND pin.at < v.next_at)"""


def _arr(values) -> str:
    """A PostgreSQL array literal (as text, cast in the query)."""
    return "{" + ",".join('"' + str(v).replace('"', "") + '"' for v in values) + "}"


def _pins(conn) -> tuple[list, list, list]:
    """The moments whose model state must stay viewable, and the rows pinned whole: (model ids, moments, row guids)."""
    pm, pt, keep = [], [], []
    for r in _rows(conn, "SELECT model_id, created_at FROM core.model_tags"):          # tags, baselines, merge bases
        pm.append(r["model_id"])
        pt.append(_iso(r["created_at"]))
    try:                                         # the projects may live in their own database (D266)
        from .db import get_projects_engine
        with get_projects_engine().connect() as pc:
            ev = _rows(pc, "SELECT model_guid::text AS g, added_at FROM proj.view_evidence")
            keep = [r["g"] for r in _rows(pc, """SELECT principle::text AS g FROM proj.gov_records WHERE principle IS NOT NULL
                                                 UNION SELECT standard::text FROM proj.gov_records WHERE standard IS NOT NULL""")]
    except Exception:  # noqa: BLE001 - no projects database: nothing pinned from there
        try:
            ev = _rows(conn, "SELECT model_guid::text AS g, added_at FROM proj.view_evidence")
            keep = [r["g"] for r in _rows(conn, """SELECT principle::text AS g FROM proj.gov_records WHERE principle IS NOT NULL
                                                   UNION SELECT standard::text FROM proj.gov_records WHERE standard IS NOT NULL""")]
        except Exception:  # noqa: BLE001
            ev = []
    if ev:
        ids = {r["guid"]: r["id"] for r in _rows(conn, "SELECT id, guid::text AS guid FROM core.models")}
        for r in ev:
            if r["g"] in ids:
                pm.append(ids[r["g"]])
                pt.append(_iso(r["added_at"]))
    return pm, pt, keep


def history_due(conn, cut, action: str, dry_run: bool, actor: str = "schedule") -> dict:
    """What the history rule finds (per model) and, on a confirmed run with "delete", removes. History stays append-only
    for everything else: the guard is lifted only inside this transaction, by the table's owner, and checked back on
    before it ends, so no other session ever sees it off (D445, D248: nothing of this is logic in the database)."""
    pm, pt, keep = _pins(conn)
    p = {"pm": _arr(pm), "pt": _arr(pt), "keep": _arr(keep), "cut": cut}
    by = _rows(conn, f"""SELECT d.model_id, coalesce(m.name, '(no model)') AS model, count(*) AS versions
                           FROM ({_DUE}) d LEFT JOIN core.models m ON m.id = d.model_id
                          GROUP BY d.model_id, m.name ORDER BY count(*) DESC""", **p)
    found = sum(int(r["versions"]) for r in by)
    out = {"found": found, "by_model": [{"model": r["model"], "versions": int(r["versions"])} for r in by],
           "pinned_moments": len(pt), "pinned_rows": len(keep), "note": HISTORY_NOTE}
    if dry_run or action != "delete" or not found:
        return out
    conn.execute(text("ALTER TABLE history.row_versions DISABLE TRIGGER row_versions_no_change"))
    n = conn.execute(text(f"DELETE FROM history.row_versions WHERE id IN (SELECT id FROM ({_DUE}) d ORDER BY id LIMIT :n)"),
                     {**p, "n": HISTORY_BATCH})
    conn.execute(text("ALTER TABLE history.row_versions ENABLE TRIGGER row_versions_no_change"))
    on = _scalar(conn, """SELECT tgenabled FROM pg_trigger WHERE tgname = 'row_versions_no_change'
                            AND tgrelid = 'history.row_versions'::regclass""")
    if on != "O":
        raise RuntimeError("The history guard did not come back on: nothing is removed.")
    removed = getattr(n, "rowcount", None)
    out["deleted"] = int(removed if removed is not None and removed >= 0 else min(found, HISTORY_BATCH))
    if found > HISTORY_BATCH:
        out["note"] = f"More than {HISTORY_BATCH}: the rest goes on the next run. " + HISTORY_NOTE
    from . import audit
    audit.record(conn, actor=actor, action="housekeeping.history_removed", object_type="history",
                 object_id="row_versions", details={"name": "old history versions", "removed": out["deleted"],
                                                    "older_than": _iso(cut), "by_model": out["by_model"][:50]})
    return out


def scheduled(conn) -> dict | None:
    """The nightly run: acts when confirmed; otherwise a dry run, once for each set of rules, waiting to be confirmed."""
    st = state(conn)
    if st["confirmed"]:
        return run(conn, "schedule", dry_run=False)
    if st["awaiting_confirmation"]:
        return None
    return run(conn, "schedule", dry_run=True)


def archive_search(conn, q: str = "", rule: str = "", limit: int = 100) -> list[dict]:
    rows = _rows(conn, """
        SELECT id, rule, source_table, source_id, model_id, summary, created_at, archived_at, run_id,
               content IS NOT NULL AS has_file, coalesce(length(content), 0) AS bytes,
               (SELECT m.name FROM core.models m WHERE m.id = a.model_id) AS model
          FROM core.archived_items a
         WHERE (:rule = '' OR rule = :rule)
           AND (:q = '' OR summary ILIKE '%' || :q || '%' OR data::text ILIKE '%' || :q || '%')
         ORDER BY archived_at DESC, id DESC LIMIT :n""", rule=rule or "", q=(q or "").strip(), n=max(1, min(int(limit), 500)))
    return _clean(rows)


def archived_item(conn, ident: int) -> dict:
    r = _rows(conn, "SELECT id, rule, source_table, source_id, summary, data, created_at, archived_at FROM core.archived_items WHERE id = :i",
              i=int(ident))
    if not r:
        raise LookupError("Not in the archive.")
    return _clean(r)[0]


def archived_file(conn, ident: int) -> tuple[bytes, str, str]:
    r = _rows(conn, "SELECT content, data, summary FROM core.archived_items WHERE id = :i AND content IS NOT NULL", i=int(ident))
    if not r:
        raise LookupError("No file in the archive under that number.")
    data = r[0]["data"] if isinstance(r[0]["data"], dict) else json.loads(r[0]["data"])
    name = data.get("file_name") or data.get("name") or f"archived-{ident}"
    return bytes(r[0]["content"]), name, data.get("content_type") or "application/octet-stream"
