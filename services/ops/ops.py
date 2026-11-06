"""EA Explorer operations helper (phase 10, D183).

A very small web service on the internal network (port 8090, never published) that the API calls when a Super Admin
restarts the system from the administration console. It talks to the Docker engine through its socket and only ever:
  GET  /health                  is the helper up (no token)
  GET  /status                  this installation's containers, their state and health
  POST /restart                 restart every container of this installation (the database first, this helper last)
  POST /restart/<service>       restart one service (api, web, proxy, keycloak, reports, dms...)
  GET  /stats                   per container: CPU, memory, network and disk input/output, processes, Docker health,
                                restarts, started at, disk (its own layer and its volumes); cached a few seconds
  GET  /containers/<service>    one container: state, health with its last checks, image, mounts, ports, networks,
                                environment, restart policy, limits, and what it uses now
  GET  /containers/<service>/logs?tail=N   its last log lines (standard output and error)
  POST /containers/<service>/exec {command, cwd} runs a command inside it, in that folder; answers the new folder (sh -c, 60 s, output kept to 200 kB), unless
                                EAX_CONTAINER_CONSOLE=off in the config file
  POST /terminal/ticket        {service, user, cols, rows}: a one-time ticket (30 s) for an interactive terminal in a
                                container (D214); the browser opens wss://<host>/ops-terminal/<ticket>, which the proxy
                                passes to port 8091 here (a network only the proxy and this helper share)
  GET  /terminal/sessions       terminal sessions open and ended (who, container, start, end, why it ended)
  POST /terminal/sessions/ack   {ids}: ended sessions recorded in the audit trail, forgotten here
  GET  /terminal/<ticket>       on port 8091 only, no token (the ticket is the key): the WebSocket of the terminal
  GET  /services                the optional services, on or off in the config file (D191)
  POST /services                {service, on, by}: switch one on or off: the config file is copied first (a dated copy
                                in work/config-history), the switch written, then its containers started or stopped
  GET  /config-copies           the dated copies of the config file
  GET  /config-file[?name=<copy>] the config file (or one copy) as it is, in clear text (owner, 5 Nov 2026)
  GET  /config-diff?a=&b=       the settings that differ between two of them (empty name: the current file), clear text
  POST /config-copy             {by, why}: keep a dated copy of the config file now
  POST /config-check            {text}: check a config file typed on screen and what it would change (nothing saved)
  POST /config-file             {text, by, why}: save it (checked; the file now copied first); changed switches apply
  POST /config-restore          {name, by}: make a copy the config file again (the current one is copied first); the
                                service switches in it apply at once, every other setting at the next eax up
The config file is the work folder's eaexplorer.env, mounted at /eax-work. Every write also refreshes
work/services.env: the switches only (no secrets), which the api container reads.
Every request but /health needs the header X-Ops-Token = EAX_OPS_TOKEN. The installation's containers are found by the
Docker Compose project label of the helper's own container, so nothing outside this installation is ever touched.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import pty
import re
import secrets
import select
import shutil
import signal
import socket
import struct
import subprocess
import termios
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("EAX_OPS_TOKEN", "")
WORK = os.environ.get("EAX_WORK_MOUNT", "/eax-work")
CONFIG = os.path.join(WORK, "eaexplorer.env")
HISTORY = os.path.join(WORK, "config-history")
# the optional services (eax/services.py): setting, containers in start order; mcp and the change log run in the api
SERVICES = {"reports": ("EAX_SERVICE_REPORTS", ["reports-init", "reports"]),
            "documents": ("EAX_SERVICE_DOCUMENTS", ["dms-broker", "dms"]),
            "drawio": ("EAX_SERVICE_DRAWIO", ["drawio"]),
            "mcp": ("EAX_SERVICE_MCP", ["api"]),
            "change_log": ("EAX_SERVICE_CHANGE_LOG", ["api"]),
            "backups": ("EAX_SERVICE_BACKUPS", ["backup"])}
OFF = {"off", "false", "0", "no", "disabled"}
SECTION = "# ---- Services (D191)"
ORDER = ["db", "dms-broker", "keycloak", "api", "reports", "dms", "drawio", "web", "backup", "proxy"]
state = {"restarting": False, "started": None, "finished": None, "log": []}
# what is being applied, one entry per service (owner, 5 Nov 2026: each switched on its own, the others stay usable),
# and "config" for a restore or a saved config file (these may touch several services, so they wait for the others)
jobs: dict[str, dict] = {}
config_lock = threading.Lock()   # one write of the config file at a time


def busy(key: str) -> bool:
    return bool(jobs.get(key, {}).get("busy"))


def switching() -> dict:
    return {"busy": any(j["busy"] for j in jobs.values()), "jobs": jobs}


def docker(*args: str, timeout: int = 120) -> str:
    r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[:500])
    return r.stdout


def project() -> str:
    labels = json.loads(docker("inspect", "--format", "{{json .Config.Labels}}", socket.gethostname()))
    return labels.get("com.docker.compose.project", "")


def containers() -> list[dict]:
    out = docker("ps", "-a", "--filter", f"label=com.docker.compose.project={project()}",
                 "--format", "{{json .}}")
    rows = []
    for line in out.splitlines():
        c = json.loads(line)
        svc = docker("inspect", "--format", '{{index .Config.Labels "com.docker.compose.service"}}', c["ID"]).strip()
        rows.append({"id": c["ID"], "name": c["Names"], "service": svc, "state": c["State"], "status": c["Status"],
                     "image": c["Image"]})
    me = socket.gethostname()
    for r in rows:
        r["self"] = r["id"].startswith(me) or me.startswith(r["id"])
    return sorted(rows, key=lambda r: (ORDER.index(r["service"]) if r["service"] in ORDER else 50, r["service"]))


def _restart(services: list[str] | None) -> None:
    state.update(restarting=True, started=time.time(), finished=None, log=[])
    try:
        time.sleep(2)   # the API answers the console first
        for c in containers():
            if c["self"] or (services and c["service"] not in services) or c["state"] != "running":
                continue   # one-shot set-up containers (setup, reports-init) that have finished are left alone
            state["log"].append(f"restarting {c['service']}")
            try:
                docker("restart", "--time", "20", c["id"], timeout=180)
                state["log"].append(f"restarted {c['service']}")
            except Exception as exc:  # noqa: BLE001 - keep going: one service must not stop the others
                state["log"].append(f"{c['service']}: {exc}")
    finally:
        state.update(restarting=False, finished=time.time())


# ---------------------------------------------------------------- the config file, its copies and the service switches
def _lines_of(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def _read_config() -> list[str]:
    with open(CONFIG, encoding="utf-8") as f:
        return f.read().splitlines()


def _values(lines: list[str]) -> dict[str, str]:
    out = {}
    for line in lines:
        t = line.strip()
        if t and not t.startswith("#") and "=" in t:
            k, v = t.split("=", 1)
            out[k.strip()] = v.strip().strip("'\"")
    return out


def switches(lines: list[str] | None = None) -> dict[str, bool]:
    v = _values(lines if lines is not None else _read_config())
    out = {}
    for key, (setting, _) in SERVICES.items():
        raw = v.get(setting, v.get("EAX_MCP_ENABLED", "on") if key == "mcp" else "on")
        out[key] = raw.strip().lower() not in OFF
    return out


def _who(by: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "-", by or "console")[:40]


def copy_config(by: str, why: str) -> str:
    """A dated copy of the config file before it changes: config-history/eaexplorer.env.<UTC time>.<who>.<why>."""
    os.makedirs(HISTORY, exist_ok=True)
    name = f"eaexplorer.env.{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}.{_who(by)}.{_who(why)}"
    shutil.copy2(CONFIG, os.path.join(HISTORY, name))
    return name


def _write(lines: list[str]) -> None:
    # in place (not a new file): keeps the owner and permissions, and bind mounts of the file see the change
    with open(CONFIG, "r+", encoding="utf-8", newline="\n") as f:
        f.seek(0)
        f.write("\n".join(lines) + "\n")
        f.truncate()
    write_services_file(lines)


def write_services_file(lines: list[str] | None = None) -> None:
    """work/services.env: the switches only, readable by the api container (D191)."""
    sw = switches(lines)
    body = "# Written by EA Explorer from eaexplorer.env: the service switches only (D191). Do not edit; change eaexplorer.env.\n"
    body += "".join(f"{SERVICES[k][0]}={'on' if on else 'off'}\n" for k, on in sw.items())
    path = os.path.join(WORK, "services.env")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    os.chmod(path, 0o644)


def set_switch(lines: list[str], key: str, on: bool) -> list[str]:
    setting, value = SERVICES[key][0], "on" if on else "off"
    out, done = [], False
    for line in lines:
        if re.match(rf"^\s*{setting}\s*=", line):
            out.append(f"{setting}={value}")
            done = True
        elif key == "mcp" and re.match(r"^\s*EAX_MCP_ENABLED\s*=", line):
            continue   # the name before phase 10
        else:
            out.append(line)
    if not done:
        if SECTION not in out:
            out += ["", SECTION]
        out.insert(out.index(SECTION) + 1, f"{setting}={value}")
    return out


def _container(service: str) -> dict | None:
    return next((c for c in containers() if c["service"] == service), None)


def _finished_ok(cid: str) -> bool:
    """A one-shot container that has run to the end without an error (exit code 0)."""
    st = docker("inspect", "--format", "{{.State.Status}} {{.State.ExitCode}} {{.State.FinishedAt}}", cid).split()
    return st[0] == "exited" and st[1] == "0" and not st[2].startswith("0001")


def apply_switch(key: str, on: bool) -> list[str]:
    """Starts (in order) or stops the service's containers; mcp and the change log restart the api container."""
    log = []
    names = SERVICES[key][1]
    if names == ["api"]:
        c = _container("api")
        if c:
            docker("restart", "--time", "20", c["id"], timeout=180)
            log.append("restarted api")
        return log
    missing = [n for n in names if not _container(n)]
    if missing and on:
        raise RuntimeError(f"No container for {', '.join(missing)} yet: run eax up once to create it; the switch is saved.")
    for n in (names if on else list(reversed(names))):
        c = _container(n)
        if not c:
            continue
        if on:
            if c["state"] == "running":
                log.append(f"{n} already running")
                continue
            if n == "reports-init" and _finished_ok(c["id"]):
                log.append("reports-init: set up before, not run again")   # eax up runs it; starting takes seconds
                continue
            docker("start", c["id"], timeout=180)
            if n == "reports-init":   # one-shot set-up (never run yet): wait until it has finished
                for _ in range(240):
                    st = docker("inspect", "--format", "{{.State.Status}} {{.State.ExitCode}}", c["id"]).split()
                    if st[0] == "exited":
                        if st[1] != "0":
                            raise RuntimeError("reports-init failed: see eax logs reports-init")
                        break
                    time.sleep(5)
            log.append(f"started {n}")
        elif n != "reports-init":
            docker("stop", "--time", "20", c["id"], timeout=180)
            log.append(f"stopped {n}")
    return log


def _in_background(key: str, what: str, fn) -> None:
    """Starting a service can take minutes (the reports set-up): the answer goes back at once, the console polls."""
    jobs[key] = {"busy": True, "what": what, "log": [], "error": "", "started": time.time(), "finished": None}

    def run():
        try:
            jobs[key]["log"] = fn() or []
        except Exception as exc:  # noqa: BLE001
            jobs[key]["error"] = str(exc)
        finally:
            jobs[key].update(busy=False, finished=time.time())
    threading.Thread(target=run, daemon=True).start()


def copies() -> list[dict]:
    if not os.path.isdir(HISTORY):
        return []
    out = []
    for name in sorted(os.listdir(HISTORY), reverse=True):
        if not name.startswith("eaexplorer.env."):
            continue
        parts = name.split(".", 4)   # eaexplorer . env . <time> . <who> . <why>
        path = os.path.join(HISTORY, name)
        out.append({"name": name, "at": parts[2] if len(parts) > 2 else "", "by": parts[3] if len(parts) > 3 else "",
                    "why": parts[4] if len(parts) > 4 else "", "bytes": os.path.getsize(path),
                    "switches": switches(_lines_of(path))})
    return out


def restore(name: str, by: str) -> dict:
    if not re.fullmatch(r"eaexplorer\.env\.[A-Za-z0-9_.-]+", name or "") or not os.path.isfile(os.path.join(HISTORY, name)):
        raise FileNotFoundError("No such copy of the config file.")
    before = switches()
    saved = copy_config(by, "before-restore")
    with open(os.path.join(HISTORY, name), encoding="utf-8") as f:
        lines = f.read().splitlines()
    _write(lines)
    after = switches(lines)

    def apply() -> list[str]:
        log = []
        for key in SERVICES:
            if before[key] != after[key]:
                try:
                    log += apply_switch(key, after[key])
                except Exception as exc:  # noqa: BLE001 - report it, keep going
                    log.append(f"{key}: {exc}")
        return log
    _in_background("config", f"restore {name}", apply)
    return {"restored": name, "saved_first": saved,
            "message": f"{name} is the config file again (the one before is kept as {saved}). Service switches applied now; "
                       "every other setting applies at the next eax up (or eax clean-restart)."}


def _path_of(name: str) -> str:
    if not name:
        return CONFIG
    if not re.fullmatch(r"eaexplorer\.env\.[A-Za-z0-9_.-]+", name) or not os.path.isfile(os.path.join(HISTORY, name)):
        raise FileNotFoundError(f"No such copy of the config file: {name}")
    return os.path.join(HISTORY, name)


def config_text(name: str = "") -> dict:
    """The config file (or one dated copy) as it is, in clear text: passwords and secrets too (owner, 5 Nov 2026)."""
    path = _path_of(name)
    lines = _lines_of(path)
    return {"name": name or "eaexplorer.env", "file": "work/" + (f"config-history/{name}" if name else "eaexplorer.env"),
            "modified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(path))),
            "text": "\n".join(lines), "switches": switches(lines),
            "editable": not name}


def _diff(va: dict[str, str], vb: dict[str, str]) -> tuple[list[dict], int]:
    rows = [{"setting": k, "change": "added" if va.get(k) is None else "removed" if vb.get(k) is None else "changed",
             "a": va.get(k), "b": vb.get(k)} for k in sorted(set(va) | set(vb)) if va.get(k) != vb.get(k)]
    return rows, sum(1 for k in set(va) & set(vb) if va[k] == vb[k])


def config_diff(a: str, b: str) -> dict:
    """Setting by setting (comments and order ignored): added, removed and changed, in clear text (owner, 5 Nov 2026)."""
    rows, same = _diff(_values(_lines_of(_path_of(a))), _values(_lines_of(_path_of(b))))
    return {"a": a or "eaexplorer.env", "b": b or "eaexplorer.env", "rows": rows, "same": same}


KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
NEEDED = ["EAX_HOSTNAME", "EAX_DEPLOYMENT", "EAX_DB_PASSWORD", "EAX_DB_MIGRATOR_PASSWORD", "EAX_KC_ADMIN_PASSWORD",
          "EAX_KEYCLOAK_REALM"]


def check_text(text: str) -> dict:
    """A config file typed on screen, before it is saved: every line a comment, empty or KEY=value; no setting twice;
    the settings EA Explorer cannot start without still there. Also what would change against the file now."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    errors, warnings, seen = [], [], {}
    for n, line in enumerate(lines, 1):
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        if "=" not in t:
            errors.append(f"Line {n}: not a setting (KEY=value) and not a comment (#): {t[:60]}")
            continue
        k = t.split("=", 1)[0].strip()
        if not KEY.match(k):
            errors.append(f"Line {n}: {k[:40]!r} is not a setting name (letters, digits and _ only)")
        elif k in seen:
            errors.append(f"Line {n}: {k} is already set on line {seen[k]}")
        else:
            seen[k] = n
    now = _values(_read_config())
    new = _values(lines)
    for k in NEEDED:
        if k in now and k not in new:
            errors.append(f"{k} is missing: EA Explorer cannot start without it")
    for k in ("EAX_DB_PASSWORD", "EAX_DB_MIGRATOR_PASSWORD", "EAX_DB_SUPERUSER_PASSWORD", "EAX_DB_REPORT_PASSWORD",
              "EAX_KEYCLOAK_DB_PASSWORD", "EAX_SUPERSET_DB_PASSWORD", "EAX_MAYAN_DB_PASSWORD"):
        if k in now and k in new and now[k] != new[k]:
            warnings.append(f"{k} changed: the database keeps the old password until it is changed there too "
                            "(rotating passwords comes with phase 36); until then the service cannot sign in")
    if new.get("EAX_KEYCLOAK_REALM", "") != now.get("EAX_KEYCLOAK_REALM", ""):
        warnings.append("EAX_KEYCLOAK_REALM changed: the realm is chosen at the first install (D187); "
                        "a new name on an existing installation means a new, empty realm")
    rows, same = _diff(now, new)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "rows": rows, "same": same, "lines": lines}


def save_text(text: str, by: str, why: str) -> dict:
    """Saves a config file typed on screen: checked, the file now copied first, then written. Service switches that
    changed apply at once (as a restore does); every other setting at the next eax up."""
    chk = check_text(text)
    if not chk["ok"]:
        raise ValueError("; ".join(chk["errors"]))
    if not chk["rows"]:
        return {"saved_first": None, "rows": [], "message": "Nothing changed: the config file is as it was."}
    before = switches()
    saved = copy_config(by, why or "edited")
    _write(chk["lines"])
    after = switches(chk["lines"])
    changed = [k for k in SERVICES if before[k] != after[k]]
    if changed:
        def apply() -> list[str]:
            log = []
            for key in changed:
                try:
                    log += apply_switch(key, after[key])
                except Exception as exc:  # noqa: BLE001 - report it, keep going
                    log.append(f"{key}: {exc}")
            return log
        _in_background("config", "config file saved", apply)
    n = len(chk["rows"])
    return {"saved_first": saved, "rows": chk["rows"], "warnings": chk["warnings"],
            "message": f"Saved: {n} setting{'' if n == 1 else 's'} changed; the file before is kept as {saved}. "
                       + (f"Service switches applied now ({', '.join(changed)}); " if changed else "")
                       + "every other setting applies at the next eax up (or eax clean-restart)."}


_stats_cache: dict = {"at": 0.0, "data": None}
_disk_cache: dict = {"at": 0.0, "data": {}}


def _size(text: str) -> int:
    """Docker's sizes ("12.5MiB", "1.2GB", "512kB", "0B") in bytes."""
    m = re.match(r"\s*([\d.]+)\s*([kKMGT]?i?B)", text or "")
    if not m:
        return 0
    unit = m.group(2).upper().replace("I", "")
    mult = {"B": 1, "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12}[unit] * (1.024 ** "BKMGT".index(unit[0]) if "i" in m.group(2) else 1)
    return int(float(m.group(1)) * mult)


def _num(v) -> float | None:
    """Docker's "2.50%", "9" or "--" (a container still starting) as a number, or None."""
    try:
        return float(str(v or "").strip().rstrip("%"))
    except ValueError:
        return None


def _volume_sizes() -> dict:
    """Volume sizes: slow on Docker, so refreshed in the background at most every five minutes; the last known
    sizes are answered meanwhile (none the very first time)."""
    if time.time() - _disk_cache["at"] >= 300 and not _disk_cache.get("busy"):
        _disk_cache["busy"] = True

        def run():
            try:
                out = json.loads(docker("system", "df", "-v", "--format", "{{json .}}", timeout=120) or "{}")
                _disk_cache["data"] = {v.get("Name"): _size(v.get("Size", "")) for v in out.get("Volumes") or []}
            except Exception:  # noqa: BLE001 - disk sizes are a nicety
                pass
            finally:
                _disk_cache.update(at=time.time(), busy=False)
        threading.Thread(target=run, daemon=True).start()
    return _disk_cache["data"]


def stats(fresh: bool = False) -> dict:
    """What each container of this installation uses now (docker stats, inspect and ps -s)."""
    if not fresh and _stats_cache["data"] and time.time() - _stats_cache["at"] < 5:
        return _stats_cache["data"]
    rows = {c["id"][:12]: {**c, "cpu_percent": None, "memory_bytes": None, "memory_limit_bytes": None,
                           "memory_percent": None, "net_io": "", "block_io": "", "pids": None}
            for c in containers()}
    running = [i for i, c in rows.items() if c["state"] == "running"]
    problems = []
    try:
        lines = docker("stats", "--no-stream", "--format", "{{json .}}", *running, timeout=60).splitlines() if running else []
    except Exception as exc:  # noqa: BLE001 - shown, the rest still answered
        lines, _ = [], problems.append(f"docker stats: {exc}")
    if lines:
        for line in lines:
            st = json.loads(line)
            r = rows.get(st.get("ID", "")[:12])
            if not r:
                continue
            used, _, limit = (st.get("MemUsage") or "").partition("/")
            r.update(cpu_percent=_num(st.get("CPUPerc")), memory_bytes=_size(used), memory_limit_bytes=_size(limit),
                     memory_percent=_num(st.get("MemPerc")), net_io=st.get("NetIO", ""), block_io=st.get("BlockIO", ""),
                     pids=int(_num(st.get("PIDs")) or 0))
    # the whole inspect as JSON, read in Python: a Go template fails on keys a container lacks (no health check, a
    # bind mount has no Name), which stopped every row being read (owner's test, 6 Nov 2026)
    try:
        inspected = json.loads(docker("inspect", *rows.keys(), timeout=60) or "[]") if rows else []
    except Exception as exc:  # noqa: BLE001
        inspected, _ = [], problems.append(f"docker inspect: {exc}")
    for d in inspected:
        r = rows.get((d.get("Id") or "")[:12])
        if not r:
            continue
        st = d.get("State") or {}
        r.update(health=(st.get("Health") or {}).get("Status") or "none", started_at=st.get("StartedAt") or "",
                 restarts=int(d.get("RestartCount") or 0), exit_code=int(st.get("ExitCode") or 0),
                 oom_killed=bool(st.get("OOMKilled")), image=(d.get("Config") or {}).get("Image") or r.get("image"),
                 volumes=[m.get("Name") for m in d.get("Mounts") or [] if m.get("Type") == "volume" and m.get("Name")])
    try:
        for line in docker("ps", "-a", "-s", "--filter", f"label=com.docker.compose.project={project()}",
                           "--format", "{{.ID}}|{{.Size}}").splitlines():
            cid, size = (line.split("|") + [""])[:2]
            if cid[:12] in rows:
                rows[cid[:12]]["layer_bytes"] = _size(size.split("(")[0])
    except Exception as exc:  # noqa: BLE001
        problems.append(f"docker ps: {exc}")
    vols = _volume_sizes()
    for r in rows.values():
        r["volume_bytes"] = sum(vols.get(v, 0) for v in r.get("volumes", []))
    out = {"containers": list(rows.values()), "at": time.time(), "volumes_at": _disk_cache["at"], "problems": problems}
    _stats_cache.update(at=time.time(), data=out)
    return out


# ---------------------------------------------------------------- the container console (owner, 6 Nov 2026)

def _one_container(service: str) -> dict:
    for c in containers():
        if c["service"] == service:
            return c
    raise FileNotFoundError(f"No container for the service {service}.")


def container_detail(service: str) -> dict:
    c = _one_container(service)
    d = json.loads(docker("inspect", c["id"]))[0]
    st, cfg, hc = d.get("State", {}), d.get("Config", {}), d.get("HostConfig", {})
    health = st.get("Health") or {}
    nets = (d.get("NetworkSettings") or {}).get("Networks") or {}
    ports = (d.get("NetworkSettings") or {}).get("Ports") or {}
    now = next((x for x in stats(fresh=True)["containers"] if x["service"] == service), {})
    return {
        "service": service, "name": c["name"], "id": d.get("Id", "")[:12], "image": cfg.get("Image"),
        "image_id": (d.get("Image") or "")[7:19], "created": d.get("Created"),
        "state": {"status": st.get("Status"), "running": st.get("Running"), "started_at": st.get("StartedAt"),
                  "finished_at": st.get("FinishedAt"), "exit_code": st.get("ExitCode"), "oom_killed": st.get("OOMKilled"),
                  "restarts": d.get("RestartCount", 0), "pid": st.get("Pid"), "error": st.get("Error")},
        "health": {"status": health.get("Status", "none"), "failing_streak": health.get("FailingStreak", 0),
                   "test": " ".join((cfg.get("Healthcheck") or {}).get("Test") or []),
                   "log": [{"start": x.get("Start"), "exit_code": x.get("ExitCode"), "output": (x.get("Output") or "")[-500:]}
                           for x in (health.get("Log") or [])[-5:]]},
        "command": " ".join((cfg.get("Entrypoint") or []) + (cfg.get("Cmd") or [])), "working_dir": cfg.get("WorkingDir"),
        "user": cfg.get("User") or "root",
        "restart_policy": (hc.get("RestartPolicy") or {}).get("Name"),
        "limits": {"memory_bytes": hc.get("Memory") or None, "cpus": (hc.get("NanoCpus") or 0) / 1e9 or None},
        "mounts": [{"type": m.get("Type"), "source": m.get("Name") or m.get("Source"), "destination": m.get("Destination"),
                    "read_only": not m.get("RW", True)} for m in d.get("Mounts") or []],
        "ports": [{"container": k, "host": ", ".join(f"{b.get('HostIp')}:{b.get('HostPort')}" for b in (v or []))}
                  for k, v in sorted(ports.items())],
        "networks": [{"name": k, "ip": v.get("IPAddress"), "aliases": v.get("Aliases") or []} for k, v in nets.items()],
        "environment": sorted(cfg.get("Env") or []),   # clear text, as the config file (D200)
        "labels": {k: v for k, v in sorted((cfg.get("Labels") or {}).items()) if k.startswith("com.docker.compose")},
        "now": {k: now.get(k) for k in ("cpu_percent", "memory_bytes", "memory_limit_bytes", "memory_percent", "net_io",
                                         "block_io", "pids", "layer_bytes", "volume_bytes")},
        "console": console_on(),
    }


def container_logs(service: str, tail: int = 300) -> dict:
    c = _one_container(service)
    r = subprocess.run(["docker", "logs", "--timestamps", "--tail", str(max(1, min(tail, 5000))), c["id"]],
                       capture_output=True, text=True, timeout=60)
    lines = sorted((r.stdout + r.stderr).splitlines())   # both streams, in time order (each line starts with its time)
    return {"service": service, "lines": lines[-tail:]}


def console_on() -> bool:
    try:
        lines = _read_config()
    except OSError:
        return False   # no config file to read: off, the safe side
    return _values(lines).get("EAX_CONTAINER_CONSOLE", "on").strip().lower() not in OFF


MARK = "__EAX_CWD__"


def container_exec(service: str, command: str, cwd: str = "") -> dict:
    """Runs one command in the container, in the folder the console is in (cwd; empty: the container's working folder),
    and answers the folder it ends in, so cd carries over to the next command like a terminal (owner, 6 Nov 2026).
    Variables set with export do not carry over: each command is still its own shell."""
    if not console_on():
        raise PermissionError("Running commands in containers is switched off (EAX_CONTAINER_CONSOLE=off in the config file).")
    command = (command or "").strip()
    if not command:
        raise ValueError("Type a command.")
    c = _one_container(service)
    if c["state"] != "running":
        raise ValueError(f"{service} is not running ({c['state']}): start it first.")
    # the folder and the command reach the shell as variables, never pasted into the script
    script = ('if [ -n "$EAX_CWD" ]; then cd -- "$EAX_CWD" 2>/dev/null || echo "cd: $EAX_CWD: no longer there" >&2; fi\n'
              '__c=$EAX_CMD; unset EAX_CMD EAX_CWD\neval "$__c"\n__rc=$?\nprintf "\\n%s%s\\n" "' + MARK + '" "$(pwd)" >&2\nexit $__rc')
    started = time.time()
    try:
        r = subprocess.run(["docker", "exec", "-e", f"EAX_CWD={cwd}", "-e", f"EAX_CMD={command}", c["id"], "sh", "-c", script],
                           capture_output=True, timeout=60)
        out, err, code = r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired as exc:
        out, err, code = (exc.stdout or b"") + b"\n[stopped after 60 seconds]", exc.stderr or b"", None
    err_text = err.decode("utf-8", "replace")
    new_cwd = cwd
    if MARK in err_text:
        err_text, _, tail = err_text.rpartition(MARK)
        new_cwd = tail.strip() or cwd
        err_text = err_text[:-1] if err_text.endswith("\n") else err_text
    text_ = out.decode("utf-8", "replace") + err_text
    cut = len(text_) > 200_000
    return {"service": service, "command": command, "exit_code": code, "output": text_[-200_000:], "cut": cut,
            "cwd": new_cwd, "ms": round((time.time() - started) * 1000)}


# ---------------------------------------------------------------- the interactive terminal (owner, 6 Nov 2026, D214)
# A real shell in a container for IT and Super Admins: docker exec -it on a pseudo-terminal here, carried to the browser
# over a WebSocket. The API checks the person and asks for a one-time ticket; the browser connects with it through the
# proxy to port 8091, which answers nothing but terminals. A session ends when the person ends it (exit, End session,
# closing the tab) or after EAX_TERMINAL_IDLE_MINUTES (default 15) without typing. Only its start and end are kept.

TERMINAL_PORT = 8091
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
SHELL = "if command -v bash >/dev/null 2>&1; then exec bash -l; else exec sh -l; fi"
_tickets: dict[str, dict] = {}
_sessions: dict[str, dict] = {}
_tlock = threading.Lock()


def idle_minutes() -> int:
    try:
        return max(1, int(_values(_read_config()).get("EAX_TERMINAL_IDLE_MINUTES", "15") or 15))
    except (OSError, ValueError):
        return 15


def terminal_ticket(service: str, user: str, cols: int = 120, rows: int = 32) -> dict:
    if not console_on():
        raise PermissionError("Terminals in containers are switched off (EAX_CONTAINER_CONSOLE=off in the config file).")
    c = _one_container(service)
    if c["state"] != "running":
        raise ValueError(f"{service} is not running ({c['state']}): start it first.")
    ticket, sid = secrets.token_urlsafe(32), secrets.token_hex(8)
    now = time.time()
    with _tlock:
        for k in [k for k, t in _tickets.items() if t["until"] < now]:
            del _tickets[k]
        _tickets[ticket] = {"session": sid, "service": service, "cid": c["id"], "user": user or "?",
                            "cols": max(20, min(int(cols or 120), 500)), "rows": max(5, min(int(rows or 32), 200)),
                            "until": now + 30}
    return {"ticket": ticket, "session": sid, "idle_minutes": idle_minutes()}


def terminal_sessions() -> list[dict]:
    with _tlock:
        return [dict(x) for x in _sessions.values()]


def terminal_ack(ids: list[str]) -> int:
    with _tlock:
        gone = [i for i in ids if i in _sessions and _sessions[i].get("ended")]
        for i in gone:
            del _sessions[i]
    return len(gone)


def _winsize(fd: int, rows: int, cols: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def ws_frame(opcode: int, payload: bytes) -> bytes:
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + payload


def ws_read(rfile) -> tuple[int, bytes] | None:
    """One whole message from the browser (frames joined), unmasked; None when the connection is gone."""
    opcode, data = None, b""
    while True:
        head = rfile.read(2)
        if len(head) < 2:
            return None
        fin, op, masked, n = head[0] & 0x80, head[0] & 0x0F, head[1] & 0x80, head[1] & 0x7F
        if n == 126:
            n = struct.unpack(">H", rfile.read(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", rfile.read(8))[0]
        if n > 1_000_000:
            return None
        mask = rfile.read(4) if masked else b""
        body = rfile.read(n) if n else b""
        if masked:
            body = bytes(b ^ mask[i % 4] for i, b in enumerate(body))
        if op >= 8:          # close, ping, pong: on their own, never fragmented
            return op, body
        if op:
            opcode = op
        data += body
        if fin:
            return opcode or 1, data


class TerminalHandler(BaseHTTPRequestHandler):
    """Port 8091: a WebSocket per terminal, opened with a ticket from /terminal/ticket. Nothing else."""
    rbufsize = 0   # unbuffered, so select() sees every byte the browser sends

    def log_message(self, fmt, *args):
        print(f"ops terminal: {self.command} -> {args[1] if len(args) > 1 else ''}", flush=True)

    def _refuse(self, code: int, msg: str) -> None:
        data = msg.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        m = re.match(r"^/terminal/([A-Za-z0-9_-]{20,80})$", self.path.split("?")[0])
        if not m:
            return self._refuse(404, "No such request.")
        with _tlock:
            t = _tickets.pop(m.group(1), None)
        if not t or t["until"] < time.time():
            return self._refuse(403, "This terminal link has expired or was used: open the terminal again.")
        key = self.headers.get("Sec-WebSocket-Key", "")
        if self.headers.get("Upgrade", "").lower() != "websocket" or not key:
            return self._refuse(400, "A WebSocket is needed.")
        accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.wfile.flush()
        run_terminal(self.connection, self.rfile, t)
        self.close_connection = True


def run_terminal(sock, rfile, t: dict) -> None:
    sid, idle = t["session"], idle_minutes() * 60
    send_lock = threading.Lock()
    rec = {"id": sid, "service": t["service"], "user": t["user"], "started": time.time(), "ended": None, "reason": "",
           "exit_code": None}
    with _tlock:
        _sessions[sid] = rec

    def send(op: int, payload: bytes) -> bool:
        try:
            with send_lock:
                sock.sendall(ws_frame(op, payload))
            return True
        except OSError:
            return False

    def note(text_: str) -> None:
        send(2, f"\r\n\x1b[33m[{text_}]\x1b[0m\r\n".encode())

    master, slave = pty.openpty()
    _winsize(slave, t["rows"], t["cols"])
    try:
        proc = subprocess.Popen(["docker", "exec", "-it", "-e", "TERM=xterm-256color", t["cid"], "sh", "-c", SHELL],
                                stdin=slave, stdout=slave, stderr=slave, close_fds=True, start_new_session=True)
    except OSError as exc:
        os.close(master)
        os.close(slave)
        note(f"could not start: {exc}")
        rec.update(ended=time.time(), reason=f"could not start: {exc}")
        return
    os.close(slave)
    done = threading.Event()

    def pump() -> None:   # the shell's output to the browser
        while True:
            try:
                data = os.read(master, 65536)
            except OSError:
                break
            if not data or not send(2, data):
                break
        done.set()
    threading.Thread(target=pump, daemon=True).start()
    last_typed, reason = time.time(), ""
    try:
        while not reason:
            if done.is_set() or proc.poll() is not None:
                done.wait(1)
                rec["exit_code"] = proc.wait(timeout=5)
                reason = "the shell ended (exit)"
                break
            if time.time() - last_typed > idle:
                note(f"closed after {idle // 60} minutes without typing")
                reason = f"idle {idle // 60} minutes"
                break
            ready, _, _ = select.select([sock], [], [], 1)
            if not ready:
                continue
            msg = ws_read(rfile)
            if msg is None:
                reason = "the browser disconnected"
                break
            op, body = msg
            if op == 8:
                reason = "ended by the person"
                break
            if op == 9:
                send(10, body)
                continue
            if op not in (1, 2):
                continue
            try:
                m = json.loads(body.decode("utf-8", "replace"))
            except ValueError:
                continue
            if m.get("t") == "i":
                last_typed = time.time()
                os.write(master, str(m.get("d", "")).encode())
            elif m.get("t") == "r":
                _winsize(master, max(5, min(int(m.get("rows") or 24), 200)), max(20, min(int(m.get("cols") or 80), 500)))
                proc.send_signal(signal.SIGWINCH)   # docker passes the new size to the shell in the container
            elif m.get("t") == "end":
                reason = "ended by the person"
    finally:
        if proc.poll() is None:
            try:
                os.write(master, b"\x04")   # Ctrl+D, then hang up: the shell in the container ends with its terminal
            except OSError:
                pass
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            os.close(master)
        except OSError:
            pass
        send(1, json.dumps({"t": "exit", "reason": reason, "code": rec["exit_code"]}).encode())
        send(8, struct.pack(">H", 1000))
        rec.update(ended=time.time(), reason=reason)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _ok(self) -> bool:
        if not TOKEN or not hmac.compare_digest(self.headers.get("X-Ops-Token", ""), TOKEN):
            self._send(403, {"message": "Not allowed."})
            return False
        return True

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            return self._send(200, {"status": "ok"})
        if not self._ok():
            return None
        if self.path.split("?")[0] == "/stats":
            try:
                return self._send(200, stats(fresh="fresh" in self.path))
            except Exception as exc:  # noqa: BLE001
                return self._send(500, {"message": str(exc)})
        m = re.match(r"^/containers/([a-z0-9_-]+)(/logs)?(?:\?(.*))?$", self.path)
        if m:
            from urllib.parse import parse_qs
            try:
                if m.group(2):
                    tail = int((parse_qs(m.group(3) or "").get("tail") or ["300"])[0])
                    return self._send(200, container_logs(m.group(1), tail))
                return self._send(200, container_detail(m.group(1)))
            except FileNotFoundError as exc:
                return self._send(404, {"message": str(exc)})
            except Exception as exc:  # noqa: BLE001
                return self._send(500, {"message": str(exc)})
        if self.path == "/services":
            try:
                return self._send(200, {"switches": switches(), "containers": containers(), "switching": switching()})
            except Exception as exc:  # noqa: BLE001
                return self._send(500, {"message": str(exc)})
        if self.path.split("?")[0] == "/config-file":
            from urllib.parse import parse_qs, urlparse
            name = (parse_qs(urlparse(self.path).query).get("name") or [""])[0]
            try:
                return self._send(200, config_text(name))
            except FileNotFoundError as exc:
                return self._send(404, {"message": str(exc)})
            except OSError as exc:
                return self._send(500, {"message": f"Could not read the config file: {exc}"})
        if self.path.split("?")[0] == "/config-diff":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            try:
                return self._send(200, config_diff((q.get("a") or [""])[0], (q.get("b") or [""])[0]))
            except FileNotFoundError as exc:
                return self._send(404, {"message": str(exc)})
            except OSError as exc:
                return self._send(500, {"message": f"Could not read the config file: {exc}"})
        if self.path == "/config-copies":
            return self._send(200, {"copies": copies()})
        if self.path == "/terminal/sessions":
            return self._send(200, {"sessions": terminal_sessions()})
        if self.path == "/status":
            try:
                return self._send(200, {"project": project(), "containers": containers(), "restart": state})
            except Exception as exc:  # noqa: BLE001
                return self._send(500, {"message": str(exc)})
        return self._send(404, {"message": "No such request."})

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}") if n else {}
        except ValueError:
            return {}

    def do_POST(self):  # noqa: N802
        if not self._ok():
            return None
        if self.path == "/terminal/ticket":
            b = self._body()
            try:
                return self._send(200, terminal_ticket(str(b.get("service") or ""), str(b.get("user") or ""),
                                                       int(b.get("cols") or 120), int(b.get("rows") or 32)))
            except FileNotFoundError as exc:
                return self._send(404, {"message": str(exc)})
            except PermissionError as exc:
                return self._send(403, {"message": str(exc)})
            except ValueError as exc:
                return self._send(400, {"message": str(exc)})
        if self.path == "/terminal/sessions/ack":
            return self._send(200, {"forgotten": terminal_ack([str(i) for i in self._body().get("ids") or []])})
        m = re.match(r"^/containers/([a-z0-9_-]+)/exec$", self.path)
        if m:
            b = self._body()
            try:
                return self._send(200, container_exec(m.group(1), str(b.get("command") or ""), str(b.get("cwd") or "")))
            except FileNotFoundError as exc:
                return self._send(404, {"message": str(exc)})
            except PermissionError as exc:
                return self._send(403, {"message": str(exc)})
            except ValueError as exc:
                return self._send(400, {"message": str(exc)})
        if self.path == "/services":
            b = self._body()
            key, on, by = b.get("service"), bool(b.get("on")), str(b.get("by") or "console")
            if key not in SERVICES:
                return self._send(404, {"message": f"No optional service {key!r}."})
            if busy(key) or busy("config"):
                what = jobs[key if busy(key) else "config"]["what"]
                return self._send(409, {"message": f"Still applying: {what}. Try again in a moment."})
            try:
                with config_lock:
                    if switches()[key] == on:   # already so in the config file: only start (or stop) its containers
                        saved = None
                    else:
                        saved = copy_config(by, f"{key}-{'on' if on else 'off'}")
                        _write(set_switch(_read_config(), key, on))
            except OSError as exc:
                return self._send(500, {"message": f"Could not write the config file: {exc}"})
            _in_background(key, f"{key} {'on' if on else 'off'}", lambda: apply_switch(key, on))
            return self._send(202, {"service": key, "on": on, "saved_first": saved,
                                    "message": (f"{key} is switched {'on' if on else 'off'} in the config file (the one before is kept "
                                                f"as {saved}); its containers are being {'started' if on else 'stopped'}.") if saved
                                    else f"{key}: its containers are being {'started' if on else 'stopped'}."})
        if self.path == "/config-copy":
            b = self._body()
            try:
                name = copy_config(str(b.get("by") or "console"), str(b.get("why") or "kept-by-hand"))
            except OSError as exc:
                return self._send(500, {"message": f"Could not copy the config file: {exc}"})
            return self._send(200, {"name": name, "message": f"Copy kept: {name}."})
        if self.path == "/config-check":
            out = check_text(str(self._body().get("text") or ""))
            out.pop("lines")
            return self._send(200, out)
        if self.path == "/config-file":
            b = self._body()
            if switching()["busy"]:
                now = ", ".join(j["what"] for j in jobs.values() if j["busy"])
                return self._send(409, {"message": f"Still applying: {now}. Try again when it is done."})
            try:
                with config_lock:
                    return self._send(200, save_text(str(b.get("text") or ""), str(b.get("by") or "console"),
                                                     str(b.get("why") or "")))
            except ValueError as exc:
                return self._send(400, {"message": f"Not saved: {exc}"})
            except OSError as exc:
                return self._send(500, {"message": f"Could not write the config file: {exc}"})
        if self.path == "/config-restore":
            b = self._body()
            if switching()["busy"]:
                now = ", ".join(j["what"] for j in jobs.values() if j["busy"])
                return self._send(409, {"message": f"Still applying: {now}. Try again when it is done."})
            try:
                with config_lock:
                    return self._send(202, restore(b.get("name", ""), str(b.get("by") or "console")))
            except FileNotFoundError as exc:
                return self._send(404, {"message": str(exc)})
            except OSError as exc:
                return self._send(500, {"message": f"Could not restore: {exc}"})
        if state["restarting"]:
            return self._send(409, {"message": "A restart is already running."})
        if self.path == "/restart":
            threading.Thread(target=_restart, args=(None,), daemon=True).start()
            return self._send(202, {"message": "Restarting every service of this installation."})
        if self.path.startswith("/restart/"):
            svc = self.path.split("/", 2)[2]
            if svc not in {c["service"] for c in containers()}:
                return self._send(404, {"message": f"No service {svc!r} in this installation."})
            threading.Thread(target=_restart, args=([svc],), daemon=True).start()
            return self._send(202, {"message": f"Restarting {svc}."})
        return self._send(404, {"message": "No such request."})

    def log_message(self, fmt, *args):  # quieter log: one line per request
        print(f"ops: {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}", flush=True)


if __name__ == "__main__":
    if not TOKEN:
        print("ops: EAX_OPS_TOKEN is not set; every request but /health is refused", flush=True)
    try:
        write_services_file()
    except OSError as exc:
        print(f"ops: could not write services.env ({exc})", flush=True)
    terminals = ThreadingHTTPServer(("0.0.0.0", TERMINAL_PORT), TerminalHandler)
    terminals.daemon_threads = True
    threading.Thread(target=terminals.serve_forever, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
