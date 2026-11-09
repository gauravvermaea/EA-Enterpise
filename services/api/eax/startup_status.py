"""The start-up status (D255): what is up, starting or down, for everyone (red, amber, green in the header).

The start-up has two tiers. The core (database, sign-in, the API, the screens) is up whenever anyone can read this. The
second tier starts after it, in the background: Reports (Superset), Documents (Mayan), Diagrams (draw.io) and the work
after the API has started (the sample data and the first data quality measurement, eax/seed/later.py). For each:
  up        it answers (its health check) or the work is done        green
  starting  its container is still starting (or set up, or waiting), or the work is going on   amber
  down      its container stopped or failed, or the work failed   red
  off       switched off in the config file (D191)   grey
Whether a part that does not answer is starting or down comes from the operations helper (its container's state); when
the helper is not reachable either, the first 15 minutes after this API server started count as starting.
The answer is kept for a few seconds, so many screens asking cost one check. Nothing is calculated in the database (D248).
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text

from . import health as hc

STARTED = time.time()            # when this API server started
GRACE_SECONDS = 15 * 60          # without the operations helper: starting for this long, then down
KEEP_SECONDS = 8
ONE_SHOT = {"reports-init", "setup"}
PARTS = [  # key, name, what it is, its check, its containers (in start order)
    ("reports", "Reports", "Apache Superset", hc.check_reports, ["reports-init", "reports"]),
    ("documents", "Documents", "Mayan EDMS", hc.check_dms, ["dms-broker", "dms"]),
    ("drawio", "Diagrams", "draw.io", hc.check_drawio, ["drawio"]),
    ("library", "Library", "the library service", hc.check_library, ["library"]),
]
CORE = ["db", "setup", "proxy", "web", "keycloak", "api"]     # the first tier: started before anyone can sign in

_lock = threading.Lock()
_kept: dict = {"at": 0.0, "data": None}


def container_state(c: dict) -> str:
    """A container's start-up state from Docker: up, starting or down (a one-shot set-up container that finished
    well is up)."""
    state, status = (c.get("state") or "").lower(), (c.get("status") or "").lower()
    if c.get("service") in ONE_SHOT:
        if state == "exited":
            return "up" if "exited (0)" in status else "down"
        return "starting"
    if state == "running":
        if "health: starting" in status or "(starting)" in status:
            return "starting"
        if "unhealthy" in status:
            return "down"
        return "up"
    if state in ("created", "restarting"):
        return "starting"
    return "down"             # exited, dead, paused, removing


def _containers() -> list[dict] | None:
    from .api.admin import _ops_raw
    try:
        return _ops_raw("GET", "/status", timeout=8).get("containers") or []
    except Exception:  # noqa: BLE001 - not reachable (it starts in the second tier too)
        return None


def _later(conn) -> dict | None:
    try:
        r = conn.execute(text("""SELECT part, name, state, done, total, detail, started_at, finished_at
                                   FROM core.startup_parts WHERE part = 'later'""")).mappings().first()
    except Exception:  # noqa: BLE001 - before the migration
        return None
    if not r:
        return None
    state = {"waiting": "starting", "skipped": "up"}.get(r["state"], r["state"])
    loading = f"loading ({r['done']} of {r['total']})" if state == "starting" else ""
    return {"key": "later", "name": r["name"], "product": "after the start", "status": state,
            "detail": loading or r["detail"], "done": r["done"], "total": r["total"],
            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None}


def _part_state(check: dict, containers: list[dict] | None, names: list[str], now: float) -> tuple[str, str]:
    if check["status"] in ("up", "warning"):
        return "up", check.get("detail") or "answering"
    if check["status"] == "off":
        return "off", check.get("detail") or "switched off"
    if containers is None:
        if now - STARTED < GRACE_SECONDS:
            return "starting", "not answering yet"
        return "down", check.get("detail") or "not answering"
    mine = [c for c in containers if c.get("service") in names]
    if not mine:
        return ("starting", "not created yet") if now - STARTED < GRACE_SECONDS else ("down", "no container")
    states = [container_state(c) for c in mine]
    if "down" in states:
        bad = next(c for c, s in zip(mine, states, strict=True) if s == "down")
        return "down", f"{bad.get('service')}: {bad.get('status') or bad.get('state')}"
    if "starting" in states:
        busy = next(c for c, s in zip(mine, states, strict=True) if s == "starting")
        what = "setting up" if busy.get("service") in ONE_SHOT else (busy.get("status") or busy.get("state") or "starting")
        return "starting", f"{busy.get('service')}: {what}"
    return "starting", "running, not answering yet"


def status(conn, fresh: bool = False) -> dict:
    """Every second-tier part's state, the work after the start, and the containers (for admins to read)."""
    now = time.time()
    with _lock:
        if not fresh and _kept["data"] and now - _kept["at"] < KEEP_SECONDS:
            data = dict(_kept["data"])
            data["later"] = _later(conn)
            return _finish(data)
    with ThreadPoolExecutor(max_workers=len(PARTS) + 1) as pool:
        checks = {k: pool.submit(f) for k, _n, _p, f, _c in PARTS}
        cs = pool.submit(_containers)
        containers = cs.result()
        results = {k: f.result() for k, f in checks.items()}
    parts = []
    for key, name, product, _f, names in PARTS:
        st, detail = _part_state(results[key], containers, names, now)
        parts.append({"key": key, "name": name, "product": product, "status": st, "detail": detail})
    data = {"parts": parts, "containers": [
        {"key": c.get("key") or c.get("service"), "service": c.get("service"), "state": c.get("state"),
         "status": c.get("status"), "startup": container_state(c),
         "tier": "first" if c.get("service") in CORE else "after"} for c in (containers or [])],
            "helper": containers is not None, "api_started": STARTED, "checked_at": now}
    with _lock:
        _kept.update(at=now, data=data)
    data = dict(data)
    data["later"] = _later(conn)
    return _finish(data)


def _finish(data: dict) -> dict:
    parts = list(data["parts"]) + ([data["later"]] if data.get("later") else [])
    states = [p["status"] for p in parts]
    data["overall"] = "down" if "down" in states else "starting" if "starting" in states else "up"
    data["all"] = parts
    return data
