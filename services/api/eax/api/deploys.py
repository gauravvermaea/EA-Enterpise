"""System admin > Deploy (phase 36, D555 to D557): Super Admins and IT Admins deploy EA Explorer from this installation
to another place (a server over SSH; AWS, Azure or DigitalOcean), with the eax deploy steps run by the operations
helper. Plans first; progress, Retry / Back / Quit and the log; the history of targets. Fleet management is R2."""

from __future__ import annotations

from urllib.parse import quote

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import audit
from .. import deploys as dp
from ..auth import require_auth
from ..db import get_engine
from .admin import _ops, _ops_raw
from .models import Free, FreeIn

blp = Blueprint("deploys", __name__, url_prefix="/api/v1/deploys",
                description="Deploying EA Explorer to another place (phase 36, D555)")
SECURITY = [{"bearerAuth": []}]


@blp.route("")
class Deploys(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The deployments (plans and real ones), the targets deployed to, the kept credentials (names only)"""
        try:
            ov = _ops_raw("GET", "/deploys", timeout=20)
        except Exception:  # noqa: BLE001 - the helper is down: the history from the database
            ov = {"runs": [], "kept": [], "helper_down": True}
        with get_engine().begin() as conn:
            dp.sync(conn, ov.get("runs") or [])
            hist = dp.history(conn)
        return {**ov, "history": hist, "targets": dp.targets(hist)}

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Start: a plan ({plan: true}: runs nothing) or a deployment ({confirm: true}); the SSH key and credentials go to
        the helper for this run only (kept there when keep is true), never stored or shown here"""
        body = dp.clean_body(data, g.user.username)
        if not body["plan"] and not data.get("confirm"):
            abort(400, message="Confirm the deployment (confirm: true), or ask for the plan first (plan: true).")
        out = _ops("POST", "/deploys", body, timeout=60)
        with get_engine().begin() as conn:
            dp.sync(conn, [out])
            audit.record(conn, actor=g.user.username, action="deploy.plan" if body["plan"] else "deploy.start",
                         object_type="deployment", object_id=out.get("id", ""),
                         details={"target": out.get("target"), "kind": out.get("kind"), "version": out.get("version"),
                                  "keep_credentials": body["keep"]})
        return out


@blp.route("/questions")
class Questions(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """The questions that apply to these answers (defaults filled): the same as eax deploy's, without the laptop"""
        answers = {k: v for k, v in (data.get("answers") or {}).items() if k not in dp.SECRET_FIELDS}
        return _ops("POST", "/deploys/questions", {"answers": answers}, timeout=20)


@blp.route("/<run_id>")
class Deploy(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, run_id):
        """One deployment: its steps, the failed step (waiting for Retry, Back or Quit), the result and the log"""
        out = _ops("GET", f"/deploys/{quote(run_id)}", timeout=20)
        with get_engine().begin() as conn:
            dp.sync(conn, [out])
        return out


@blp.route("/<run_id>/decide")
class Decide(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, run_id, data):
        """The answer to a failed step: retry, back (to the answers) or quit"""
        choice = str(data.get("choice") or "")
        out = _ops("POST", f"/deploys/{quote(run_id)}/decide", {"choice": choice})
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="deploy.decide", object_type="deployment", object_id=run_id,
                         details={"choice": choice})
        return out


@blp.route("/kept/<path:target>")
class Kept(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def delete(self, target):
        """Forget the credentials kept for a target"""
        out = _ops("POST", f"/deploys/kept/{quote(target, safe='')}/forget", {})
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="deploy.forget", object_type="deployment", object_id=target,
                         details={})
        return out
