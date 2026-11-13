"""Remote instances (R2.2, D634): each person's list on the personal data service, the SSH session on the main API.

GET    /me/remote-instances                my instances and how SSH sign-in works here (EAX_REMOTE_SSH_AUTH)
POST   /me/remote-instances                {name, url, note, ssh_host, ssh_port, ssh_user, ssh_key (stored mode)}
PATCH  /me/remote-instances/<id>           the same fields; ssh_key '' forgets the kept key
DELETE /me/remote-instances/<id>
POST   /remote-instances/<id>/ssh          {cols, rows, ssh_key (ask mode, optional)}: a one-time terminal address for an
                                           SSH session to its host (Super Admins), recorded
GET    /admin/ssh-sessions                 the recorded sessions (Super Admins); /admin/ssh-sessions/<s> a transcript
GET    /admin/ssh-key                      this installation's own SSH key's public part (server_key mode)
"""

from __future__ import annotations

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy import text

from .. import audit, databases
from .. import remote_instances as ri
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError
from .models import Free, FreeIn
from .personal import blp as personal_blp

blp = Blueprint("remote_ssh", __name__, url_prefix="/api/v1", description="SSH to a remote instance's host (R2.2)")
SECURITY = [{"bearerAuth": []}]


def _run(fn, write: bool = False):
    try:
        with (get_engine().begin() if write else get_engine().connect()) as conn:
            return fn(conn)
    except EditError as exc:
        abort(getattr(exc, "status", 400), message=str(exc))


@personal_blp.route("/remote-instances")
class MyInstances(MethodView):
    @personal_blp.doc(security=SECURITY)
    @personal_blp.response(200, Free)
    @require_auth()
    def get(self):
        """My remote EA Explorer instances (the site picker), and how SSH sign-in works on this installation"""
        return _run(lambda c: ri.listing(c, g.user.username))

    @personal_blp.doc(security=SECURITY)
    @personal_blp.arguments(FreeIn)
    @personal_blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """Add an instance to my list {name, url, note, ssh_host, ssh_port, ssh_user, ssh_key}"""
        return _run(lambda c: ri.create(c, g.user.username, data or {}), write=True)


@personal_blp.route("/remote-instances/<uuid:ident>")
class MyInstance(MethodView):
    @personal_blp.doc(security=SECURITY)
    @personal_blp.arguments(FreeIn)
    @personal_blp.response(200, Free)
    @require_auth()
    def patch(self, data, ident):
        """Change one of my instances"""
        return _run(lambda c: ri.update(c, g.user.username, ident, data or {}), write=True)

    @personal_blp.doc(security=SECURITY)
    @personal_blp.response(200, Free)
    @require_auth()
    def delete(self, ident):
        """Take an instance off my list"""
        return _run(lambda c: ri.delete(c, g.user.username, ident), write=True)


@blp.route("/remote-instances/<uuid:ident>/ssh")
class InstanceSsh(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data, ident):
        """An SSH session to the instance's host (Super Admins; recorded): a one-time address for the browser's terminal"""
        from .admin import _ops
        req = _run(lambda c: ri.ssh_request(c, g.user, ident, data or {}))
        out = _ops("POST", "/ssh/ticket", req)
        with get_engine().begin() as conn:
            databases.on("operations", conn).execute(text("""
                INSERT INTO operations.ssh_sessions (session, username, instance, host, port, ssh_user, auth)
                VALUES (:s, :u, :i, :h, :p, :su, :a)"""),
                {"s": out["session"], "u": g.user.username, "i": req["instance"], "h": req["host"], "p": req["port"],
                 "su": req["ssh_user"], "a": req["auth"]})
            audit.record(conn, actor=g.user.username, action="remote.ssh.open", object_type="remote_instance",
                         object_id=str(ident), details={"session": out["session"], "name": req["instance"], "host": req["host"]},
                         request_id=getattr(g, "request_id", None))
        return {"url": f"/ops-terminal/{out['ticket']}", "session": out["session"], "idle_minutes": out.get("idle_minutes"),
                "auth": req["auth"]}


@blp.route("/admin/ssh-sessions")
class SshSessions(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Every recorded SSH session to a remote instance's host, newest first (Super Admins)"""
        if "super-admin" not in (g.user.roles or ()):
            abort(403, message="The SSH sessions are for Super Admins.")
        with get_engine().connect() as conn:
            rows = [dict(r) for r in databases.on("operations", conn).execute(text(
                "SELECT * FROM operations.ssh_sessions ORDER BY started_at DESC LIMIT 500")).mappings()]
        return {"items": rows}


@blp.route("/admin/ssh-sessions/<string:session>")
class SshTranscript(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, session):
        """One recorded session's transcript (what the host showed; Super Admins)"""
        if "super-admin" not in (g.user.roles or ()):
            abort(403, message="The SSH sessions are for Super Admins.")
        from .admin import _ops
        return _ops("GET", f"/ssh/sessions/{session}")


@blp.route("/admin/ssh-key")
class SshKey(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """This installation's own SSH key's public part, to put on remote hosts (EAX_REMOTE_SSH_AUTH=server_key)"""
        from .admin import _ops
        return {**_ops("GET", "/ssh/public-key"), "mode": ri.auth_mode()}
