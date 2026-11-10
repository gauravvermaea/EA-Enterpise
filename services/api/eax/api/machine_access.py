"""Machine access (phase 25, D366): tokens, API keys, client certificates and service accounts.

Everyone manages their own tokens and API keys; Super Admins and IT Admins see and revoke every credential, make service
accounts and their credentials, and upload client certificates (D378). A credential cannot manage credentials: these
calls need a person signed in.
"""

from __future__ import annotations

from flask import current_app, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import machine_access as ma
from ..auth import require_auth
from ..db import get_engine
from .models import Free, FreeIn

blp = Blueprint("machine_access", __name__, url_prefix="/api/v1/machine-access",
                description="Machine access: tokens, API keys, client certificates, service accounts (phase 25)")
SECURITY = [{"bearerAuth": []}]


def _person_only():
    if getattr(g.user, "machine", None) is not None:
        abort(403, message="Credentials are managed by a person signed in, not with a credential.")


def _do(fn, write: bool = False):
    _person_only()
    try:
        with (get_engine().begin() if write else get_engine().connect()) as conn:
            return fn(conn)
    except PermissionError as exc:
        abort(403, message=str(exc))
    except LookupError as exc:
        abort(404, message=str(exc))
    except ValueError as exc:
        abort(422, message=str(exc))


def _routes():
    return [(sorted(m for m in r.methods if m not in ("HEAD", "OPTIONS")), r.rule)
            for r in current_app.url_map.iter_rules() if r.rule.startswith("/api/")] + [(["POST"], "/mcp")]


@blp.route("/areas")
class Areas(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The API areas a credential is given read or read-write on, with the addresses in each"""
        return {"areas": ma.areas(_routes()), "levels": list(ma.LEVELS), "kinds": ma.KINDS,
                "max_days": ma.MAX_DAYS, "default_days": ma.DEFAULT_DAYS, "manage_all": ma.can_manage_all(g.user.roles),
                "service_roles": ma.SERVICE_ROLES, "certificate_port_note":
                    "Client certificates are presented on the machine-access port (EAX_MTLS_PORT, 9443 unless set)."}


@blp.route("/credentials")
class Credentials(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """My credentials; with ?all=1, every credential (Super Admins and IT Admins)"""
        return _do(lambda c: ma.listing(c, g.user.username, g.user.roles, everyone=request.args.get("all") == "1"))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data):
        """A new token or API key (the secret is shown once), or an uploaded client certificate"""
        return _do(lambda c: ma.create(c, g.user.username, g.user.roles, data or {}), write=True)


@blp.route("/credentials/<ident>")
class Credential(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def patch(self, data, ident):
        """Change its areas, limits or name, or bring its expiry forward"""
        return _do(lambda c: ma.change(c, g.user.username, g.user.roles, ident, data or {}), write=True)


@blp.route("/credentials/<ident>/revoke")
class Revoke(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, ident):
        """Revoke it at once (its owner, a Super Admin or an IT Admin)"""
        return _do(lambda c: ma.revoke(c, g.user.username, g.user.roles, ident, (data or {}).get("reason", "")), write=True)


@blp.route("/service-accounts")
class ServiceAccounts(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Every service account (Super Admins and IT Admins)"""
        return _do(ma.service_accounts)

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth("system.operate")
    def post(self, data):
        """A new service account: svc-<name>, with global roles (model roles are given on each model's People tab)"""
        return _do(lambda c: ma.create_service_account(c, g.user.username, g.user.roles, data or {}), write=True)


@blp.route("/service-accounts/<username>")
class ServiceAccount(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def patch(self, data, username):
        """Change its roles or description, or disable it (its credentials stop working) or enable it again"""
        return _do(lambda c: ma.change_service_account(c, g.user.username, g.user.roles, username, data or {}), write=True)
