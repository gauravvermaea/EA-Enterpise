"""The personal data service's API (R2.53, D632; owner, 13 Nov 2026: the front door sends /api/v1/me/... to it).

GET    /me/notifications ...           mine (see api/notifications.py); counts, read, dismiss, dismiss-all, resolve
GET    /me/requests ...                requests to and from me (see api/notifications.py)
GET    /me/saved-views, /me/favourites my saved views and favourites (see api/grids.py)
GET    /me/skills                      my skills (see api/projects.py)
GET    /me/settings                    my own settings {key: value}
PUT    /me/settings/<key>              {value}: one of my settings, kept
DELETE /me/settings/<key>              one of my settings, gone
GET    /me/remote-instances ...        my remote EA Explorer instances (R2.2, see api/remote_instances.py)

/api/v1/me itself (who am I, my roles) stays on the main API. The routes are defined beside the code they use and
registered on this one blueprint, which only the personal data service's container serves (eax/service_split.py).
"""

from __future__ import annotations

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import personal as P
from ..auth import require_auth
from ..db import get_engine
from .models import Free, FreeIn

blp = Blueprint("personal", __name__, url_prefix="/api/v1/me",
                description="Each person's own data: notifications, requests, favourites, saved views, skills, settings (R2.53)")
SECURITY = [{"bearerAuth": []}]


def _run(fn, write: bool = False):
    try:
        with (get_engine().begin() if write else get_engine().connect()) as conn:
            return fn(conn)
    except P.Unavailable as exc:
        abort(503, message=f"Your personal data is not available right now: {exc}")
    except ValueError as exc:
        abort(400, message=str(exc))


@blp.route("/settings")
class Settings(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """My own settings, by key"""
        return {"settings": _run(lambda c: P.get_settings(c, g.user.username))}


@blp.route("/settings/<string:key>")
class Setting(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, key):
        """{value}: one of my settings, kept (any JSON, at most 64 KB)"""
        return _run(lambda c: P.put_setting(c, g.user.username, key, (data or {}).get("value")), write=True)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, key):
        """One of my settings, gone"""
        return _run(lambda c: P.delete_setting(c, g.user.username, key), write=True)
