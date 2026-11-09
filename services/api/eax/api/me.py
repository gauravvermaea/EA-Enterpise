"""Who am I: the signed-in user as the API sees them, with their EA Explorer roles and models."""

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint

from .. import permissions
from ..auth import require_auth
from ..db import get_engine
from .schemas import Me

blp = Blueprint("me", __name__, url_prefix="/api/v1/me", description="The signed-in user")


@blp.route("")
class MeView(MethodView):
    @blp.response(200, Me)
    @blp.doc(security=[{"bearerAuth": []}])
    @require_auth()
    def get(self):
        """The signed-in user: EA Explorer roles (mapped from Keycloak's), what they allow, and the
        models assigned to them"""
        u = g.user
        with get_engine().connect() as conn:
            models = permissions.assigned_models(conn, u.username)
        return {"username": u.username, "email": u.email, "name": u.name, "roles": u.roles,
                "keycloak_roles": u.keycloak_roles, "permissions": permissions.describe(u.roles),
                "sees_every_model": permissions.sees_every_model(u.roles), "models": models,
                "break_glass": u.break_glass, "parts": _parts(), "library": _library()}


def _library() -> dict:
    from .. import settings as st
    try:
        return st.library()
    except Exception:  # noqa: BLE001
        return {"mode": "ours", "link": "", "search_link": "", "service": True}


def _parts() -> dict:
    from .. import settings as st
    try:
        return st.parts()
    except Exception:  # noqa: BLE001 - settings not readable: everything on
        return dict.fromkeys(st.PARTS, True)
