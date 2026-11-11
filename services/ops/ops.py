"""EA Explorer operations helper (phase 10, D183).

A very small web service on the internal network (port 8090, never published) that the API calls when a Super Admin
restarts the system from the administration console. It talks to the Docker engine through its socket and only ever:
  GET  /health                  is the helper up (no token)
  GET  /status                  this installation's containers, their state and health
  POST /restart                 restart every container of this installation (the database first, this helper last)
  POST /restart/<service>       restart one service (api, web, proxy, keycloak, reports, dms...)
  GET  /stats                   per container: CPU, memory, network and disk input/output, processes, Docker health,
                                restarts, started at, disk (its own layer and its volumes); cached a few seconds;
                                and the file systems: size, used and free of the disks Docker and the work and backup
                                folders sit on, and what Docker keeps (images, containers, volumes, build cache)
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
  GET  /commands, /commands/runs, /commands/runs/<id>   POST /commands/run, /commands/console, /commands/runs/<id>/stop
                                GET/POST /commands/schedules (D559)    GET /banner, /banner/all   POST /banner, /banner/clear (D558)
                                eax commands from a web page: the Command centre and the Console (D554; commandcentre.py)
  GET  /terminal/<ticket>       on port 8091 only, no token (the ticket is the key): the WebSocket of the terminal
  GET  /backups                 the infrastructure backups, the one running (progress), maintenance
  POST /backups/backup          {tag, by, kind, version, pinned, keep}: an infrastructure backup now, in the background
                                (D216); then the oldest beyond `keep` go (pinned ones stay)
  POST /backups/stop            {by}: stop the backups running (D231)
  POST /backups/restore         {name, what, by, version}: restore one (what: full, app, app+data, db, files), in
                                read-only maintenance, a backup of the current state first
  POST /backups/<name>/pin      {pinned}: a pinned backup is never cleaned away
  POST /backups/cleanup         {keep}: keep the newest `keep` and the pinned ones, remove the rest
  GET  /backups/events          backups, restores and clean-ups since last asked (for the audit trail)
  POST /backups/<name>/delete   delete an infrastructure backup by hand (not pinned, not being restored)
  GET  /restores                every restore (infrastructure and application) with its status; the one running
  GET  /restores/<id>[?tail=N]  one restore with its log;  POST /restores/<id>/delete  forget a finished one
  GET  /restore/active          on port 8091, no token: whether a restore runs (the screens' lock page, D227)
  GET  /restore/<id>?token=     on port 8091: a restore's status and log for whoever started it, while the API is down
  GET  /servers                 the API and job servers (copies of the api container) and how many are wanted (D249)
  POST /servers                 {count, by}: run that many (1 to 16): copies of the first are added, or the highest-numbered
                                stopped (their jobs finish first) and removed; the number is written to the config file
  GET  /scaling                 the scaling rules, the load seen and the decisions (phase 36.3, D526; scaling.py)
  POST /scaling                 {settings, by}: save the rules (config file, a dated copy first)
  GET  /tests                   the test runner image and the self-test going on;  POST /tests {run_id, level, suites,
                                role, area, watch, by}: start it at once;  POST /tests/stop (phase 36.1, D367; testruns.py);
                                POST /tests/build, GET /tests/build/<id>, POST /tests/settings (the runner, D570)
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
  GET  /updates, /updates/versions?channel=   POST /updates/settings, /updates/start, /updates/retry,
       /updates/rollback, /updates/schedule/cancel   updating to a new release (phase 36, D417; updates.py)
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
import sys
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
            "backups": ("EAX_SERVICE_BACKUPS", ["backup"]),
            "library": ("EAX_SERVICE_LIBRARY", ["library"]),
            "views": ("EAX_SERVICE_VIEWS", ["views"])}
OFF = {"off", "false", "0", "no", "disabled"}
SECTION = "# ---- Services (D191)"
ORDER = ["db", "dms-broker", "keycloak", "api", "library", "views", "reports", "dms", "drawio", "web", "backup", "proxy"]
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
        svc, num = (docker("inspect", "--format", '{{index .Config.Labels "com.docker.compose.service"}}|'
                                                  '{{index .Config.Labels "com.docker.compose.container-number"}}',
                           c["ID"]).strip().split("|") + ["1"])[:2]
        rows.append({"id": c["ID"], "name": c["Names"], "service": svc, "number": int(num or 1) if (num or "1").isdigit() else 1,
                     "state": c["State"], "status": c["Status"], "image": c["Image"]})
    # a service with several containers (the API and job servers, D249): each is named and reached as service-number
    count: dict[str, int] = {}
    for r in rows:
        count[r["service"]] = count.get(r["service"], 0) + 1
    for r in rows:
        r["key"] = f"{r['service']}-{r['number']}" if count[r["service"]] > 1 or r["service"] == "api" and r["number"] > 1 else r["service"]
    me = socket.gethostname()
    for r in rows:
        r["self"] = r["id"].startswith(me) or me.startswith(r["id"])
    return sorted(rows, key=lambda r: (ORDER.index(r["service"]) if r["service"] in ORDER else 50, r["service"], r["number"]))


def _restart(services: list[str] | None) -> None:
    state.update(restarting=True, started=time.time(), finished=None, log=[])
    try:
        time.sleep(2)   # the API answers the console first
        for c in containers():
            if c["self"] or (services and c["service"] not in services and c["key"] not in services) or c["state"] != "running":
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
    if names == ["api"]:          # every API and job server (D249)
        for c in [x for x in containers() if x["service"] == "api" and x["state"] == "running"]:
            docker("restart", "--time", "20", c["id"], timeout=180)
            log.append(f"restarted {c['name']}")
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


# ---------------------------------------------------------------- API and job servers (D249)
MAX_SERVERS = 16
SERVERS_KEY = "EAX_API_SERVERS"


def api_servers() -> list[dict]:
    """The api containers (each answers API calls, which nginx spreads across them, and runs background jobs), by their
    number; number 1 is the first, which applies the database upgrade at start."""
    out = []
    for c in containers():
        if c["service"] != "api":
            continue
        info = json.loads(docker("inspect", "--format", "{{json .}}", c["id"]))
        labels = info["Config"].get("Labels") or {}
        health = ((info.get("State") or {}).get("Health") or {}).get("Status", "")
        out.append({"id": c["id"], "name": c["name"], "key": c["key"], "number": int(labels.get("com.docker.compose.container-number", "1")),
                    "state": c["state"], "health": health, "started": (info.get("State") or {}).get("StartedAt", ""),
                    "status": c["status"]})
    return sorted(out, key=lambda x: x["number"])


def servers_wanted(lines: list[str] | None = None) -> int:
    try:
        return max(1, min(MAX_SERVERS, int(_values(lines if lines is not None else _read_config()).get(SERVERS_KEY, "1"))))
    except ValueError:
        return 1


def _set_value(lines: list[str], key: str, value: str) -> list[str]:
    out, done = [], False
    for line in lines:
        if re.match(rf"^\s*{key}\s*=", line):
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out += ["", "# ---- API and job servers (D249): how many copies of the api container run; .\\eax servers <n> or the console",
                f"{key}={value}"]
    return out


def _clone_api(template: dict, number: int) -> str:
    """A new api container like the first one (image, settings, volumes, networks, labels, health check), with the next
    number, so Docker Compose counts it as one of the api service's containers (eax up keeps it)."""
    import shlex
    info = json.loads(docker("inspect", "--format", "{{json .}}", template["id"]))
    cfg, host = info["Config"], info["HostConfig"]
    labels = dict(cfg.get("Labels") or {})
    labels["com.docker.compose.container-number"] = str(number)
    project_name = labels.get("com.docker.compose.project", project())
    name = f"{project_name}-api-{number}"
    args = ["create", "--name", name]
    for e in cfg.get("Env") or []:
        args += ["-e", e]
    for k, v in labels.items():
        args += ["--label", f"{k}={v}"]
    for m in info.get("Mounts") or []:
        src = m.get("Name") if m.get("Type") == "volume" else m.get("Source")
        args += ["-v", f"{src}:{m['Destination']}{'' if m.get('RW', True) else ':ro'}"]
    rp = (host.get("RestartPolicy") or {}).get("Name")
    if rp:
        args += ["--restart", rp]
    lc = host.get("LogConfig") or {}
    if lc.get("Type"):
        args += ["--log-driver", lc["Type"]]
        for k, v in (lc.get("Config") or {}).items():
            args += ["--log-opt", f"{k}={v}"]
    hc = cfg.get("Healthcheck") or {}
    test = hc.get("Test") or []
    if test and test[0] in ("CMD", "CMD-SHELL"):
        args += ["--health-cmd", test[1] if test[0] == "CMD-SHELL" else shlex.join(test[1:])]
        for key, flag in (("Interval", "--health-interval"), ("Timeout", "--health-timeout"), ("StartPeriod", "--health-start-period")):
            if hc.get(key):
                args += [flag, f"{int(hc[key] / 1e9)}s"]
        if hc.get("Retries"):
            args += ["--health-retries", str(hc["Retries"])]
    if cfg.get("User"):
        args += ["--user", cfg["User"]]
    if host.get("StopTimeout") or cfg.get("StopTimeout"):
        args += ["--stop-timeout", str(cfg.get("StopTimeout") or host.get("StopTimeout"))]
    nets = (info.get("NetworkSettings") or {}).get("Networks") or {}
    names = list(nets)
    if names:
        args += ["--network", names[0], "--network-alias", "api"]
    args.append(cfg["Image"])
    cid = docker(*args, timeout=120).strip()
    for n in names[1:]:
        docker("network", "connect", "--alias", "api", n, cid)
    docker("start", cid, timeout=120)
    return name


def scale_api(count: int) -> list[str]:
    """Adds api containers up to count (copies of the first), or stops and removes the highest-numbered ones down to it
    (each stops gracefully: the jobs it is running finish first; the first is never removed)."""
    log = []
    have = api_servers()
    if not have:
        raise RuntimeError("No api container yet: run eax up first.")
    first = next((s for s in have if s["state"] == "running"), have[0])
    running = [s for s in have if s["state"] == "running"]
    for s in have:          # a stopped copy within the count is started again
        if s["state"] != "running" and s["number"] <= count and len(running) < count:
            docker("start", s["id"], timeout=120)
            running.append(s)
            log.append(f"started api {s['number']} again")
    used = {s["number"] for s in have}
    n = 1
    while len(running) < count:
        while n in used:
            n += 1
        name = _clone_api(first, n)
        used.add(n)
        running.append({"number": n})
        log.append(f"added api {n} ({name})")
    now = [s for s in api_servers() if s["state"] == "running"]
    for s in sorted(now, key=lambda x: -x["number"]):
        if len(now) <= count or s["number"] == 1:
            break
        log.append(f"stopping api {s['number']} (its running jobs finish first)")
        docker("stop", "--time", "120", s["id"], timeout=200)
        docker("rm", s["id"], timeout=60)
        now = [x for x in now if x["id"] != s["id"]]
        log.append(f"removed api {s['number']}")
    return log


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
              "EAX_KEYCLOAK_DB_PASSWORD", "EAX_SUPERSET_DB_PASSWORD", "EAX_MAYAN_DB_PASSWORD", "EAX_LIBRARY_DB_PASSWORD",
              "EAX_VIEWS_DB_PASSWORD"):
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


# the file systems the status shows (owner, 8 Nov 2026): the disk under Docker (images, containers and volumes: this
# helper's own / is on it), the work folder and the backups folder on the host (a share when mounted there)
FILESYSTEMS = [("/", "Docker's disk", "images, containers and volumes (the databases and Documents' files among them)"),
               ("/eax-work", "Work folder", "work/: the config file, logs, imports and exports"),
               ("/backups", "Backups folder", "work/backups: every backup (a share when one is mounted there)")]


def filesystems() -> list[dict]:
    """Size, used and free of each file system (os.statvfs); two paths on the same disk are shown once, the second
    saying so. Above 80% used: amber; above 90%: red."""
    out, seen = [], {}
    for path, label, holds in FILESYSTEMS:
        try:
            st = os.statvfs(path)
        except OSError as exc:
            out.append({"path": path, "label": label, "holds": holds, "error": str(exc)})
            continue
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - st.f_bfree * st.f_frsize
        pct = round(used / (used + free) * 100, 1) if used + free else 0.0     # as df counts it (space kept for root aside)
        key = (st.f_fsid, total) if st.f_fsid else (total, st.f_blocks)
        row = {"path": path, "label": label, "holds": holds, "total_bytes": total, "used_bytes": used, "free_bytes": free,
               "used_percent": pct, "inodes_used_percent": round((1 - st.f_ffree / st.f_files) * 100, 1) if st.f_files else None,
               "level": "red" if pct >= 90 else "amber" if pct >= 80 else "green"}
        if key in seen:
            row["same_as"] = seen[key]
        seen.setdefault(key, label)
        out.append(row)
    return out


def _volume_sizes() -> dict:
    """Volume sizes: slow on Docker, so refreshed in the background at most every five minutes; the last known
    sizes are answered meanwhile (none the very first time)."""
    if time.time() - _disk_cache["at"] >= 300 and not _disk_cache.get("busy"):
        _disk_cache["busy"] = True

        def run():
            try:
                out = json.loads(docker("system", "df", "-v", "--format", "{{json .}}", timeout=120) or "{}")
                _disk_cache["data"] = {v.get("Name"): _size(v.get("Size", "")) for v in out.get("Volumes") or []}
                # what Docker keeps on its disk, by kind, and how much could be freed
                kinds = []
                for line in docker("system", "df", "--format", "{{json .}}", timeout=120).splitlines():
                    k = json.loads(line)
                    kinds.append({"kind": k.get("Type", ""), "count": k.get("TotalCount", ""), "active": k.get("Active", ""),
                                  "bytes": _size(k.get("Size", "")), "reclaimable": k.get("Reclaimable", "")})
                _disk_cache["docker"] = kinds
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
    try:
        fs = filesystems()
    except Exception as exc:  # noqa: BLE001
        fs, _ = [], problems.append(f"file systems: {exc}")
    out = {"containers": list(rows.values()), "at": time.time(), "volumes_at": _disk_cache["at"], "problems": problems,
           "filesystems": fs, "docker_disk": _disk_cache.get("docker", [])}
    _stats_cache.update(at=time.time(), data=out)
    return out


# ---------------------------------------------------------------- the container console (owner, 6 Nov 2026)

def _one_container(service: str) -> dict:
    """A container by its key (api-2 for the second API and job server, D249) or its service (the first one)."""
    rows = containers()
    for c in rows:
        if c.get("key") == service:
            return c
    for c in rows:
        if c["service"] == service:
            return c
    raise FileNotFoundError(f"No container {service}.")


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

    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        from urllib.parse import parse_qs, urlparse
        u = urlparse(self.path)
        if u.path == "/restore/active":     # the screens ask while the API may be stopped (D227)
            return self._json(200, active_restore())
        m = re.match(r"^/restore/([A-Za-z0-9._-]+)$", u.path)
        if m:
            try:
                return self._json(200, restore_detail(m.group(1), 3000, (parse_qs(u.query).get("token") or [""])[0]))
            except PermissionError:
                return self._json(403, {"message": "Not allowed: follow the restore from the screen that started it."})
            except (OSError, FileNotFoundError, ValueError):
                return self._json(404, {"message": "No such restore."})
        m = re.match(r"^/terminal/([A-Za-z0-9_-]{20,80})$", u.path)
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
        # the Console of the Command centre (D554) brings its own command line (eaxcli/webconsole.py in a container
        # of its own); a container terminal is a shell in that container (D214)
        cmd = t.get("argv") or ["docker", "exec", "-it", "-e", "TERM=xterm-256color", t["cid"], "sh", "-c", SHELL]
        proc = subprocess.Popen(cmd,
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


# ---------------------------------------------------------------- infrastructure backups and restores (phase 8.4, D216)
# One tagged folder per backup under work/backups/infrastructure: databases/ and files/ (written by backup.sh in the
# backup container), code/ (release version, image names with their digests, the compose files), config/ (the config
# file and services.env), SHA256SUMS and manifest.json. Backups run while people work; a restore puts the installation
# in read-only maintenance (work/maintenance.json), takes a backup of the current state first (pinned), stops what uses
# the parts restored, restores them in the backup container, starts them again and ends maintenance. One at a time.
BACKUPS = os.environ.get("EAX_BACKUP_MOUNT", "/backups")
INFRA = os.path.join(BACKUPS, "infrastructure")
REPO = os.environ.get("EAX_REPO_MOUNT", "/eax-repo")
MAINTENANCE = os.path.join(WORK, "maintenance.json")
# What an infrastructure backup holds (D410). Every database on the server is dumped (the library's and the views' from
# their own servers when they have them); every named volume of docker-compose.yml with state is a file set, and the
# others are said not needed and why (tests/test_backup_coverage.py keeps both lists whole).
FILE_SETS = {   # file set: (named volume, what it is)
    "documents": ("eax-docs", "Documents' files (Mayan)"),
    "tls": ("eax-tls", "the site certificate and key"),
    "reports": ("eax-superset-home", "the reports' home (Superset's secret key and uploads; its dashboards are in its database)"),
    "imports": ("eax-imports", "the API's import folder (files uploaded to be imported)"),
    "exports": ("eax-exports", "the API's export folder (files made to be downloaded)"),
    "persist": ("./persist", "the settings that survive resets: schedules and the banner (persist/, D558; its "
                             "safety-backups/ are left out, being backups themselves)"),
}
NOT_NEEDED = {  # named volume: why it is not in a backup
    "eax-pgdata": "the database server's own files: every database in it is in the backup as a dump (databases/)",
    "eax-rendered": "made again from the config file by the setup service at every start",
    "eax-kc-import": "the Keycloak realm, made again from the config file by the setup service at every start "
                     "(the people and roles are in Keycloak's database)",
}
RESTORE_WHAT = {   # what a restore puts back: config file, databases (None: every one), file sets
    "full": {"config": True, "dbs": None, "files": ["documents", "tls", "reports", "imports", "exports", "persist"],
             "label": "Everything: the config file, every database and the files"},
    "app": {"config": True, "dbs": [], "files": [],
            "label": "Application: the config file (the release and image versions are shown; run eax up after)"},
    "app+data": {"config": True, "dbs": ["mayan"], "files": ["documents", "imports", "exports"],   # and the repository,
                 # library and views databases (every one that is not Keycloak's or Superset's)
                 "label": "Application and data: the config file, the repository, library, views and document databases, "
                          "the document files and the import and export folders (people and roles in Keycloak and the "
                          "reports' own settings stay as they are)"},
    "db": {"config": False, "dbs": None, "files": [], "label": "Databases only: every database"},
    "files": {"config": False, "dbs": ["mayan"], "only": True,   # Documents' files and its database together
              "files": ["documents", "tls", "reports", "imports", "exports", "persist"],
              "label": "Files only: Documents (its files with its own database), the certificate, the reports' home, "
                       "the import and export folders and persist/ (schedules, the banner)"},
}
KEEP_UP = {"db", "backup", "ops", "proxy"}   # what keeps running while a restore runs (D230); the rest stops
# the containers that use each part (kept for reference: since D230 every container but KEEP_UP stops)
USERS_OF = {"eaexplorer": ["api", "reports"], "keycloak": ["keycloak"], "superset": ["reports"], "mayan": ["dms"],
            "documents": ["dms"], "tls": [], "reports": ["reports"], "imports": ["api"], "exports": ["api"],
            "eaxlibrary": ["library"], "eaxviews": ["views"]}   # the proxy keeps running (the lock page and the log are reached through it); it
#                                               is restarted at the end to take the restored certificate
backup_state: dict = {"busy": False, "what": "", "name": "", "log": [], "error": "", "started": None, "finished": None,
                      "result": None}
backup_events: list[dict] = []     # finished backups and restores, for the audit trail (taken by the API's job runner)
RESTORES = os.path.join(BACKUPS, "restores")   # one folder per restore: status.json and restore.log (D227)


class _BackupLock:
    """One backup or restore at a time, in this helper and in the eax command (a file lock in the backups folder)."""

    def __init__(self):
        self._t = threading.Lock()
        self._f = None

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if not self._t.acquire(blocking, timeout):
            return False
        try:
            os.makedirs(BACKUPS, exist_ok=True)
            self._f = open(os.path.join(BACKUPS, ".lock"), "w")
            fcntl.flock(self._f, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            return True
        except OSError:
            if self._f:
                self._f.close()
                self._f = None
            self._t.release()
            return False

    def release(self) -> None:
        if self._f:
            try:
                fcntl.flock(self._f, fcntl.LOCK_UN)
            finally:
                self._f.close()
                self._f = None
        self._t.release()


_block = _BackupLock()


def _slug(text_: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", (text_ or "").strip()).strip("-.")[:60]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _rec_path(rid: str, name: str = "status.json") -> str:
    if not re.match(r"^[A-Za-z0-9._-]+$", rid or ""):
        raise FileNotFoundError("No such restore.")
    return os.path.join(RESTORES, rid, name)


def _rec_write(rec: dict) -> None:
    os.makedirs(os.path.dirname(_rec_path(rec["id"])), exist_ok=True)
    tmp = _rec_path(rec["id"]) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
    os.replace(tmp, _rec_path(rec["id"]))


def new_restore(kind: str, backup: str, what: str, by: str) -> tuple[dict, str]:
    """A restore record (status.json and restore.log in work/backups/restores/<id>) and the token that follows it."""
    rid = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{kind[:5]}-{_slug(backup)[:40] or 'restore'}"
    token = secrets.token_urlsafe(24)
    rec = {"id": rid, "kind": kind, "backup": backup, "what": what, "by": by, "started": _now_iso(), "finished": None,
           "status": "running", "error": "", "warnings": [], "step": "starting",
           "token_sha": hashlib.sha256(token.encode()).hexdigest()}
    _rec_write(rec)
    return rec, token


def rlog(rec: dict | None, msg: str, step: str = "") -> None:
    """A line in the restore's log (and the helper's own log)."""
    _blog(msg)
    if not rec:
        return
    try:
        with open(_rec_path(rec["id"], "restore.log"), "a", encoding="utf-8") as f:
            f.write(f"{_now_iso()} {msg}\n")
        if step:
            rec["step"] = step
            _rec_write(rec)
    except OSError:
        pass


def _public(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if k != "token_sha"}


def list_restores() -> list[dict]:
    out = []
    try:
        names = os.listdir(RESTORES)
    except OSError:
        return out
    for n in names:
        try:
            with open(_rec_path(n), encoding="utf-8") as f:
                out.append(_public(json.load(f)))
        except (OSError, ValueError, FileNotFoundError):
            continue
    return sorted(out, key=lambda r: r.get("started") or "", reverse=True)


def restore_detail(rid: str, tail: int = 5000, token: str | None = None) -> dict:
    with open(_rec_path(rid), encoding="utf-8") as f:
        rec = json.load(f)
    if token is not None and not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), rec.get("token_sha", "")):
        raise PermissionError("Not allowed.")
    try:
        with open(_rec_path(rid, "restore.log"), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    return {**_public(rec), "log": lines[-tail:], "lines": len(lines)}


def delete_restore(rid: str) -> dict:
    rec = restore_detail(rid, 0)
    if rec["status"] == "running":
        raise ValueError("This restore is still running: it can be deleted when it has finished.")
    shutil.rmtree(os.path.dirname(_rec_path(rid)), ignore_errors=True)
    return {"deleted": rid}


def _someone_restoring() -> bool:
    """Whether a backup or restore holds the lock now (here, or in an eax command)."""
    try:
        with open(os.path.join(BACKUPS, ".lock"), "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
            return False
    except OSError:
        return True


def _settle_stale() -> None:
    """A restore still marked running while nobody holds the lock was cut off (the helper or an eax command stopped):
    it is marked interrupted and maintenance ends, so a restore can simply be run again (D227)."""
    if _someone_restoring():
        return
    stale = [r for r in list_restores() if r.get("status") == "running" and r.get("kind") == "infrastructure"]
    if stale or maintenance():
        recover_after_restart()


def active_restore() -> dict:
    """What anyone may know while a restore runs (for the screens' lock page): whether one runs, what, since when."""
    _settle_stale()
    for r in list_restores():
        if r.get("status") == "running" and r.get("kind") == "infrastructure":
            return {"active": True, "id": r["id"], "backup": r["backup"], "what": r["what"], "by": r["by"],
                    "since": r["started"], "step": r.get("step", "")}
    m = maintenance()
    return {"active": bool(m), **({"what": m.get("what"), "by": m.get("by"), "since": m.get("since")} if m else {})}


def recover_after_restart() -> None:
    """A restore that was running when this helper stopped is marked interrupted, and maintenance ends (D227)."""
    for r in list_restores():
        if r.get("status") == "running" and r.get("kind") == "infrastructure":
            try:
                with open(_rec_path(r["id"]), encoding="utf-8") as f:
                    rec = json.load(f)
                rec.update(status="interrupted", finished=_now_iso(),
                           error="The operations helper stopped while restoring. The databases and files are as they were if "
                                 "the swap had not started; check the log, and restore again or restore the backup taken before.")
                _rec_write(rec)
                rlog(rec, "marked interrupted: the operations helper restarted during this restore")
            except (OSError, ValueError):
                pass
    if maintenance():
        _set_maintenance(False)


def delete_infra_backup(name: str) -> dict:
    folder = _infra_folder(name)
    m = _manifest_of(folder) or {}
    if m.get("pinned"):
        raise ValueError(f"{name} is pinned: unpin it first.")
    if m.get("status") == "running":
        raise ValueError(f"{name} is still being made.")
    for r in list_restores():
        if r.get("status") == "running" and r.get("backup") == name:
            raise ValueError(f"{name} is being restored.")
    shutil.rmtree(folder, ignore_errors=True)
    backup_events.append({"kind": "delete", "name": name, "at": time.time()})
    return {"deleted": name}


def _blog(msg: str) -> None:
    backup_state["log"].append(f"{time.strftime('%H:%M:%S', time.gmtime())} {msg}")
    print(f"ops backup: {msg}", flush=True)


def _manifest_of(folder: str) -> dict | None:
    try:
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        return None
    m["name"] = os.path.basename(folder)
    m["pinned"] = os.path.exists(os.path.join(folder, "PINNED"))
    return m


def list_infra() -> list[dict]:
    """Every infrastructure backup, newest first (backups made before phase 8.4 are listed as legacy)."""
    out = []
    for base, legacy in ((INFRA, False), (BACKUPS, True)):
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for n in names:
            folder = os.path.join(base, n)
            if not os.path.isdir(folder) or (legacy and n in ("infrastructure", "application")):
                continue
            m = _manifest_of(folder)
            if not m:
                continue
            if legacy:
                m = {"name": n, "tag": "", "kind": "legacy", "created": m.get("created"), "version": m.get("version"),
                     "status": "ok", "legacy": True, "pinned": m.get("pinned"), "by": "", "parts": {"databases": [], "files": []}}
            m["bytes"] = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(folder) for f in fs)
            out.append(m)
    return sorted(out, key=lambda m: str(m.get("created") or ""), reverse=True)


def resolve_backup(arg: str) -> str:
    """The infrastructure backup a name, a tag or "latest" means (the eax command): a backup's full name; "latest" (or
    "newest") the newest good one; a tag the newest good one with that tag."""
    arg = (arg or "").strip()
    good = [m for m in list_infra() if m.get("status") in (None, "ok")]        # newest first
    if arg.lower() in ("latest", "newest"):
        if not good:
            raise FileNotFoundError("No infrastructure backup to restore.")
        return good[0]["name"]
    try:
        _infra_folder(arg)
        return arg
    except (FileNotFoundError, ValueError):
        pass
    low = arg.lower()
    hits = [m for m in good if str(m.get("tag") or "").lower() == low or m["name"].split("-", 1)[-1].lower() == low]
    if hits:
        return hits[0]["name"]
    raise FileNotFoundError(f"No backup named or tagged '{arg}': .\\eax backups lists them.")


def _infra_folder(name: str) -> str:
    if not re.match(r"^[A-Za-z0-9._-]+$", name or ""):
        raise ValueError("No such backup.")
    for base in (INFRA, BACKUPS):
        folder = os.path.join(base, name)
        if os.path.isfile(os.path.join(folder, "manifest.json")):
            return folder
    raise FileNotFoundError(f"No backup {name}.")


def pin_backup(name: str, pinned: bool) -> dict:
    folder = _infra_folder(name)
    flag = os.path.join(folder, "PINNED")
    if pinned:
        with open(flag, "w", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    elif os.path.exists(flag):
        os.remove(flag)
    return _manifest_of(folder) or {}


def cleanup_infra(keep: int = 7, locked: bool = False) -> list[str]:
    """Removes infrastructure backups beyond the newest `keep` (set on Administration > Backups, D222; pinned ones are
    never removed nor counted)."""
    gone = []
    if not locked and not _block.acquire(timeout=60):
        return gone
    try:
        unpinned = [m for m in list_infra() if not m.get("pinned") and m.get("status") != "running"]
        for m in unpinned[max(1, int(keep)):]:
            folder = _infra_folder(m["name"])
            shutil.rmtree(folder, ignore_errors=True)
            gone.append(m["name"])
    finally:
        if not locked:
            _block.release()
    if gone:
        backup_events.append({"kind": "cleanup", "removed": gone, "at": time.time()})
    return gone


def _image_info() -> list[dict]:
    out = []
    for c in containers():
        try:
            d = json.loads(docker("image", "inspect", c["image"]))[0]
        except Exception:  # noqa: BLE001
            d = {}
        out.append({"service": c["service"], "image": c["image"], "id": (d.get("Id") or "")[7:19],
                    "digests": d.get("RepoDigests") or [], "created": d.get("Created")})
    return out


def _write_code_and_config(folder: str, version: str) -> None:
    code, cfg = os.path.join(folder, "code"), os.path.join(folder, "config")
    os.makedirs(code, exist_ok=True)
    os.makedirs(cfg, exist_ok=True)
    with open(os.path.join(code, "release.json"), "w", encoding="utf-8") as f:
        json.dump({"version": version, "images": _image_info()}, f, indent=2)
    for rel in ("docker-compose.yml", "deploy/compose", "deploy/proxy", "deploy/templates"):
        src = os.path.join(REPO, rel)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(code, rel), dirs_exist_ok=True)
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(os.path.join(code, rel)) or code, exist_ok=True)
            shutil.copy2(src, os.path.join(code, rel))
    for n in ("eaexplorer.env", "services.env"):
        if os.path.isfile(os.path.join(WORK, n)):
            shutil.copy2(os.path.join(WORK, n), os.path.join(cfg, n))


def _parts(folder: str) -> dict:
    dbs = sorted(f[:-5] for f in os.listdir(os.path.join(folder, "databases")) if f.endswith(".dump")) \
        if os.path.isdir(os.path.join(folder, "databases")) else []
    files = sorted(f.split(".")[0] for f in os.listdir(os.path.join(folder, "files"))) \
        if os.path.isdir(os.path.join(folder, "files")) else []
    elsewhere = {}
    try:
        with open(os.path.join(folder, "databases", "HOSTS"), encoding="utf-8") as f:
            for line in f:
                bits = line.split()
                if len(bits) == 3:
                    elsewhere[bits[0]] = f"{bits[1]}:{bits[2]}"
    except OSError:
        pass
    return {"databases": dbs, "files": files, "config": os.path.isfile(os.path.join(folder, "config", "eaexplorer.env")),
            "code": os.path.isfile(os.path.join(folder, "code", "release.json")), "elsewhere": elsewhere}


def contents(parts: dict) -> dict:
    """What a backup holds and what it does not (and why), for its manifest (D410)."""
    have = set(parts.get("files") or [])
    return {"databases": {d: (f"from {parts['elsewhere'][d]}" if d in (parts.get("elsewhere") or {}) else "from the main server")
                          for d in parts.get("databases") or []},
            "files": {k: what for k, (_vol, what) in FILE_SETS.items() if k in have},
            "empty": {k: f"{what}: empty when the backup was taken" for k, (_vol, what) in FILE_SETS.items() if k not in have},
            "config": "the config file and services.env (config/)" if parts.get("config") else "",
            "code": "the release, the image names and digests, the compose files (code/)" if parts.get("code") else "",
            "not_included": dict(NOT_NEEDED)}


def _do_backup(tag: str, by: str, kind: str, version: str, pinned: bool = False, keep: int = 0) -> dict:
    """One infrastructure backup, now (the caller holds _block). Returns its manifest."""
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    name = f"{stamp}-{_slug(tag) or kind}"
    folder = os.path.join(INFRA, name)
    os.makedirs(folder, exist_ok=True)
    manifest = {"format": "eax-infrastructure-backup/1", "tag": tag or kind, "kind": kind, "by": by, "created": stamp,
                "version": version, "status": "running"}
    with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    started = time.time()
    if os.path.exists(STOP_FLAG):
        os.remove(STOP_FLAG)
    try:
        _blog(f"backup {name}: release, images and config")
        _write_code_and_config(folder, version)
        c = _container("backup")
        if not c or c["state"] != "running":
            raise RuntimeError("The backup container is not running: switch Backups on in Administration > Services.")
        _blog(f"backup {name}: databases and files")
        r = subprocess.run(["docker", "exec", c["id"], "backup.sh", f"infrastructure/{name}"], capture_output=True, text=True,
                           timeout=6 * 3600)
        for line in (r.stdout + r.stderr).splitlines()[-20:]:
            _blog(line)
        if r.returncode:
            raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else "backup.sh failed")
        parts = _parts(folder)
        manifest.update(status="ok", parts=parts, contents=contents(parts), seconds=round(time.time() - started))
    except Exception as exc:  # noqa: BLE001 - recorded on the backup and shown
        manifest.update(status="failed", error=str(exc)[:500], seconds=round(time.time() - started))
    if manifest["status"] != "ok" and os.path.exists(STOP_FLAG):    # stopped by hand (D231): the partial folder goes
        with open(STOP_FLAG, encoding="utf-8") as f:
            who = f.read().strip()
        os.remove(STOP_FLAG)
        shutil.rmtree(folder, ignore_errors=True)
        manifest.update(status="stopped", error=f"Stopped by {who}; the partial backup was deleted.", name=name)
        backup_events.append({"kind": "backup", "name": name, "tag": manifest["tag"], "by": by, "reason": kind,
                              "status": "stopped", "error": manifest["error"], "at": time.time()})
        _blog(f"backup {name}: stopped by {who}; the partial backup was deleted")
        return manifest
    with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    if pinned:
        pin_backup(name, True)
    manifest["name"] = name
    backup_events.append({"kind": "backup", "name": name, "tag": manifest["tag"], "by": by, "reason": kind,
                          "status": manifest["status"], "error": manifest.get("error", ""), "at": time.time()})
    _blog(f"backup {name}: {manifest['status']}{' - ' + manifest['error'] if manifest.get('error') else ''}")
    if keep and manifest["status"] == "ok":   # the oldest beyond the number kept go (pinned ones stay)
        removed = cleanup_infra(keep, locked=True)
        if removed:
            _blog(f"removed the oldest: {', '.join(removed)}")
    return manifest


STOP_FLAG = os.path.join(BACKUPS, ".stop")    # a backup asked to stop (D231): who asked


def stop_backup(by: str) -> dict:
    """Stops the backups running (D231): an infrastructure backup is killed in the backup container and its partial
    folder deleted; a running application backup is asked to stop after the model it is on (the API deletes it). A
    restore cannot be stopped (it puts things back itself when it fails)."""
    if any(r.get("status") == "running" and r.get("kind") == "infrastructure" for r in list_restores()):
        raise ValueError("A restore is running: it cannot be stopped (if it fails, it puts everything back itself).")
    out: list[str] = []
    running = [m for m in list_infra() if m.get("status") == "running" and not m.get("legacy")]
    if running:
        if _block.acquire(blocking=False):      # nothing holds the lock: left over from a helper that stopped
            try:
                for m in running:
                    shutil.rmtree(os.path.join(INFRA, m["name"]), ignore_errors=True)
                    out.append(f"{m['name']} (left unfinished; deleted)")
            finally:
                _block.release()
        else:
            with open(STOP_FLAG, "w", encoding="utf-8") as f:
                f.write(by or "someone")
            b = _container("backup")
            if b and b["state"] == "running":
                subprocess.run(["docker", "exec", b["id"], "sh", "-c",
                                "pkill -f backup.sh; pkill pg_dump; pkill pg_dumpall; pkill tar; pkill gzip; true"],
                               capture_output=True, text=True, timeout=60)
            out += [m["name"] for m in running]
    for r in _app_runs():
        if r.get("status") == "running":
            try:
                with open(os.path.join(BACKUPS, "application", r["name"], "STOP"), "w", encoding="utf-8") as f:
                    f.write(by or "someone")
                out.append(f"{r['name']} (application: stops after the model it is on)")
            except OSError:
                pass
    if not out:
        raise ValueError("No backup is running.")
    _blog(f"stop asked by {by or 'someone'}: {', '.join(out)}")
    return {"stopping": out}


def _vt(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.-]", v or "0")[:3])


def maintenance() -> dict | None:
    try:
        with open(MAINTENANCE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


PROXY_FLAG = os.path.join(WORK, "proxy", "maintenance")   # the proxy shows its maintenance page while it exists (D230)


def _set_maintenance(on: bool, what: str = "", by: str = "") -> None:
    if on:
        with open(MAINTENANCE, "w", encoding="utf-8") as f:
            json.dump({"since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "what": what, "by": by}, f)
        try:
            os.makedirs(os.path.dirname(PROXY_FLAG), exist_ok=True)
            with open(PROXY_FLAG, "w", encoding="utf-8") as f:
                f.write(f"{what}\n")
        except OSError:
            pass
    else:
        for p in (MAINTENANCE, PROXY_FLAG):
            if os.path.exists(p):
                os.remove(p)


def _tell_everyone(rec: dict) -> None:
    """Everyone is told that a restore starts (D229): the API writes it to every bell and sends the webhooks at once,
    before anything is stopped (a full restore replaces its database a moment later). If the API cannot be reached, the
    end of the restore is still announced when it is back."""
    import urllib.request
    url = os.environ.get("EAX_API_URL", "http://api:8000") + "/api/v1/internal/restore-started"
    req = urllib.request.Request(url, data=json.dumps({"restore": rec["id"]}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Ops-Token": TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - the API of this installation
            told = json.loads(r.read() or b"{}").get("notified")
        rlog(rec, "everyone is told: a notification and the webhooks" if told else "everyone had been told already")
    except Exception as exc:  # noqa: BLE001 - the API may be down: the end is announced when it is back
        rlog(rec, f"could not tell everyone now ({str(exc)[:120]}); they are told when the restore has ended")


def _do_restore(name: str, what: str, by: str, version: str, force: bool = False, rec: dict | None = None) -> dict:
    """Restores (part of) an infrastructure backup (the caller holds _block); every step goes into the restore's log."""
    rec = rec or new_restore("infrastructure", name, what, by)[0]
    # the very first step (D230): the proxy shows the maintenance page and the API refuses changes, at once
    _set_maintenance(True, f"Restoring {name} ({what})", by)
    rlog(rec, "maintenance page on: EA Explorer cannot be used until the restore has finished", "maintenance")
    _tell_everyone(rec)
    try:
        out = _restore_steps(name, what, by, version, force, rec)
    except Exception as exc:  # noqa: BLE001 - refused before it started (unknown backup, newer version, ...)
        out = {"status": "failed", "name": name, "what": what, "error": str(exc)[:500], "warnings": []}
        rlog(rec, f"not restored: {exc}")
        _set_maintenance(False)
    rec.update(status=out["status"], finished=_now_iso(), error=out.get("error", ""), warnings=out.get("warnings", []),
               before=out.get("before", ""), step="done" if out["status"] == "ok" else "failed")
    _rec_write(rec)
    out["restore"] = rec["id"]
    return out


def _restore_steps(name: str, what: str, by: str, version: str, force: bool, rec: dict) -> dict:
    plan = RESTORE_WHAT[what]
    folder = _infra_folder(name)
    m = _manifest_of(folder) or {}
    if m.get("status") not in (None, "ok"):
        raise ValueError(f"The backup {name} did not finish ({m.get('status')}): it cannot be restored.")
    parts = _parts(folder) if not m.get("legacy") else {"databases": [f[:-5] for f in os.listdir(folder) if f.endswith(".dump")],
                                                         "files": ["documents"], "config": False}
    if plan["dbs"] != [] and version and m.get("version") and _vt(m["version"]) > _vt(version) and not force:
        raise ValueError(f"The backup is from version {m['version']}, newer than this installation ({version}): install that "
                         "release first, then restore.")
    others = ("keycloak", "superset", "mayan")   # the repository database has the installation's own name (EAX_DB_NAME)
    if plan["dbs"] is None:
        dbs = parts["databases"]
    elif plan.get("only"):
        dbs = [d for d in parts["databases"] if d in plan["dbs"]]
    elif plan["dbs"]:
        dbs = [d for d in parts["databases"] if d not in others or d in plan["dbs"]]
    else:
        dbs = []
    files = [f for f in plan["files"] if f in parts["files"]]
    warnings = []
    lacking = [FILE_SETS[f][1] for f in plan["files"] if f not in parts["files"] and f in FILE_SETS and f != "documents"]
    if lacking:   # an older backup (before D410) or a folder that was empty: what is here now stays
        warnings.append("This backup does not have " + "; ".join(lacking) + ": they were left as they are.")
    if what == "db":
        warnings.append("Only part of the installation was restored: documents and the records that point at them may no longer "
                        "match (newer documents without records, or records whose files are older). Check the documents of a few "
                        "models.")
    if plan["config"] and not parts.get("config"):
        warnings.append("This backup has no config file: the current one was kept.")
    rlog(rec, f"restore of {name} ({what}) by {by}: {plan['label']}", "maintenance")
    _set_maintenance(True, f"Restoring {name} ({what})", by)      # on already (_do_restore); kept for direct callers
    stopped: list[dict] = []
    rank = {n: i for i, n in enumerate(ORDER)}
    try:
        rlog(rec, f"restore {name} ({what}): a backup of the current state first")
        rec["step"] = "backup of the current state"
        _rec_write(rec)
        before = _do_backup(f"before-restore-of-{name}", by, "before-restore", version, pinned=True)
        rlog(rec, f"backup of the current state: {before['status']} ({before['name']})")
        if before["status"] != "ok":
            raise RuntimeError(f"The backup of the current state failed ({before.get('error')}): nothing was restored.")
        # the whole environment comes down (D230): everything but the database, the backup container, this helper and
        # the proxy (which shows its maintenance page), the last started first
        for c in sorted(containers(), key=lambda c: -rank.get(c["service"], len(ORDER))):
            if c["service"] not in KEEP_UP and c["state"] == "running" and not c["self"]:
                rlog(rec, f"stopping {c['service']}")
                docker("stop", "--time", "20", c["id"], timeout=120)
                stopped.append(c)
        if plan["config"] and parts.get("config"):
            copy_config(by, f"before-restore-of-{name}")
            servers_now = servers_wanted()
            shutil.copy2(os.path.join(folder, "config", "eaexplorer.env"), CONFIG)
            rlog(rec, "config file restored (the one before is kept in config-history)")
            # how many API and job servers run is how the installation is sized now, not restored data (D249): kept
            if servers_wanted() != servers_now:
                with config_lock:
                    _write(_set_value(_read_config(), SERVERS_KEY, str(servers_now)))
                rlog(rec, f"kept {servers_now} API and job server(s) (the backup had another number)")
            try:
                write_services_file()
            except OSError:
                pass
        if dbs or files:
            b = _container("backup")
            if not b or b["state"] != "running":
                raise RuntimeError("The backup container is not running.")
            args = ["docker", "exec", b["id"], "restore.sh", os.path.relpath(folder, BACKUPS),
                    "--dbs", ",".join(dbs) or "-", "--files", ",".join(files)]
            rlog(rec, f"restoring databases {', '.join(dbs) or 'none'}; files {', '.join(files) or 'none'}")
            rec["step"] = "restoring databases and files"
            _rec_write(rec)
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            last = ""
            for line in proc.stdout:   # every line, as it comes: large restores take hours
                line = line.rstrip()
                if line:
                    rlog(rec, line)
                    last = line
            if proc.wait() != 0:
                raise RuntimeError(last or "restore.sh failed")
        if "tls" in files:
            px = _container("proxy")
            if px and px["state"] == "running":
                rlog(rec, "restarting the proxy for the restored certificate")
                docker("restart", "--time", "5", px["id"], timeout=120)
        result = {"status": "ok", "name": name, "what": what, "databases": dbs, "files": files, "config": bool(plan["config"]),
                  "before": before["name"], "warnings": warnings}
    except Exception as exc:  # noqa: BLE001
        result = {"status": "failed", "name": name, "what": what, "error": str(exc)[:500], "warnings": warnings}
    finally:
        for c in sorted(stopped, key=lambda c: rank.get(c["service"], len(ORDER))):
            try:
                rlog(rec, f"starting {c['service']}")
                docker("start", c["id"], timeout=180)
            except Exception as exc:  # noqa: BLE001
                rlog(rec, f"{c['service']} did not start: {exc}")
        if "keycloak" not in {c["service"] for c in stopped}:   # everyone signs in again after a restore
            k = _container("keycloak")
            if k and k["state"] == "running":
                try:
                    docker("restart", "--time", "20", k["id"], timeout=180)
                    rlog(rec, "restarted keycloak: everyone signs in again")
                except Exception:  # noqa: BLE001
                    pass
        _set_maintenance(False)
    backup_events.append({"kind": "restore", "by": by, "at": time.time(), **result})
    rlog(rec, f"restore {name}: {result['status']}{' - ' + result.get('error', '') if result.get('error') else ''}")
    return result


def start_backup_job(action: str, **kw) -> dict:
    """Runs a backup or a restore in the background (one at a time); its progress is in backup_state, and a restore's in
    its own record and log (work/backups/restores/<id>)."""
    if not _block.acquire(blocking=False):
        raise RuntimeError(f"Busy: {backup_state['what'] or 'another backup or restore (perhaps from the eax command)'}. "
                           "Try again when it is done.")
    rec, token = (None, None)
    if action == "restore":
        try:
            rec, token = new_restore("infrastructure", kw["name"], kw["what"], kw.get("by", ""))
        except Exception:
            _block.release()
            raise
    backup_state.update(busy=True, what=f"{action} {kw.get('tag') or kw.get('name') or ''}".strip(), log=[], error="",
                        started=time.time(), finished=None, result=None, name=kw.get("name", ""))

    def run():
        try:
            out = _do_backup(kw.get("tag", ""), kw.get("by", ""), kw.get("kind", "on-demand"), kw.get("version", ""),
                             bool(kw.get("pinned")), int(kw.get("keep") or 0)) if action == "backup" else \
                _do_restore(kw["name"], kw["what"], kw.get("by", ""), kw.get("version", ""), bool(kw.get("force")), rec)
            backup_state.update(result=out, error=out.get("error", "") if out.get("status") != "ok" else "")
        except Exception as exc:  # noqa: BLE001
            backup_state.update(error=str(exc)[:500])
            _set_maintenance(False)
        finally:
            backup_state.update(busy=False, finished=time.time())
            _block.release()
    threading.Thread(target=run, daemon=True).start()
    return {"started": True, "what": backup_state["what"], **({"restore": rec["id"], "token": token} if rec else {})}


def take_events() -> list[dict]:
    out = list(backup_events)
    del backup_events[:len(out)]
    return out


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
        if self.path == "/tests":                    # test runs (phase 36.1, D367; testruns.py)
            return self._send(200, testruns.status())
        if self.path.startswith("/tests/build/"):    # building the test runner from the page (D570)
            from urllib.parse import parse_qs, urlparse
            u = urlparse(self.path)
            try:
                frm = int((parse_qs(u.query).get("from") or ["0"])[0] or 0)
                return self._send(200, testruns.build_detail(u.path.rsplit("/", 1)[-1], frm))
            except (FileNotFoundError, ValueError) as exc:
                return self._send(404, {"message": str(exc)})
        if self.path == "/deploys" or self.path.startswith("/deploys/"):   # deploying elsewhere (D555; deploys.py)
            try:
                if self.path == "/deploys":
                    return self._send(200, deploys.overview())
                return self._send(200, deploys.run(self.path.split("/")[2]))
            except ValueError as exc:
                return self._send(404, {"message": str(exc)})
        if self.path == "/scaling":                  # scaling rules (phase 36.3, D526; scaling.py)
            try:
                return self._send(200, scaling.describe())
            except Exception as exc:  # noqa: BLE001
                return self._send(500, {"message": str(exc)})
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
        if self.path == "/servers":
            try:
                return self._send(200, {"servers": api_servers(), "wanted": servers_wanted(), "max": MAX_SERVERS,
                                        "busy": busy("servers"), "job": jobs.get("servers")})
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
        if self.path.split("?")[0].startswith("/commands"):      # the Command centre (D554; commandcentre.py)
            return self._commands_get()
        if self.path.split("?")[0].startswith("/banner"):        # the banner under the top bar (D558)
            return self._banner("GET")
        if self.path == "/backups":
            return self._send(200, {"infrastructure": list_infra(), "state": backup_state,
                                    "maintenance": maintenance(), "restore_choices": {k: v["label"] for k, v in RESTORE_WHAT.items()}})
        if self.path == "/backups/events":
            return self._send(200, {"events": take_events()})
        if self.path == "/restores":
            active = active_restore()
            return self._send(200, {"restores": list_restores(), "active": active})
        m = re.match(r"^/restores/([A-Za-z0-9._-]+)(?:\?tail=(\d+))?$", self.path)
        if m:
            try:
                return self._send(200, restore_detail(m.group(1), int(m.group(2) or 5000)))
            except (OSError, FileNotFoundError, ValueError):
                return self._send(404, {"message": "No such restore."})
        if self.path.split("?")[0].startswith("/updates"):
            return self._updates_get()
        if self.path == "/status":
            try:
                return self._send(200, {"project": project(), "containers": containers(), "restart": state})
            except Exception as exc:  # noqa: BLE001
                return self._send(500, {"message": str(exc)})
        return self._send(404, {"message": "No such request."})

    def _updates_get(self):
        """Updates (phase 36, D417): status and the versions a channel offers."""
        from urllib.parse import parse_qs, urlparse
        u = urlparse(self.path)
        try:
            if u.path == "/updates":
                return self._send(200, updates.status(int((parse_qs(u.query).get("tail") or ["200"])[0])))
            if u.path == "/updates/versions":
                return self._send(200, updates.versions((parse_qs(u.query).get("channel") or ["prod"])[0]))
        except PermissionError as exc:
            return self._send(403, {"message": str(exc)})
        except ValueError as exc:
            return self._send(400, {"message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return self._send(409, {"message": str(exc)})
        return self._send(404, {"message": "No such request."})

    def _updates_post(self):
        b = self._body()
        by = str(b.get("by") or "")
        try:
            if self.path == "/updates/settings":
                return self._send(200, updates.save_settings(b, by))
            if self.path == "/updates/start":
                return self._send(202, updates.start(b))
            if self.path in ("/updates/retry", "/updates/rollback"):
                return self._send(202, updates.decide(self.path.rsplit("/", 1)[1], by))
            if self.path == "/updates/schedule/cancel":
                return self._send(200, updates.cancel_schedule(by))
        except PermissionError as exc:
            return self._send(403, {"message": str(exc)})
        except ValueError as exc:
            return self._send(400, {"message": str(exc)})
        except Exception as exc:  # noqa: BLE001 - refused: a running update, no repository link, nothing newer
            return self._send(409, {"message": str(exc)})
        return self._send(404, {"message": "No such request."})

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}") if n else {}
        except ValueError:
            return {}

    def _commands_get(self):
        from urllib.parse import parse_qs, urlparse
        u = urlparse(self.path)
        try:
            if u.path == "/commands":
                return self._send(200, commandcentre.catalogue())
            if u.path == "/commands/runs":
                return self._send(200, {"runs": commandcentre.history()})
            if u.path == "/commands/schedules":
                return self._send(200, commandcentre.schedules_list())
            if u.path == "/commands/reset-survival":
                return self._send(200, commandcentre.reset_survival_runs())
            m = re.match(r"^/commands/runs/([A-Za-z0-9_-]+)$", u.path)
            if m:
                start = int((parse_qs(u.query).get("from") or ["0"])[0] or 0)
                return self._send(200, commandcentre.detail(m.group(1), start))
        except FileNotFoundError as exc:
            return self._send(404, {"message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"message": str(exc)})
        return self._send(404, {"message": "No such page."})

    def _commands_post(self):
        b = self._body()
        refused = getattr(commandcentre.C, "Refused", ValueError)
        try:
            if self.path == "/commands/run":
                return self._send(202, commandcentre.start(b))
            if self.path == "/commands/console":
                return self._send(200, commandcentre.console_ticket(b))
            if self.path == "/commands/ack":
                return self._send(200, {"acked": commandcentre.ack([str(x) for x in b.get("ids") or []])})
            if self.path == "/commands/schedules":
                return self._send(201, commandcentre.schedule_add(b))
            m = re.match(r"^/commands/schedules/([A-Za-z0-9_-]+)/(on|off|remove|run)$", self.path)
            if m:
                return self._send(200, commandcentre.schedule_change(m.group(1), m.group(2), b))
            m = re.match(r"^/commands/runs/([A-Za-z0-9_-]+)/stop$", self.path)
            if m:
                return self._send(200, commandcentre.stop(m.group(1), str(b.get("by") or "")))
        except refused as exc:
            return self._send(400, {"message": str(exc)})
        except FileNotFoundError as exc:
            return self._send(404, {"message": str(exc)})
        except ValueError as exc:          # a schedule that cannot be made (eaxcli/schedules.py ScheduleError)
            return self._send(400, {"message": str(exc)})
        except RuntimeError as exc:
            return self._send(409, {"message": str(exc)})
        return self._send(404, {"message": "No such page."})

    def _banner(self, method: str):
        """The banner under the top bar (D558; commandcentre.banner_*, persist/banner.json)."""
        try:
            if method == "GET":
                if self.path.startswith("/banner/all"):
                    return self._send(200, commandcentre.banner_all())
                return self._send(200, commandcentre.banner_now("admin=1" in self.path))
            b = self._body()
            if self.path == "/banner/clear":
                return self._send(200, commandcentre.banner_clear(b))
            if self.path == "/banner":
                return self._send(200, commandcentre.banner_set(b))
        except ValueError as exc:
            return self._send(400, {"message": str(exc)})
        except RuntimeError as exc:
            return self._send(409, {"message": str(exc)})
        return self._send(404, {"message": "No such page."})

    def do_POST(self):  # noqa: N802
        if not self._ok():
            return None
        if self.path in ("/tests", "/tests/stop", "/tests/build", "/tests/settings", "/scaling"):   # self-test, scaling
            b = self._body()
            try:
                if self.path == "/tests":
                    return self._send(202, testruns.start(b))
                if self.path == "/tests/build":
                    return self._send(202, testruns.build(b))
                if self.path == "/tests/settings":
                    return self._send(200, testruns.set_auto_build(bool(b.get("auto_build")), str(b.get("by") or "")))
                if self.path == "/tests/stop":
                    return self._send(200, testruns.stop(b))
                return self._send(200, scaling.save(b.get("settings") or {}, str(b.get("by") or "console")))
            except ValueError as exc:
                return self._send(400, {"message": str(exc)})
            except RuntimeError as exc:
                return self._send(409, {"message": str(exc)})
        if self.path == "/deploys" or self.path.startswith("/deploys/"):   # deploying elsewhere (D555; deploys.py)
            b = self._body()
            try:
                if self.path == "/deploys/questions":
                    return self._send(200, deploys.questions(b.get("answers") or {}))
                if self.path == "/deploys":
                    return self._send(202, deploys.start(b))
                m = re.match(r"^/deploys/([^/]+)/decide$", self.path)
                if m:
                    return self._send(200, deploys.decide(m.group(1), str(b.get("choice") or "")))
                m = re.match(r"^/deploys/kept/([^/]+)/forget$", self.path)
                if m:
                    from urllib.parse import unquote
                    return self._send(200, deploys.forget(unquote(m.group(1))))
                return self._send(404, {"message": "No such request."})
            except ValueError as exc:
                return self._send(400, {"message": str(exc)})
            except RuntimeError as exc:
                return self._send(409, {"message": str(exc)})
        if self.path.startswith("/commands"):                  # the Command centre (D554; commandcentre.py)
            return self._commands_post()
        if self.path.startswith("/banner"):                    # the banner under the top bar (D558)
            return self._banner("POST")
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
        if self.path.startswith("/updates/"):
            return self._updates_post()
        if self.path == "/backups/stop":
            try:
                return self._send(200, stop_backup(str(self._body().get("by") or "")))
            except ValueError as exc:
                return self._send(409, {"message": str(exc)})
        if self.path in ("/backups/backup", "/backups/restore"):
            b = self._body()
            try:
                if self.path == "/backups/backup":
                    return self._send(202, start_backup_job("backup", tag=str(b.get("tag") or ""), by=str(b.get("by") or ""),
                                                            kind=str(b.get("kind") or "on-demand"), version=str(b.get("version") or ""),
                                                            pinned=bool(b.get("pinned")), keep=int(b.get("keep") or 0)))
                what = str(b.get("what") or "")
                if what not in RESTORE_WHAT:
                    return self._send(400, {"message": f"Restore one of: {', '.join(RESTORE_WHAT)}."})
                _infra_folder(str(b.get("name") or ""))
                return self._send(202, start_backup_job("restore", name=str(b["name"]), what=what, by=str(b.get("by") or ""),
                                                        version=str(b.get("version") or ""), force=bool(b.get("force"))))
            except FileNotFoundError as exc:
                return self._send(404, {"message": str(exc)})
            except (RuntimeError, ValueError) as exc:
                return self._send(409, {"message": str(exc)})
        m = re.match(r"^/backups/([A-Za-z0-9._-]+)/pin$", self.path)
        if m:
            try:
                return self._send(200, pin_backup(m.group(1), bool(self._body().get("pinned"))))
            except (FileNotFoundError, ValueError) as exc:
                return self._send(404, {"message": str(exc)})
        m = re.match(r"^/restores/([A-Za-z0-9._-]+)/delete$", self.path)
        if m:
            try:
                return self._send(200, delete_restore(m.group(1)))
            except (OSError, FileNotFoundError) as exc:
                return self._send(404, {"message": str(exc) or "No such restore."})
            except ValueError as exc:
                return self._send(409, {"message": str(exc)})
        m = re.match(r"^/backups/([A-Za-z0-9._-]+)/delete$", self.path)
        if m:
            try:
                return self._send(200, delete_infra_backup(m.group(1)))
            except FileNotFoundError as exc:
                return self._send(404, {"message": str(exc)})
            except ValueError as exc:
                return self._send(409, {"message": str(exc)})
        if self.path == "/backups/cleanup":
            return self._send(200, {"removed": cleanup_infra(int(self._body().get("keep") or 7))})
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
        if self.path == "/servers":
            b = self._body()
            try:
                count = int(b.get("count"))
            except (TypeError, ValueError):
                return self._send(400, {"message": "count is a whole number."})
            if not 1 <= count <= MAX_SERVERS:
                return self._send(400, {"message": f"Between 1 and {MAX_SERVERS} servers."})
            if busy("servers") or busy("config"):
                return self._send(409, {"message": "Still changing the servers. Try again in a moment."})
            by = str(b.get("by") or "console")
            try:
                with config_lock:
                    saved = None
                    if servers_wanted() != count:
                        saved = copy_config(by, f"servers-{count}")
                        _write(_set_value(_read_config(), SERVERS_KEY, str(count)))
            except OSError as exc:
                return self._send(500, {"message": f"Could not write the config file: {exc}"})
            _in_background("servers", f"{count} API and job servers", lambda: scale_api(count))
            return self._send(202, {"count": count, "saved_first": saved,
                                    "message": f"{count} API and job server{'s' if count != 1 else ''}: being started or stopped; "
                                               "nginx spreads API calls across them within seconds."})
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


def _app_runs() -> list[dict]:
    base = os.path.join(BACKUPS, "application")
    out = []
    try:
        names = sorted(os.listdir(base), reverse=True)
    except OSError:
        return out
    for n in names:
        try:
            with open(os.path.join(base, n, "manifest.json"), encoding="utf-8") as f:
                m = json.load(f)
        except (OSError, ValueError):
            continue
        out.append({**m, "name": n, "pinned": os.path.exists(os.path.join(base, n, "PINNED"))})
    return out


def _ask(prompt: str, choices: list[str] | None = None) -> str:
    while True:
        try:
            answer = input(prompt).strip()
        except EOFError:
            return ""
        if not choices or answer in choices:
            return answer
        print(f"  Type one of: {', '.join(choices)}")


def _print_infra(rows: list[dict]) -> None:
    print(f"  {'#':>3}  {'name':<58} {'status':<8} {'kind':<15} {'version':<8} {'size':>9}")
    for i, m in enumerate(rows, 1):
        print(f"  {i:>3}  {m['name']:<58} {m.get('status', ''):<8} {m.get('kind', ''):<15} {str(m.get('version') or ''):<8} "
              f"{m.get('bytes', 0) / 1e6:7.1f} MB{'  pinned' if m.get('pinned') else ''}")


def _follow_print(rec_id: str) -> None:
    d = restore_detail(rec_id)
    print("\n".join(d["log"]))


def _matches(m: dict, words: list[str]) -> bool:
    """Search (D232): every word in the tag, name or who made it."""
    hay = f"{m.get('tag', '')} {m.get('name', '')} {m.get('by', '')}".lower()
    return all(w in hay for w in words)


def cli(argv: list[str]) -> int:
    """The eax command's backups and restores (they work when the console cannot, D227):
      list [words]                           every backup (or those whose tag, name or maker has the words)
      stop-backup                            stop the backups running (the partial backup is deleted)
      backup [tag]                           an infrastructure backup now
      restore                                choose a backup from a numbered list, what to restore, confirm; then restore
      restore <name|tag|latest> [--what full|app|app+data|db|files] [--yes] [--force]
                                             a tag or latest: the newest good backup with that tag, or of all
      restores                               every restore with its status
      restore-log <id>                       a restore's whole log
      delete-backup <name>                   delete an infrastructure backup (not pinned)
      delete-restore <id>                    forget a finished restore and its log
      filesystems                            size, used and free of Docker's disk and the work and backups folders"""
    cmd, args = (argv[0] if argv else "help"), argv[1:]
    if cmd == "test":                     # eax test (phase 36.1, D367)
        return testruns.cli(args)
    if cmd in ("update", "rollback"):      # eax update / eax rollback (phase 36, D417)
        return updates.cli(argv if cmd == "rollback" else args)
    version = args[args.index("--version") + 1] if "--version" in args else os.environ.get("EAX_VERSION", "")
    if cmd == "filesystems":              # .\eax status shows these after the containers (owner, 8 Nov 2026)
        g = lambda b: f"{b / 1e9:,.1f} GB"  # noqa: E731
        print("File systems:")
        print(f"  {'':2}{'File system':<16}{'Size':>12}{'Used':>12}{'Free':>12}{'Used %':>9}   Holds")
        for f in filesystems():
            if f.get("error"):
                print(f"  !! {f['label']:<16} not readable: {f['error']}")
                continue
            mark = {"red": "!!", "amber": "! "}.get(f["level"], "  ")
            same = f"  (same disk as {f['same_as']})" if f.get("same_as") else ""
            print(f"  {mark}{f['label']:<16}{g(f['total_bytes']):>12}{g(f['used_bytes']):>12}{g(f['free_bytes']):>12}"
                  f"{f['used_percent']:>8.1f}%   {f['holds']}{same}")
        print("  (! over 80% used, !! over 90%)")
        return 0
    if cmd == "stop-backup":
        try:
            print("Stopping:", ", ".join(stop_backup("eax command")["stopping"]))
            return 0
        except ValueError as exc:
            print(exc)
            return 1
    if cmd == "list":
        words = [a.lower() for a in args if not a.startswith("--") and a != version]
        rows = [m for m in list_infra() if _matches(m, words)]
        print("Infrastructure backups (work/backups/infrastructure):")
        _print_infra(rows) if rows else print("  none yet")
        runs = [r for r in _app_runs() if _matches(r, words)]
        print("\nApplication backups (work/backups/application): restore them with: eax restore-model")
        for r in runs:
            ok = [x for x in r.get("models") or [] if x.get("status") == "ok"]
            print(f"  {r['name']:<58} {r.get('status', ''):<8} {len(ok):>3} models{'  pinned' if r.get('pinned') else ''}")
        if not runs:
            print("  none yet")
        return 0
    if cmd == "restores":
        rows = list_restores()
        for r in rows:
            print(f"  {r['id']:<62} {r.get('kind', ''):<15} {r.get('status', ''):<12} {r.get('what', ''):<9} by {r.get('by', '')}"
                  f"{'  - ' + r['error'][:80] if r.get('error') else ''}")
        if not rows:
            print("  no restore yet")
        return 0
    if cmd == "restore-log" and args:
        try:
            _follow_print(args[0])
        except (OSError, FileNotFoundError):
            print(f"No restore {args[0]}.")
            return 1
        return 0
    if cmd == "delete-restore" and args:
        try:
            print(delete_restore(args[0])["deleted"], "deleted")
        except (OSError, FileNotFoundError):
            print(f"No restore {args[0]}.")
            return 1
        except ValueError as exc:
            print(exc)
            return 1
        return 0
    if cmd in ("backup", "restore", "delete-backup"):
        if not _block.acquire(blocking=False):
            print("Busy: another backup or restore is running (in the console or another eax command).")
            return 1
        try:
            if cmd == "delete-backup" and args:
                try:
                    print(delete_infra_backup(args[0])["deleted"], "deleted")
                    return 0
                except (FileNotFoundError, ValueError) as exc:
                    print(exc)
                    return 1
            if cmd == "backup":
                tag = next((a for a in args if not a.startswith("--") and a != version), "on-demand")
                m = _do_backup(tag, "eax command", "on-demand", version)
                return 0 if m["status"] == "ok" else 1
            if cmd == "restore":
                name = next((a for a in args if not a.startswith("--") and a not in (version,) and a not in RESTORE_WHAT), "")
                what = args[args.index("--what") + 1] if "--what" in args else ""
                if name:       # a name, a tag or latest
                    try:
                        name = resolve_backup(name)
                    except (FileNotFoundError, ValueError) as exc:
                        print(exc)
                        return 1
                    m = _manifest_of(_infra_folder(name)) or {}
                    print(f"Backup: {name}  (tag {m.get('tag') or '-'}, made {m.get('created') or '?'} by {m.get('by') or '?'}, "
                          f"version {m.get('version') or '?'}{', pinned' if m.get('pinned') else ''})")
                else:          # choose from a list
                    rows = [m for m in list_infra() if m.get("status") == "ok"]
                    if not rows:
                        print("No infrastructure backup to restore.")
                        return 1
                    _print_infra(rows)
                    n = _ask(f"Which backup (1-{len(rows)}, empty to stop)? ", [""] + [str(i) for i in range(1, len(rows) + 1)])
                    if not n:
                        return 1
                    name = rows[int(n) - 1]["name"]
                if not what:
                    keys = list(RESTORE_WHAT)
                    for i, k in enumerate(keys, 1):
                        print(f"  {i}  {k:<9} {RESTORE_WHAT[k]['label']}")
                    n = _ask(f"What to restore (1-{len(keys)})? ", [str(i) for i in range(1, len(keys) + 1)])
                    what = keys[int(n) - 1] if n else "full"
                if what not in RESTORE_WHAT:
                    print(f"--what is one of: {', '.join(RESTORE_WHAT)}")
                    return 2
                if "--yes" not in args:
                    print(f"Restore {name} ({what}). A backup of the current state is taken first; EA Explorer is read only while "
                          "it runs and everyone signs in again afterwards.")
                    if _ask("Type RESTORE to go on: ") != "RESTORE":
                        print("Nothing restored.")
                        return 1
                rec, _ = new_restore("infrastructure", name, what, "eax command")
                t0 = time.time()
                line = "=" * 78
                print(f"\n{line}\n  RESTORE RUNNING: {name} ({what})\n"
                      "  EA Explorer is locked for everyone until it has finished (every screen shows the lock page),\n"
                      "  and everyone is notified. Do not close this window; if it is closed, run .\\eax restore again.\n"
                      f"  Log: work/backups/restores/{rec['id']}/restore.log\n{line}", flush=True)
                r = _do_restore(name, what, "eax command", version, "--force" in args, rec)
                mins = (time.time() - t0) / 60
                print(f"\n{line}\n  RESTORE {'FINISHED' if r['status'] == 'ok' else r['status'].upper()} after {mins:.1f} minutes: "
                      f"{name} ({what})", flush=True)
                for w in r.get("warnings") or []:
                    print(f"  Warning: {w}")
                if r.get("error"):
                    print(f"  {r['error']}")
                print("  Everyone is told when the API is back (within a minute); everyone signs in again.\n" + line)
                return 0 if r["status"] == "ok" else 1
        finally:
            _block.release()
    print(cli.__doc__)
    return 2


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # updates.py beside this file (also when tests load it)
import updates  # noqa: E402 - updating to a new release (phase 36, D417)

updates.hooks.update(read_config=_read_config, write_config=_write, copy_config=copy_config, docker=docker)
import scaling  # noqa: E402 - scaling the API and job servers by rules (phase 36.3, D526)
import testruns  # noqa: E402 - test runs (phase 36.1, D367)
import commandcentre  # noqa: E402 - eax commands from a web page: the Command centre and the Console (D554)

commandcentre.hooks.update(docker=docker, me=updates._me, read_config=_read_config, tickets=_tickets, tlock=_tlock,
                           idle_minutes=idle_minutes)
import deploys  # noqa: E402 - deploying EA Explorer elsewhere from the page (phase 36, D555)

scaling.bind(globals())
testruns.bind(globals())
deploys.bind(globals())


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        sys.exit(cli(sys.argv[1:]))
    if not TOKEN:
        print("ops: EAX_OPS_TOKEN is not set; every request but /health is refused", flush=True)
    try:
        write_services_file()
    except OSError as exc:
        print(f"ops: could not write services.env ({exc})", flush=True)
    try:
        recover_after_restart()
    except OSError as exc:
        print(f"ops: could not check the restores ({exc})", flush=True)
    try:                                  # laptop sample data: past runs in the Command centre's History (D554)
        commandcentre.seed_samples(_values(_read_config()).get("EAX_DEPLOYMENT", ""))
    except OSError as exc:
        print(f"ops: could not write the sample command runs ({exc})", flush=True)
    try:                                  # laptop sample data: schedules and a past banner in persist/ (D558, D559)
        commandcentre.seed_persist(_values(_read_config()).get("EAX_DEPLOYMENT", ""))
    except OSError as exc:
        print(f"ops: could not write the sample schedules ({exc})", flush=True)
    threading.Thread(target=updates.scheduler, daemon=True).start()   # scheduled updates (D417)
    threading.Thread(target=commandcentre.scheduler, daemon=True).start()   # scheduled eax commands (D559)
    scaling.start()                       # the scaling rules, looked at every minute (D526)
    threading.Thread(target=testruns.auto_build_loop, daemon=True).start()   # the test runner built when missing (D570)
    terminals = ThreadingHTTPServer(("0.0.0.0", TERMINAL_PORT), TerminalHandler)
    terminals.daemon_threads = True
    threading.Thread(target=terminals.serve_forever, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
