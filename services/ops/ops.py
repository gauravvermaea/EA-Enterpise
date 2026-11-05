"""EA Explorer operations helper (phase 10, D183).

A very small web service on the internal network (port 8090, never published) that the API calls when a Super Admin
restarts the system from the administration console. It talks to the Docker engine through its socket and only ever:
  GET  /health                  is the helper up (no token)
  GET  /status                  this installation's containers, their state and health
  POST /restart                 restart every container of this installation (the database first, this helper last)
  POST /restart/<service>       restart one service (api, web, proxy, keycloak, reports, dms...)
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

import hmac
import json
import os
import re
import shutil
import socket
import subprocess
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
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
