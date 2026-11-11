"""Scaling out the API and job servers by rules (phase 36.3, D378, D520, D526).

Set in the web application (System admin > Scaling; Super and IT Admins) and kept in the config file:

  EAX_SCALE_MODE=fixed|auto        fixed: EAX_API_SERVERS servers, as set (D249); auto: the rules below decide
  EAX_SCALE_MIN=1                  never fewer servers than this ...
  EAX_SCALE_MAX=4                  ... nor more (1 to 16)
  EAX_SCALE_USERS_PER_SERVER=25    one server for every this many people active in the last 15 minutes
  EAX_SCALE_CPU_UP=75              a server more when the servers' average CPU (%) stays above this ...
  EAX_SCALE_CPU_DOWN=25            ... one fewer when it stays below this (and the people allow it)
  EAX_SCALE_MINUTES=5              how long the CPU must stay above or below before anything changes
  EAX_SCALE_COOLDOWN=10            minutes to wait after a change before the next

Every minute in auto mode the helper reads the load (the servers' CPU from Docker; the people active, from the API,
which counts who it has seen in the last 15 minutes), decides (decide(), one step at a time) and applies it like
`eax servers <n>`: the number is written to EAX_API_SERVERS (a dated copy of the config file first) and servers are
added, or stopped once their jobs finish (D249). Each decision is logged in work/logs/scaling.jsonl.

Bound to ops.py's helpers with bind(globals())."""

from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.request

H: dict = {}
LOG = "/eax-work/logs/scaling.jsonl"
DEFAULTS = {"EAX_SCALE_MODE": "fixed", "EAX_SCALE_MIN": "1", "EAX_SCALE_MAX": "4", "EAX_SCALE_USERS_PER_SERVER": "25",
            "EAX_SCALE_CPU_UP": "75", "EAX_SCALE_CPU_DOWN": "25", "EAX_SCALE_MINUTES": "5", "EAX_SCALE_COOLDOWN": "10"}
LIMITS = {"EAX_SCALE_MIN": (1, 16), "EAX_SCALE_MAX": (1, 16), "EAX_SCALE_USERS_PER_SERVER": (1, 10000),
          "EAX_SCALE_CPU_UP": (10, 100), "EAX_SCALE_CPU_DOWN": (0, 90), "EAX_SCALE_MINUTES": (1, 120),
          "EAX_SCALE_COOLDOWN": (1, 240)}
samples: list[dict] = []        # the last hour of load samples
state: dict = {"last_change": 0.0, "last": None, "error": ""}


def bind(ns: dict) -> None:
    H.update(ns)


def settings(values: dict[str, str] | None = None) -> dict:
    v = values if values is not None else H["_values"](H["_read_config"]())
    out: dict = {}
    for key, default in DEFAULTS.items():
        raw = str(v.get(key, default)).strip() or default
        if key == "EAX_SCALE_MODE":
            out[key] = raw if raw in ("fixed", "auto") else "fixed"
        else:
            lo, hi = LIMITS[key]
            try:
                out[key] = max(lo, min(hi, int(raw)))
            except ValueError:
                out[key] = int(default)
    out["EAX_SCALE_MAX"] = max(out["EAX_SCALE_MAX"], out["EAX_SCALE_MIN"])
    return out


def check(new: dict) -> dict:
    """The settings asked for, checked: unknown keys and values out of range are refused (ValueError)."""
    clean: dict[str, str] = {}
    for key, value in new.items():
        if key not in DEFAULTS:
            raise ValueError(f"{key} is not a scaling setting.")
        if key == "EAX_SCALE_MODE":
            if value not in ("fixed", "auto"):
                raise ValueError("EAX_SCALE_MODE is fixed or auto.")
            clean[key] = value
            continue
        lo, hi = LIMITS[key]
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} is a whole number.") from None
        if not lo <= n <= hi:
            raise ValueError(f"{key} is between {lo} and {hi}.")
        clean[key] = str(n)
    merged = {**{k: str(v) for k, v in settings().items()}, **clean}
    if int(merged["EAX_SCALE_MAX"]) < int(merged["EAX_SCALE_MIN"]):
        raise ValueError("The most servers cannot be fewer than the fewest.")
    if int(merged["EAX_SCALE_CPU_DOWN"]) >= int(merged["EAX_SCALE_CPU_UP"]):
        raise ValueError("The CPU to scale down must be below the CPU to scale up.")
    return clean


def decide(s: dict, now_servers: int, users: int, history: list[dict], now: float, last_change: float) -> tuple[int, str]:
    """How many servers there should be, and why (one step at a time; pure, for the tests).

    history: load samples {t, cpu} of the last minutes (newest last). Never below the people's need nor outside min..max;
    the CPU moves it one up when it stayed above CPU_UP for MINUTES, one down when it stayed below CPU_DOWN; nothing
    changes within COOLDOWN minutes of the last change."""
    lo, hi = s["EAX_SCALE_MIN"], s["EAX_SCALE_MAX"]
    for_people = max(1, math.ceil(users / s["EAX_SCALE_USERS_PER_SERVER"])) if users else 1
    window = [h for h in history if h["t"] >= now - s["EAX_SCALE_MINUTES"] * 60]
    full = bool(window) and window[0]["t"] <= now - (s["EAX_SCALE_MINUTES"] * 60 - 90)   # the window is (almost) covered
    target, why = now_servers, "no change"
    if full and all(h["cpu"] > s["EAX_SCALE_CPU_UP"] for h in window):
        target, why = now_servers + 1, f"CPU above {s['EAX_SCALE_CPU_UP']}% for {s['EAX_SCALE_MINUTES']} minutes"
    elif full and all(h["cpu"] < s["EAX_SCALE_CPU_DOWN"] for h in window):
        target, why = now_servers - 1, f"CPU below {s['EAX_SCALE_CPU_DOWN']}% for {s['EAX_SCALE_MINUTES']} minutes"
    if target < for_people:
        target, why = min(for_people, now_servers + 1), f"{users} people active: {for_people} server(s) needed"
    if target < lo:
        target, why = lo, f"at least {lo} server(s)"
    if target > hi:
        target, why = hi, (why + f"; at most {hi}") if target != now_servers else why
    target = max(lo, min(hi, target))
    if target != now_servers and last_change and now - last_change < s["EAX_SCALE_COOLDOWN"] * 60:
        return now_servers, f"waiting: changed {int((now - last_change) / 60)} minute(s) ago (cool-down {s['EAX_SCALE_COOLDOWN']})"
    if target > now_servers + 1:
        target = now_servers + 1
    elif target < now_servers - 1:
        target = now_servers - 1
    return target, why


def cpu_of_servers() -> float | None:
    """The api containers' average CPU (%) now, from docker stats."""
    ids = [s["id"] for s in H["api_servers"]() if s["state"] == "running"]
    if not ids:
        return None
    out = H["docker"]("stats", "--no-stream", "--format", "{{.CPUPerc}}", *ids, timeout=60)
    vals = []
    for line in out.splitlines():
        try:
            vals.append(float(line.strip().rstrip("%")))
        except ValueError:
            pass
    return round(sum(vals) / len(vals), 1) if vals else None


def active_people() -> int | None:
    """How many people the API has seen in the last 15 minutes (it answers the helper with the ops token)."""
    url = os.environ.get("EAX_SCALE_API_URL", "http://api:8000") + "/api/v1/admin/scaling/load"
    req = urllib.request.Request(url, headers={"X-Ops-Token": os.environ.get("EAX_OPS_TOKEN", "")})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return int(json.load(r).get("people", 0))
    except (OSError, ValueError):
        return None


def log(entry: dict) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def events(limit: int = 50) -> list[dict]:
    try:
        with open(LOG, encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def tick() -> dict | None:
    """One minute's look: a load sample, and in auto mode a decision applied."""
    s = settings()
    now = time.time()
    cpu, people = cpu_of_servers(), active_people()
    servers = len([x for x in H["api_servers"]() if x["state"] == "running"])
    sample = {"t": now, "cpu": cpu if cpu is not None else 0.0, "people": people, "servers": servers}
    samples.append(sample)
    del samples[:-60]
    state["last"] = sample
    if s["EAX_SCALE_MODE"] != "auto" or cpu is None or H["busy"]("servers") or H["busy"]("config") or not servers:
        return None
    target, why = decide(s, servers, people or 0, [x for x in samples if x["cpu"] is not None], now, state["last_change"])
    if target == servers:
        return None
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "from": servers, "to": target, "why": why,
             "cpu": cpu, "people": people}
    with H["config_lock"]:
        H["copy_config"]("scaling", f"servers-{target}")
        H["_write"](H["_set_value"](H["_read_config"](), H["SERVERS_KEY"], str(target)))
    H["_in_background"]("servers", f"{target} API and job servers (scaling rule)", lambda: H["scale_api"](target))
    state["last_change"] = now
    log(entry)
    return entry


def loop() -> None:
    while True:
        try:
            tick()
            state["error"] = ""
        except Exception as exc:  # noqa: BLE001 - the loop never stops; the screen shows the last problem
            state["error"] = str(exc)[:300]
        time.sleep(60)


def start() -> None:
    threading.Thread(target=loop, daemon=True, name="scaling").start()


def describe() -> dict:
    s = settings()
    return {"settings": s, "defaults": DEFAULTS, "limits": LIMITS, "servers": H["servers_wanted"](),
            "running": len([x for x in H["api_servers"]() if x["state"] == "running"]),
            "last_sample": state["last"], "samples": samples[-30:], "events": events(), "error": state["error"],
            "last_change": state["last_change"]}


def save(new: dict, by: str) -> dict:
    clean = check(new)
    with H["config_lock"]:
        H["copy_config"](by or "console", "scaling-rules")
        lines = H["_read_config"]()
        for key, value in clean.items():
            lines = _set(lines, key, value)
        H["_write"](lines)
    log({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "settings": clean, "by": by})
    return describe()


def _set(lines: list[str], key: str, value: str) -> list[str]:
    import re
    out, done = [], False
    for line in lines:
        if re.match(rf"^\s*{key}\s*=", line):
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        if not any(line.startswith("# ---- Scaling") for line in out):
            out += ["", "# ---- Scaling the API and job servers (phase 36.3, D526): System admin > Scaling"]
        out.append(f"{key}={value}")
    return out
