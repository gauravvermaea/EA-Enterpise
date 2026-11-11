"""The Command centre and the Console (D554): System admin > Command centre, for IT Admins and Super Admins.

Every eax command, grouped as in eaxcli/help.txt, with a guided form; it runs through the operations helper in a
container of its own (services/ops/commandcentre.py, eaxcli/cmdrun.py), never a shell. The Console is a terminal in
the browser that takes eax commands as typed, and eax console's menu (eaxcli/webconsole.py). The commands that delete
everything need a Super Admin, the installation's name typed and "I understand", and take a backup first. Every run
and console session is the person's, in the audit trail."""

from __future__ import annotations

from flask import g, request
from flask.views import MethodView
from flask_smorest import Blueprint

from .. import audit
from .. import permissions as perms
from ..auth import require_auth
from ..db import get_engine
from .admin import _ops
from .models import Free, FreeIn

blp = Blueprint("command_centre", __name__, url_prefix="/api/v1/admin/commands",
                description="eax commands from a web page: the Command centre and the Console (D554)")
SECURITY = [{"bearerAuth": []}]


def _roles() -> list[str]:
    return [r for r in g.user.roles if r in (perms.SUPER_ADMIN, perms.IT_ADMIN)]


def _record(action: str, object_id: str, details: dict) -> None:
    with get_engine().begin() as conn:
        audit.record(conn, actor=g.user.username, action=action, object_type="eax command", object_id=object_id,
                     details=details, request_id=getattr(g, "request_id", None))


@blp.route("")
class Catalogue(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Every eax command from eaxcli/help.txt, grouped as in the help: summary, full help, examples, the form's
        fields, its kind (run, offline, wipe, host, interactive), who may run it; and the installation's name"""
        out = _ops("GET", "/commands", timeout=20)
        out["you"] = {"roles": _roles(), "super_admin": perms.SUPER_ADMIN in g.user.roles}
        return out


@blp.route("/run")
class Run(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Run one command now ({argv} or {name, values}; for the wipe commands also {confirm: {typed, understood}}).
        Checked again by the helper: only known eax commands with their own options"""
        body = {"argv": data.get("argv"), "name": data.get("name"), "values": data.get("values") or {},
                "confirm": data.get("confirm") or {}, "by": g.user.username, "roles": _roles()}
        out = _ops("POST", "/commands/run", body, timeout=60)
        _record("command.run", out.get("id", ""), {"command": out.get("command"), "kind": out.get("kind")})
        return out


@blp.route("/runs")
class Runs(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The history: every run and console session, newest first (who, when, the command, its exit code)"""
        return _ops("GET", "/commands/runs", timeout=20)


@blp.route("/runs/<run_id>")
class RunDetail(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, run_id):
        """A run's record and its output from byte ?from= (the page asks again for what is new), or a console
        session's transcript and the commands typed in it"""
        start = int(request.args.get("from", "0") or 0)
        return _ops("GET", f"/commands/runs/{run_id}?from={start}", timeout=20)


@blp.route("/runs/<run_id>/stop")
class Stop(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data, run_id):
        """Stop a run that may be stopped halfway (logs, debug, status, test...)"""
        out = _ops("POST", f"/commands/runs/{run_id}/stop", {"by": g.user.username}, timeout=30)
        _record("command.stop", run_id, {"command": out.get("command")})
        return out


@blp.route("/console")
class Console(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Open the Console: a one-time address (30 seconds) for the browser's WebSocket; {cols, rows} the screen size.
        Only eax commands are taken in it; everything typed is kept with the session"""
        out = _ops("POST", "/commands/console", {"by": g.user.username, "roles": _roles(),
                                                 "cols": int((data or {}).get("cols") or 120),
                                                 "rows": int((data or {}).get("rows") or 32)}, timeout=20)
        _record("command.console.open", out.get("session", ""), {})
        return {"url": f"/ops-terminal/{out['ticket']}", "session": out.get("session"),
                "idle_minutes": out.get("idle_minutes")}


# ---------------------------------------------------------------- scheduled commands (D559)
@blp.route("/schedules")
class Schedules(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Every scheduled eax command (persist/schedules.json): its command, when in words, on or off, the next run
        and the last run with its result; any warning about the file (a bad file falls back to its last good copy)"""
        out = _ops("GET", "/commands/schedules", timeout=20)
        out["you"] = {"roles": _roles(), "super_admin": perms.SUPER_ADMIN in g.user.roles}
        return out

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth("system.operate")
    def post(self, data):
        """A new schedule: {name, argv | command + values, cron | preset {kind nightly|weekly|hourly|once, time_, day,
        minute, at}, enabled, backup_first, keep, banner, confirm {typed, understood}}, or {demo: true, at, confirm}
        for the one-click demo reset (clean-restart laptop every night). A command that deletes everything needs a
        Super Admin and the strong confirm, given once here"""
        body = {**(data or {}), "by": g.user.username, "roles": _roles()}
        out = _ops("POST", "/commands/schedules", body, timeout=30)
        _record("schedule.add", out.get("id", ""), {"name": out.get("name"), "command": " ".join(["eax", *out.get("argv", [])]),
                                                     "when": out.get("when"), "wipe": out.get("wipe")})
        return out


@blp.route("/schedules/<sid>/<what>")
class ScheduleChange(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data, sid, what):
        """on, off, remove, or run (run it now; recorded like any run)"""
        if what not in ("on", "off", "remove", "run"):
            from flask_smorest import abort
            abort(404, message="Choose on, off, remove or run.")
        out = _ops("POST", f"/commands/schedules/{sid}/{what}", {"by": g.user.username, "roles": _roles()}, timeout=30)
        _record(f"schedule.{what}", sid, {"name": out.get("name"), "run": out.get("id") if what == "run" else None})
        return out


@blp.route("/reset-survival")
class ResetSurvival(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The reset-survival test's results (D561), from persist/test-results: started from the Self-test page or
        `eax test --reset-survival` (a real clean-restart; Super Admins only, through POST /run with the strong confirm)"""
        out = _ops("GET", "/commands/reset-survival", timeout=20)
        out["you"] = {"super_admin": perms.SUPER_ADMIN in g.user.roles}
        return out
