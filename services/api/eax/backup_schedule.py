"""When backups run and how many are kept (phase 8.4, D222).

One row per kind in operations.backup_schedules (infrastructure, application): on or off, a schedule (cron: minute hour day
month weekday, in the installation's time zone), the tag of the backups it makes, how many to keep, and after how many
hours without a backup the health check warns. IT and Super Admins change them on Administration > Backups; nothing
about backups is in the config file. The job runner looks every minute and starts what is due.
"""

from __future__ import annotations

import logging
import zoneinfo
from datetime import UTC, datetime

from sqlalchemy import text

from . import databases
from .metamodel_edit import EditError

log = logging.getLogger(__name__)
KINDS = ("infrastructure", "application")
FIELDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))   # weekday 0 and 7 are Sunday


def _part(spec: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for item in spec.split(","):
        step = 1
        if "/" in item:
            item, s = item.split("/", 1)
            step = int(s)
            if step < 1:
                raise ValueError
        if item == "*":
            a, b = lo, hi
        elif "-" in item:
            a, b = (int(x) for x in item.split("-", 1))
        else:
            a = b = int(item)
        if a < lo or b > hi or a > b:
            raise ValueError
        out.update(range(a, b + 1, step))
    return out


def parse(cron: str) -> list[set[int]]:
    """The five fields of a schedule as sets of numbers; EditError when it is not a schedule."""
    parts = (cron or "").split()
    if len(parts) != 5:
        raise EditError("A schedule has five parts: minute hour day month weekday (for example 0 1 * * * for 01:00 every day).")
    try:
        sets = [_part(p, lo, hi) for p, (lo, hi) in zip(parts, FIELDS, strict=True)]
    except ValueError as exc:
        raise EditError(f"'{cron}' is not a schedule: minute 0-59, hour 0-23, day 1-31, month 1-12, weekday 0-7.") from exc
    if 7 in sets[4]:
        sets[4].add(0)
    return sets


def matches(cron: str, at: datetime) -> bool:
    minute, hour, day, month, weekday = parse(cron)
    dow = (at.weekday() + 1) % 7      # Python: Monday 0; cron: Sunday 0
    day_ok = at.day in day
    dow_ok = dow in weekday
    restricted_day, restricted_dow = len(day) < 31, len(weekday) < 8   # cron: either restricted field may match
    days_match = (day_ok or dow_ok) if (restricted_day and restricted_dow) else (day_ok and dow_ok)
    return at.minute in minute and at.hour in hour and at.month in month and days_match


def describe(cron: str) -> str:
    """A schedule in words, for the screen (the common forms; others shown as they are)."""
    p = cron.split()
    days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    if len(p) == 5 and p[0].isdigit() and p[1].isdigit() and p[2] == "*" and p[3] == "*":
        at = f"{int(p[1]):02d}:{int(p[0]):02d}"
        if p[4] == "*":
            return f"every day at {at}"
        if p[4].isdigit():
            return f"every {days[int(p[4])]} at {at}"
    return f"on the schedule {cron}"


def zone(conn=None) -> zoneinfo.ZoneInfo:
    from . import settings as app_settings
    try:
        return zoneinfo.ZoneInfo(app_settings.values(conn).get("time_zone") or "UTC")
    except Exception:  # noqa: BLE001
        return zoneinfo.ZoneInfo("UTC")


def get_all(conn) -> list[dict]:
    rows = [dict(r) for r in databases.on("operations", conn).execute(text("SELECT * FROM operations.backup_schedules ORDER BY kind DESC")).mappings().all()]
    for r in rows:
        r["in_words"] = describe(r["cron"])
    return rows


def get(conn, kind: str) -> dict:
    r = databases.on("operations", conn).execute(text("SELECT * FROM operations.backup_schedules WHERE kind = :k"), {"k": kind}).mappings().first()
    if not r:
        return {"kind": kind, "enabled": False, "cron": "0 1 * * *", "tag": "scheduled", "keep": 7, "warn_after_hours": 36}
    return dict(r)


def keep(conn, kind: str) -> int:
    try:
        return int(get(conn, kind)["keep"])
    except Exception:  # noqa: BLE001 - before the migration ran
        return 7


def update(conn, kind: str, data: dict, by: str) -> dict:
    """Changes one schedule (IT and Super Admins): enabled, cron, tag, keep, warn_after_hours."""
    if kind not in KINDS:
        raise EditError("The kinds are infrastructure and application.", 404)
    cur = get(conn, kind)
    new = {k: data.get(k, cur[k]) for k in ("enabled", "cron", "tag", "keep", "warn_after_hours")}
    new["cron"] = " ".join(str(new["cron"]).split())
    parse(new["cron"])
    new["tag"] = str(new["tag"] or "").strip()[:60] or "scheduled"
    try:
        new["keep"], new["warn_after_hours"] = int(new["keep"]), int(new["warn_after_hours"])
    except (TypeError, ValueError) as exc:
        raise EditError("Keep and warn after are whole numbers.") from exc
    if not 1 <= new["keep"] <= 365:
        raise EditError("Keep between 1 and 365 backups.")
    if not 1 <= new["warn_after_hours"] <= 8760:
        raise EditError("Warn after between 1 and 8760 hours.")
    databases.on("operations", conn).execute(text("""UPDATE operations.backup_schedules SET enabled = :enabled, cron = :cron, tag = :tag, keep = :keep,
                                warn_after_hours = :warn_after_hours, updated_by = :by, updated_at = now() WHERE kind = :k"""),
                 {**new, "enabled": bool(new["enabled"]), "by": by.lower(), "k": kind})
    out = get(conn, kind)
    out["in_words"] = describe(out["cron"])
    return out


def due(conn, now: datetime | None = None) -> list[dict]:
    """The schedules due this minute (in the installation's time zone) that have not run in it yet; marks them run."""
    now = (now or datetime.now(UTC)).astimezone(zone(conn)).replace(second=0, microsecond=0)
    out = []
    for s in get_all(conn):
        if not s["enabled"]:
            continue
        try:
            if not matches(s["cron"], now):
                continue
        except EditError:
            continue
        last = s.get("last_run_at")
        if isinstance(last, str):
            last = datetime.fromisoformat(last)
        if last and last.astimezone(now.tzinfo).replace(second=0, microsecond=0) >= now:
            continue
        databases.on("operations", conn).execute(text("UPDATE operations.backup_schedules SET last_run_at = :t, last_status = 'started' WHERE kind = :k"),
                     {"t": now.astimezone(UTC), "k": s["kind"]})
        out.append(s)
    return out


def set_status(conn, kind: str, status: str) -> None:
    databases.on("operations", conn).execute(text("UPDATE operations.backup_schedules SET last_status = :s WHERE kind = :k"), {"s": status[:300], "k": kind})
