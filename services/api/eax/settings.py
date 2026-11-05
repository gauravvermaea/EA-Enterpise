"""Phase 10 (D156, D182, D183): the settings of the administration console.

Two kinds:
  * runtime settings, in core.settings: changed on screen by a Super Admin and applied at once. The application
    settings every screen, report and export follow (base currency and symbol, country, time zone, date and number
    formats, first day of the week, the month the financial year starts) and the runtime system settings (largest
    upload, how long change log entries are kept, session time-outs, applied to Keycloak)
  * start-up settings: the config file (work/eaexplorer.env) the containers start with. Shown in the console with
    in clear text (IT and Super Admins); edited through the config file (D200); rotating secrets comes with phase 36 (D183)
"""

from __future__ import annotations

import os
import re
import threading
import time
import zoneinfo
from typing import Any

from sqlalchemy import text

from . import permissions as perms
from .metamodel_edit import EditError

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
DATE_FORMATS = ["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "DD.MM.YYYY", "DD MMM YYYY", "MMM DD, YYYY"]
CURRENCIES = ["USD", "ZAR", "EUR", "GBP", "AUD", "CAD", "INR", "JPY", "CHF", "CNY", "NZD", "SGD", "AED", "BRL", "KES", "NGN"]

# key: (group, label, type, default, choices or (min, max), help)
REGISTRY: dict[str, tuple] = {
    "base_currency": ("application", "Base currency", "choice", "USD", CURRENCIES, "Every money value is in this currency (D182)."),
    "currency_symbol": ("application", "Currency symbol", "text", "$", (1, 5), "Shown before amounts, for example $, R or €."),
    "country": ("application", "Country or region", "text", "South Africa", (2, 60), "Where the installation is used."),
    "time_zone": ("application", "Time zone", "timezone", "Africa/Johannesburg", None,
                  "Times are stored in UTC and shown in this time zone, for everyone."),
    "date_format": ("application", "Date format", "choice", "YYYY-MM-DD", DATE_FORMATS, "How dates are shown on screens and in exports."),
    "decimal_separator": ("application", "Decimal separator", "choice", ".", [".", ","], "1234.5 or 1234,5"),
    "thousands_separator": ("application", "Thousands separator", "choice", " ", [" ", ",", ".", "'", ""],
                            "Between groups of three digits (empty for none)."),
    "first_day_of_week": ("application", "First day of the week", "choice", "Monday", ["Monday", "Sunday", "Saturday"],
                          "Calendars and week-based reports."),
    "financial_year_start": ("application", "Month the financial year starts", "month", 3, (1, 12),
                             "Financial years and quarters in reports start in this month."),
    "upload_max_mb": ("system", "Largest upload (MB)", "int", 50, (1, 100),
                      "Packages, Excel and CSV sheets, documents. The web server lets at most 100 MB through."),
    "change_log_keep_days": ("system", "Keep change log entries (days)", "int", 730, (0, 36500),
                             "Older entries are removed automatically every hour; 0 keeps them for ever."),
    "session_idle_minutes": ("system", "Signed out after idle (minutes)", "int", 60, (5, 1440), "Applied to Keycloak at once."),
    "session_max_hours": ("system", "Longest session (hours)", "int", 10, (1, 168),
                          "Signed out after this long whatever happens; applied to Keycloak at once."),
    "log_level": ("system", "Log level", "choice", "INFO", ["DEBUG", "INFO", "WARNING", "ERROR"],
                  "How much the API, the job runner and the change log write to their logs (eax logs api); applied at once. "
                  "DEBUG is very verbose: use it only while looking into a problem."),
}

_cache: dict[str, Any] = {"at": 0.0, "values": None}
_lock = threading.Lock()
CACHE_SECONDS = 15


def _default_values() -> dict[str, Any]:
    return {k: v[3] for k, v in REGISTRY.items()}


def values(conn=None) -> dict[str, Any]:
    """Every runtime setting (cached for a few seconds); the defaults for any not in the database."""
    with _lock:
        if _cache["values"] is not None and time.monotonic() - _cache["at"] < CACHE_SECONDS:
            return dict(_cache["values"])
    out = _default_values()
    try:
        if conn is None:
            from .db import get_engine
            with get_engine().connect() as c:
                rows = c.execute(text("SELECT key, value FROM core.settings")).mappings().all()
        else:
            rows = conn.execute(text("SELECT key, value FROM core.settings")).mappings().all()
        for r in rows:
            if r["key"] in REGISTRY:
                out[r["key"]] = r["value"]
    except Exception:  # noqa: BLE001 - the defaults keep the API answering
        return out
    with _lock:
        _cache.update(at=time.monotonic(), values=dict(out))
    return out


def forget() -> None:
    with _lock:
        _cache.update(at=0.0, values=None)


def describe(conn) -> dict:
    """The settings with their labels, types, choices and help, grouped (for the console)."""
    v = values(conn)
    rows = {r["key"]: r for r in conn.execute(text("SELECT key, modified_at, modified_by FROM core.settings")).mappings()}
    out: dict[str, list] = {"application": [], "system": []}
    for k, (group, label, typ, default, choices, help_) in REGISTRY.items():
        out[group].append({"key": k, "label": label, "type": typ, "value": v[k], "default": default,
                           "choices": choices if isinstance(choices, list) else None,
                           "range": list(choices) if isinstance(choices, tuple) else None, "help": help_,
                           "modified_at": rows.get(k, {}).get("modified_at") if _by_person(rows.get(k, {})) else None,
                           "modified_by": rows.get(k, {}).get("modified_by") if _by_person(rows.get(k, {})) else None})
    out["months"] = MONTHS
    return out


def _by_person(row: dict) -> bool:
    """A setting changed by a person (not the installer's defaults)."""
    return bool(row.get("modified_by")) and row["modified_by"] not in ("eax_app", "eax_migrator", "postgres")


def check(key: str, value: Any) -> Any:
    """The value as stored, or EditError saying what is wrong."""
    if key not in REGISTRY:
        raise EditError(f"There is no setting '{key}'.", 404)
    _group, label, typ, _default, choices, _help = REGISTRY[key]
    if typ in ("int", "month"):
        try:
            n = int(value)
        except (TypeError, ValueError) as exc:
            raise EditError(f"{label}: a whole number, please.") from exc
        lo, hi = choices
        if not lo <= n <= hi:
            raise EditError(f"{label}: between {lo} and {hi}.")
        return n
    s = "" if value is None else str(value)
    if typ == "choice":
        if s not in choices:
            raise EditError(f"{label}: one of {', '.join(repr(c) for c in choices)}.")
        return s
    if typ == "timezone":
        if s not in zoneinfo.available_timezones():
            raise EditError(f"{label}: '{s}' is not a time zone (for example Africa/Johannesburg).")
        return s
    lo, hi = choices
    s = s.strip()
    if not lo <= len(s) <= hi:
        raise EditError(f"{label}: {lo} to {hi} characters.")
    return s


def update(conn, user, changes: dict) -> dict:
    """Changes settings (Super Admin), applies them at once (session time-outs in Keycloak), returns the new values."""
    if perms.SUPER_ADMIN not in (user.roles or []):
        raise EditError("Only a Super Admin changes settings.", 403)
    clean = {k: check(k, v) for k, v in (changes or {}).items()}
    if clean.get("decimal_separator", values(conn)["decimal_separator"]) == clean.get("thousands_separator",
                                                                                       values(conn)["thousands_separator"]):
        raise EditError("The decimal and thousands separators must differ.")
    import json
    for k, v in clean.items():
        conn.execute(text("""INSERT INTO core.settings (key, value, name) VALUES (:k, CAST(:v AS jsonb), :n)
                             ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, modified_at = now(),
                                 modified_by = core.current_actor(), row_version = core.settings.row_version + 1
                             WHERE core.settings.value IS DISTINCT FROM EXCLUDED.value"""),
                     {"k": k, "v": json.dumps(v), "n": REGISTRY[k][1]})
    forget()
    applied, note = [], ""
    if {"session_idle_minutes", "session_max_hours"} & set(clean):
        v = {**values(conn), **clean}
        try:
            from . import keycloak_admin
            keycloak_admin.set_sessions(int(v["session_idle_minutes"]) * 60, int(v["session_max_hours"]) * 3600)
            applied.append("session time-outs (Keycloak)")
        except Exception as exc:  # noqa: BLE001
            note = f" The session time-outs are saved but Keycloak did not take them ({exc}); they apply after the next restart."
    return {"values": values(conn), "changed": sorted(clean), "note": f"{len(clean)} settings saved and applied at once.{note}",
            "applied": applied}


# ---------------------------------------------------------------- start-up settings (shown only, D183)
SECRET = re.compile(r"(PASSWORD|SECRET|TOKEN|_KEY$|PRIVATE)", re.I)
GROUPS = [("Database", ("EAX_DB_",)), ("Change log", ("EAX_CHANGELOG_",)), ("Host and network", ("EAX_HOSTNAME", "EAX_HTTP", "EAX_TLS",
          "EAX_PUBLIC")), ("Sign-in (Keycloak)", ("EAX_KC_", "EAX_KEYCLOAK", "EAX_FIRST_ADMIN", "EAX_BREAK_GLASS", "EAX_API_AUDIENCE")),
          ("Reports (Superset)", ("EAX_SUPERSET",)), ("Documents (Mayan)", ("EAX_MAYAN", "EAX_DMS")), ("MCP", ("EAX_MCP",)),
          ("Folders and backups", ("EAX_BACKUP", "EAX_IMPORT", "EAX_EXPORT", "EAX_WORK")), ("Operations helper", ("EAX_OPS",))]


def startup() -> dict:
    """The start-up settings the containers were started with (this container's view), grouped, in clear text: only IT
    and Super Admins see them (owner, 5 Nov 2026)."""
    env = {k: v for k, v in os.environ.items() if k.startswith("EAX_")}
    out: dict[str, list] = {}
    for k in sorted(env):
        group = next((g for g, prefixes in GROUPS if k.startswith(prefixes)), "General")
        out.setdefault(group, []).append({"key": k, "value": env[k], "secret": bool(SECRET.search(k))})
    return {"groups": [{"name": g, "settings": out[g]} for g, _ in [("General", ())] + GROUPS if g in out],
            "file": "work/eaexplorer.env",
            "note": "The values the containers were started with. Change them in the config file below (Edit): they apply at "
                    "the next eax up. Rotating passwords in the database and Keycloak comes with phase 36."}


_LEVEL = {"level": None}


def apply_log_level() -> None:
    """The log level set in the console (D191), applied to this process when it changed (cheap: values() is cached)."""
    import logging
    try:
        level = str(values().get("log_level") or "INFO").upper()
    except Exception:  # noqa: BLE001
        return
    if level != _LEVEL["level"] and level in ("DEBUG", "INFO", "WARNING", "ERROR"):
        logging.getLogger().setLevel(level)
        logging.getLogger("eax").setLevel(level)
        _LEVEL["level"] = level
