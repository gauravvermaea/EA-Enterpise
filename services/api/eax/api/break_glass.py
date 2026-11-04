"""The break-glass account (D80): sign in as a Super Admin when Keycloak or sign-in is down.

The password is EAX_BREAK_GLASS_PASSWORD in the config file: on a server, generate a long one, seal
it (write it down and lock it away, outside the product) and keep it only in the config file. Every
sign-in, failed attempt and call is audited. After a use the heartbeat warns until the password is
changed (EAX_BREAK_GLASS_PASSWORD and a restart): the key that signs break-glass tokens comes from
the password, so changing it also ends every break-glass session.
"""

from __future__ import annotations

import hashlib
import hmac

from flask import g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields
from sqlalchemy import text

from .. import audit
from ..auth import BREAK_GLASS_USER, make_break_glass_token
from ..config import get_settings
from ..db import get_engine

blp = Blueprint("break-glass", __name__, url_prefix="/api/v1/break-glass",
                description="Emergency sign-in when Keycloak is down (audited and alerted)")
MAX_FAILURES, WINDOW_MINUTES = 5, 15


class SignInIn(Schema):
    password = fields.String(required=True, load_only=True)


class SignInOut(Schema):
    access_token = fields.String()
    token_type = fields.String()
    expires_in = fields.Integer(allow_none=True, metadata={"description": "Always null: the session lasts until sign-out or a password change"})
    username = fields.String()


class StatusOut(Schema):
    enabled = fields.Boolean()
    last_used_at = fields.DateTime(allow_none=True)
    change_password = fields.Boolean(metadata={"description": "Used with the current password: change it"})


def fingerprint(password: str) -> str:
    """Identifies which password was used, without keeping it."""
    return hashlib.sha256(b"eax-break-glass-fingerprint:" + password.encode()).hexdigest()[:16]


def status(conn) -> dict:
    pw = get_settings().break_glass_password
    last = conn.execute(text("""SELECT at, details->>'fingerprint' AS fp FROM audit.events
                                WHERE action = 'break-glass.sign-in' ORDER BY at DESC LIMIT 1""")).mappings().first()
    return {"enabled": bool(pw), "last_used_at": last["at"] if last else None,
            "change_password": bool(pw and last and last["fp"] == fingerprint(pw))}


@blp.route("/status")
class Status(MethodView):
    @blp.response(200, StatusOut)
    def get(self):
        """Whether break-glass sign-in is set up, when it was last used, and whether its password must be
        changed (public: the sign-in page asks before Keycloak is reachable)"""
        with get_engine().connect() as conn:
            return status(conn)


@blp.route("/sign-in")
class SignIn(MethodView):
    @blp.arguments(SignInIn)
    @blp.response(200, SignInOut)
    def post(self, body):
        """Sign in with the break-glass password: a Super Admin token that does not expire. It ends when the
        person signs out or the break-glass password is changed. Five failures in 15 minutes lock it for 15
        minutes. Every attempt and every call is audited."""
        pw = get_settings().break_glass_password
        if not pw:
            abort(404, message="Break-glass sign-in is not set up (EAX_BREAK_GLASS_PASSWORD is empty).")
        where = {"ip": request.headers.get("X-Real-IP") or request.remote_addr,
                 "agent": request.headers.get("User-Agent", "")[:200]}
        with get_engine().begin() as conn:
            failures = conn.execute(text(f"""SELECT count(*) FROM audit.events WHERE action = 'break-glass.failed'
                                              AND at > now() - interval '{WINDOW_MINUTES} minutes'""")).scalar()
            if failures >= MAX_FAILURES:
                abort(429, message=f"Too many failed attempts: try again in {WINDOW_MINUTES} minutes.")
            ok = hmac.compare_digest(body["password"].encode(), pw.encode())
            audit.record(conn, actor=BREAK_GLASS_USER, action="break-glass.sign-in" if ok else "break-glass.failed",
                         object_type="account", object_id=BREAK_GLASS_USER, source="api",
                         request_id=getattr(g, "request_id", None),
                         details={**where, **({"fingerprint": fingerprint(pw)} if ok else {})})
        if not ok:
            abort(401, message="Wrong break-glass password.")
        return {"access_token": make_break_glass_token(), "token_type": "Bearer",
                "expires_in": None, "username": BREAK_GLASS_USER}
