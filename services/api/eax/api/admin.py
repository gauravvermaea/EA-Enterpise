"""Phase 10 (D183): the administration console's API: settings, start-up settings, licences, the containers and a
restart of the whole system through the operations helper."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from flask import g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import audit
from .. import services as sv
from .. import settings as st
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError
from .models import Free, FreeIn

blp = Blueprint("admin", __name__, url_prefix="/api/v1", description="Administration console (phase 10)")
SECURITY = [{"bearerAuth": []}]


def _ops_raw(method: str, path: str, body: dict | None = None, timeout: int = 10) -> dict:
    """The operations helper's answer, raising on any failure (no HTTP error for the caller)."""
    url, token = os.environ.get("EAX_OPS_URL", "http://ops:8090"), os.environ.get("EAX_OPS_TOKEN", "")
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(f"{url}{path}", method=method, data=data,
                                 headers={"X-Ops-Token": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _ops(method: str, path: str, body: dict | None = None, timeout: int = 10) -> dict:
    url, token = os.environ.get("EAX_OPS_URL", "http://ops:8090"), os.environ.get("EAX_OPS_TOKEN", "")
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(f"{url}{path}", method=method, data=data,
                                 headers={"X-Ops-Token": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        try:
            msg = json.load(exc).get("message")
        except Exception:  # noqa: BLE001
            msg = exc.reason
        abort(exc.code, message=f"The operations helper refused: {msg}")
    except (urllib.error.URLError, TimeoutError) as exc:
        abort(503, message=f"The operations helper is not reachable ({exc.reason if hasattr(exc, 'reason') else exc}). "
                           "Check that the ops container runs.")
    return {}


@blp.route("/settings")
class PublicSettings(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The application settings every screen follows: currency, time zone, date and number formats, week, financial year"""
        v = st.values()
        out = {k: v[k] for k, spec in st.REGISTRY.items() if spec[0] == "application"}
        out["services"] = sv.switches()   # which optional services are on (D191): screens hide the others
        return out


@blp.route("/admin/first-run")
class FirstRun(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The first-run setup (UI-009): its steps, which are done, and whether to show it (a Super Admin, not finished)"""
        from .. import first_run as fr
        with get_engine().connect() as conn:
            return fr.status(conn, g.user)

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """{step, done} marks a step; {finished: true} puts the setup away, {finished: false} opens it again (Super Admins)"""
        from .. import first_run as fr
        try:
            with get_engine().connect() as conn, conn.begin():
                out = fr.mark(conn, g.user, data or {})
                audit.record(conn, actor=g.user.username, action="first-run.mark", object_type="settings", object_id="first_run",
                             details=data or {})
                return out
        except EditError as exc:
            abort(exc.status, message=str(exc))


@blp.route("/admin/settings")
class AdminSettings(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Every runtime setting with its label, type, choices and help; the start-up settings (in clear text) for IT and Super Admins"""
        with get_engine().connect() as conn:
            out = st.describe(conn)
        out["may_change"] = g.user.can("settings.manage")
        if g.user.can("system.operate"):
            out["startup"] = st.startup()
        return out

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("settings.manage")
    def put(self, data):
        """Changes settings (Super Admin) and applies them at once: {key: value, ...}"""
        try:
            with get_engine().connect() as conn, conn.begin():
                out = st.update(conn, g.user, data)
                audit.record(conn, actor=g.user.username, action="settings.change", object_type="settings", object_id="",
                             details={k: data[k] for k in out["changed"]})
                return out
        except EditError as exc:
            abort(exc.status, message=str(exc))


@blp.route("/admin/licences")
class Licences(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The products and libraries EA Explorer runs and their licences"""
        return json.loads((Path(__file__).resolve().parent.parent / "licences.json").read_text(encoding="utf-8"))


@blp.route("/admin/containers")
class Containers(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """This installation's containers, their state and health, and a running restart (from the operations helper)"""
        return _ops("GET", "/status")


@blp.route("/admin/restart")
class Restart(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth("settings.manage")
    def post(self, data):
        """Restarts the whole system, or one service ({service}), through the operations helper (Super Admin)"""
        service = (data or {}).get("service") or ""
        with get_engine().connect() as conn, conn.begin():
            audit.record(conn, actor=g.user.username, action="system.restart", object_type="system", object_id=service or "all",
                         details={"service": service or "every service"})
        return _ops("POST", f"/restart/{service}" if service else "/restart")


# ---------------------------------------------------------------- optional services and copies of the config file (D191)
@blp.route("/admin/services")
class Services(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The optional services (reports, documents, draw.io, MCP, change log, backups): on or off, what stops while off,
        and (IT and Super Admins) their containers' state"""
        out = {"services": sv.describe(), "core": sv.describe_core(), "may_change": g.user.can("settings.manage")}
        if g.user.can("system.operate"):
            try:
                st_ = _ops("GET", "/services")
                states = {c["service"]: c["state"] for c in st_.get("containers", [])}
                out["switching"] = st_.get("switching")
                for s_ in out["services"] + out["core"]:
                    s_["state"] = {c: states.get(c, "not created") for c in s_["containers"]}
            except Exception:  # noqa: BLE001 - the switches still show without the helper
                out["helper"] = "The operations helper is not reachable: the switches show, their containers do not."
        return out


@blp.route("/admin/services/health")
class ServicesHealth(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Each service's health now (IT and Super Admins): its health check with the response time, and per container
        CPU, memory, disk, Docker health, restarts and uptime from the operations helper. Checked afresh each call"""
        from ..admin_check import health_now
        return health_now()


@blp.route("/admin/sign-in-check")
class SignInCheck(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self):
        """The sign-in check (IT and Super Admins, D215): the screens call it once when an admin signs in; it runs in the
        background and, when containers, services, backups, the certificate, versions or default passwords need
        attention, makes one notification for this admin listing them (and tells the webhooks when the list changed)"""
        from ..jobs import admin_sign_in_check
        try:
            admin_sign_in_check.configure(queueing_lock=f"sign_in_check:{g.user.username.lower()}").defer(
                username=g.user.username)
        except Exception as exc:  # noqa: BLE001 - one already waiting for this admin: that one will do
            return {"queued": False, "message": f"A check is already waiting ({exc.__class__.__name__})."}
        return {"queued": True, "message": "Checking in the background: a notification follows if anything needs attention."}


# ---------------------------------------------------------------- the container console (owner, 6 Nov 2026)
@blp.route("/admin/containers/<service>")
class Container(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, service):
        """One container: state, health and its last checks, image, mounts, ports, networks, environment (clear text),
        restart policy, limits and what it uses now (IT and Super Admins)"""
        return _ops("GET", f"/containers/{service}", timeout=90)


@blp.route("/admin/containers/<service>/logs")
class ContainerLogs(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "tail", "schema": {"type": "integer"}}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, service):
        """The container's last log lines (?tail=, at most 5,000)"""
        return _ops("GET", f"/containers/{service}/logs?tail={int(request.args.get('tail', 300))}", timeout=60)


@blp.route("/admin/containers/<service>/exec")
class ContainerExec(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data, service):
        """Run a command inside a container ({command, cwd}: cwd is the folder to run it in, answered back after cd; sh -c,
        60 seconds; IT and Super Admins, D214; off when EAX_CONTAINER_CONSOLE=off). Every command is in the audit trail"""
        command = str((data or {}).get("command") or "")
        cwd = str((data or {}).get("cwd") or "")[:1000]
        out = _ops("POST", f"/containers/{service}/exec", {"command": command, "cwd": cwd}, timeout=75)
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="container.exec", object_type="container", object_id=service,
                         details={"command": command[:2000], "folder": cwd, "exit_code": out.get("exit_code")},
                         request_id=getattr(g, "request_id", None))
        return out


@blp.route("/admin/containers/<service>/terminal")
class ContainerTerminal(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data, service):
        """Open an interactive terminal in a container (IT and Super Admins, D214; off when EAX_CONTAINER_CONSOLE=off):
        answers a one-time address (good for 30 seconds) for the browser's WebSocket, {cols, rows} the screen size.
        The start is in the audit trail now, the end when the session ends"""
        out = _ops("POST", "/terminal/ticket", {"service": service, "user": g.user.username,
                                                "cols": int((data or {}).get("cols") or 120),
                                                "rows": int((data or {}).get("rows") or 32)})
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="container.terminal.open", object_type="container",
                         object_id=service, details={"session": out.get("session")},
                         request_id=getattr(g, "request_id", None))
        return {"url": f"/ops-terminal/{out['ticket']}", "session": out.get("session"),
                "idle_minutes": out.get("idle_minutes")}


def record_terminal_ends() -> int:
    """The job runner, every minute: terminal sessions that have ended go into the audit trail (who, which container,
    how long, why it ended), then the operations helper forgets them."""
    try:
        sessions = _ops_raw("GET", "/terminal/sessions").get("sessions", [])
    except Exception:  # noqa: BLE001 - the helper is down or switched off: try again next minute
        return 0
    done = [x for x in sessions if x.get("ended")]
    if not done:
        return 0
    with get_engine().begin() as conn:
        for x in done:
            audit.record(conn, actor=x.get("user") or "?", action="container.terminal.close", object_type="container",
                         object_id=x.get("service") or "", details={"session": x.get("id"), "reason": x.get("reason"),
                         "minutes": round(((x.get("ended") or 0) - (x.get("started") or 0)) / 60, 1),
                         "exit_code": x.get("exit_code")})
    _ops_raw("POST", "/terminal/sessions/ack", {"ids": [x["id"] for x in done]})
    return len(done)


@blp.route("/admin/services/<key>")
class Service(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("settings.manage")
    def put(self, data, key):
        """Switches an optional service on or off ({on: true|false}, Super Admin): a dated copy of the config file is kept,
        the switch written to it, then the service's containers started or stopped by the operations helper"""
        if key not in sv.SERVICES:
            abort(404, message=f"No optional service {key!r}.")
        on = bool((data or {}).get("on"))
        with get_engine().connect() as conn, conn.begin():
            audit.record(conn, actor=g.user.username, action="system.service", object_type="system", object_id=key,
                         details={"name": sv.SERVICES[key][1], "on": on})
        return _ops("POST", "/services", {"service": key, "on": on, "by": g.user.username}, timeout=30)


@blp.route("/admin/servers")
class Servers(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The API and job servers (copies of the api container: each answers API calls, which nginx spreads across them,
        and runs background jobs), and how many are wanted (D249; Super and IT Admins)"""
        return _ops("GET", "/servers")

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def put(self, data):
        """Run this many API and job servers {count: 1 to 16}, at once and without a restart: copies of the first are added,
        or the highest-numbered stop (the jobs they run finish first) and are removed; the number is kept in the config
        file (a dated copy first) so eax up keeps it (D249; Super and IT Admins)"""
        try:
            count = int((data or {}).get("count"))
        except (TypeError, ValueError):
            abort(400, message="count is a whole number.")
        with get_engine().connect() as conn, conn.begin():
            audit.record(conn, actor=g.user.username, action="system.servers", object_type="system", object_id="api",
                         details={"count": count})
        return _ops("POST", "/servers", {"count": count, "by": g.user.username}, timeout=30)


@blp.route("/admin/config-file")
class ConfigFile(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "name", "schema": {"type": "string"}}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The config file (work/eaexplorer.env), or one dated copy of it (?name=), as it is: in clear text, passwords and
        secrets too (owner, 5 Nov 2026). Every view is recorded in the audit trail"""
        from urllib.parse import quote
        name = request.args.get("name", "")
        out = _ops("GET", "/config-file" + (f"?name={quote(name)}" if name else ""))
        with get_engine().connect() as conn, conn.begin():
            audit.record(conn, actor=g.user.username, action="system.config_view", object_type="system",
                         object_id=name or "eaexplorer.env", details={"file": out.get("file")})
        return out


@blp.route("/admin/config-file/check")
class ConfigCheck(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Checks a config file typed on screen ({text}) and lists what it would change; nothing is saved"""
        return _ops("POST", "/config-check", {"text": (data or {}).get("text") or ""}, timeout=30)


@blp.route("/admin/config-file/save")
class ConfigSave(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Saves the config file typed on screen ({text, why}; IT and Super Admins, owner 5 Nov 2026): checked first, the
        file now kept as a dated copy, then written. Changed service switches apply at once; every other setting at the
        next eax up. Recorded in the audit trail with the names of the settings that changed (not their values)"""
        data = data or {}
        out = _ops("POST", "/config-file", {"text": data.get("text") or "", "why": data.get("why") or "edited",
                                            "by": g.user.username}, timeout=30)
        if out.get("rows"):
            with get_engine().connect() as conn, conn.begin():
                audit.record(conn, actor=g.user.username, action="system.config_edit", object_type="system", object_id="config",
                             details={"settings": [r["setting"] for r in out["rows"]], "saved_first": out.get("saved_first"),
                                      "why": data.get("why") or ""})
        return out


@blp.route("/admin/config-diff")
class ConfigDiff(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "a", "schema": {"type": "string"}},
                                            {"in": "query", "name": "b", "schema": {"type": "string"}}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The differences between two config files, in clear text: a and b are copy names, empty for the current file"""
        from urllib.parse import urlencode
        return _ops("GET", "/config-diff?" + urlencode({"a": request.args.get("a", ""), "b": request.args.get("b", "")}))


@blp.route("/admin/config-copies")
class ConfigCopies(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The dated copies of the config file (each kept before a change from the console or the eax command)"""
        return _ops("GET", "/config-copies")


@blp.route("/admin/config-copies/new")
class ConfigCopyNew(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Keeps a dated copy of the config file now ({why}: a few words, part of the copy's name)"""
        why = (data or {}).get("why") or "kept-by-hand"
        out = _ops("POST", "/config-copy", {"why": why, "by": g.user.username})
        with get_engine().connect() as conn, conn.begin():
            audit.record(conn, actor=g.user.username, action="system.config_copy", object_type="system", object_id="config",
                         details={"name": out.get("name")})
        return out


@blp.route("/admin/config-copies/restore")
class ConfigRestore(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Makes a copy the config file again ({name}, IT and Super Admins; the current one is copied first). Service switches
        apply at once; every other start-up setting at the next eax up"""
        name = (data or {}).get("name") or ""
        with get_engine().connect() as conn, conn.begin():
            audit.record(conn, actor=g.user.username, action="system.config_restore", object_type="system", object_id="config",
                         details={"name": name})
        return _ops("POST", "/config-restore", {"name": name, "by": g.user.username}, timeout=30)
