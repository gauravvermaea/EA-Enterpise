"""The banner under the top bar (owner, 10 Nov 2026, D558): one message an admin sets; nothing shows without it.

Kept by the operations helper in persist/banner.json (it survives cleanup, clean-run and clean-restart, D558).
GET /api/v1/banner answers every signed-in person with the banner they see now, or null; System admin > Banner
(IT Admins and Super Admins) sets and clears it, and the change log records who."""

from __future__ import annotations

import time

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint

from .. import audit
from .. import permissions as perms
from ..auth import require_auth
from ..db import get_engine
from .admin import _ops, _ops_raw
from .models import Free, FreeIn

blp = Blueprint("banner", __name__, url_prefix="/api/v1", description="The banner under the top bar (D558)")
SECURITY = [{"bearerAuth": []}]
_cache: dict = {}          # (admin) -> (until, answer): the banner is read at most every 15 seconds per kind of person


def _admin() -> bool:
    return bool({perms.SUPER_ADMIN, perms.IT_ADMIN} & set(g.user.roles))


def _record(action: str, details: dict) -> None:
    with get_engine().begin() as conn:
        audit.record(conn, actor=g.user.username, action=action, object_type="banner", object_id="banner",
                     details=details, request_id=getattr(g, "request_id", None))
    _cache.clear()


@blp.route("/banner")
class Banner(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The banner this person sees now ({banner: null} when none is set, it is outside its times, or it is for
        admins only): the page then shows nothing at all"""
        key = _admin()
        hit = _cache.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
        try:
            out = _ops_raw("GET", f"/banner?admin={1 if key else 0}", timeout=5)
        except Exception:  # noqa: BLE001 - no helper, no banner: nothing is shown
            out = {"banner": None}
        _cache[key] = (time.time() + 15, out)
        return out


@blp.route("/admin/banner")
class BannerAdmin(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The banner as set, what shows now, the last 20 banners set or cleared, and any warning about the file"""
        return _ops("GET", "/banner/all", timeout=10)

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def put(self, data):
        """Set the banner: {text, link, link_text, level info|notice|urgent, starts, ends, audience everyone|admins,
        dismissible}"""
        out = _ops("POST", "/banner", {"banner": data or {}, "by": g.user.username}, timeout=10)
        b = out.get("banner") or {}
        _record("banner.set", {"text": b.get("text"), "level": b.get("level"), "audience": b.get("audience"),
                               "starts": b.get("starts"), "ends": b.get("ends")})
        return out

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def delete(self):
        """Clear the banner: nothing is shown"""
        out = _ops("POST", "/banner/clear", {"by": g.user.username}, timeout=10)
        _record("banner.clear", {"cleared": out.get("cleared")})
        return out
