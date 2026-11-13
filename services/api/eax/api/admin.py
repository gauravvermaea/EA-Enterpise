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
from sqlalchemy import text

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


@blp.route("/admin/databases")
class Databases(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Every database EA Explorer uses (R2.50, D611): what it holds, its setting, where it lives (the shared server or
        its own) and, for EA Explorer's own, whether it answers. Passwords are never shown"""
        from .. import databases as dbs
        return {"databases": dbs.status(), "guide": "docs/databases.md"}


@blp.route("/admin/logs/files")
class LogFiles(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The containers' logs kept on disk, one file a day (R2.32): ?service= for one container"""
        from urllib.parse import quote
        return _ops("GET", f"/logs/files?service={quote(request.args.get('service', ''))}", timeout=30)


@blp.route("/admin/logs/read")
class LogRead(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """A day of one or several containers' logs, merged by time (R2.31): ?services=api,db&day=YYYY-MM-DD&level=
        (debug|info|warning|error: that and worse)&q=&since=HH:MM&until=HH:MM&page=N (1,000 lines a page); secrets masked"""
        from urllib.parse import urlencode
        keep = {k: request.args.get(k, "") for k in ("services", "day", "level", "q", "since", "until", "page")}
        return _ops("GET", "/logs/read?" + urlencode(keep), timeout=60)


@blp.route("/admin/logs/own")
class LogOwn(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """eax's own logs (work/logs) and the log backups (R2.31): listed; ?name= reads one of eax's logs, ?backup= lists a
        backup's files and &member= reads one; &q= words, &page=N (1,000 lines a page); secrets masked"""
        from urllib.parse import urlencode
        keep = {k: request.args.get(k, "") for k in ("name", "backup", "member", "q", "page") if request.args.get(k)}
        return _ops("GET", "/logs/own" + (f"?{urlencode(keep)}" if keep else ""), timeout=60)


@blp.route("/admin/logs/<any(backup, clean):what>")
class LogKeep(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data, what):
        """backup {tag}: the containers' logs and eax's own in one zip in work/backups/logs; clean {days}: those and the
        log backups older than `days` deleted for good (R2.30). In the audit trail"""
        data = data or {}
        if what == "clean":
            try:
                days = int(data.get("days") or 0)
            except (TypeError, ValueError):
                abort(400, message="days is a whole number of days.")
            if days < 1:
                abort(400, message="Clean the logs older than 1 day or more.")
            out = _ops("POST", "/logs/clean", {"days": days, "by": g.user.username}, timeout=120)
        else:
            out = _ops("POST", "/logs/backup", {"tag": str(data.get("tag") or "")[:40], "by": g.user.username}, timeout=300)
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action=f"logs.{what}", object_type="logs", object_id=what,
                         details={k: v for k, v in out.items() if k != "deleted"} | {"deleted": len(out.get("deleted") or [])})
        return out


@blp.route("/admin/footprint")
class Footprint(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """How much each container takes (R2.22): the newest measurement and the one before (image, own disk, volumes,
        memory, CPU, start-up seconds), as `eax footprint` keeps them in work/footprint"""
        return _ops("GET", "/footprint", timeout=30)

    @blp.doc(security=[{"bearerAuth": []}])
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Measures now {label}; kept beside the ones before"""
        return _ops("POST", "/footprint", {"label": str((data or {}).get("label") or "")[:60]}, timeout=180)


@blp.route("/admin/estate")
class Estate(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """EA Explorer's own estate (R2.33): the logical diagram (components and who calls whom) and the physical one of
        this installation as it runs (containers, images, networks, published ports, volumes and folders), as nodes and
        edges"""
        return _ops("GET", "/estate", timeout=60)


@blp.route("/admin/persist")
class Persist(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """What persist/ holds (R2.26): the settings that survive every reset (schedules, banner, Self-test settings),
        the safety backups and the reset-survival results; name, size, when changed, what each is"""
        return _ops("GET", "/persist", timeout=30)


@blp.route("/admin/persist/delete")
class PersistDelete(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Deletes an item of persist/ for good {item} or everything {all: true, confirm: "DELETE"} (R2.26); a deleted
        settings file falls back to its default. In the audit trail"""
        data = data or {}
        if data.get("confirm") != "DELETE":
            abort(400, message="Type DELETE to confirm: what is deleted from persist/ cannot be brought back.")
        body = {"all": True} if data.get("all") else {"item": str(data.get("item") or "")}
        out = _ops("POST", "/persist/delete", {**body, "by": g.user.username}, timeout=60)
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="persist.deleted", object_type="persist",
                         object_id="all" if body.get("all") else body["item"][:200], details={"deleted": out.get("deleted")})
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
        return record_command_ends()
    done = [x for x in sessions if x.get("ended")]
    if not done:
        return record_command_ends()
    with get_engine().begin() as conn:
        for x in done:
            if x.get("kind") == "ssh":         # an SSH session to a remote instance's host (R2.2): its row completed
                from .. import databases
                databases.on("operations", conn).execute(text(
                    """UPDATE operations.ssh_sessions SET ended_at = to_timestamp(:e), reason = :r, bytes = :b
                        WHERE session = :s"""), {"e": x.get("ended") or 0, "r": str(x.get("reason") or "")[:300],
                                                 "b": int(x.get("bytes") or 0), "s": x.get("id")})
                audit.record(conn, actor=x.get("user") or "?", action="remote.ssh.close", object_type="remote_instance",
                             object_id=x.get("service") or "", details={"session": x.get("id"), "reason": x.get("reason")})
                continue
            audit.record(conn, actor=x.get("user") or "?", action="container.terminal.close", object_type="container",
                         object_id=x.get("service") or "", details={"session": x.get("id"), "reason": x.get("reason"),
                         "minutes": round(((x.get("ended") or 0) - (x.get("started") or 0)) / 60, 1),
                         "exit_code": x.get("exit_code")})
    _ops_raw("POST", "/terminal/sessions/ack", {"ids": [x["id"] for x in done]})
    return len(done) + record_command_ends()


def record_command_ends() -> int:
    """With the terminal ends: Command centre runs and Console sessions that have ended go into the audit trail with
    their exit code (D554), each once."""
    try:
        runs = _ops_raw("GET", "/commands/runs").get("runs", [])
    except Exception:  # noqa: BLE001
        return 0
    done = [r for r in runs if r.get("ended") and not r.get("logged")]
    if not done:
        return 0
    with get_engine().begin() as conn:
        for r in done:
            audit.record(conn, actor=r.get("by") or "?", action="command.end", object_type="eax command",
                         object_id=r.get("id") or "", details={"command": r.get("command"), "exit_code": r.get("exit_code"),
                                                               "state": r.get("state"), "source": r.get("source")})
    _ops_raw("POST", "/commands/ack", {"ids": [r["id"] for r in done]})
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


# ---------------------------------------------------------------- the engine, the mounts, container files, alerts
# (Release 2: R2.16 to R2.19, D638 to D641) all through the operations helper; IT Admins and Super Admins
def _looked(action: str, object_id: str, details: dict | None = None) -> None:
    with get_engine().begin() as conn:
        audit.record(conn, actor=g.user.username, action=action, object_type="container", object_id=object_id[:200],
                     details=details or {}, request_id=getattr(g, "request_id", None))


@blp.route("/admin/hosts")
class Hosts(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The Docker engine EA Explorer runs on (R2.16): OS, kernel, Docker and Compose versions, CPUs and their use, load,
        memory (EA Explorer's and the rest), disks and Docker's own disk, containers, uptime, the levels (green, amber,
        red by EAX_HOST_WARN_* and EAX_HOST_ALERT_*) and the day's history, one sample a minute"""
        return _ops("GET", "/hosts", timeout=90)


@blp.route("/admin/mounts")
class Mounts(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Every volume and bind mount the containers use (R2.17): which containers use it, where, read only or not, its
        size, and warnings (read only where it must be writable, a container that could not start with it)"""
        return _ops("GET", "/mounts", timeout=90)


@blp.route("/admin/mounts/<mid>")
class MountDetail(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "path", "schema": {"type": "string"}}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, mid):
        """One mount, looked into read only: its size, free space, files, largest folders and files, newest and oldest
        (or, with ?path=, one folder in it). Every look is in the audit trail"""
        path = request.args.get("path", "")
        _looked("mount.look", mid, {"path": path or "/"})
        from urllib.parse import quote
        return _ops("GET", f"/mounts/{mid}" + (f"?path={quote(path)}" if path else ""), timeout=240)


@blp.route("/admin/mounts/<mid>/search")
class MountSearch(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, mid):
        """Files in a mount by name (?name=), size (?min_mb=) or age (?days=, changed in the last N days); up to 500"""
        from urllib.parse import urlencode
        q = {k: request.args[k] for k in ("name", "min_mb", "days") if request.args.get(k)}
        _looked("mount.search", mid, q)
        return _ops("GET", f"/mounts/{mid}/search?{urlencode(q)}", timeout=240)


@blp.route("/admin/containers/<service>/files")
class ContainerFiles(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "path", "schema": {"type": "string"}}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, service):
        """A folder in a container (R2.18): name, size, date, owner and permissions, the mounts marked; secrets and keys
        are not shown. Off with EAX_CONTAINER_CONSOLE=off"""
        from urllib.parse import quote
        return _ops("GET", f"/containers/{service}/files?path={quote(request.args.get('path', '/'))}", timeout=60)

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data, service):
        """A change in a container's files {op: write|upload|mkdir|rename|move|copy|delete, path, to, content, sha256,
        files: [{name, content (base64)}], overwrite, confirm, confirm_path}: an edit is refused when the file changed
        since it was opened (sha256); a delete needs the full path typed again; a database's data folder needs
        confirm "database"; the helper's own files, secrets and Docker's socket are never written. Every change is in
        the audit trail (an edit with its before and after)"""
        data = data or {}
        out = _ops("POST", f"/containers/{service}/files", data, timeout=300)
        _looked(f"container.files.{str(data.get('op') or '?')[:20]}", service,
                {k: out.get(k) for k in ("path", "to", "files", "bytes", "before", "after") if out.get(k) is not None})
        return {k: v for k, v in out.items() if k not in ("before", "after")}


@blp.route("/admin/containers/<service>/files/content")
class ContainerFileContent(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "path", "schema": {"type": "string"}}])
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, service):
        """A text file in a container (up to 2 MB), with its sha256 for a safe edit; a binary file: its size only"""
        from urllib.parse import quote
        path = request.args.get("path", "")
        _looked("container.files.view", service, {"path": path})
        return _ops("GET", f"/containers/{service}/files/content?path={quote(path)}", timeout=120)


@blp.route("/admin/containers/<service>/files/download")
class ContainerFileDownload(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "path", "schema": {"type": "string"}}])
    @require_auth("system.operate")
    def get(self, service):
        """A file from a container, or a folder as a zip"""
        import base64
        from urllib.parse import quote

        from flask import Response
        path = request.args.get("path", "")
        out = _ops("GET", f"/containers/{service}/files/download?path={quote(path)}", timeout=300)
        _looked("container.files.download", service, {"path": path, "name": out.get("name")})
        name = str(out.get("name") or "file").replace('"', "")
        return Response(base64.b64decode(out.get("content") or ""), mimetype="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})


@blp.route("/admin/alerts")
class Alerts(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Containers not working now and the history of alerts and recoveries (R2.19), from the operations helper's
        watcher (it looks every minute, also while the API is down)"""
        import time
        for attempt in (1, 2, 3):             # a moment while ops starts again (a restart, an update) is not an alert
            try:
                return _ops_raw("GET", "/alerts", timeout=15)
            except Exception:  # noqa: BLE001
                if attempt < 3:
                    time.sleep(2)
        return {"open": [{"service": "ops", "kind": "stopped",
                          "text": "The operations helper (the ops container) is not answering: Containers, Hosts, backups "
                                  "and the alerts wait for it",
                          "since": None}], "history": [], "helper": False}


@blp.route("/admin/alerts/test")
class AlertTest(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """A test alert {service}: the watcher tells it as if that container had stopped, then its recovery notice on
        the next look (the self-test uses it; nothing is stopped)"""
        _looked("container.alert.test", str((data or {}).get("service") or "api"))
        return _ops("POST", "/alerts/test", {"service": str((data or {}).get("service") or "api")})


@blp.route("/internal/container-alerts")
class ContainerAlertsIn(MethodView):
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    def post(self, data):
        """For the operations helper only (X-Ops-Token): alerts, reminders and recoveries from its watcher become
        notifications for the IT Admins and Super Admins (an alert needs action) and go to the webhooks (R2.19)"""
        import hmac
        token = os.environ.get("EAX_OPS_TOKEN", "")
        if not token or not hmac.compare_digest(request.headers.get("X-Ops-Token", ""), token):
            abort(403, message="Not allowed.")
        from .. import container_alerts
        with get_engine().begin() as conn:
            return {"told": container_alerts.tell(conn, (data or {}).get("events") or [])}


@blp.route("/admin/coverage")
class Coverage(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Code coverage of the API since it started (D642; EAX_COVERAGE=on): the share of EA Explorer's lines run, by
        area and by file (the least covered first). The self-test keeps it with its run"""
        from .. import coverage_probe
        return coverage_probe.report()


# ---------------------------------------------------------------- the sites (R2.1, D646)
def _sites_call(fn):
    from .. import sites
    try:
        with get_engine().begin() as conn:
            return fn(conn, sites)
    except EditError as exc:
        abort(exc.status, message=str(exc))


@blp.route("/sites")
class Sites(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Every EA Explorer site (Local first) with its health (green, amber, red) from its public heartbeat, every 5
        minutes; anyone signed in sees them and opens one to sign in there (R2.1)"""
        return _sites_call(lambda c, s: {"sites": s.listing(c), "may_change": "super-admin" in (g.user.roles or ())})

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data):
        """Add a site {name, url, note} (Super Admins)"""
        def go(c, s):
            out = s.create(c, g.user, data or {})
            audit.record(c, actor=g.user.username, action="site.add", object_type="site", object_id=str(out["id"]),
                         details={"name": out["name"], "url": out["url"]})
            return out
        return _sites_call(go)


@blp.route("/sites/<sid>")
class Site(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, sid):
        """Change a site's name, address or note (Super Admins; Local's address comes from its settings)"""
        def go(c, s):
            out = s.update(c, g.user, sid, data or {})
            audit.record(c, actor=g.user.username, action="site.change", object_type="site", object_id=sid,
                         details={k: (data or {}).get(k) for k in ("name", "url", "note") if k in (data or {})})
            return out
        return _sites_call(go)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, sid):
        """Remove a site from the list (Super Admins; nothing happens to the site itself; Local stays)"""
        def go(c, s):
            out = s.delete(c, g.user, sid)
            audit.record(c, actor=g.user.username, action="site.remove", object_type="site", object_id=sid, details={})
            return out
        return _sites_call(go)
