"""Updates (phase 36, D417, D512): System admin > Updates for Super Admins and IT Admins, and the notice everyone sees
(a banner before a scheduled update, a What's new note after one). Everything is relayed to the operations helper,
which starts the updater container (services/ops/updates.py)."""

from __future__ import annotations

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import audit
from .. import updates as up
from ..auth import require_auth
from ..db import get_engine
from .admin import _ops, _ops_raw
from .models import Free, FreeIn

blp = Blueprint("updates", __name__, url_prefix="/api/v1/operations/updates",
                description="Updating to a new release from git (phase 36, D417)")
SECURITY = [{"bearerAuth": []}]


def _status() -> dict | None:
    try:
        return _ops_raw("GET", "/updates", timeout=15)
    except Exception:  # noqa: BLE001 - the helper is down (or being rebuilt): the database's copy is shown
        return None


@blp.route("")
class Updates(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The installed version, settings and channels, the update running or waiting, the schedule and the history"""
        st = _status()
        with get_engine().begin() as conn:
            if st:
                up.sync(conn, st)
            hist = up.history(conn)
        out = dict(st or {"available": False, "helper_down": True})
        out["history"] = hist
        return out


@blp.route("/versions/<channel>")
class Versions(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, channel):
        """What a channel offers above the installed version (forward only), oldest first, with release notes"""
        return _ops("GET", f"/updates/versions?channel={channel}", timeout=200)


@blp.route("/settings")
class Settings(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def put(self, data):
        """The repository link and whether RC and Latest are offered (written to the config file, a dated copy first)"""
        out = _ops("POST", "/updates/settings", {**data, "by": g.user.username})
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="update.settings", object_type="system", object_id="updates",
                         details=out)
        return out


@blp.route("/start")
class Start(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Update now, or at a time ({channel, to, at}): a full backup first, then one release at a time"""
        if not data.get("confirm"):
            abort(422, message="Confirm the update (confirm: true): EA Explorer is unavailable while it runs.")
        out = _ops("POST", "/updates/start", {"channel": data.get("channel", "prod"), "to": data.get("to", ""),
                                              "at": data.get("at", ""), "by": g.user.username}, timeout=240)
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="update.scheduled" if out.get("scheduled") else "update.start",
                         object_type="system", object_id="updates", details=out)
        return out


def _decide(action: str):
    out = _ops("POST", f"/updates/{action}", {"by": g.user.username}, timeout=60)
    with get_engine().begin() as conn:
        audit.record(conn, actor=g.user.username, action=f"update.{action}", object_type="system", object_id="updates",
                     details=out)
    return out


@blp.route("/retry")
class Retry(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self):
        """A failed update: its failed step again, then the rest"""
        return _decide("retry")


@blp.route("/rollback")
class Rollback(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Back to the version before the update: its backup put back (work since is lost; the current state is backed
        up first)"""
        if not data.get("confirm"):
            abort(422, message="Confirm the roll back (confirm: true): work done since the update is lost.")
        return _decide("rollback")


@blp.route("/schedule/cancel")
class CancelSchedule(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self):
        """Cancel the scheduled update"""
        return _decide("schedule/cancel")


@blp.route("/notice")
class Notice(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """For everyone signed in: a scheduled update (banner) and the latest update's What's new note"""
        st = _status()
        with get_engine().begin() as conn:
            if st:
                up.sync(conn, st)
            return up.notice(conn, st)
