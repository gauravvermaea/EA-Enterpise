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
        import time
        from concurrent.futures import ThreadPoolExecutor

        from .. import health as hc
        checks = {"api": hc.check_api, "db": hc.check_database, "keycloak": hc.check_keycloak, "web": hc.check_web,
                  "proxy": hc.check_proxy, "reports": hc.check_reports, "documents": hc.check_dms,
                  "documents_broker": hc.check_dms_broker, "drawio": hc.check_drawio, "mcp": hc.check_mcp,
                  "backups": hc.check_backup, "api_jobs": hc.check_jobs}
        with ThreadPoolExecutor(max_workers=len(checks) + 1) as pool:
            futures = {k: pool.submit(f) for k, f in checks.items()}

            def ops_stats():
                started = time.perf_counter()
                try:
                    return _ops_raw("GET", "/stats?fresh=1", timeout=60), round((time.perf_counter() - started) * 1000), None
                except Exception as exc:  # noqa: BLE001
                    return None, round((time.perf_counter() - started) * 1000), str(exc)
            st = pool.submit(ops_stats)
            out = {"checks": {k: f.result() for k, f in futures.items()}}
            stats, ms, err = st.result()
        out["checks"]["ops"] = {"name": "Operations helper", "status": "down" if err else "up", "response_ms": ms,
                                "detail": err or "answering"}
        out["containers"] = (stats or {}).get("containers", [])
        out["volumes_at"] = (stats or {}).get("volumes_at")
        out["checked_at"] = time.time()
        if err:
            out["helper"] = f"The operations helper is not reachable: CPU, memory and disk cannot be shown ({err})."
        return out


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
