"""The start-up status (D255).

GET /api/v1/startup           every signed-in person: Reports, Documents, Diagrams and the sample data, each up, starting,
                              down or off (red, amber, green, grey in the header); IT and Super Admins also get every
                              container with its tier (first or after) and its start-up state (Administration > Containers)
GET /api/startup              without signing in, the parts only (for the set-up of Reports, which waits for the
                              sample data before adding its datasets); no containers, no details
"""

from __future__ import annotations

from flask import g, request
from flask.views import MethodView
from flask_smorest import Blueprint

from .. import startup_status as ss
from ..auth import require_auth
from ..db import get_engine
from .models import Free

blp = Blueprint("startup", __name__, url_prefix="/api/v1", description="Start-up status")
SECURITY = [{"bearerAuth": []}]


@blp.route("/startup")
class Startup(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """What is up, starting or down after the start (D255); kept a few seconds; ?fresh=1 checks again"""
        with get_engine().connect() as conn:
            out = ss.status(conn, fresh=request.args.get("fresh") == "1")
        if not g.user.can("system.operate"):
            out = {k: v for k, v in out.items() if k not in ("containers", "helper")}
        out["admin"] = g.user.can("system.operate")
        return out


def public() -> dict:
    """The parts' states only, without signing in."""
    with get_engine().connect() as conn:
        out = ss.status(conn)
    return {"overall": out["overall"], "parts": [{"key": p["key"], "status": p["status"]} for p in out["all"]]}
